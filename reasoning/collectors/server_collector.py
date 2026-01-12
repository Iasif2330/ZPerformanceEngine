# reasoning/collectors/server_collector.py

import os
import requests
from typing import Dict, List


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

        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

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

        :param environment: qa / stage / prod
        :param service: service name / app label used in metrics
        :param start_ts: epoch seconds
        :param end_ts: epoch seconds
        """

        queries = self._build_queries(environment, service)

        response = self._execute_queries(
            queries=queries,
            start_ts=start_ts,
            end_ts=end_ts,
        )

        return self._normalize_response(response)

    # ------------------------------------------------------------
    # INTERNALS
    # ------------------------------------------------------------

    def _build_queries(self, environment: str, service: str) -> List[Dict]:
        """
        Build PromQL queries using actual labels present in Prometheus.
        """

        return [
            {
                "refId": "CPU",
                "expr": (
                    f'avg(rate(container_cpu_usage_seconds_total'
                    f'{{tags_datadoghq_com_service="{service}",'
                    f'tags_datadoghq_com_env="{environment}"}}[5m])) * 100'
                ),
            },
            {
                "refId": "MEM",
                "expr": (
                    f'avg(container_memory_working_set_bytes'
                    f'{{tags_datadoghq_com_service="{service}",'
                    f'tags_datadoghq_com_env="{environment}"}})'
                ),
            },
            {
                "refId": "THREADS",
                "expr": (
                    f'avg(jvm_threads_live'
                    f'{{tags_datadoghq_com_service="{service}",'
                    f'tags_datadoghq_com_env="{environment}"}})'
                ),
            },
            {
                "refId": "DB_WAIT",
                "expr": (
                    f'avg(db_connection_wait_seconds'
                    f'{{tags_datadoghq_com_service="{service}",'
                    f'tags_datadoghq_com_env="{environment}"}}) * 1000'
                ),
            },
            {
                "refId": "LB_QUEUE",
                "expr": (
                    f'histogram_quantile(0.95, '
                    f'rate(lb_request_queue_time_bucket'
                    f'{{tags_datadoghq_com_service="{service}",'
                    f'tags_datadoghq_com_env="{environment}"}}[5m]))'
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
            resp.raise_for_status()

            results[q["refId"]] = resp.json()

        return {"results": results}


    def _normalize_response(self, raw: Dict) -> Dict:
        """
        Normalize Prometheus responses into server signals.
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

            _, value = values[-1]

            try:
                value = float(value)
            except (TypeError, ValueError):
                continue

            signals.append(
                {
                    "metric": ref_id.lower(),
                    "current": round(value, 2),
                    "baseline": None,
                    "deviation_pct": None,
                    "severity": None,
                }
            )

        return {
            "status": "AVAILABLE",
            "signals": signals,
        }