# reasoning/collectors/server_collector.py

import os
import requests
from typing import Dict, List
from datetime import datetime


class ServerCollector:
    """
    Collects server-side telemetry using Grafana HTTP API.
    Uses READ-ONLY Grafana API token.
    """

    def __init__(self):
        # ============================================================
        # 🔴 PLACEHOLDER 1: Grafana base URL
        # Example: https://grafana.company.com
        # ============================================================
        self.grafana_url = os.environ.get("GRAFANA_URL")
        if not self.grafana_url:
            raise ValueError("GRAFANA_URL environment variable not set")

        # ============================================================
        # 🔴 PLACEHOLDER 2: Grafana API token (READ ONLY)
        # Create this from Grafana UI → API Keys → Viewer role
        # ============================================================
        self.api_token = os.environ.get("GRAFANA_API_TOKEN")
        if not self.api_token:
            raise ValueError("GRAFANA_API_TOKEN environment variable not set")

        # ============================================================
        # 🔴 PLACEHOLDER 3: Grafana datasource UID
        # This is the Prometheus (or other) datasource UID in Grafana
        # Example: "PBFA97CFB590B2093"
        # ============================================================
        self.datasource_uid = os.environ.get("GRAFANA_DS_UID")
        if not self.datasource_uid:
            raise ValueError("GRAFANA_DS_UID environment variable not set")

        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }

    # ------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------
    def collect(
        self,
        environment: str,
        service: str,
        start_ts: int,
        end_ts: int
    ) -> Dict:
        """
        Collect server metrics for the anomaly time window.

        :param environment: qa / stage / prod
        :param service: service name / app label used in metrics
        :param start_ts: epoch seconds (start of anomaly window)
        :param end_ts: epoch seconds (end of anomaly window)
        """

        queries = self._build_queries(environment, service)

        response = self._execute_queries(
            queries=queries,
            start_ts=start_ts,
            end_ts=end_ts
        )

        return self._normalize_response(response)

    # ------------------------------------------------------------
    # INTERNALS
    # ------------------------------------------------------------

    def _build_queries(self, environment: str, service: str) -> List[Dict]:
        """
        Build Grafana datasource queries.
        🔴 Replace PromQL expressions according to your metrics.
        """

        return [
            {
                "refId": "CPU",
                "expr": f"""
                    avg(rate(container_cpu_usage_seconds_total{{app="{service}",env="{environment}"}}[5m])) * 100
                """,
            },
            {
                "refId": "MEM",
                "expr": f"""
                    avg(container_memory_working_set_bytes{{app="{service}",env="{environment}"}})
                """,
            },
            {
                "refId": "THREADS",
                "expr": f"""
                    avg(jvm_threads_live{{app="{service}",env="{environment}"}})
                """,
            },
            {
                "refId": "DB_WAIT",
                "expr": f"""
                    avg(db_connection_wait_seconds{{app="{service}",env="{environment}"}}) * 1000
                """,
            },
            {
                "refId": "LB_QUEUE",
                "expr": f"""
                    histogram_quantile(0.95, rate(lb_request_queue_time_bucket{{service="{service}",env="{environment}"}}[5m]))
                """,
            }
        ]

    def _execute_queries(
        self,
        queries: List[Dict],
        start_ts: int,
        end_ts: int
    ) -> Dict:
        """
        Execute Grafana datasource queries.
        """

        payload = {
            "queries": [
                {
                    "refId": q["refId"],
                    "datasource": {"uid": self.datasource_uid},
                    "expr": q["expr"],
                    "format": "time_series"
                }
                for q in queries
            ],
            "from": start_ts * 1000,
            "to": end_ts * 1000
        }

        url = f"{self.grafana_url}/api/ds/query"

        resp = requests.post(url, headers=self.headers, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _normalize_response(self, raw: Dict) -> Dict:
        """
        Normalize Grafana response into server signals.
        """

        signals = []

        for ref_id, data in raw.get("results", {}).items():
            frames = data.get("frames", [])
            if not frames:
                continue

            # Take last datapoint in window
            values = frames[0]["data"]["values"]
            timestamps, metrics = values[0], values[1]
            if not metrics:
                continue

            value = metrics[-1]

            signals.append({
                "metric": ref_id.lower(),
                "current": round(value, 2),
                # baseline will be filled later by correlator
                "baseline": None,
                "deviation_pct": None,
                "severity": None
            })

        return {
            "status": "AVAILABLE",
            "signals": signals
        }