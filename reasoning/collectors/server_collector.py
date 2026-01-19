import os
import requests
from typing import Dict, List


# ============================================================
# Aggregation strategy per metric
# ============================================================
# We intentionally take MAX values over the time window
# because we care about worst-case infra stress during the test,
# not averages that can hide short but important spikes.
AGGREGATION_STRATEGY = {
    "cpu_pct": "max",
    "mem_pct": "max",
    "cpu_throttle_pct": "max",
    "mem_pressure_pct": "max",

    # raw metrics (also aggregated, but mainly for transparency)
    "cpu_used_cores": "max",
    "cpu_limit_cores": "max",
    "mem_used_bytes": "max",
    "mem_limit_bytes": "max",
}


class ServerCollector:
    """
    Collects INFRASTRUCTURE-LEVEL server telemetry using Grafana → Prometheus.

    DESIGN INTENT:
    --------------
    - Infra-only (Kubernetes / container metrics)
    - No app latency or error metrics
    - CPU & memory limits are NOT guessed
    - Limits are fetched dynamically from Kubernetes via Prometheus
    - Percentages are calculated from raw usage + raw limits
    """

    def __init__(self):
        self.grafana_url = os.environ.get("GRAFANA_URL")
        if not self.grafana_url:
            raise ValueError("GRAFANA_URL environment variable not set")

        self.api_token = os.environ.get("GRAFANA_API_TOKEN")
        if not self.api_token:
            raise ValueError("GRAFANA_API_TOKEN environment variable not set")

        self.datasource_uid = os.environ.get("GRAFANA_DS_UID")
        if not self.datasource_uid:
            raise ValueError("GRAFANA_DS_UID environment variable not set")

    # ------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------
    def collect(
        self,
        environment: str,
        service: str,
        start_ts: int,
        end_ts: int,
    ) -> Dict:
        """
        Collect infra metrics for the anomaly time window.

        NOTE:
        - Currently cluster-scoped (no namespace/pod filter)
        - Service scoping can be added later without logic change
        """

        queries = self._build_queries()

        raw = self._execute_queries(
            queries=queries,
            start_ts=start_ts,
            end_ts=end_ts,
        )

        normalized = self._normalize_response(raw)

        normalized["window"] = {
            "start_ts": start_ts,
            "end_ts": end_ts,
            "duration_sec": end_ts - start_ts,
        }

        return normalized

    # ------------------------------------------------------------
    # QUERY DEFINITIONS
    # ------------------------------------------------------------
    def _build_queries(self) -> List[Dict]:
        """
        IMPORTANT:
        ----------
        Percentages are computed as:

            usage / limit * 100

        Raw usage and raw limits are ALSO fetched explicitly
        for transparency and Grafana comparison.
        """

        return [
            # ==================================================
            # RAW CPU USAGE (cores)
            # ==================================================
            {
                "refId": "CPU_USED_CORES",
                "expr": (
                    'sum(rate(container_cpu_usage_seconds_total{container!="",pod!=""}[5m]))'
                ),
            },

            # ==================================================
            # RAW CPU LIMIT (cores)
            # ==================================================
            {
                "refId": "CPU_LIMIT_CORES",
                "expr": (
                    'sum(container_spec_cpu_quota{container!="",pod!=""} '
                    '/ container_spec_cpu_period{container!="",pod!=""})'
                ),
            },

            # ==================================================
            # CPU USAGE % (usage / limit)
            # ==================================================
            {
                "refId": "CPU_PCT",
                "expr": (
                    'sum(rate(container_cpu_usage_seconds_total{container!="",pod!=""}[5m])) '
                    '/ sum(container_spec_cpu_quota{container!="",pod!=""} '
                    '/ container_spec_cpu_period{container!="",pod!=""}) * 100'
                ),
            },

            # ==================================================
            # RAW MEMORY USAGE (bytes)
            # ==================================================
            {
                "refId": "MEM_USED_BYTES",
                "expr": (
                    'sum(container_memory_working_set_bytes{container!="",pod!=""})'
                ),
            },

            # ==================================================
            # RAW MEMORY LIMIT (bytes)
            # ==================================================
            {
                "refId": "MEM_LIMIT_BYTES",
                "expr": (
                    'sum(container_spec_memory_limit_bytes{container!="",pod!=""})'
                ),
            },

            # ==================================================
            # MEMORY USAGE % (usage / limit)
            # ==================================================
            {
                "refId": "MEM_PCT",
                "expr": (
                    'sum(container_memory_working_set_bytes{container!="",pod!=""}) '
                    '/ sum(container_spec_memory_limit_bytes{container!="",pod!=""}) * 100'
                ),
            },

            # ==================================================
            # CPU THROTTLING % (limit enforcement)
            # ==================================================
            {
                "refId": "CPU_THROTTLE_PCT",
                "expr": (
                    'sum(rate(container_cpu_cfs_throttled_seconds_total{container!="",pod!=""}[5m])) '
                    '/ sum(rate(container_cpu_usage_seconds_total{container!="",pod!=""}[5m])) * 100'
                ),
            },

            # ==================================================
            # MEMORY PRESSURE % (PSI)
            # ==================================================
            {
                "refId": "MEM_PRESSURE_PCT",
                "expr": (
                    'sum(rate(container_pressure_memory_stalled_seconds_total{container!="",pod!=""}[5m])) * 100'
                ),
            },
        ]

    # ------------------------------------------------------------
    # EXECUTION
    # ------------------------------------------------------------
    def _execute_queries(
        self,
        queries: List[Dict],
        start_ts: int,
        end_ts: int,
    ) -> Dict:
        """
        Executes PromQL queries via Grafana's Prometheus proxy.
        """

        base_url = (
            f"{self.grafana_url}/api/datasources/proxy/uid/"
            f"{self.datasource_uid}/api/v1/query_range"
        )

        step = max(1, int((end_ts - start_ts) / 60))
        results = {}

        for q in queries:
            resp = requests.get(
                base_url,
                headers={"Authorization": f"Bearer {self.api_token}"},
                params={
                    "query": q["expr"],
                    "start": start_ts,
                    "end": end_ts,
                    "step": step,
                },
                timeout=30,
            )
            resp.raise_for_status()
            results[q["refId"]] = resp.json()

        return {"results": results}

    # ------------------------------------------------------------
    # NORMALIZATION
    # ------------------------------------------------------------
    def _normalize_response(self, raw: Dict) -> Dict:
        """
        Normalizes Prometheus responses into:
        - Percentage signals (existing behavior)
        - Raw usage & limit values (new transparency)
        """

        signals = []
        raw_lookup: Dict[str, float] = {}

        # -------------------------
        # First pass: collect all raw values
        # -------------------------
        for ref_id, resp in raw.get("results", {}).items():
            series = resp.get("data", {}).get("result", [])
            if not series:
                continue

            values = series[0].get("values", [])
            numeric = []
            for _, v in values:
                try:
                    numeric.append(float(v))
                except Exception:
                    continue

            if not numeric:
                continue

            metric = ref_id.lower()
            strategy = AGGREGATION_STRATEGY.get(metric, "max")
            value = max(numeric) if strategy == "max" else sum(numeric) / len(numeric)

            raw_lookup[metric] = value

        # -------------------------
        # Second pass: build final signals
        # -------------------------
        for metric, value in raw_lookup.items():
            if metric not in AGGREGATION_STRATEGY:
                continue

            signal = {
                "metric": metric,
                "current": round(value, 2),
                "aggregation": AGGREGATION_STRATEGY[metric],
            }

            # Attach calculation transparency for percentages
            if metric == "cpu_pct":
                signal["details"] = {
                    "used_cores": round(raw_lookup.get("cpu_used_cores", 0.0), 3),
                    "limit_cores": round(raw_lookup.get("cpu_limit_cores", 0.0), 3),
                    "formula": "used_cores / limit_cores * 100",
                }

            if metric == "mem_pct":
                signal["details"] = {
                    "used_bytes": round(raw_lookup.get("mem_used_bytes", 0.0)),
                    "limit_bytes": round(raw_lookup.get("mem_limit_bytes", 0.0)),
                    "formula": "used_bytes / limit_bytes * 100",
                }

            signals.append(signal)

        return {
            "status": "AVAILABLE" if signals else "NOT_AVAILABLE",
            "signals": signals,
        }