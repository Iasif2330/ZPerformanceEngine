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
}


class ServerCollector:
    """
    Collects INFRASTRUCTURE-LEVEL server telemetry using Grafana → Prometheus.

    IMPORTANT DESIGN INTENT:
    ------------------------
    - This collector is infra-only (Kubernetes / container level)
    - It does NOT look at application latency or errors
    - It does NOT guess limits
    - It reads CPU & memory limits dynamically from Kubernetes
    - It normalizes usage against limits to produce percentages
    """

    def __init__(self):
        # Base Grafana URL (used only as a proxy to Prometheus)
        self.grafana_url = os.environ.get("GRAFANA_URL")
        if not self.grafana_url:
            raise ValueError("GRAFANA_URL environment variable not set")

        # Grafana API token (read-only)
        self.api_token = os.environ.get("GRAFANA_API_TOKEN")
        if not self.api_token:
            raise ValueError("GRAFANA_API_TOKEN environment variable not set")

        # UID of the Prometheus datasource configured in Grafana
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
        -----
        - `environment` and `service` are currently NOT used
          inside PromQL filters.
        - This means metrics are cluster-scoped for now.
        - (Service scoping can be added later without changing logic.)
        """

        # Build PromQL queries (usage + limits + derived percentages)
        queries = self._build_queries()

        # Execute queries against Prometheus via Grafana proxy
        raw = self._execute_queries(
            queries=queries,
            start_ts=start_ts,
            end_ts=end_ts,
        )

        # Normalize raw Prometheus responses into simple signals
        normalized = self._normalize_response(raw)

        # Attach time window metadata (for reporting/debugging)
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
        IMPORTANT CONCEPT:
        ------------------
        Each percentage metric below is calculated as:

            usage / limit * 100

        The LIMITS come from Kubernetes pod specs
        (exposed by cAdvisor → Prometheus).

        Grafana does NOT calculate these percentages.
        YOUR PromQL does.
        """

        return [
            # --------------------------------------------------
            # CPU USAGE %
            # --------------------------------------------------
            {
                "refId": "CPU_PCT",
                "expr": (
                    # ---------------------------
                    # CPU USAGE (numerator)
                    # ---------------------------
                    # container_cpu_usage_seconds_total:
                    #   - Actual CPU time consumed by containers
                    # rate(...[5m]):
                    #   - Converts cumulative CPU time into cores used
                    'sum(rate(container_cpu_usage_seconds_total{container!="",pod!=""}[5m])) '
                    '/'
                    # ---------------------------
                    # CPU LIMIT (denominator)
                    # ---------------------------
                    # container_spec_cpu_quota / container_spec_cpu_period:
                    #   - CPU limit defined in Kubernetes pod spec
                    #   - Expressed in CPU cores
                    'sum(container_spec_cpu_quota{container!="",pod!=""} '
                    '/ container_spec_cpu_period{container!="",pod!=""}) '
                    # ---------------------------
                    # NORMALIZATION
                    # ---------------------------
                    '* 100'
                ),
            },

            # --------------------------------------------------
            # MEMORY USAGE %
            # --------------------------------------------------
            {
                "refId": "MEM_PCT",
                "expr": (
                    # ---------------------------
                    # MEMORY USAGE (numerator)
                    # ---------------------------
                    # container_memory_working_set_bytes:
                    #   - Memory actively used by containers
                    'sum(container_memory_working_set_bytes{container!="",pod!=""}) '
                    '/'
                    # ---------------------------
                    # MEMORY LIMIT (denominator)
                    # ---------------------------
                    # container_spec_memory_limit_bytes:
                    #   - Memory limit defined in Kubernetes pod spec
                    'sum(container_spec_memory_limit_bytes{container!="",pod!=""}) '
                    # ---------------------------
                    # NORMALIZATION
                    # ---------------------------
                    '* 100'
                ),
            },

            # --------------------------------------------------
            # CPU THROTTLING %
            # --------------------------------------------------
            {
                "refId": "CPU_THROTTLE_PCT",
                "expr": (
                    # ---------------------------
                    # CPU THROTTLED TIME (numerator)
                    # ---------------------------
                    # container_cpu_cfs_throttled_seconds_total:
                    #   - Time CPU was denied due to CFS quota (limits)
                    'sum(rate(container_cpu_cfs_throttled_seconds_total{container!="",pod!=""}[5m])) '
                    '/'
                    # ---------------------------
                    # CPU REQUESTED TIME (denominator)
                    # ---------------------------
                    # rate(container_cpu_usage_seconds_total):
                    #   - CPU time containers attempted to use
                    'sum(rate(container_cpu_usage_seconds_total{container!="",pod!=""}[5m])) '
                    # ---------------------------
                    # NORMALIZATION
                    # ---------------------------
                    '* 100'
                ),
            },

            # --------------------------------------------------
            # MEMORY PRESSURE %
            # --------------------------------------------------
            {
                "refId": "MEM_PRESSURE_PCT",
                "expr": (
                    # ---------------------------
                    # MEMORY PRESSURE (PSI)
                    # ---------------------------
                    # container_pressure_memory_stalled_seconds_total:
                    #   - Time containers were stalled waiting for memory
                    #   - Indicates memory contention (not heap size)
                    'sum(rate(container_pressure_memory_stalled_seconds_total{container!="",pod!=""}[5m])) '
                    '* 100'
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

        NOTE:
        -----
        - Grafana is used ONLY as a proxy
        - All computation happens in Prometheus
        """

        base_url = (
            f"{self.grafana_url}/api/datasources/proxy/uid/"
            f"{self.datasource_uid}/api/v1/query_range"
        )

        # Resolution: ~60 points over the window
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
        Converts Prometheus time-series responses into
        simple aggregated signals.

        Each signal becomes:
        - metric name
        - worst-case value (max)
        - aggregation strategy
        """

        signals = []

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

            # Worst-case behavior during the test window
            value = max(numeric) if strategy == "max" else sum(numeric) / len(numeric)

            signals.append({
                "metric": metric,
                "current": round(value, 2),
                "aggregation": strategy,
            })

        return {
            "status": "AVAILABLE" if signals else "NOT_AVAILABLE",
            "signals": signals,
        }