# reasoning/main.py

import os
import sys
import json
import yaml
from datetime import datetime, timezone

# ---------------- Collectors ----------------
from reasoning.collectors.client_host_collector import ClientHostCollector
from reasoning.collectors.network_collector import NetworkCollector
from reasoning.collectors.client_metrics_collector import ClientMetricsCollector

# ---------------- Validators ----------------
from reasoning.validators.client_host_validator import ClientHostValidator
from reasoning.validators.network_validator import NetworkValidator

# ---------------- Core Logic ----------------
from reasoning.baselines.baseline_store import BaselineStore
from reasoning.detectors.anomaly_detector import AnomalyDetector
from reasoning.decisions.decision_engine import DecisionEngine
from reasoning.reports.reasoning_report import ReasoningReport


# ---------------- Helpers ----------------
def fail(msg: str):
    print(f"\n❌ ERROR: {msg}\n", flush=True)
    sys.exit(1)


def load_yaml(path: str):
    if not os.path.exists(path):
        fail(f"Missing config file: {path}")
    with open(path) as f:
        return yaml.safe_load(f)


def load_json(path: str):
    if not os.path.exists(path):
        fail(f"Missing required file: {path}")
    with open(path) as f:
        return json.load(f)


def save_json(path: str, payload: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)


def section(title: str):
    print(f"\n▶ {title}", flush=True)


def kv(label: str, value):
    print(f"  - {label}: {value}", flush=True)


def evidence(label: str, value):
    if value is not None:
        print(f"     • {label}: {value}", flush=True)


def is_localhost(host: str) -> bool:
    return host in {"localhost", "127.0.0.1", "::1"}


