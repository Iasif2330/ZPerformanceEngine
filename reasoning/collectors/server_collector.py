# reasoning/collectors/server_collector.py

import os
import requests
from typing import Dict, List


# ============================================================
# Aggregation strategy per metric
# ============================================================
# max  → worst value observed during test window
# avg  → average over test window
AGGREGATION_STRATEGY = {
    "cpu": "max",
    "mem": "max",
    "threads": "max",
    "http5xx": "avg",
    "httplatp95": "max",
}


class ServerCollector:
    """
    Collects server-side telemetry using Grafana HTTP API.
    Uses READ-ONLY Grafana API token.
    """

    def __init__(self):
        # ============================================================
        # Grafana base URL (from environment)
        # ============================================================
        self.grafana_url = os.environ.get("GRAFANA_URL")
        if not self.grafana_url:
            raise ValueError("GRAFANA_URL environment variable not set")

        # ============================================================
        # Grafana API token (READ ONLY, Viewer role)
        # ============================================================
        self.api_token = os.environ.get("GRAFANA_API_TOKEN")
        if not self.api_token:
            raise ValueError("GRAFANA_API_TOKEN environment variable not set")

        # ============================================================
        # Grafana Prometheus datasource UID
        # ============================================================
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
        Collect server metrics for the anomaly time window.

        Metrics are aggregated over the full window [start_ts, end_ts]
        according to AGGREGATION_STRATEGY.
        """

        queries = self._build_queries(environment, service)

        raw_response = self._execute_queries(
            queries=queries,
            start_ts=start_ts,
            end_ts=end_ts,
        )

        normalized = self._normalize_response(raw_response)

        # ✅ Attach window metadata (purely additive)
        normalized["window"] = {
            "start_ts": start_ts,
            "end_ts": end_ts,
            "duration_sec": end_ts - start_ts,
        }

        return normalized

    # ------------------------------------------------------------
    # INTERNALS
    # ------------------------------------------------------------

    def _build_queries(self, environment: str, service: str) -> List[Dict]:
        return [
            {
                # CPU usage percentage (0–100)
                "refId": "CPU",
                "expr": (
                    'sum(rate(container_cpu_usage_seconds_total{container!="",pod!=""}[5m])) '
                    '/ sum(container_spec_cpu_quota{container!="",pod!=""} '
                    '/ container_spec_cpu_period{container!="",pod!=""}) * 100'
                ),
            },
            {
                # Memory usage percentage (0–100)
                "refId": "MEM",
                "expr": (
                    'sum(container_memory_working_set_bytes{container!="",pod!=""}) '
                    '/ sum(container_spec_memory_limit_bytes{container!="",pod!=""}) * 100'
                ),
            },
            {
                # JVM thread count
                "refId": "THREADS",
                "expr": 'avg(jvm_threads_current)',
            },
            {
                # HTTP 5xx error rate
                "refId": "HTTP_5XX",
                "expr": 'sum(rate(http_responseCodes_serverError_total[5m]))',
            },
            {
                # P95 latency in ms
                "refId": "HTTP_LAT_P95",
                "expr": (
                    'histogram_quantile(0.95, '
                    'sum(rate(service_latency_bucket[5m])) by (le))'
                ),
            },
        ]

    def _execute_queries(
        self,
        queries: List[Dict],
        start_ts: int,
        end_ts: int,
    ) -> Dict:
        """
        Execute PromQL queries via Grafana datasource proxy.
        """

        base_url = (
            f"{self.grafana_url}/api/datasources/proxy/uid/"
            f"{self.datasource_uid}/api/v1/query_range"
        )

        step = max(1, int((end_ts - start_ts) / 60))
        results = {}

        for q in queries:
            params = {
                "query": q["expr"],
                "start": start_ts,
                "end": end_ts,
                "step": step,
            }

            resp = requests.get(
                base_url,
                headers={"Authorization": f"Bearer {self.api_token}"},
                params=params,
                timeout=30,
            )
            try:
                resp.raise_for_status()
            except requests.HTTPError as e:
                status = resp.status_code
                if status >= 500:
                    return {
                        "status": "unavailable",
                        "reason": f"Grafana/Prometheus returned {status}",
                        "query": query,
                    }
                raise

            results[q["refId"]] = resp.json()

        return {"results": results}

    def _normalize_response(self, raw: Dict) -> Dict:
        """
        Normalize Prometheus responses into server signals.
        Aggregates values over the full time window.
        """

        signals = []

        for ref_id, resp in raw.get("results", {}).items():
            data = resp.get("data", {})
            series = data.get("result", [])

            if not series:
                continue

            values = series[0].get("values", [])
            if not values:
                continue

            numeric_values = []
            for _, v in values:
                try:
                    numeric_values.append(float(v))
                except (TypeError, ValueError):
                    continue

            if not numeric_values:
                continue

            metric_name = ref_id.lower().replace("_", "")
            strategy = AGGREGATION_STRATEGY.get(metric_name, "avg")

            # ✅ Apply aggregation
            if strategy == "max":
                aggregated_value = max(numeric_values)
            elif strategy == "avg":
                aggregated_value = sum(numeric_values) / len(numeric_values)
            else:
                aggregated_value = numeric_values[-1]

            signals.append(
                {
                    "metric": metric_name,
                    "current": round(aggregated_value, 2),
                    "aggregation": strategy,  # 👈 semantic meaning
                    "baseline": None,
                    "deviation_pct": None,
                    "severity": None,
                }
            )

        return {
            "status": "AVAILABLE",
            "signals": signals,
        }