# ZPerformanceEngine Setup Guide

## 1) What this repository does

`ZPerformanceEngine` is a YAML-driven performance test framework built around:

- dynamic JMeter test-plan generation via Groovy
- containerized execution via Docker
- CI orchestration via Jenkins pipeline
- pre/post-run reasoning over client/network/server signals
- HTML executive report generation

Core run flow:

1. Build Docker image.
2. Generate a functional JMX (`1 user`) and run a functional gate.
3. Select eligible APIs from functional pass results.
4. Generate final load JMX and run load test.
5. Run reasoning engine (preflight and postrun).
6. Generate executive HTML report and archive artifacts.

---

## 2) Repository structure (detailed)

### Root files

- `Dockerfile`: Runtime image (Temurin 11, Groovy, Python, JMeter 5.6.3, requirements, listener jar).
- `Jenkinsfile`: Full CI pipeline (build, test generation, runs, reasoning, archive, email).
- `requirements.txt`: Python dependencies used inside container.
- `jmeter-prometheus-listener.jar`: Required JMeter backend listener plugin.
- `SETUP.md`: This document.

### `engine/`

- `engine/generateTestPlan.groovy`: Main dynamic JMX generator from YAML + CLI system properties.
- `engine/loadYaml.groovy`: SnakeYAML loader helper.

### `lib/`

- `lib/snakeyaml.jar`: YAML parser dependency used by Groovy generator.

### `config/`

- `config/environments.yaml`: Environment mapping (`baseUrl`, `host`, user CSV, payload files).
- `config/apis.yaml`: API sampler definitions.
- `config/api-groups.yaml`: Named API groups for grouped execution.
- `config/headers.yaml`: Login/API header templates with `__BASE_URL__` substitution.
- `config/load-profile.yaml`: Universal overrides + named load profiles.
- `config/assertions.yaml`: YAML-driven per-API/default JMeter assertions.
- `config/reporting.yaml`: Reporting/AI toggles and rendering options.

### `config/users/`

- `config/users/autoprod.csv`
- `config/users/autoprod1.csv`
- `config/users/dev.csv`
- `config/users/qa.csv`

Each file is expected to contain `username,password` CSV and is consumed by JMeter `CSVDataSet`.

### `data/`

Payload bodies for API requests by environment:

- `data/login-payload.json`
- `data/qa/*.json`
- `data/dev/*.json`
- `data/autoprod/*.json`
- `data/autoprod1/*.json`

### `reasoning/`

Python reasoning engine and policies:

- `reasoning/main.py`: Entry point (preflight/postrun modes).
- `reasoning/collectors/*.py`: client host, network, client metrics, server telemetry collection.
- `reasoning/validators/*.py`: host/network invariant validators.
- `reasoning/detectors/anomaly_detector.py`: baseline vs current anomaly checks.
- `reasoning/correlators/correlator.py`: server-state correlation and attribution.
- `reasoning/decisions/decision_engine.py`: review/decision logic (currently diagnostic-oriented flow).
- `reasoning/reports/reasoning_report.py`: writes `reasoning_report.txt/json`.
- `reasoning/explanations/explanation_engine.py`: deterministic explanation rules.

Rules/policies:

- `reasoning/rules/client_host_rules.yaml`
- `reasoning/rules/network_rules.yaml`
- `reasoning/rules/client_metrics_rules.yaml`
- `reasoning/rules/server_rules.yaml`
- `reasoning/baselines/baseline_policy.yaml`
- `reasoning/decisions/auto_accept_rules.yaml`

### `reporting/` (currently local/untracked in this workspace)

- `reporting/orchestrator.py`
- `reporting/aggregators/*.py`
- `reporting/agents/*.py`
- `reporting/models/*.py`
- `reporting/decisions/*.py`
- `reporting/renderers/*.py`
- `reporting/templates/*.html`

### `scripts/`

- `scripts/generate_executive_report.py`: Builds `output/executive/index.html` from JMeter stats/JTL.
- `scripts/read_yaml.py`: Utility script to print YAML as JSON.
- `scripts/test_*.py` (currently local/untracked in this workspace): reporting-related tests.

---

## 3) Prerequisites on another machine

## Mandatory

- Git
- Docker Engine + Docker CLI
- Network access from runner to:
  - target API hosts in `config/environments.yaml`
  - Grafana endpoint configured in Jenkins (`GRAFANA_URL`)

## For Jenkins-based runs

- Jenkins with Pipeline support.
- Jenkins agent where Docker is installed and Jenkins user can execute Docker.
- Jenkins SMTP/mail configured if keeping `mail(...)` post action.

## Optional (local development outside Docker)

- Python 3.10+ (for local script/testing convenience)
- Groovy + JDK (only if generating JMX outside container)
- Ollama (`ollama run mistral`) only if using local AI summaries from `reporting/orchestrator.py`
- `OPENAI_API_KEY` + `openai` pip package only if using `reporting/agents/llm_client.py`

