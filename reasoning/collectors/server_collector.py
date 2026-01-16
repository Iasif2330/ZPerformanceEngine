# reasoning/collectors/server_collector.py

import os
import requests
from typing import Dict, List


# ============================================================
# Aggregation strategy per metric
# ============================================================
# max → worst-case infra stress during test window
AGGREGATION_STRATEGY = {
    "cpu_pct": "max",
    "mem_pct": "max",
    "cpu_throttle_pct": "max",
    "mem_pressure_pct": "max",
}


class ServerCollector:
    """
    Collects INFRASTRUCTURE-LEVEL server telemetry using Grafana → Prometheus.

    IMPORTANT:
    - This collector is intentionally infra-only
    - No application latency or error metrics
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
        return [
            # --------------------------------------------------
            # CPU USAGE %
            # --------------------------------------------------
            {
                "refId": "CPU_PCT",
                "expr": (
                    'sum(rate(container_cpu_usage_seconds_total{container!="",pod!=""}[5m])) '
                    '/ sum(container_spec_cpu_quota{container!="",pod!=""} '
                    '/ container_spec_cpu_period{container!="",pod!=""}) * 100'
                ),
            },

            # --------------------------------------------------
            # MEMORY USAGE %
            # --------------------------------------------------
            {
                "refId": "MEM_PCT",
                "expr": (
                    'sum(container_memory_working_set_bytes{container!="",pod!=""}) '
                    '/ sum(container_spec_memory_limit_bytes{container!="",pod!=""}) * 100'
                ),
            },

            # --------------------------------------------------
            # CPU THROTTLING %
            # --------------------------------------------------
            {
                "refId": "CPU_THROTTLE_PCT",
                "expr": (
                    'sum(rate(container_cpu_cfs_throttled_seconds_total{container!="",pod!=""}[5m])) '
                    '/ sum(rate(container_cpu_usage_seconds_total{container!="",pod!=""}[5m])) * 100'
                ),
            },

            # --------------------------------------------------
            # MEMORY PRESSURE %
            # --------------------------------------------------
            {
                "refId": "MEM_PRESSURE_PCT",
                "expr": (
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