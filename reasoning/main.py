# reasoning/main.py

import os
import sys
import yaml
from time import time
from datetime import datetime, timezone

# ---------------- Collectors ----------------
from reasoning.collectors.client_host_collector import ClientHostCollector
from reasoning.collectors.network_collector import NetworkCollector
from reasoning.collectors.client_metrics_collector import ClientMetricsCollector
from reasoning.collectors.server_collector import ServerCollector

# ---------------- Validators ----------------
from reasoning.validators.client_host_validator import ClientHostValidator
from reasoning.validators.network_validator import NetworkValidator

# ---------------- Core Logic ----------------
from reasoning.baselines.baseline_store import BaselineStore
from reasoning.detectors.anomaly_detector import AnomalyDetector
from reasoning.correlators.correlator import Correlator
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

def load_ts(path: str) -> int:
    """
    Load a unix timestamp (seconds) from a file.
    """
    if not os.path.exists(path):
        fail(f"Missing timestamp file: {path}")

    with open(path) as f:
        return int(f.read().strip())

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

    causal_chain = []

    reasoning_phase = os.environ.get("REASONING_PHASE", "postrun").lower()

    # ============================================================
    # 1. RUN CONTEXT
    # ============================================================
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

    # ============================================================
    # 2. LOAD RULES
    # ============================================================
    client_host_rules = load_yaml("reasoning/rules/client_host_rules.yaml")
    network_rules = load_yaml("reasoning/rules/network_rules.yaml")
    client_metrics_rules_yaml = load_yaml("reasoning/rules/client_metrics_rules.yaml")
    server_rules = load_yaml("reasoning/rules/server_rules.yaml")
    baseline_policy = load_yaml("reasoning/baselines/baseline_policy.yaml")
    auto_accept_rules = load_yaml("reasoning/decisions/auto_accept_rules.yaml")

    client_metrics_rules = {
        "p95_latency_pct_increase": client_metrics_rules_yaml["latency"]["p95"]["deviation_pct"],
        "p99_latency_pct_increase": client_metrics_rules_yaml["latency"]["p99"]["deviation_pct"],
        "throughput_pct_drop": client_metrics_rules_yaml["throughput"]["drop_pct"],
        "error_rate_pct": client_metrics_rules_yaml["errors"]["max_error_rate_pct"]
    }

    # ============================================================
    # 3. CLIENT HOST HEALTH (TRUST GATE #1)
    # ============================================================
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
            decision="REVIEW_REQUIRED",
            confidence="LOW",
            reasons=["Load generator host unstable"],
            causal_chain=causal_chain,
            environment=environment,
            load_profile=load_profile,
            run_id=run_id,
            client_host=host_validation,
            network=None,
            client_metrics=None,
            baseline=None,
            anomaly=None,
            server_correlation=None
        )

    causal_chain.append({
        "step": "Client host health validated",
        "evidence": host_telemetry
    })

    # ============================================================
    # 4. NETWORK HEALTH (TRUST GATE #2)
    # ============================================================
    section("Network Path Health Check")

    if is_localhost(target_host):
        kv("Status", "NOT_APPLICABLE")
        print("     • Target host is localhost; no network boundary exists", flush=True)

        causal_chain.append({
            "step": "Network health check skipped",
            "evidence": "Target host is localhost; no network path to validate"
        })

        network_validation = {"status": "NOT_APPLICABLE"}
        network_telemetry = None

    else:
        network_telemetry = NetworkCollector(target_host).collect()
        network_validation = NetworkValidator(network_rules, environment).validate(network_telemetry)

        kv("Status", network_validation["status"])

        rtt = network_telemetry.get("rtt", {}).get("avg_ms")
        pkt_loss = network_telemetry.get("packet_loss", {}).get("pct")

        if rtt is None or pkt_loss is None:
            causal_chain.append({
                "step": "Network health verification failed",
                "evidence": network_telemetry,
                "impact": "Required network metrics unavailable"
            })
            _final_exit(
                decision="REVIEW_REQUIRED",
                confidence="LOW",
                reasons=["Network metrics unavailable"],
                causal_chain=causal_chain,
                environment=environment,
                load_profile=load_profile,
                run_id=run_id,
                client_host=host_validation,
                network=network_validation,
                client_metrics=None,
                baseline=None,
                anomaly=None,
                server_correlation=None
            )

        evidence("RTT avg (ms)", rtt)
        evidence("Packet loss %", pkt_loss)

        causal_chain.append({
            "step": "Network health validated",
            "evidence": {
                "rtt_avg_ms": rtt,
                "packet_loss_pct": pkt_loss
            }
        })

    # ============================================================
    # PRE-FLIGHT EXIT (NO DECISION HERE)
    # ============================================================
    if reasoning_phase == "preflight":
        _final_exit(
            decision="ACCEPT",
            confidence="HIGH",
            reasons=["Pre-flight checks passed"],
            causal_chain=causal_chain,
            environment=environment,
            load_profile=load_profile,
            run_id=run_id,
            client_host=host_validation,
            network=network_validation,
            client_metrics=None,
            baseline=None,
            anomaly=None,
            server_correlation=None
        )

    # ============================================================
    # 5. CLIENT METRICS (POST-RUN ONLY)
    # ============================================================
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

    # ============================================================
    # 6. BASELINE & ANOMALY
    # ============================================================
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

    # ============================================================
    # 6.5 SERVER METRICS CORRELATION
    # ============================================================
    section("Server Metrics Correlation")

    server_correlation = None

    try:
        start_ts = load_ts("output/test_start_ts")
        end_ts   = load_ts("output/test_end_ts")

        kv("Server metrics window", f"{start_ts} → {end_ts}")

        server_metrics = ServerCollector().collect(
            environment=environment,
            service=os.environ.get("SERVICE_NAME", "captain-api"),
            start_ts=start_ts,
            end_ts=end_ts
        )

        if not server_metrics.get("signals"):
            kv("Server metrics", "No matching Prometheus series found")
        else:
            for s in server_metrics["signals"]:
                evidence(s["metric"], s["current"])

        causal_chain.append({
            "step": "Server metrics collected",
            "evidence": {
                "window_start_ts": start_ts,
                "window_end_ts": end_ts,
                **{
                    s["metric"]: s["current"]
                    for s in server_metrics.get("signals", [])
                }
            }
        })

        server_correlation = Correlator().correlate(
            server_metrics=server_metrics,
            server_baseline=None,
            rules=server_rules
        )

        kv("Server correlation status", server_correlation.get("status"))

        causal_chain.append({
            "step": "Server metrics correlated",
            "evidence": server_correlation
        })

    except Exception as e:
        kv("Server correlation", "SKIPPED")
        evidence("Reason", str(e))

        causal_chain.append({
            "step": "Server metrics correlation skipped",
            "evidence": str(e)
        })

    # ============================================================
    # 7. FINAL DECISION (POST-RUN ONLY)
    # ============================================================
    section("Final Decision")

    decision_obj = DecisionEngine(auto_accept_rules).decide(
        client_anomaly=anomaly_result,
        server_correlation=server_correlation
    )

    # Bootstrap handling
    if anomaly_result["status"] == "NO_BASELINE":
        decision_obj["decision"] = "ACCEPT"
        decision_obj["confidence"] = "LOW"
        decision_obj.setdefault("reasons", []).append(
            "Baseline not yet established; accepting run for bootstrap"
        )

    decision_obj["causal_chain"] = causal_chain

    kv("Decision", decision_obj["decision"])
    kv("Confidence", decision_obj["confidence"])

    # ============================================================
    # 8. CAUSAL CHAIN PRINT
    # ============================================================
    print("\n▶ Causal Chain", flush=True)
    for i, step in enumerate(causal_chain, 1):
        print(f"\n{i}. {step['step']}", flush=True)
        ev = step.get("evidence")
        if isinstance(ev, dict):
            for k, v in ev.items():
                print(f"   Evidence: {k} = {v}", flush=True)
        elif isinstance(ev, str):
            print(f"   Evidence: {ev}", flush=True)
        if "impact" in step:
            print(f"   Impact: {step['impact']}", flush=True)

    # ============================================================
    # 9. REPORT
    # ============================================================
    ReasoningReport().generate(
        output_dir="output/reasoning",
        metadata={
            "environment": environment,
            "load_profile": load_profile,
            "run_id": run_id,
            "generated_at": datetime.now(timezone.utc).isoformat()
        },
        client_host=host_validation,
        network=network_validation,
        client_metrics=client_metrics,
        baseline=baseline_metrics,
        anomaly=anomaly_result,
        server_correlation=server_correlation,
        decision=decision_obj
    )

    # Never fail Jenkins here; reporting only
    sys.exit(0)


def _final_exit(
    decision, confidence, reasons, causal_chain,
    environment, load_profile, run_id,
    client_host, network, client_metrics,
    baseline, anomaly, server_correlation
):
    decision_obj = {
        "decision": decision,
        "confidence": confidence,
        "reasons": reasons,
        "causal_chain": causal_chain
    }

    ReasoningReport().generate(
        output_dir="output/reasoning",
        metadata={
            "environment": environment,
            "load_profile": load_profile,
            "run_id": run_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),

            # ✅ ONLY include server window if it exists
            **(
                {
                    "server_metrics_window": {
                        "start_ts": start_ts,
                        "end_ts": end_ts,
                    }
                }
                if "start_ts" in locals() and "end_ts" in locals()
                else {}
            ),
        },
        client_host=client_host,
        network=network,
        client_metrics=client_metrics,
        baseline=baseline,
        anomaly=anomaly,
        server_correlation=server_correlation,
        decision=decision_obj
    )

    # Preflight exits 0; postrun REVIEW_REQUIRED is reported, not failed
    sys.exit(0)


if __name__ == "__main__":
    main()