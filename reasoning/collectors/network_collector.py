# reasoning/collectors/network_collector.py

import subprocess
import re
import psutil
from typing import Dict, Optional


class NetworkCollector:
    """
    Collects independent client → server network telemetry.
    Phase 1 uses OS-level signals (ping, TCP stats).
    """

    def __init__(self, target_host: str):
        self.target_host = target_host

    def collect(self, ping_count: int = 10) -> Dict:
        rtt = self._collect_rtt(ping_count)
        packet_loss = self._collect_packet_loss(ping_count)
        retrans = self._collect_retransmissions()

        return {
            "rtt": rtt,
            "packet_loss": packet_loss,
            "retransmissions": retrans,
            "load_balancer": {
                "queue_time_p95_ms": None  # Phase 2 (APM/LB APIs)
            }
        }

    # -------------------------
    # Internal collectors
    # -------------------------

    def _collect_rtt(self, count: int) -> Dict:
        """
        Collect RTT using ICMP ping.
        """
        try:
            result = subprocess.check_output(
                ["ping", "-c", str(count), self.target_host],
                stderr=subprocess.STDOUT,
                text=True
            )
        except Exception:
            return {"avg_ms": None, "p95_ms": None}

        times = [
            float(t)
            for t in re.findall(r"time=([\d.]+) ms", result)
        ]

        if not times:
            return {"avg_ms": None, "p95_ms": None}

        times.sort()
        p95_index = int(0.95 * len(times)) - 1

        return {
            "avg_ms": round(sum(times) / len(times), 2),
            "p95_ms": round(times[p95_index], 2)
        }

    def _collect_packet_loss(self, count: int) -> Dict:
        """
        Packet loss derived from ping summary.
        """
        try:
            result = subprocess.check_output(
                ["ping", "-c", str(count), self.target_host],
                stderr=subprocess.STDOUT,
                text=True
            )
        except Exception:
            return {"pct": None}

        match = re.search(r"(\d+)% packet loss", result)
        if not match:
            return {"pct": None}

        return {"pct": float(match.group(1))}

    def _collect_retransmissions(self) -> Dict:
        """
        TCP retransmissions via OS stats.
        """
        try:
            tcp = psutil.net_io_counters()
            # psutil does not expose retrans directly on all OSes
            return {"pct": None}
        except Exception:
            return {"pct": None}