---

## 4) Security and secrets

This repo currently stores credentials in `config/users/*.csv` in plaintext. Before sharing externally:

1. Rotate credentials.
2. Replace with non-production/test accounts.
3. Prefer secret injection (Jenkins credentials + runtime file generation) instead of committing passwords.

Required Jenkins credential(s):

- String credential ID: `grafana-readonly-token`

---

## 5) Local run (Docker, no Jenkins)

From repo root:

```bash
docker build -t zperformance-engine .
mkdir -p output reasoning/baselines/snapshots
```

Generate JMX (example):

```bash
docker run --rm \
  -v "$PWD:/workspace" \
  -w /workspace \
  zperformance-engine \
  groovy -Denv=qa -Dprofile=baseline-minimal -DloopLogin=true engine/generateTestPlan.groovy
```

Run JMeter with generated plan:

```bash
docker run --rm \
  -v "$PWD:/workspace" \
  -w /workspace \
  zperformance-engine \
  sh -c 'jmeter -n -t output/generated-test-plan.jmx -l output/results.jtl -e -o output/dashboard'
```

Run preflight reasoning:

```bash
docker run --rm \
  -v "$PWD:/workspace" \
  -w /workspace \
  -e ENVIRONMENT=qa \
  -e LOAD_PROFILE=baseline-minimal \
  -e TARGET_HOST=qa.ontic.ai \
  -e REASONING_PHASE=preflight \
  -e GRAFANA_URL=<grafana-url> \
  -e GRAFANA_DS_UID=<prom-ds-uid> \
  -e GRAFANA_API_TOKEN=<token> \
  -e SERVICE_NAME=captain-api \
  zperformance-engine \
  python3 -m reasoning.main
```

Run postrun reasoning requires:

- `output/test_start_ts`
- `output/test_end_ts`
- `output/results.jtl`
- `output/dashboard/statistics.json`
- preflight snapshot at `output/reasoning/preflight_snapshot.yaml`

Generate executive HTML:

```bash
docker run --rm \
  -v "$PWD:/workspace" \
  -w /workspace \
  zperformance-engine \
  python3 scripts/generate_executive_report.py output/dashboard/statistics.json output/executive
```

---

## 6) Jenkins setup (recommended production path)

## 6.1 Create pipeline job

- Job type: Pipeline (or Multibranch Pipeline).
- SCM: point to this repo.
- Pipeline source: `Jenkinsfile` from SCM.

## 6.2 Install Jenkins plugins

- Pipeline
- Git
- Credentials Binding
- Mailer
- Active Choices (if using dynamic dropdown parameters)

## 6.3 Configure credentials

- Add string credential with ID `grafana-readonly-token`.

## 6.4 Configure parameters (UI-managed currently)

`Jenkinsfile` reads these `params.*` values but does not define them inside pipeline code, so configure in Jenkins UI:

- `ENVIRONMENT`
- `LOAD_PROFILE`
- `SELECTED_APIS`
- `LOOPLOGIN`
- `DEBUG`
- `DURATION`

## 6.5 Jenkinsfile portability fix required

Current `Jenkinsfile` has:

- `DOCKER_CLI = "/Applications/Docker.app/Contents/Resources/bin/docker"`

This is macOS-specific. On Linux Jenkins agents, change to:

- `DOCKER_CLI = "docker"`

(or make node-specific).

## 6.6 Jenkins global config dependencies

- SMTP configured if `post { always { mail(...) } }` should work.
- Agent permissions to run Docker commands.

---

## 7) YAML-driven behavior reference

## Environment selection

`-Denv=<name>` must exist in `config/environments.yaml`.

## Load profile selection

`-Dprofile=<name>` must exist in `config/load-profile.yaml`.

## API selection

- `-Dgroup=<group-name>` from `config/api-groups.yaml`
- `-Dapis=api1,api2,...` explicit list
- If no group/apis is provided, all APIs run.
- Login sampler is always forced first.

## Assertions

Configured in `config/assertions.yaml` and converted to JSR223 assertions in generated JMX.

---

## 8) YAML <-> Jenkins dropdown sync (your current flow and recommended flow)

You mentioned you use a local mirror repo copy to refresh Jenkins parameter dropdowns. That is an external dependency and must be handed over.

## Current flow (works but fragile)

- Active Choices scripts read YAML from a fixed local filesystem path.
- You manually update/sync local repo clone.
- Jenkins dropdowns update based on that local clone.

Handover must include:

1. exact local path on Jenkins host,
2. update method (`git pull` schedule/manual),
3. exact Active Choices Groovy scripts used for each parameter.

## Recommended flow (more portable)

- Remove path dependency on personal/local mirror.
- Read YAML from current Jenkins workspace checkout.
- Keep one source of truth: SCM branch used by the job.

