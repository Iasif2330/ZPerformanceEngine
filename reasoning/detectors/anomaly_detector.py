# reasoning/detectors/anomaly_detector.py

from typing import Optional, Dict


class AnomalyDetector:
    """
    Detects client-side performance anomalies using baseline comparison.
    """

    def __init__(self, rules: dict):
        """
        rules example:
        {
          "p95_latency_pct_increase": 25,
          "p99_latency_pct_increase": 35,
          "throughput_pct_drop": 20,
          "error_rate_pct": 1.0
        }
        """
        self.rules = rules

    # -------------------------
    # Public API
    # -------------------------

    def detect(
        self,
        current: dict,
        baseline: Optional[dict]
    ) -> Dict:
        """
        Compare current metrics against baseline.

        Returns anomaly result dict.
        """

        # No baseline yet → learning phase
        if baseline is None:
            return {
                "status": "NO_BASELINE",
                "anomalies": {}
            }

        anomalies = {}

        # ---- Latency checks ----
        anomalies.update(
            self._check_latency(current["latency"], baseline["latency"])
        )

        # ---- Throughput checks ----
        anomalies.update(
            self._check_throughput(
                current["throughput"],
                baseline["throughput"]
            )
        )

        # ---- Error checks ----
        anomalies.update(
            self._check_errors(current["errors"])
        )

        status = "ANOMALY" if anomalies else "OK"

        return {
            "status": status,
            "anomalies": anomalies
        }

    # -------------------------
    # Metric checks
    # -------------------------

    def _check_latency(self, current: dict, baseline: dict) -> dict:
        results = {}

        # p95 latency
        p95_dev = self._pct_increase(
            current["p95_ms"],
            baseline["p95_ms"]
        )

        if p95_dev >= self.rules["p95_latency_pct_increase"]:
            results["p95_latency"] = {
                "current": current["p95_ms"],
                "baseline": baseline["p95_ms"],
                "deviation_pct": round(p95_dev, 2),
                "threshold_pct": self.rules["p95_latency_pct_increase"]
            }

        # p99 latency
        p99_dev = self._pct_increase(
            current["p99_ms"],
            baseline["p99_ms"]
        )

        if p99_dev >= self.rules["p99_latency_pct_increase"]:
            results["p99_latency"] = {
                "current": current["p99_ms"],
                "baseline": baseline["p99_ms"],
                "deviation_pct": round(p99_dev, 2),
                "threshold_pct": self.rules["p99_latency_pct_increase"]
            }

        return results

    def _check_throughput(self, current: dict, baseline: dict) -> dict:
        results = {}

        tps_drop = self._pct_drop(
            current["tps"],
            baseline["tps"]
        )

        if tps_drop >= self.rules["throughput_pct_drop"]:
            results["throughput"] = {
                "current": current["tps"],
                "baseline": baseline["tps"],
                "deviation_pct": round(tps_drop, 2),
                "threshold_pct": self.rules["throughput_pct_drop"]
            }

        return results

    def _check_errors(self, current: dict) -> dict:
        results = {}

        if current["error_rate_pct"] >= self.rules["error_rate_pct"]:
            results["error_rate"] = {
                "current": current["error_rate_pct"],
                "threshold_pct": self.rules["error_rate_pct"]
            }

        return results

    # -------------------------
    # Helpers
    # -------------------------

    @staticmethod
    def _pct_increase(current: float, baseline: float) -> float:
        if baseline <= 0:
            return 0.0
        return ((current - baseline) / baseline) * 100.0

    @staticmethod
    def _pct_drop(current: float, baseline: float) -> float:
        if baseline <= 0:
            return 0.0
        return ((baseline - current) / baseline) * 100.0