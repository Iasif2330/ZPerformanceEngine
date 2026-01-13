# reasoning/detectors/anomaly_detector.py

from typing import Optional, Dict


class AnomalyDetector:
    """
    Detects client-side performance anomalies using baseline comparison.
    """

    def __init__(self, rules: dict, min_baseline_samples: int = 3):
        self.rules = rules
        self.min_baseline_samples = min_baseline_samples

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
                "anomalies": {},
                "baseline_meta": None
            }

        baseline_metrics = baseline["metrics"]
        baseline_meta = baseline["meta"]

        anomalies = {}

        # ---- Latency checks ----
        anomalies.update(
            self._check_latency(
                current["latency"],
                baseline_metrics["latency"]
            )
        )

        # ---- Throughput checks ----
        anomalies.update(
            self._check_throughput(
                current["throughput"],
                baseline_metrics["throughput"]
            )
        )

        # ---- Error checks (absolute) ----
        anomalies.update(
            self._check_errors(current["errors"])
        )

        # ---- Status resolution ----
        if anomalies:
            status = "ANOMALY"
        elif baseline_meta.get("sample_count", 0) < self.min_baseline_samples:
            status = "WEAK_BASELINE"
        else:
            status = "OK"

        return {
            "status": status,
            "anomalies": anomalies,
            "baseline_meta": baseline_meta
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
                "type": "relative",
                "metric": "latency.p95_ms",
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
                "type": "relative",
                "metric": "latency.p99_ms",
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
                "type": "relative",
                "metric": "throughput.tps",
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
                "type": "absolute",
                "metric": "errors.error_rate_pct",
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