import os
import sys
import yaml
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

from reasoning.explanations.explanation_engine import (ExplanationEngine, EXPLANATION_RULES)


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


# ---------------- Metric Effects ----------------
CLIENT_HOST_EFFECTS = {
    "cpu.avg_pct": (
        "High CPU usage can throttle load generator threads, "
        "reducing the actual load applied."
    ),
    "cpu.max_pct": (
        "CPU spikes can introduce timing jitter, "
        "causing inconsistent request pacing."
    ),
    "memory.avg_pct": (
        "High memory usage increases the risk of garbage collection pauses "
        "during load generation."
    ),
    "memory.max_pct": (
        "Near-exhausted memory can destabilize the load generator "
        "and interrupt request flow."
    ),
    "memory.swap_used_pct": (
        "Swap usage severely distorts timing accuracy "
        "and invalidates load test results."
    ),
    "disk.iowait_avg_pct": (
        "Disk waits can delay result logging "
        "and block load generator threads."
    ),
    "disk.iowait_max_pct": (
        "High IO wait can intermittently stall request execution."
    ),
    "network.tx_bytes_per_sec": (
        "Low outbound traffic indicates the load generator "
        "may not be sending the intended load."
    ),
    "os.load_avg_per_core": (
        "High runnable load can delay thread scheduling "
        "and reduce effective concurrency."
    ),
}

NETWORK_EFFECTS = {
    "network.rtt.avg_ms":
        "High network latency can slow request delivery and distort response times.",
    "network.rtt.p95_ms":
        "Intermittent network delays can cause request stalls and timeouts.",
    "network.packet_loss.pct":
        "Packet loss can cause retries and dropped requests, invalidating test results.",
}

def print_client_host_metrics(host_telemetry, host_validation, rules):
    print("\n  Metrics vs Rules:", flush=True)

    # Build observed metrics FIRST (facts)
    observed = {
        "cpu.avg_pct": host_telemetry["cpu"]["avg_pct"],
        "cpu.max_pct": host_telemetry["cpu"]["max_pct"],
        "memory.avg_pct": host_telemetry["memory"]["avg_pct"],
        "memory.max_pct": host_telemetry["memory"]["max_pct"],
        "memory.swap_used_pct": host_telemetry["memory"]["swap_used_pct"],
        "disk.iowait_avg_pct": host_telemetry["disk"]["iowait_avg_pct"],
        "disk.iowait_max_pct": host_telemetry["disk"]["iowait_max_pct"],
        "network.tx_bytes_per_sec": host_telemetry["network"]["tx_bytes_per_sec"],
    }

    cores = host_telemetry["cpu"]["cores"]
    observed["os.load_avg_per_core"] = round(
        host_telemetry["os"]["load_avg_1m"] / cores, 2
    )

    # Build rule lookup (may be partial)
    rule_lookup = {
        "cpu.avg_pct": {
            "type": "max",
            "value": rules.get("cpu", {}).get("avg_pct_max")
        },
        "cpu.max_pct": {
            "type": "max",
            "value": rules.get("cpu", {}).get("max_pct_max")
        },
        "memory.avg_pct": {
            "type": "max",
            "value": rules.get("memory", {}).get("avg_pct_max")
        },
        "memory.max_pct": {
            "type": "max",
            "value": rules.get("memory", {}).get("max_pct_max")
        },
        "memory.swap_used_pct": {
            "type": "max",
            "value": rules.get("memory", {}).get("swap_used_pct_max")
        },
        "disk.iowait_avg_pct": {
            "type": "max",
            "value": rules.get("disk", {}).get("iowait_avg_pct_max")
        },
        "disk.iowait_max_pct": {
            "type": "max",
            "value": rules.get("disk", {}).get("iowait_max_pct_max")
        },
        "network.tx_bytes_per_sec": {
            "type": "min",   # 👈 THIS IS THE IMPORTANT PART
            "value": rules.get("network", {}).get("tx_bytes_per_sec_min")
        },
        "os.load_avg_per_core": {
            "type": "max",
            "value": rules.get("os", {}).get("load_avg_per_core_max")
        },
    }


    violated = {v["metric"] for v in host_validation["violations"]}

    for metric, value in observed.items():
        rule = rule_lookup.get(metric)

        if rule is None:
            print(f"     • {metric} = {value} (no rule)", flush=True)
            continue

        symbol = "✖" if metric in violated else "✔"
        rule_meta = rule_lookup.get(metric)

        if rule_meta is None or rule_meta["value"] is None:
            print(f"     • {metric} = {value} (no rule)", flush=True)
            continue

        rule_type = rule_meta["type"]
        limit = rule_meta["value"]

        if rule_type == "max":
            comparison = f"< {limit}"
        elif rule_type == "min":
            comparison = f">= {limit}"
        else:
            comparison = f"{limit}"

        symbol = "✖" if metric in violated else "✔"

        print(
            f"     {symbol} {metric} = {value} (allowed {comparison})",
            flush=True
        )


        effect = CLIENT_HOST_EFFECTS.get(metric)
        if effect:
            print(f"        ↳ Effect: {effect}", flush=True)

