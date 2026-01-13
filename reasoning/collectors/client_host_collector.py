# reasoning/collectors/client_host_collector.py

import psutil
import time
from typing import Dict


class ClientHostCollector:
    """
    Collects load-generator (client host) machine telemetry.
    This collector gathers raw facts only.
    No thresholds. No validation. No interpretation.
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
        iowait_samples = []

        net_tx_start = {}
        net_rx_start = {}

        cores = psutil.cpu_count(logical=True)

        # Capture initial network counters
        net_start = psutil.net_io_counters(pernic=True)
        for nic, stats in net_start.items():
            net_tx_start[nic] = stats.bytes_sent
            net_rx_start[nic] = stats.bytes_recv

        for _ in range(sample_window_sec):
            cpu_times = psutil.cpu_times_percent(interval=1)

            cpu_samples.append(cpu_times.user + cpu_times.system)
            iowait_samples.append(getattr(cpu_times, "iowait", 0.0))

            mem = psutil.virtual_memory()
            mem_samples.append(mem.percent)

            # Load average (Unix only, safe fallback)
            try:
                load_1m, _, _ = psutil.getloadavg()
                load_samples.append(load_1m)
            except (AttributeError, OSError):
                load_samples.append(0.0)

        # Capture final network counters
        net_end = psutil.net_io_counters(pernic=True)

        net_tx_bytes = 0
        net_rx_bytes = 0

        for nic, stats in net_end.items():
            if nic in net_tx_start:
                net_tx_bytes += max(0, stats.bytes_sent - net_tx_start[nic])
                net_rx_bytes += max(0, stats.bytes_recv - net_rx_start[nic])

        swap = psutil.swap_memory()

        return {
            "cpu": {
                "avg_pct": round(sum(cpu_samples) / len(cpu_samples), 2),
                "max_pct": round(max(cpu_samples), 2),
                "cores": cores
            },
            "memory": {
                "avg_pct": round(sum(mem_samples) / len(mem_samples), 2),
                "max_pct": round(max(mem_samples), 2),
                "swap_used_pct": round(swap.percent, 2)
            },
            "disk": {
                "iowait_avg_pct": round(sum(iowait_samples) / len(iowait_samples), 2),
                "iowait_max_pct": round(max(iowait_samples), 2)
            },
            "network": {
                "tx_bytes_per_sec": round(net_tx_bytes / sample_window_sec, 2),
                "rx_bytes_per_sec": round(net_rx_bytes / sample_window_sec, 2)
            },
            "os": {
                "load_avg_1m": round(sum(load_samples) / len(load_samples), 2)
            }
        }