# reasoning/collectors/client_collector.py

import json
import csv
from pathlib import Path
from statistics import mean
import numpy as np


class ClientMetricsCollector:
    """
    Collects raw client-side metrics from JMeter artifacts.
    This module performs NO reasoning — only data extraction.
    """

    def __init__(self, results_jtl_path: str, statistics_json_path: str):
        self.results_jtl = Path(results_jtl_path)
        self.statistics_json = Path(statistics_json_path)

        if not self.results_jtl.exists():
            raise FileNotFoundError(f"results.jtl not found: {self.results_jtl}")

        if not self.statistics_json.exists():
            raise FileNotFoundError(f"statistics.json not found: {self.statistics_json}")

    # -------------------------
    # Public API
    # -------------------------

    def collect(self) -> dict:
        """
        Main entry point.
        Returns a normalized dictionary of client-side metrics.
        """
        stats_metrics = self._read_statistics_json()
        jtl_metrics = self._read_jtl_metrics()

        return {
            "latency": {
                "avg_ms": stats_metrics["avg_latency_ms"],
                "median_ms": stats_metrics["median_latency_ms"],
                "p95_ms": stats_metrics["p95_latency_ms"],
                "p99_ms": stats_metrics["p99_latency_ms"],
            },
            "throughput": {
                "tps": stats_metrics["throughput_tps"],
            },
            "errors": {
                "error_rate_pct": stats_metrics["error_rate_pct"],
                "failed_samples": stats_metrics["failed_samples"],
                "total_samples": stats_metrics["total_samples"],
            },
            "network": {
                "connect_time_avg_ms": jtl_metrics["connect_time_avg_ms"],
                "connect_time_p95_ms": jtl_metrics["connect_time_p95_ms"],
            },
            "threads": {
                "active_threads_max": jtl_metrics["active_threads_max"],
            },
            "raw": {
                "statistics_json": stats_metrics,
                "jtl_summary": jtl_metrics,
            }
        }

    # -------------------------
    # Internal helpers
    # -------------------------

    def _read_statistics_json(self) -> dict:
        """
        Reads JMeter statistics.json (HTML report backend).

        Schema validated against JMeter 5.6+:
        Keys observed:
          - meanResTime
          - medianResTime
          - pct2ResTime (p95)
          - pct3ResTime (p99)
          - throughput
          - sampleCount
          - errorCount
          - errorPct
        """
        with self.statistics_json.open() as f:
            data = json.load(f)

        total = data.get("Total")
        if not total:
            raise ValueError("Invalid statistics.json: 'Total' section missing")

        return {
            "avg_latency_ms": float(total["meanResTime"]),
            "median_latency_ms": float(total["medianResTime"]),
            "p95_latency_ms": float(total["pct2ResTime"]),
            "p99_latency_ms": float(total["pct3ResTime"]),
            "throughput_tps": float(total["throughput"]),
            "total_samples": int(total["sampleCount"]),
            "failed_samples": int(total["errorCount"]),
            "error_rate_pct": float(total["errorPct"]),
        }

    def _read_jtl_metrics(self) -> dict:
        """
        Reads results.jtl for connect time and thread info.
        Uses CSV mode JTL.
        """
        connect_times = []
        active_threads = []

        with self.results_jtl.open(newline="") as csvfile:
            reader = csv.DictReader(csvfile)

            for row in reader:
                # Connect Time (network proxy)
                if "Connect Time" in row and row["Connect Time"]:
                    try:
                        connect_times.append(float(row["Connect Time"]))
                    except ValueError:
                        pass

                # Active threads (load generator sanity)
                if "grpThreads" in row and row["grpThreads"]:
                    try:
                        active_threads.append(int(row["grpThreads"]))
                    except ValueError:
                        pass

        if connect_times:
            connect_avg = mean(connect_times)
            connect_p95 = np.percentile(connect_times, 95)
        else:
            connect_avg = 0.0
            connect_p95 = 0.0

        return {
            "connect_time_avg_ms": round(connect_avg, 2),
            "connect_time_p95_ms": round(connect_p95, 2),
            "active_threads_max": max(active_threads) if active_threads else 0,
        }