from datetime import datetime
from typing import Dict
import json
import os


class ReasoningReport:
    """
    Generates a human-readable reasoning report that must
    faithfully reflect collected evidence.
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

        lines = []

        # ================= Metadata =================
        lines.append("=== PERFORMANCE REASONING REPORT ===\n")
        lines.append(f"Environment      : {metadata['environment']}")
        lines.append(f"Load Profile     : {metadata['load_profile']}")
        lines.append(f"Run ID           : {metadata['run_id']}")
        lines.append(f"Generated At     : {timestamp} UTC\n")

        # ================= Client Host =================
        lines.append("== Load Generator Health ==")
        lines.append(f"Status: {client_host.get('status')}")

        cpu = client_host.get("cpu", {})
        mem = client_host.get("memory", {})
        os_metrics = client_host.get("os", {})

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
        network_status = network.get("status") if network else None
        lines.append(f"Status: {network_status}")

        if network_status == "NETWORK_OK":
            rtt = network.get("rtt", {})
            pkt = network.get("packet_loss", {})

            lines.append(f"RTT avg (ms)     : {rtt.get('avg_ms')}")
            lines.append(f"RTT p95 (ms)     : {rtt.get('p95_ms')}")
            lines.append(f"Packet loss %   : {pkt.get('pct')}")

        for issue in network.get("issues", []) if network else []:
            lines.append(f"- {issue}")
        lines.append("")

        # ================= Client Metrics =================
        lines.append("== Client-Side Metrics ==")

        if client_metrics:
            latency = client_metrics.get("latency", {})
            lines.append(f"avg_ms           : {latency.get('avg_ms')}")
            lines.append(f"median_ms        : {latency.get('median_ms')}")
            lines.append(f"p95_ms           : {latency.get('p95_ms')}")
            lines.append(f"p99_ms           : {latency.get('p99_ms')}")
            lines.append(
                f"Throughput       : {client_metrics['throughput']['tps']} TPS"
            )
            lines.append(
                f"Error Rate       : {client_metrics['errors']['error_rate_pct']}%"
            )
        else:
            lines.append("Client metrics unavailable.")
        lines.append("")

        # ================= Anomaly =================
        lines.append("== Anomaly Detection ==")
        if anomaly:
            lines.append(f"Status: {anomaly.get('status')}")
            for name, info in anomaly.get("anomalies", {}).items():
                deviation = info.get("deviation_pct")
                if deviation is not None:
                    lines.append(f"- {name}: deviation {deviation}%")
                else:
                    lines.append(f"- {name}: threshold breached")
        else:
            lines.append("Anomaly detection unavailable.")
        lines.append("")

        # ================= Server Correlation =================
        lines.append("== Server Correlation ==")

        if server_correlation:
            lines.append(f"Status: {server_correlation.get('status')}")
            for sig in server_correlation.get("signals", []):
                lines.append(
                    f"- {sig['metric']}: {sig['severity']} "
                    f"(current {sig['current']}, baseline {sig['baseline']})"
                )
        else:
            lines.append(
                "Server metrics collected. "
                "No automated server-side correlation signals identified "
                "for this phase."
            )

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

        with open(os.path.join(output_dir, "reasoning_report.json"), "w") as f:
            json.dump(
                {
                    "metadata": metadata,
                    "client_host": client_host,
                    "network": network,
                    "client_metrics": client_metrics,
                    "baseline": baseline,
                    "anomaly": anomaly,
                    "server_correlation": server_correlation,
                    "decision": decision,
                },
                f,
                indent=2,
            )