from typing import Dict, List


# ============================================================
# Phase-1 Explanation Rules (Invariant-Based)
# ============================================================
EXPLANATION_RULES = [

    # --------------------------------------------------
    # ERROR-DOMINANT INVARIANTS
    # --------------------------------------------------
    {
        "when": {
            "has_errors": True,
            "server_healthy": True
        },
        "explain": [
            "Users are experiencing a high rate of request failures.",
            "Server capacity, latency, and error signals remained healthy during the same window.",
            "This issue is unlikely to be caused by infrastructure saturation.",
            "Investigate functional errors, authentication issues, test data, or upstream dependencies."
        ]
    },

    {
        "when": {
            "has_errors": True,
            "server_erroring": True
        },
        "explain": [
            "Users are experiencing request failures.",
            "Server-side error signals were observed during the test window.",
            "Client failures are corroborated by server-side errors."
        ]
    },

    # --------------------------------------------------
    # LATENCY-DOMINANT INVARIANTS
    # --------------------------------------------------
    {
        "when": {
            "has_latency": True,
            "server_saturated": True
        },
        "explain": [
            "User-facing latency increased during the test.",
            "Server resource saturation was observed during the same period.",
            "Latency regression is likely related to capacity constraints."
        ]
    },

    {
        "when": {
            "has_latency": True,
            "server_throttled": True
        },
        "explain": [
            "User-facing latency increased during the test.",
            "CPU throttling was observed on the server during the same window.",
            "Latency regression may be caused by CPU scheduling pressure or throttling."
        ]
    },

    {
        "when": {
            "has_latency": True,
            "server_mem_pressure": True
        },
        "explain": [
            "User-facing latency increased during the test.",
            "Memory pressure was observed on the server.",
            "Latency regression may be caused by memory contention or reclamation overhead."
        ]
    },

    {
        "when": {
            "has_latency": True,
            "server_healthy": True
        },
        "explain": [
            "User-facing latency increased during the test.",
            "Server capacity and health metrics remained within normal limits.",
            "Latency regression is unlikely to be caused by infrastructure constraints."
        ]
    },

    # --------------------------------------------------
    # THROUGHPUT-DOMINANT INVARIANTS
    # --------------------------------------------------
    {
        "when": {
            "has_throughput_drop": True,
            "server_saturated": True
        },
        "explain": [
            "System throughput dropped during the test.",
            "Server resource saturation was observed.",
            "Throughput reduction is likely related to capacity limits."
        ]
    },

    {
        "when": {
            "has_throughput_drop": True,
            "server_healthy": True
        },
        "explain": [
            "System throughput dropped during the test.",
            "Server capacity and latency remained healthy.",
            "Throughput reduction may be caused by application logic, rate limiting, or external dependencies."
        ]
    },
]


# ============================================================
# Explanation Engine
# ============================================================
class ExplanationEngine:
    """
    Composes human-readable explanations from
    client anomalies and server states.

    GUARANTEES:
    - Invariant-based reasoning only
    - No root-cause guessing
    - No CI impact
    - Deterministic output
    """

    def __init__(self, rules: List[Dict]):
        self.rules = rules

    def explain(
        self,
        client_anomaly: Dict,
        server_correlation: Dict
    ) -> List[str]:

        # --------------------------------------------------
        # Safe early exits
        # --------------------------------------------------
        if client_anomaly.get("status") in ("OK", "NO_BASELINE"):
            return [
                "No client-side performance anomalies were detected during this test run."
            ]

        facts = self._extract_facts(client_anomaly, server_correlation)
        explanation: List[str] = []

        # --------------------------------------------------
        # Apply invariant rules
        # --------------------------------------------------
        for rule in self.rules:
            if self._matches(rule["when"], facts):
                explanation.extend(rule["explain"])

                # Error-dominant rules short-circuit
                if facts.get("has_errors"):
                    break

        # --------------------------------------------------
        # Fallback (now truly rare)
        # --------------------------------------------------
        if not explanation:
            explanation.append(
                "Observed client behavior could not be conclusively "
                "explained using available server signals."
            )
        # --------------------------------------------------
        # Add attribution summary (human-readable)
        # --------------------------------------------------
        attribution = server_correlation.get("attribution")

        if attribution:
            dist = attribution.get("distribution", {})

            if dist:
                top = max(dist, key=dist.get)
                pct = int(dist[top] * 100)

                explanation.append(
                    f"Most likely cause category: {top.replace('_', ' ')} "
                    f"({pct}% likelihood based on infrastructure signals)."
                )
        return explanation

    # --------------------------------------------------
    # Internal helpers
    # --------------------------------------------------

    def _extract_facts(
        self,
        client_anomaly: Dict,
        server_correlation: Dict
    ) -> Dict:

        anomalies = client_anomaly.get("anomalies", {})
        states = server_correlation.get("states", {})

        return {
            # -------- Client facts --------
            "has_errors": any(
                v.get("metric") == "errors.error_rate_pct"
                for v in anomalies.values()
            ),

            "has_latency": any(
                "latency" in v.get("metric", "")
                for v in anomalies.values()
            ),

            "has_throughput_drop": any(
                "throughput" in v.get("metric", "")
                for v in anomalies.values()
            ),

            # -------- Server facts --------
            "server_healthy": states.get("server_healthy", False),
            "server_saturated": states.get("server_saturated", False),
            "server_throttled": states.get("server_throttled", False),
            "server_mem_pressure": states.get("server_mem_pressure", False),
            "server_erroring": states.get("server_erroring", False),
        }

    @staticmethod
    def _matches(conditions: Dict, facts: Dict) -> bool:
        return all(facts.get(k) == v for k, v in conditions.items())