def explain_server_states(server_metrics, server_states, server_rules):
    """
    Generate one-line, data-backed explanations for each server state.
    """

    # Build metric lookup
    metrics = {
        s["metric"]: s["current"]
        for s in server_metrics.get("signals", [])
    }

    rules = server_rules.get("server_rules", {})

    explanations = {}

    # ---- server_saturated ----
    cpu = metrics.get("cpu")
    threads = metrics.get("threads")

    cpu_limit = rules["cpu"]["minor_abs"]
    thread_limit = rules["threads"]["minor_abs"]

    cpu_ok = cpu < cpu_limit
    threads_ok = threads < thread_limit

    if server_states.get("server_saturated"):
        explanations["server_saturated"] = (
            f"CPU max {cpu}% ≥ {cpu_limit}% or "
            f"threads max {threads} ≥ {thread_limit}"
        )
    else:
        explanations["server_saturated"] = (
            f"CPU max {cpu}% {'<' if cpu_ok else '≥'} {cpu_limit}%, "
            f"threads max {threads} {'<' if threads_ok else '≥'} {thread_limit}"
        )

    # ---- server_slow ----
    lat = metrics.get("httplatp95")
    lat_limit = rules["httplatp95"]["minor_abs"]

    lat_ok = lat < lat_limit

    if server_states.get("server_slow"):
        explanations["server_slow"] = (
            f"Server p95 latency {lat} ms ≥ {lat_limit} ms"
        )
    else:
        explanations["server_slow"] = (
            f"Server p95 latency {lat} ms {'<' if lat_ok else '≥'} {lat_limit} ms"
        )

    # ---- server_erroring ----
    err = metrics.get("http5xx")

    if server_states.get("server_erroring"):
        explanations["server_erroring"] = (
            "Server returned 5xx errors"
        )
    else:
        explanations["server_erroring"] = (
            f"Server 5xx rate {err} = 0"
        )

    # ---- server_healthy ----
    if server_states.get("server_healthy"):
        explanations["server_healthy"] = (
            "No saturation, slowness, or server errors observed during anomaly window"
        )
    else:
        explanations["server_healthy"] = (
            "One or more server stress conditions detected"
        )

    return explanations

    # Build observed values
    observed = {
        "cpu.avg_pct": host_telemetry["cpu"]["avg_pct"],
        "cpu.max_pct": host_telemetry["cpu"]["max_pct"],
        "memory.avg_pct": host_telemetry["memory"]["avg_pct"],
        "memory.max_pct": host_telemetry["memory"]["max_pct"],
        "memory.swap_used_pct": host_telemetry["memory"]["swap_used_pct"],
        "disk.iowait_avg_pct": host_telemetry["disk"]["iowait_avg_pct"],
        "disk.iowait_max_pct": host_telemetry["disk"]["iowait_max_pct"],
        "network.tx_bytes_per_sec": host_telemetry["network"]["tx_bytes_per_sec"],
    }

    # Derived metric
    cores = host_telemetry["cpu"]["cores"]
    observed["os.load_avg_per_core"] = round(
        host_telemetry["os"]["load_avg_1m"] / cores, 2
    )

    violated_metrics = {
        v["metric"] for v in host_validation["violations"]
    }

    for metric, limit in rule_map.items():
        value = observed.get(metric)
        if value is None:
            continue

        if metric in violated_metrics:
            symbol = "✖"
            status = f"(allowed < {limit})"
        else:
            symbol = "✔"
            status = f"(allowed < {limit})"

        print(
            f"     {symbol} {metric} = {value} {status}",
            flush=True
        )

        effect = CLIENT_HOST_EFFECTS.get(metric)
        if effect:
            print(
                f"        ↳ Effect: {effect}",
                flush=True
            )


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
    # RUN CONTEXT (ALWAYS COLLECT)
    # ============================================================
    environment = os.environ.get("ENVIRONMENT")
    load_profile = os.environ.get("LOAD_PROFILE")
    build_number = os.environ.get("BUILD_NUMBER", "local")
    target_host = os.environ.get("TARGET_HOST")

    if not environment or not load_profile or not target_host:
        fail("ENVIRONMENT, LOAD_PROFILE, or TARGET_HOST missing")

    run_id = f"jenkins-{build_number}"

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
    # LOAD RULES
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

    snapshot_path = "output/reasoning/preflight_snapshot.yaml"

    # ============================================================
    # PRE-FLIGHT
    # ============================================================
    if reasoning_phase == "preflight":
        section("Run Context")
        kv("Environment", environment)
        kv("Load Profile", load_profile)
        kv("Run ID", run_id)
        kv("Target Host", target_host)

        section("Client Host Health")
        host_telemetry = ClientHostCollector().collect()
        host_validation = ClientHostValidator(client_host_rules).validate(host_telemetry)

        kv("Healthy", host_validation["healthy"])
        kv("Fail Fast", host_validation["fail_fast"])

        print_client_host_metrics(
            host_telemetry,
            host_validation,
            client_host_rules["client_host"]
        )

        causal_chain.append({
            "step": "Client host health validated",
            "evidence": host_telemetry
        })

        if host_validation["fail_fast"]:
            _final_exit(
                decision="INVALID",
                confidence="HIGH",
                reasons=["Client host failed pre-flight health checks"],
                causal_chain=causal_chain + [{
                    "step": "Client host pre-flight fail-fast",
                    "evidence": host_validation
                }],
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

        section("Network Health")
        if is_localhost(target_host):
            network_validation = {"status": "NOT_APPLICABLE"}
            kv("Status", "NOT_APPLICABLE")
        else:
            net_telemetry = NetworkCollector(target_host).collect()
            network_validation = NetworkValidator(network_rules, environment).validate(net_telemetry)

            kv("Healthy", network_validation["healthy"])
            kv("Fail Fast", network_validation["fail_fast"])

            print("\n  Metrics vs Rules:", flush=True)

            violated = {v["metric"] for v in network_validation["violations"]}

            # RTT avg
            if net_telemetry["rtt"]["avg_ms"] is not None:
                metric = "network.rtt.avg_ms"
                value = net_telemetry["rtt"]["avg_ms"]
                limit = network_validation["rtt_limits"]["avg_ms_max"]
                symbol = "✖" if metric in violated else "✔"

                print(f"     {symbol} {metric} = {value} (allowed < {limit})", flush=True)
                print(f"        ↳ Effect: {NETWORK_EFFECTS[metric]}", flush=True)

            # RTT p95
            if net_telemetry["rtt"]["p95_ms"] is not None:
                metric = "network.rtt.p95_ms"
                value = net_telemetry["rtt"]["p95_ms"]
                limit = network_validation["rtt_limits"]["p95_ms_max"]
                symbol = "✖" if metric in violated else "✔"

                print(f"     {symbol} {metric} = {value} (allowed < {limit})", flush=True)
                print(f"        ↳ Effect: {NETWORK_EFFECTS[metric]}", flush=True)

            # Packet loss
            if net_telemetry["packet_loss"]["pct"] is not None:
                metric = "network.packet_loss.pct"
                value = net_telemetry["packet_loss"]["pct"]
                limit = network_rules["network"]["packet_loss"]["pct_max"]
                symbol = "✖" if metric in violated else "✔"

                print(f"     {symbol} {metric} = {value} (allowed < {limit})", flush=True)
                print(f"        ↳ Effect: {NETWORK_EFFECTS[metric]}", flush=True)

        causal_chain.append({
            "step": "Network health validated",
            "evidence": network_validation
        })

        if network_validation.get("fail_fast"):
            _final_exit(
                decision="INVALID",
                confidence="HIGH",
                reasons=["Network failed pre-flight health checks"],
                causal_chain=causal_chain + [{
                    "step": "Network pre-flight fail-fast",
                    "evidence": network_validation
                }],
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

        os.makedirs("output/reasoning", exist_ok=True)
        with open(snapshot_path, "w") as f:
            yaml.safe_dump({
                "client_host": host_validation,
                "network": network_validation
            }, f)

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
    # POST-FLIGHT
    # ============================================================
    if not os.path.exists(snapshot_path):
        fail("Missing preflight snapshot")

    with open(snapshot_path) as f:
        snapshot = yaml.safe_load(f)

    host_validation = snapshot["client_host"]
    network_validation = snapshot["network"]

    section("Client Performance Metrics")
    client_metrics = ClientMetricsCollector(
        "output/results.jtl",
        "output/dashboard/statistics.json"
    ).collect()

    kv("P95 latency (ms)", client_metrics["latency"]["p95_ms"])
    kv("Error rate (%)", client_metrics["errors"]["error_rate_pct"])

    causal_chain.append({
        "step": "Client metrics collected",
        "evidence": client_metrics
    })

    # -----------------------------
    # Baseline Evaluation
    # -----------------------------
    section("Baseline Evaluation")

    baseline_store = BaselineStore(baseline_policy, environment, load_profile)
    baseline = baseline_store.load_baseline()

    if baseline is None:
        kv("Baseline Status", "LEARNING (no baseline yet)")
    else:
        meta = baseline["meta"]
        kv("Baseline Type", meta["type"])
        kv("Sample Count", meta.get("sample_count"))

    # -----------------------------
    # Anomaly Detection
    # -----------------------------
    section("Anomaly Detection")


    baseline = baseline_store.load_baseline()

    anomaly_result = AnomalyDetector(client_metrics_rules).detect(
        client_metrics=client_metrics,
        baseline=baseline["numeric"],   # ✅ correct
    )

    # Expose baseline meta to anomaly result for downstream reporting
    if isinstance(baseline, dict) and "meta" in baseline:
        anomaly_result["baseline_meta"] = baseline["meta"]

    kv("Anomaly Status", anomaly_result["status"])

    if anomaly_result["status"] == "WEAK_BASELINE":
        evidence(
            "Baseline strength",
            f"Weak (samples = {anomaly_result['baseline_meta']['sample_count']})"
        )

    if anomaly_result.get("anomalies"):
        print("\n  Detected Anomalies:", flush=True)
        for name, details in anomaly_result["anomalies"].items():
            if details.get("type") == "absolute":
                print(
                    f"     ✖ {details['metric']}: "
                    f"current={details['current']}% "
                    f"(allowed ≤ {details['threshold_pct']}%)",
                    flush=True
                )
            else:
                print(
                    f"     ✖ {details['metric']}: "
                    f"current={details['current']} "
                    f"(baseline={details['baseline']}, "
                    f"threshold={details['threshold_pct']}%)",
                    flush=True
                )

    baseline_store.save_run(run_id, client_metrics)

    causal_chain.append({
        "step": "Client anomaly evaluation",
        "evidence": anomaly_result
    })

    section("Server Metrics Correlation")
    start_ts = load_ts("output/test_start_ts")
    end_ts = load_ts("output/test_end_ts")

    server_metrics = ServerCollector().collect(
        environment,
        os.environ.get("SERVICE_NAME", "captain-api"),
        start_ts,
        end_ts
    )

    print("\n  Server Metrics (aggregated over test window):", flush=True)
    for s in server_metrics.get("signals", []):
        evidence(
            f"{s['metric']} ({s['aggregation']})",
            s["current"]
        )

    server_correlation = Correlator().correlate(server_metrics, None, server_rules)
    kv("Server correlation status", server_correlation["status"])
    states = server_correlation.get("states", {})
    state_explanations = explain_server_states(
        server_metrics,
        states,
        server_rules
    )
    print("\n  Server States:", flush=True)
    for state, value in states.items():
        symbol = "✔" if value else "✖"
        print(f"     {symbol} {state}: {value}", flush=True)
        print(f"        ↳ {state_explanations[state]}", flush=True)
    section("Explanation")
    if anomaly_result.get("status") == "OK":
        explanations = ["No client-side anomalies detected."]
        print("  • No client-side anomalies detected.", flush=True)
    else:
        explanations = ExplanationEngine(EXPLANATION_RULES).explain(
            anomaly_result,
            server_correlation
        )
        for line in explanations:
            print(f"  • {line}", flush=True)
    causal_chain.append({
        "step": "Explanation derived",
        "evidence": explanations
    })

    causal_chain.append({
        "step": "Server metrics correlated",
        "evidence": server_correlation
    })

    section("Final Decision")
    decision_obj = DecisionEngine(auto_accept_rules).decide(
        anomaly_result,
        server_correlation
    )
    decision_obj["explanations"] = explanations

    # Propagate baseline metadata so reports and decisions can account for baseline strength
    decision_obj["baseline_meta"] = anomaly_result.get("baseline_meta")

    kv("Decision", decision_obj["decision"])
    kv("Confidence", decision_obj["confidence"])

    decision_obj["causal_chain"] = causal_chain

    section("Causal Chain")
    for i, step in enumerate(causal_chain, 1):
        print(f"\n{i}. {step['step']}", flush=True)

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
        baseline=baseline,
        anomaly=anomaly_result,
        server_correlation=server_correlation,
        decision=decision_obj
    )

    sys.exit(0)


def _final_exit(
    decision, confidence, reasons, causal_chain,
    environment, load_profile, run_id,
    client_host, network, client_metrics,
    baseline, anomaly, server_correlation
):
    ReasoningReport().generate(
        output_dir="output/reasoning",
        metadata={
            "environment": environment,
            "load_profile": load_profile,
            "run_id": run_id,
            "generated_at": datetime.now(timezone.utc).isoformat()
        },
        client_host=client_host,
        network=network,
        client_metrics=client_metrics,
        baseline=baseline,
        anomaly=anomaly,
        server_correlation=server_correlation,
        decision={
            "decision": decision,
            "confidence": confidence,
            "reasons": reasons,
            "causal_chain": causal_chain
        }
    )

    section("Final Outcome")
    kv("Decision", decision)
    kv("Confidence", confidence)

    sys.exit(0)


if __name__ == "__main__":
    main()