Typical pattern:

1. Add a lightweight “refresh parameters” stage/job that checks out SCM.
2. Active Choices scripts parse files from workspace path.
3. Re-run refresh after merges to keep dropdowns aligned.

---

## 9) What must be committed before sharing

In this current workspace, `git status` shows local-only assets not yet committed (for example `reporting/`, `config/reporting.yaml`, and test scripts). If another person clones now, they will not get those files.

Before sharing:

1. Commit/push required untracked files.
2. Remove non-portable local artifacts (`.venv`, caches, `test-results`, etc).
3. Verify with a clean clone on a second machine.

Validation checklist:

```bash
git clone <repo-url> /tmp/zperf-verify
cd /tmp/zperf-verify
docker build -t zperformance-engine .
```

Then run one minimal generation/test cycle.

---

## 10) Known issues to fix (recommended)

1. `config/environments.yaml` has `autoprod1.baseUrl: "https:autoprod1.ontic.ai"` (missing `//`).
2. Jenkins Docker path is hardcoded for macOS.
3. Credentials are stored in plaintext CSV in repo.
4. Parameter definitions are not versioned in `Jenkinsfile` (UI drift risk).

---

## 11) Operational output paths

Generated at runtime (ignored by git):

- `output/generated-test-plan.jmx`
- `output/functional-test-plan.jmx`
- `output/functional_results.jtl`
- `output/results.jtl`
- `output/dashboard/`
- `output/reasoning/`
- `output/executive/`
- `output/performance-reports.zip`

Baseline snapshots:

- `reasoning/baselines/snapshots/*.json`

---

## 12) Quick handover checklist

1. Push complete repo state (including currently local/untracked required files).
2. Rotate and secure credentials.
3. Set up Jenkins job + plugins + credentials + SMTP.
4. Fix Docker CLI path in Jenkinsfile for target agent OS.
5. Recreate/standardize Jenkins parameters.
6. Rewire YAML dropdown scripts to workspace-based path (recommended).
7. Run one known profile (`baseline-minimal`) in `qa` and verify artifacts are produced.


## 13) Exact file inventory

### Tracked files in Git

```text
.gitignore
Dockerfile
Jenkinsfile
config/api-groups.yaml
config/apis.yaml
config/assertions.yaml
config/environments.yaml
config/headers.yaml
config/load-profile.yaml
config/users/autoprod.csv
config/users/autoprod1.csv
config/users/dev.csv
config/users/qa.csv
data/autoprod/allfeeds-payload.json
data/autoprod/createentity-payload.json
data/autoprod/crimedata-payload.json
data/autoprod/crimeevents-payload.json
data/autoprod/feedpreview-payload.json
data/autoprod/riskintelligence-payload.json
data/autoprod1/allfeeds-payload.json
data/autoprod1/createentity-payload.json
data/autoprod1/crimeevents-payload.json
data/autoprod1/riskintelligence-payload.json
data/dev/allfeeds-payload.json
data/dev/crimedata-payload.json
data/dev/riskintelligence-payload.json
data/login-payload.json
data/qa/accepttac-payload.json
data/qa/allfeeds-payload.json
data/qa/createentity-payload.json
data/qa/crimedata-payload.json
data/qa/crimeevents-payload.json
data/qa/feedpreview-payload.json
data/qa/riskintelligence-payload.json
engine/generateTestPlan.groovy
engine/loadYaml.groovy
jmeter-prometheus-listener.jar
lib/snakeyaml.jar
reasoning/__init__.py
reasoning/baselines/baseline_policy.yaml
reasoning/baselines/baseline_store.py
reasoning/collectors/client_host_collector.py
reasoning/collectors/client_metrics_collector.py
reasoning/collectors/network_collector.py
reasoning/collectors/server_collector.py
reasoning/correlators/correlator.py
reasoning/decisions/auto_accept_rules.yaml
reasoning/decisions/decision_engine.py
reasoning/detectors/anomaly_detector.py
reasoning/explanations/explanation_engine.py
reasoning/main.py
reasoning/reports/reasoning_report.py
reasoning/rules/client_host_rules.yaml
reasoning/rules/client_metrics_rules.yaml
reasoning/rules/network_rules.yaml
reasoning/rules/server_rules.yaml
reasoning/validators/client_host_validator.py
reasoning/validators/network_validator.py
requirements.txt
scripts/generate_executive_report.py
scripts/read_yaml.py
```

### Currently untracked in this workspace

```text
SETUP.md
config/reporting.yaml
reporting/
scripts/test_api_summary_agent.py
scripts/test_baseline_aggregator.py
scripts/test_executive_agent.py
scripts/test_infra_aggregator.py
scripts/test_infra_summary_agent.py
scripts/test_jmeter_aggregator.py
scripts/test_llm_client.py
scripts/test_reporting.py
test-results/
```
