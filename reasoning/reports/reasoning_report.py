from datetime import datetime, timezone
from typing import Dict
import json
import os


class ReasoningReport:
    """
    Generates a human-readable reasoning report that must
    faithfully reflect collected evidence.
    """

    def build_baseline_comparison(
        client_metrics: Dict | None,
        baseline: Dict | None,
        anomaly: Dict | None,
    ) -> Dict | None:
        """
        Promote baseline + anomaly evidence into a reportable baseline comparison.
        This is conservative by design.
        """

        if not client_metrics or not baseline or not anomaly:
            return None

        # Only export when an anomaly is actually detected
        if anomaly.get("status") not in ("ANOMALY", "WEAK_BASELINE"):
            return None

        meta = baseline.get("meta", {})
        sample_count = meta.get("sample_count", 0)

        # Require minimum evidence
        if sample_count < 2:
            return None

        try:
            baseline_p95 = baseline["numeric"]["latency"]["p95_ms"]
            current_p95 = client_metrics["latency"]["p95_ms"]
            delta_pct = anomaly["anomalies"]["p95_latency"]["deviation_pct"]
        except KeyError:
            # Schema not as expected → do not export
            return None

        # Confidence heuristic (simple & honest)
        if sample_count < 3:
            confidence = "LOW"
        elif sample_count < 5:
            confidence = "MEDIUM"
        else:
            confidence = "HIGH"

        return {
            "overall_status": "DEGRADED",
            "latency": {
                "baseline_p95_ms": baseline_p95,
                "current_p95_ms": current_p95,
                "delta_pct": round(delta_pct, 2),
                "confidence": confidence,
            },
            "meta": {
                "type": meta.get("type"),
                "aggregation": meta.get("aggregation"),
                "sample_count": sample_count,
            },
        }

    def generate(
        self,
        output_dir: str,
        metadata: Dict,
        client_host: Dict | None,
        network: Dict | None,
        client_metrics: Dict | None,
        baseline: Dict | None,
        anomaly: Dict | None,
        server_correlation: Dict | None,
        decision: Dict
    ) -> None:

        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now(timezone.utc).isoformat()

        lines: list[str] = []

        # ================= Metadata =================
        lines.append("=== PERFORMANCE REASONING REPORT ===\n")
        lines.append(f"Environment      : {metadata.get('environment')}")
        lines.append(f"Load Profile     : {metadata.get('load_profile')}")
        lines.append(f"Run ID           : {metadata.get('run_id')}")
        lines.append(f"Generated At     : {timestamp} UTC\n")
        # ===== Server Metrics Time Window =====
        window = metadata.get("server_metrics_window")
        if window:
            start_ts = window.get("start_ts")
            end_ts = window.get("end_ts")

            if start_ts and end_ts:
                start_dt = datetime.fromtimestamp(start_ts, timezone.utc)
                end_dt = datetime.fromtimestamp(end_ts, timezone.utc)

                lines.append(
                    f"Server Metrics Window : "
                    f"{start_dt.isoformat()} → {end_dt.isoformat()}"
                )
                lines.append("")

        # ================= Client Host =================
        lines.append("== Load Generator Health ==")

        if not client_host:
            lines.append("Status: NOT_EVALUATED\n")
        else:
            lines.append(f"Status: {client_host.get('status')}")

            cpu = client_host.get("cpu")
            mem = client_host.get("memory")
            os_metrics = client_host.get("os")

            if cpu:
                lines.append(f"CPU avg %        : {cpu.get('avg_pct')}")
                lines.append(f"CPU max %        : {cpu.get('max_pct')}")
            if mem:
                lines.append(f"Memory avg %     : {mem.get('avg_pct')}")
                lines.append(f"Memory max %     : {mem.get('max_pct')}")
            if os_metrics:
                lines.append(f"OS load avg (1m) : {os_metrics.get('load_avg_1m')}")

            for issue in client_host.get("issues", []):
                lines.append(f"- {issue}")

            lines.append("")

        # ================= Network =================
        lines.append("== Network Path Health ==")

        if not network:
            lines.append("Status: NOT_EVALUATED\n")
        else:
            status = network.get("status")
            lines.append(f"Status: {status}")

            rtt = (
                network.get("rtt", {}).get("avg_ms")
                or network.get("rtt_avg_ms")
            )
            pkt = (
                network.get("packet_loss", {}).get("pct")
                or network.get("packet_loss_pct")
            )

            if rtt is not None:
                lines.append(f"RTT avg (ms)     : {rtt}")
            else:
                lines.append("RTT avg (ms)     : UNAVAILABLE")

            if pkt is not None:
                lines.append(f"Packet loss %   : {pkt}")
            else:
                lines.append("Packet loss %   : UNAVAILABLE")

            for issue in network.get("issues", []):
                lines.append(f"- {issue}")

            lines.append("")

        # ================= Client Metrics =================
        lines.append("== Client-Side Metrics ==")

        if not client_metrics:
            lines.append("Client metrics not collected.\n")
        else:
            latency = client_metrics.get("latency", {})
            throughput = client_metrics.get("throughput", {})
            errors = client_metrics.get("errors", {})

            lines.append(f"avg_ms           : {latency.get('avg_ms')}")
            lines.append(f"median_ms        : {latency.get('median_ms')}")
            lines.append(f"p95_ms           : {latency.get('p95_ms')}")
            lines.append(f"p99_ms           : {latency.get('p99_ms')}")
            lines.append(f"Throughput       : {throughput.get('tps')} TPS")
            lines.append(f"Error Rate       : {errors.get('error_rate_pct')}%")
            lines.append("")

        # ================= Anomaly =================
        lines.append("== Anomaly Detection ==")

        if not anomaly:
            lines.append("Anomaly detection not executed.\n")
        else:
            lines.append(f"Status: {anomaly.get('status')}")

            for name, info in anomaly.get("anomalies", {}).items():
                if "current" in info and "threshold_pct" in info:
                    lines.append(
                        f"- {name}: {info['current']} "
                        f"(threshold {info['threshold_pct']}%)"
                    )
                else:
                    lines.append(f"- {name}: threshold breached")

            lines.append("")

        # ================= Server Correlation =================
        lines.append("== Server Correlation ==")

        if server_correlation is None:
            lines.append("Server-side correlation not evaluated for this run.")
        elif not server_correlation.get("signals"):
            lines.append(
                "Server metrics collected. "
                "No automated server-side correlation signals identified."
            )
        else:
            lines.append(f"Status: {server_correlation.get('status')}")

            for sig in server_correlation.get("signals", []):
                metric = sig.get("metric")
                severity = sig.get("severity")
                current = sig.get("current")
                baseline_val = sig.get("baseline")

                # 🔒 Baseline-safe rendering
                if baseline_val is not None:
                    detail = f"(current {current}, baseline {baseline_val})"
                else:
                    detail = f"(current {current})"

                lines.append(f"- {metric}: {severity} {detail}")

        lines.append("")

        # ================= Decision =================
        lines.append("== Final Decision ==")
        lines.append(f"Decision  : {decision.get('decision')}")
        lines.append(f"Confidence: {decision.get('confidence')}")

        for r in decision.get("reasons", []):
            lines.append(f"- {r}")

        # ================= Write =================
        with open(os.path.join(output_dir, "reasoning_report.txt"), "w") as f:
            f.write("\n".join(lines))

        report_json = {
            "metadata": metadata,
            "client_host": client_host,
            "network": network,
            "client_metrics": client_metrics,
            "baseline": baseline,
            "anomaly": anomaly,
            "server_correlation": server_correlation,
            "decision": decision,
        }

        # 🔑 NEW: baseline comparison export
        baseline_comparison = self.build_baseline_comparison(
            client_metrics,
            baseline,
            anomaly,
        )

        if baseline_comparison:
            report_json["baseline_comparison"] = baseline_comparison

        with open(os.path.join(output_dir, "reasoning_report.json"), "w") as f:
            json.dump(report_json, f, indent=2)
