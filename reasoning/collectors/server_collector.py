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
                "expr_candidates": [
                    # Primary: cAdvisor container usage / cAdvisor limits
                    (
                        'sum(rate(container_cpu_usage_seconds_total{container!="",pod!=""}[5m])) '
                        '/ '
                        'sum(container_spec_cpu_quota{container!="",pod!=""} '
                        '/ container_spec_cpu_period{container!="",pod!=""}) '
                        '* 100'
                    ),
                    # Fallback: cAdvisor container usage / kube-state limits
                    (
                        'sum(rate(container_cpu_usage_seconds_total{container!="",pod!=""}[5m])) '
                        '/ '
                        'sum(kube_pod_container_resource_limits{resource="cpu",unit="core"}) '
                        '* 100'
                    ),
                    # Last resort: node-level CPU busy %
                    (
                        '(1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m]))) '
                        '* 100'
                    ),
                ],
            },
            # --------------------------------------------------
            # MEMORY USAGE %
            # --------------------------------------------------
            {
                "refId": "MEM_PCT",
                "expr_candidates": [
                    # Primary: cAdvisor container memory / cAdvisor limits
                    (
                        'sum(container_memory_working_set_bytes{container!="",pod!=""}) '
                        '/ '
                        'sum(container_spec_memory_limit_bytes{container!="",pod!=""}) '
                        '* 100'
                    ),
                    # Fallback: cAdvisor container memory / kube-state limits
                    (
                        'sum(container_memory_working_set_bytes{container!="",pod!=""}) '
                        '/ '
                        'sum(kube_pod_container_resource_limits{resource="memory",unit="byte"}) '
                        '* 100'
                    ),
                    # Last resort: node-level memory used %
                    (
                        '(1 - (sum(node_memory_MemAvailable_bytes) '
                        '/ sum(node_memory_MemTotal_bytes))) * 100'
                    ),
                ],
            },
            # --------------------------------------------------
            # CPU THROTTLING %
            # --------------------------------------------------
            {
                "refId": "CPU_THROTTLE_PCT",
                "expr_candidates": [
                    # Primary: cAdvisor throttling ratio
                    (
                        'sum(rate(container_cpu_cfs_throttled_seconds_total{container!="",pod!=""}[5m])) '
                        '/ '
                        'sum(rate(container_cpu_usage_seconds_total{container!="",pod!=""}[5m])) '
                        '* 100'
                    ),
                    # Fallback: node-level scheduler pressure proxy (not true CFS throttling)
                    (
                        'sum(rate(node_pressure_cpu_waiting_seconds_total[5m])) * 100'
                    ),
                ],
            },
            # --------------------------------------------------
            # MEMORY PRESSURE %
            # --------------------------------------------------
            {
                "refId": "MEM_PRESSURE_PCT",
                "expr_candidates": [
                    # Primary: container memory PSI
                    (
                        'sum(rate(container_pressure_memory_stalled_seconds_total{container!="",pod!=""}[5m])) '
                        '* 100'
                    ),
                    # Fallback: node memory PSI
                    (
                        'sum(rate(node_pressure_memory_stalled_seconds_total[5m])) * 100'
                    ),
                ],
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
            ref_id = q["refId"]
            chosen = None
            last_json = None

            for idx, expr in enumerate(q.get("expr_candidates", []), start=1):
                try:
                    resp = requests.get(
                        base_url,
                        headers={"Authorization": f"Bearer {self.api_token}"},
                        params={
                            "query": expr,
                            "start": start_ts,
                            "end": end_ts,
                            "step": step,
                        },
                        timeout=90,
                    )
                    resp.raise_for_status()
                except requests.exceptions.HTTPError as e:
                    print(f"\n❌ Grafana Query Failed:", flush=True)
                    print(f"   Status: {resp.status_code}", flush=True)
                    print(f"   URL: {base_url}", flush=True)
                    print(f"   Query: {expr[:100]}...", flush=True)
                    print(f"   Response: {resp.text[:200]}", flush=True)
                    raise
                except requests.exceptions.ConnectionError as e:
                    print(f"\n❌ Cannot Connect to Grafana:", flush=True)
                    print(f"   URL: {base_url}", flush=True)
                    print(f"   Error: {str(e)}", flush=True)
                    raise
                
                payload = resp.json()
                last_json = payload

                series = payload.get("data", {}).get("result", [])
                if series:
                    chosen = {
                        "candidate_index": idx,
                        "expr": expr,
                        "payload": payload,
                    }
                    break

            if chosen is not None:
                results[ref_id] = {
                    **chosen["payload"],
                    "_meta": {
                        "candidate_index": chosen["candidate_index"],
                        "used_fallback": chosen["candidate_index"] > 1,
                    },
                }
            else:
                results[ref_id] = {
                    **(last_json or {"status": "success", "data": {"result": []}}),
                    "_meta": {
                        "candidate_index": None,
                        "used_fallback": False,
                    },
                }

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