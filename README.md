# ZPerformanceEngine Framework Blueprint

## Overview

ZPerformanceEngine is a comprehensive **API performance testing and intelligent analysis framework** designed for automated load testing, real-time monitoring, anomaly detection, and AI-powered reporting. It integrates JMeter-based load generation with multi-dimensional metrics collection, statistical analysis, and LLM-driven insights to provide end-to-end performance validation for web APIs.

## Core Architecture Components

### 1. Configuration Layer (`config/`)

- **`environments.yaml`**: Defines target environments (qa, autoprod, dev, autoprod1) with base URLs, hosts, user datasets, and payload mappings
- **`apis.yaml`**: API endpoint definitions with HTTP methods, paths, and authentication requirements
- **`api-groups.yaml`**: Logical grouping of APIs for organized testing
- **`load-profile.yaml`**: Load testing parameters (threads, ramp-up, duration)
- **`users/`**: CSV files containing test user credentials for different environments
- **`headers.yaml`**: HTTP headers for API requests
- **`assertions.yaml`**: Response validation rules

### 2. Test Generation Engine (`engine/`)

- **`generateTestPlan.groovy`**: Groovy script that dynamically generates JMeter (.jmx) test plans from YAML configurations
- **`loadYaml.groovy`**: YAML parsing utilities for configuration loading
- Uses SnakeYAML library for configuration processing

### 3. Data Layer (`data/`)

- Environment-specific JSON payloads for API requests
- Supports multiple test scenarios (login, feeds, crime data, risk intelligence, etc.)

### 4. Reasoning Engine (`reasoning/`)

The intelligent analysis core that validates test conditions and detects performance issues:

#### Collectors: Gather telemetry from multiple sources

- **`client_host_collector.py`**: CPU, memory, disk, network metrics from load generator host
- **`network_collector.py`**: Network latency, packet loss between client and server
- **`client_metrics_collector.py`**: JMeter performance metrics (latency, throughput, errors)
- **`server_collector.py`**: Server-side infrastructure metrics via Prometheus

#### Validators: Pre-flight health checks

- **`client_host_validator.py`**: Ensures load generator is healthy
- **`network_validator.py`**: Validates network connectivity quality

#### Core Analysis Components:

- **`baseline_store.py`**: Historical performance data management
- **`anomaly_detector.py`**: Statistical anomaly detection using baseline comparisons
- **`correlator.py`**: Server-side metrics correlation and causal attribution
- **`decision_engine.py`**: Automated decision making based on rules
- **`explanation_engine.py`**: Natural language explanations of findings

#### Rules Engine: YAML-defined thresholds for different metrics

- Client host rules (CPU, memory, disk, network limits)
- Network rules (latency, packet loss thresholds)
- Client metrics rules (latency deviations, throughput drops, error rates)
- Server rules (CPU, memory, throttling thresholds)

### 5. Reporting System (`reporting/`)

AI-powered report generation with multiple analysis layers:

#### Aggregators: Data consolidation from raw results

- **`jmeter_aggregator.py`**: Processes JMeter JTL results and statistics
- **`baseline_aggregator.py`**: Historical comparison data
- **`infra_aggregator.py`**: Infrastructure metrics summary

#### Decision Engines:

- **`run_validity.py`**: Determines if test run is valid for analysis
- **`regression_status.py`**: Classifies performance regression severity

#### AI Agents (LLM-powered analysis):

- **`executive_agent.py`**: High-level executive summary generation
- **`api_summary_agent.py`**: Per-API performance analysis
- **`infra_summary_agent.py`**: Infrastructure bottleneck analysis
- **`llm_client.py`** & **`local_llm_client.py`**: LLM integration (supports Mistral model)

#### Renderers:

- **`html_renderer.py`**: Generates interactive HTML reports
- **`json_renderer.py`**: Structured data export
- **`markdown_renderer.py`**: Documentation format output

## Execution Flow & Order

### Phase 1: Test Plan Generation

1. **Configuration Loading**: Parse YAML configs (environments, APIs, load profiles)
2. **Environment Resolution**: Select target environment (CLI override or default)
3. **JMeter Plan Generation**: Groovy script creates .jmx file with:
   - Thread groups based on load profile
   - HTTP samplers for each API endpoint
   - Assertions and response validation
   - Prometheus backend listener for metrics export

