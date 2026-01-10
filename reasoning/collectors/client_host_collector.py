# reasoning/collectors/client_host_collector.py

import psutil
import time
from typing import Dict


class ClientHostCollector:
    """
    Collects load-generator (client host) machine telemetry.
    This collector gathers raw facts only.
    No thresholds. No validation.
    """

    def collect(self, sample_window_sec: int = 5) -> Dict:
        """
        Collect host metrics over a short sampling window.

        :param sample_window_sec: duration to sample metrics
        :return: dict of host telemetry
        """
        cpu_samples = []
        mem_samples = []
        load_samples = []

        cores = psutil.cpu_count(logical=True)

        for _ in range(sample_window_sec):
            cpu_samples.append(psutil.cpu_percent(interval=1))
            mem = psutil.virtual_memory()
            mem_samples.append(mem.percent)

            # loadavg available on Unix-like systems
            try:
                load_1m, _, _ = psutil.getloadavg()
                load_samples.append(load_1m)
            except (AttributeError, OSError):
                # Not supported (e.g., Windows)
                load_samples.append(0.0)

        return {
            "cpu": {
                "avg_pct": round(sum(cpu_samples) / len(cpu_samples), 2),
                "max_pct": round(max(cpu_samples), 2),
                "cores": cores
            },
            "memory": {
                "avg_pct": round(sum(mem_samples) / len(mem_samples), 2),
                "max_pct": round(max(mem_samples), 2)
            },
            "os": {
                "load_avg_1m": round(sum(load_samples) / len(load_samples), 2)
            }
        }