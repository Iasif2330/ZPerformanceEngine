from datetime import datetime
from typing import Dict
import json
import os


class ReasoningReport:
    """
    Generates a human-readable reasoning report.
    """

    def generate(
        self,
        output_dir: str,
        metadata: Dict,
        client_host: Dict,
        network: Dict,
        client_metrics: Dict,
        baseline: Dict,
        anomaly: Dict,
        server_correlation: Dict,
        decision: Dict
    ) -> None:

        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.utcnow().isoformat()
        report_lines = []

        # ---------------- Metadata ----------------
        report_lines.append("=== PERFORMANCE REASONING REPORT ===\n")
        report_lines.append(f"Environment      : {metadata['environment']}")
        report_lines.append(f"Load Profile     : {metadata['load_profile']}")
        report_lines.append(f"Run ID           : {metadata['run_id']}")
        report_lines.append(f"Generated At     : {timestamp} UTC\n")

        # ---------------- Client Host ----------------
        report_lines.append("== Load Generator Health ==")
        report_lines.append(f"Status: {client_host.get('status')}")
        for issue in client_host.get("issues", []):
            report_lines.append(f"- {issue}")
        report_lines.append("")

        # ---------------- Network ----------------
        report_lines.append("== Network Path Health ==")
        network_status = network.get("status") if network else None
        report_lines.append(f"Status: {network_status}")

        # Print telemetry if present
        if network and network_status == "NETWORK_OK":
            rtt = network.get("rtt", {})
            pkt = network.get("packet_loss", {})

            if rtt.get("avg_ms") is not None:
                report_lines.append(f"RTT avg: {rtt.get('avg_ms')} ms")
            if rtt.get("p95_ms") is not None:
                report_lines.append(f"RTT p95: {rtt.get('p95_ms')} ms")
            if pkt.get("pct") is not None:
                report_lines.append(f"Packet loss: {pkt.get('pct')} %")

        for issue in network.get("issues", []) if network else []:
            report_lines.append(f"- {issue}")
        report_lines.append("")

        # ---------------- Client Metrics ----------------
        report_lines.append("== Client-Side Metrics ==")

        if client_metrics is None:
            report_lines.append(
                "Client-side metrics unavailable."
            )
        else:
            latency = client_metrics.get("latency", {})
            for k in ["avg_ms", "median_ms", "p95_ms", "p99_ms"]:
                if k in latency:
                    report_lines.append(f"{k}: {latency[k]}")

            report_lines.append(
                f"Throughput: {client_metrics['throughput']['tps']} TPS"
            )
            report_lines.append(
                f"Error Rate: {client_metrics['errors']['error_rate_pct']}%"
            )

        report_lines.append("")

        # ---------------- Anomaly ----------------
        report_lines.append("== Anomaly Detection ==")
        if anomaly is None:
            report_lines.append(
                "Anomaly detection skipped due to missing client metrics."
            )
        else:
            report_lines.append(f"Status: {anomaly.get('status')}")
            for name, info in anomaly.get("anomalies", {}).items():
                report_lines.append(
                    f"- {name}: deviation {info.get('deviation_pct')}%"
                )
        report_lines.append("")

        # ---------------- Server Correlation ----------------
        report_lines.append("== Server Correlation ==")

        if server_correlation:
            report_lines.append(f"Status: {server_correlation.get('status')}")
            for sig in server_correlation.get("signals", []):
                report_lines.append(
                    f"- {sig['metric']}: {sig['severity']} "
                    f"(current {sig['current']}, baseline {sig['baseline']})"
                )
        else:
            # IMPORTANT: use network STATUS, not telemetry presence
            if network_status == "NETWORK_OK":
                report_lines.append(
                    "Server correlation skipped because server-side "
                    "correlation is not implemented in this phase."
                )
            elif network_status == "NOT_APPLICABLE":
                report_lines.append(
                    "Server correlation skipped because network attribution "
                    "is not applicable for this target."
                )
            else:
                report_lines.append(
                    "Server correlation skipped due to network validation failure."
                )

        report_lines.append("")

        # ---------------- Decision ----------------
        report_lines.append("== Final Decision ==")
        report_lines.append(f"Decision: {decision.get('decision')}")
        report_lines.append(f"Confidence: {decision.get('confidence')}")
        for r in decision.get("reasons", []):
            report_lines.append(f"- {r}")

        # ---------------- Write Reports ----------------
        with open(os.path.join(output_dir, "reasoning_report.txt"), "w") as f:
            f.write("\n".join(report_lines))

        with open(os.path.join(output_dir, "reasoning_report.json"), "w") as f:
            json.dump({
                "metadata": metadata,
                "client_host": client_host,
                "network": network,
                "client_metrics": client_metrics,
                "baseline": baseline,
                "anomaly": anomaly,
                "server_correlation": server_correlation,
                "decision": decision
            }, f, indent=2)