### Phase 2: Pre-Flight Validation (Reasoning Engine)

1. **Context Initialization**: Load environment variables (ENVIRONMENT, LOAD_PROFILE, TARGET_HOST)
2. **Rules Loading**: Parse all YAML rule files
3. **Client Host Health Check**:
   - Collect CPU, memory, disk, network metrics
   - Validate against `client_host_rules.yaml`
   - Fail-fast if unhealthy (prevents invalid test runs)
4. **Network Health Check**:
   - Measure RTT, packet loss to target
   - Validate against `network_rules.yaml`
   - Skip for localhost targets

### Phase 3: Load Test Execution

1. **JMeter Execution**: Run generated .jmx plan
2. **Real-time Metrics**: Prometheus listener exports metrics during test
3. **Timestamp Capture**: Record test start/end timestamps

### Phase 4: Post-Run Analysis (Reasoning Engine)

1. **Client Metrics Collection**: Parse JMeter results (JTL, statistics.json)
2. **Baseline Comparison**: Load historical data, detect anomalies
3. **Server Metrics Correlation**:
   - Collect server-side metrics over test window
   - Correlate with client-side issues
   - Probabilistic causal attribution
4. **State Analysis**: Determine server health states (saturated, throttled, memory pressure)
5. **Explanation Generation**: Natural language explanations of findings
6. **Report Generation**: JSON reasoning report with causal chain

### Phase 5: Intelligent Reporting

1. **Data Aggregation**: Consolidate JMeter, baseline, and infrastructure metrics
2. **Run Validation**: Check if test results are trustworthy
3. **Regression Classification**: Determine performance change severity
4. **AI Analysis**:
   - Executive summary generation
   - Per-API detailed analysis
   - Infrastructure bottleneck identification
5. **Report Rendering**: Generate HTML dashboard with interactive visualizations

## Tools & Techniques Used

### Load Testing

- **JMeter 5.6.3**: Industry-standard load testing tool
- **Groovy Scripting**: Dynamic test plan generation
- **Prometheus Integration**: Real-time metrics collection via JMeter backend listener

### Metrics Collection

- **System Metrics**: `psutil` library for host telemetry
- **Network Diagnostics**: `ping`, `mtr` for latency/packet loss measurement
- **Server Monitoring**: Prometheus queries for infrastructure metrics
- **Performance Parsing**: JMeter result file processing

### Data Processing

- **YAML Configuration**: Human-readable, version-controllable config files
- **JSON Data Exchange**: Standardized data formats between components
- **CSV User Management**: Bulk test user credential handling

### Analysis Techniques

- **Statistical Anomaly Detection**: Baseline comparison with configurable thresholds
- **Correlation Analysis**: Multi-dimensional metric correlation for root cause analysis
- **Rule-Based Validation**: Configurable health checks and failure criteria
- **Probabilistic Attribution**: Bayesian-style causal reasoning for issue attribution

### AI/ML Integration

- **Local LLM**: Mistral model for natural language report generation
- **Prompt Engineering**: Structured prompts for different analysis types
- **Contextual Summarization**: API-specific and infrastructure-focused insights

### Infrastructure & Deployment

- **Docker Containerization**: Self-contained execution environment
- **Python 3**: Primary analysis language with rich ecosystem
- **Java/Groovy**: Test generation and JMeter integration
- **Shell Scripting**: Orchestration and environment management

### Reporting & Visualization

- **HTML Rendering**: Interactive web-based reports
- **Template System**: Jinja2-based report templating
- **Multi-format Output**: JSON, Markdown, HTML export options

## Key Innovations

1. **Intelligent Pre-flight Checks**: Prevents wasted test runs on unhealthy infrastructure
2. **Multi-layer Correlation**: Connects client, network, and server metrics for holistic analysis
3. **AI-Powered Insights**: LLM-generated explanations and summaries
4. **Automated Decision Making**: Rules-based validity assessment and regression classification
5. **Dynamic Test Generation**: Configuration-driven JMeter plan creation
6. **Causal Chain Tracking**: Maintains audit trail of analysis decisions

---

_This framework transforms traditional performance testing from manual analysis of raw metrics into an automated, intelligent system that provides actionable insights with minimal human intervention._
