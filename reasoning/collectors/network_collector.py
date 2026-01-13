# reasoning/collectors/network_collector.py

import socket
import time
from typing import Dict


class NetworkCollector:
    """
    Collects client → server network telemetry using TCP probes.
    CI-safe, Docker-safe, no ICMP dependency.
    """

    def __init__(self, target_host: str, port: int = 443):
        self.target_host = target_host
        self.port = port

    def collect(self, attempts: int = 5, timeout: int = 3) -> Dict:
        rtt = self._collect_rtt(attempts, timeout)
        packet_loss = self._collect_packet_loss(attempts, timeout)

        return {
            "rtt": rtt,
            "packet_loss": packet_loss
        }

    # -------------------------------------------------
    # Internal collectors
    # -------------------------------------------------

    def _collect_rtt(self, attempts: int, timeout: int) -> Dict:
        times_ms = []

        for _ in range(attempts):
            try:
                start = time.time()
                sock = socket.create_connection(
                    (self.target_host, self.port),
                    timeout=timeout
                )
                sock.close()
                times_ms.append((time.time() - start) * 1000)
            except Exception:
                pass

        if not times_ms:
            return {"avg_ms": None, "p95_ms": None}

        times_ms.sort()
        p95_index = max(0, int(0.95 * len(times_ms)) - 1)

        return {
            "avg_ms": round(sum(times_ms) / len(times_ms), 2),
            "p95_ms": round(times_ms[p95_index], 2)
        }

    def _collect_packet_loss(self, attempts: int, timeout: int) -> Dict:
        failures = 0

        for _ in range(attempts):
            try:
                sock = socket.create_connection(
                    (self.target_host, self.port),
                    timeout=timeout
                )
                sock.close()
            except Exception:
                failures += 1

        return {
            "pct": round((failures / attempts) * 100, 2)
        }