# ---------------- Main ----------------
def main():
    print("\n==============================")
    print("PERFORMANCE REASONING ENGINE")
    print("==============================\n")

    reasoning_phase = os.environ.get("REASONING_PHASE", "postrun").lower()

    environment = os.environ.get("ENVIRONMENT")
    load_profile = os.environ.get("LOAD_PROFILE")
    build_number = os.environ.get("BUILD_NUMBER", "local")
    target_host = os.environ.get("TARGET_HOST")

    if not environment:
        fail("ENVIRONMENT is not set")
    if not load_profile:
        fail("LOAD_PROFILE is not set")
    if not target_host:
        fail("TARGET_HOST is not set")

    run_id = f"jenkins-{build_number}"

    # ============================================================
    # PREFLIGHT PHASE
    # ============================================================
    if reasoning_phase == "preflight":
        causal_chain = []

        section("Run Context")
        kv("Environment", environment)
        kv("Load Profile", load_profile)
        kv("Run ID", run_id)
        kv("Target Host", target_host)
        kv("Reasoning Phase", reasoning_phase)

        causal_chain.append({
            "step": "Run context initialized",
            "evidence": {
                "environment": environment,
                "load_profile": load_profile,
                "run_id": run_id,
                "target_host": target_host,
                "phase": reasoning_phase
            }
        })

        # ---------------- Load Rules ----------------
        client_host_rules = load_yaml("reasoning/rules/client_host_rules.yaml")
        network_rules = load_yaml("reasoning/rules/network_rules.yaml")

        # ---------------- Client Host Health ----------------
        section("Client Host Health Check")
        host_telemetry = ClientHostCollector().collect()
        host_validation = ClientHostValidator(client_host_rules).validate(host_telemetry)

        kv("Status", host_validation["status"])
        evidence("CPU avg %", host_telemetry.get("cpu", {}).get("avg_pct"))
        evidence("CPU max %", host_telemetry.get("cpu", {}).get("max_pct"))
        evidence("Memory avg %", host_telemetry.get("memory", {}).get("avg_pct"))
        evidence("Memory max %", host_telemetry.get("memory", {}).get("max_pct"))
        evidence("OS load avg (1m)", host_telemetry.get("os", {}).get("load_avg_1m"))

        if host_validation["status"] != "CLIENT_HOST_OK":
            causal_chain.append({
                "step": "Client host health validation failed",
                "evidence": host_telemetry,
                "impact": "Load generator stability not guaranteed"
            })
            _final_exit(
                causal_chain,
                environment,
                load_profile,
                run_id,
                host_validation,
                None,
                None,
                None,
                None,
                decision="REVIEW_REQUIRED",
                confidence="LOW",
                reasons=["Load generator host unstable"]
            )

        causal_chain.append({
            "step": "Client host health validated",
            "evidence": host_telemetry
        })

        # ---------------- Network Health ----------------
        section("Network Path Health Check")

        if is_localhost(target_host):
            kv("Status", "NOT_APPLICABLE")
            causal_chain.append({
                "step": "Network health check skipped",
                "evidence": "Target host is localhost"
            })
            network_validation = {"status": "NOT_APPLICABLE"}
            network_telemetry = None
        else:
            network_telemetry = NetworkCollector(target_host).collect()
            network_validation = NetworkValidator(network_rules, environment).validate(network_telemetry)

            kv("Status", network_validation["status"])
            rtt = network_telemetry.get("rtt", {}).get("avg_ms")
            pkt = network_telemetry.get("packet_loss", {}).get("pct")

            evidence("RTT avg (ms)", rtt)
            evidence("Packet loss %", pkt)

            causal_chain.append({
                "step": "Network health validated",
                "evidence": {
                    "rtt_avg_ms": rtt,
                    "packet_loss_pct": pkt
                }
            })

        # ---------------- Persist Trust Snapshot ----------------
        save_json(
            "output/preflight/trust_snapshot.json",
            {
                "metadata": {
                    "environment": environment,
                    "load_profile": load_profile,
                    "run_id": run_id,
                    "target_host": target_host
                },
                "client_host": host_telemetry,
                "network": network_telemetry,
                "causal_chain": causal_chain
            }
        )

        _final_exit(
            causal_chain,
            environment,
            load_profile,
            run_id,
            host_telemetry,
            network_telemetry,
            None,
            None,
            None,
            decision="ACCEPT",
            confidence="HIGH",
            reasons=["Preflight trust gates passed"]
        )

    # ============================================================
    # POSTRUN PHASE
    # ============================================================
    section("Loaded Preflight Trust Context")
    trust = load_json("output/preflight/trust_snapshot.json")
    causal_chain = trust["causal_chain"]

    print("     • Client host and network health validated during preflight", flush=True)

    # ---------------- Load Rules ----------------
    client_metrics_rules_yaml = load_yaml("reasoning/rules/client_metrics_rules.yaml")
    baseline_policy = load_yaml("reasoning/baselines/baseline_policy.yaml")
    auto_accept_rules = load_yaml("reasoning/decisions/auto_accept_rules.yaml")

    client_metrics_rules = {
        "p95_latency_pct_increase": client_metrics_rules_yaml["latency"]["p95"]["deviation_pct"],
        "p99_latency_pct_increase": client_metrics_rules_yaml["latency"]["p99"]["deviation_pct"],
        "throughput_pct_drop": client_metrics_rules_yaml["throughput"]["drop_pct"],
        "error_rate_pct": client_metrics_rules_yaml["errors"]["max_error_rate_pct"]
    }

    # ---------------- Client Metrics ----------------
    section("Client Performance Metrics")

    results_jtl = "output/results.jtl"
    statistics_json = "output/dashboard/statistics.json"

    if not os.path.exists(results_jtl):
        fail(f"Missing JMeter results file: {results_jtl}")
    if not os.path.exists(statistics_json):
        fail(f"Missing JMeter statistics file: {statistics_json}")

    client_metrics = ClientMetricsCollector(
        results_jtl_path=results_jtl,
        statistics_json_path=statistics_json
    ).collect()

    kv("P95 latency (ms)", client_metrics["latency"]["p95_ms"])
    kv("Error rate (%)", client_metrics["errors"]["error_rate_pct"])

    causal_chain.append({
        "step": "Client metrics collected",
        "evidence": {
            "p95_ms": client_metrics["latency"]["p95_ms"],
            "error_rate_pct": client_metrics["errors"]["error_rate_pct"]
        }
    })

    # ---------------- Baseline & Anomaly ----------------
    section("Baseline & Anomaly Detection")

    baseline_store = BaselineStore(baseline_policy, environment, load_profile)
    baseline_metrics = baseline_store.load_baseline()

    anomaly_result = AnomalyDetector(client_metrics_rules).detect(
        current=client_metrics,
        baseline=baseline_metrics
    )

    kv("Anomaly status", anomaly_result["status"])
    baseline_store.save_run(run_id, client_metrics)

    causal_chain.append({
        "step": "Client anomaly evaluation",
        "evidence": anomaly_result
    })

    # ---------------- Final Decision ----------------
    section("Final Decision")

    decision_obj = DecisionEngine(auto_accept_rules).decide(
        client_anomaly=anomaly_result,
        server_correlation=None
    )

    decision_obj["causal_chain"] = causal_chain

    kv("Decision", decision_obj["decision"])
    kv("Confidence", decision_obj["confidence"])

    # ---------------- Causal Chain ----------------
    print("\n▶ Causal Chain", flush=True)
    for i, step in enumerate(causal_chain, 1):
        print(f"\n{i}. {step['step']}", flush=True)
        for k, v in step.get("evidence", {}).items():
            print(f"   Evidence: {k} = {v}", flush=True)

    # ---------------- Report ----------------
    ReasoningReport().generate(
        output_dir="output/reasoning",
        metadata={
            "environment": environment,
            "load_profile": load_profile,
            "run_id": run_id,
        },
        client_host=trust.get("client_host"),
        network=trust.get("network"),
        client_metrics=client_metrics,
        baseline=baseline_metrics,
        anomaly=anomaly_result,
        server_correlation=None,
        decision=decision_obj
    )

    sys.exit(0)


# ---------------- Final Exit Helper ----------------
def _final_exit(
    causal_chain,
    environment,
    load_profile,
    run_id,
    client_host,
    network,
    client_metrics,
    baseline,
    anomaly,
    decision,
    confidence,
    reasons,
):
    decision_obj = {
        "decision": decision,
        "confidence": confidence,
        "reasons": reasons,
        "causal_chain": causal_chain,
    }

    ReasoningReport().generate(
        output_dir="output/reasoning",
        metadata={
            "environment": environment,
            "load_profile": load_profile,
            "run_id": run_id,
        },
        client_host=client_host,
        network=network,
        client_metrics=client_metrics,
        baseline=baseline,
        anomaly=anomaly,
        server_correlation=None,
        decision=decision_obj,
    )

    sys.exit(0)


if __name__ == "__main__":
    main()