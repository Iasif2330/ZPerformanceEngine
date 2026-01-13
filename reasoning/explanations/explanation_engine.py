# reasoning/explanations/explanation_engine.py

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
            "server_slow": True
        },
        "explain": [
            "User-facing latency increased during the test.",
            "Server-side latency was elevated.",
            "The regression may be caused by slow execution paths or downstream dependencies."
        ]
    },

    {
        "when": {
            "has_latency": True,
            "server_healthy": True
        },
        "explain": [
            "User-facing latency increased during the test.",
            "Server capacity and latency metrics remained healthy.",
            "Latency regression is unlikely to be caused by server resource constraints."
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

    This engine:
    - Uses invariant-based reasoning
    - Does NOT guess root cause
    - Does NOT affect CI decisions
    """

    def __init__(self, rules: List[Dict]):
        self.rules = rules

    def explain(
        self,
        client_anomaly: Dict,
        server_correlation: Dict
    ) -> List[str]:

        facts = self._extract_facts(client_anomaly, server_correlation)
        explanation: List[str] = []

        for rule in self.rules:
            if self._matches(rule["when"], facts):
                explanation.extend(rule["explain"])

        # Fallback (should rarely happen)
        if not explanation:
            explanation.append(
                "Observed client behavior could not be conclusively "
                "explained using available server signals."
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
            # ---- Client facts ----
            "has_errors": any(
                k.endswith("error_rate_pct") for k in anomalies
            ),
            "has_latency": any(
                "latency" in k for k in anomalies
            ),
            "has_throughput_drop": any(
                "throughput" in k for k in anomalies
            ),

            # ---- Server facts ----
            "server_healthy": states.get("server_healthy", False),
            "server_saturated": states.get("server_saturated", False),
            "server_slow": states.get("server_slow", False),
            "server_erroring": states.get("server_erroring", False),
        }

    @staticmethod
    def _matches(conditions: Dict, facts: Dict) -> bool:
        return all(facts.get(k) == v for k, v in conditions.items())