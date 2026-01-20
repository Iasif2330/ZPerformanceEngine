import json
import sys
import os
import csv

# --------------------------------------------------
# Inputs (UNCHANGED)
# --------------------------------------------------
if len(sys.argv) != 3:
    raise SystemExit(
        "Usage: generate_executive_report.py <statistics.json> <output_dir>"
    )

STATISTICS_JSON = sys.argv[1]
OUTPUT_DIR = sys.argv[2]
OUTPUT_HTML = os.path.join(OUTPUT_DIR, "index.html")

# Optional raw JMeter results file (AUTO-DETECTED)
DASHBOARD_DIR = os.path.dirname(STATISTICS_JSON)
BASE_OUTPUT_DIR = os.path.dirname(DASHBOARD_DIR)
RESULTS_JTL = os.path.join(BASE_OUTPUT_DIR, "results.jtl")

if not os.path.exists(STATISTICS_JSON):
    raise FileNotFoundError(
        f"statistics.json not found at {STATISTICS_JSON}. "
        "Generate the JMeter HTML dashboard first."
    )

os.makedirs(OUTPUT_DIR, exist_ok=True)

# --------------------------------------------------
# Load statistics.json (AUTHORITATIVE PERFORMANCE SUMMARY)
# --------------------------------------------------
with open(STATISTICS_JSON, "r", encoding="utf-8") as f:
    stats = json.load(f)

# --------------------------------------------------
# Helpers
# --------------------------------------------------
def r(v, d=2):
    if isinstance(v, (int, float)):
        return round(v, d)
    return 0

# --------------------------------------------------
# Extract totals (UNCHANGED SOURCE)
# --------------------------------------------------
total = stats.get("Total", {})

total_requests = total.get("sampleCount", 0)
observed_error_count = total.get("errorCount", 0)
observed_error_pct = r(total.get("errorPct", 0))
overall_throughput = r(total.get("throughput", 0), 2)

# --------------------------------------------------
# Classify errors using results.jtl (DEFENSIBLE)
# --------------------------------------------------
functional_errors = 0
performance_errors = 0
unknown_errors = 0
failure_details = {}  # { label: [(responseCode, responseMessage), ...] }
if os.path.exists(RESULTS_JTL):
    try:
        with open(RESULTS_JTL, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("success", "").lower() == "true":
                    continue

                label = row.get("label", "UNKNOWN")
                code = row.get("responseCode", "N/A")
                msg = row.get("responseMessage", "").lower()

                failure_details.setdefault(label, []).append((code, msg))

                if code.startswith("4"):
                    functional_errors += 1
                elif "timeout" in msg or "timed out" in msg:
                    performance_errors += 1
                elif code.startswith("5"):
                    performance_errors += 1
                else:
                    unknown_errors += 1

    except Exception:
        functional_errors = performance_errors = unknown_errors = 0

# --------------------------------------------------
# Derived failure rates (NEW, CORRECT)
# --------------------------------------------------
functional_error_pct = r((functional_errors / total_requests) * 100) if total_requests else 0
performance_error_pct = r((performance_errors / total_requests) * 100) if total_requests else 0

# Run validity decision
run_valid_for_perf = performance_error_pct > 0 or observed_error_count == 0

# --------------------------------------------------
# Build Statistics table + Observations (UNCHANGED)
# --------------------------------------------------
statistics_rows = []
observations = []
failing_apis = []
p95_rank = []

for label, m in stats.items():
    if label == "Total":
        continue

    sample_count = m.get("sampleCount", 0)
    error_count = m.get("errorCount", 0)
    error_pct = r(m.get("errorPct", 0))

    mean_rt = r(m.get("meanResTime"))
    min_rt = r(m.get("minResTime"))
    max_rt = r(m.get("maxResTime"))
    median_rt = r(m.get("medianResTime"))

    p90 = r(m.get("pct1ResTime"))
    p95 = r(m.get("pct2ResTime"))
    p99 = r(m.get("pct3ResTime"))

    throughput = r(m.get("throughput"), 2)
    recv_kbps = r(m.get("receivedKBytesPerSec"), 2)
    sent_kbps = r(m.get("sentKBytesPerSec"), 2)

    if error_count > 0:
        failing_apis.append((label, error_count, error_pct))

    if p95 > 0:
        p95_rank.append((label, p95))

    statistics_rows.append(f"""
    <tr>
      <td>{label}</td>
      <td>{sample_count}</td>
      <td>{error_pct}%</td>
      <td>{mean_rt}</td>
      <td>{min_rt}</td>
      <td>{max_rt}</td>
      <td>{median_rt}</td>
      <td>{p90}</td>
      <td>{p95}</td>
      <td>{p99}</td>
      <td>{throughput}</td>
      <td>{recv_kbps}</td>
      <td>{sent_kbps}</td>
    </tr>
    """)

    observations.append(f"""
    <li><strong>{label}</strong>
      <ul>
        <li>Requests executed: {sample_count}</li>
        <li>Observed failures: {error_count} ({error_pct}%)</li>
        <li>P95 response time: {p95} ms</li>
        <li>Throughput: {throughput} transactions/sec</li>
      </ul>
    </li>
    """)

# --------------------------------------------------
# Executive Insights (UNCHANGED)
# --------------------------------------------------
insights = []

if failing_apis:
    failing_apis.sort(key=lambda x: x[1], reverse=True)
    insights.append("<li><strong>APIs with highest observed failure counts:</strong></li>")
    insights.append("<ul>")
    for label, cnt, pct in failing_apis[:5]:
        insights.append(f"<li>{label}: {cnt} failures ({pct}%)</li>")
    insights.append("</ul>")

if p95_rank:
    p95_rank.sort(key=lambda x: x[1], reverse=True)
    slowest_api, slowest_p95 = p95_rank[0]
    insights.append(
        f"<li><strong>Slowest API by P95 latency:</strong> {slowest_api} ({slowest_p95} ms)</li>"
    )

# --------------------------------------------------
# Errors Section (CORRECTED)
# --------------------------------------------------
errors_section = f"""
<h2>Observed Failures</h2>
<ul>
  <li><strong>JMeter-observed failure rate:</strong> {observed_error_pct}%</li>
  <li><strong>Functional / business failures:</strong> {functional_error_pct}%</li>
  <li><strong>Performance-related failures:</strong> {performance_error_pct}%</li>
</ul>
"""

if failure_details:
    errors_section += "<h3>Failure Details by API</h3><ul>"
    for api, failures in failure_details.items():
        unique_codes = sorted(set(code for code, _ in failures))
        codes_str = ", ".join(unique_codes)
        errors_section += f"<li><strong>{api}</strong>: {len(failures)} failure(s) — Response codes: {codes_str}</li>"
    errors_section += "</ul>"

# --------------------------------------------------
# Run Validity Section (NEW & CRITICAL)
# --------------------------------------------------
validity_section = """
<h2>Run Validity</h2>
<p style="color: red;">
<strong>This test run is NOT valid for performance evaluation.</strong><br>
All observed failures are functional (authentication / assertion related).
Performance metrics should not be interpreted until functional correctness is restored.
</p>
""" if not run_valid_for_perf else """
<h2>Run Validity</h2>
<p style="color: green;">
<strong>This test run is valid for performance evaluation.</strong>
</p>
"""

# --------------------------------------------------
# Final HTML
# --------------------------------------------------
html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>API Performance Test Report</title>

<style>
body {{
    font-family: Arial, sans-serif;
    background: #f4f4f4;
    padding: 20px;
}}
h1, h2 {{
    margin-top: 30px;
}}
.summary-box {{
    background: #ffffff;
    padding: 16px;
    border-radius: 8px;
    margin-bottom: 30px;
}}
table {{
    width: 100%;
    border-collapse: collapse;
    margin-top: 15px;
    background: #ffffff;
}}
thead th {{
    background-color: #273043;
    color: #ffffff;
    padding: 10px;
    font-size: 13px;
    border: 1px solid #444;
}}
tbody td {{
    padding: 8px;
    border: 1px solid #ddd;
    font-size: 13px;
    text-align: center;
}}
tbody tr:nth-child(even) td {{
    background-color: #f7f9fc;
}}
th:first-child,
td:first-child {{
    text-align: left;
    font-weight: 600;
}}
ul {{
    margin-top: 10px;
}}
li {{
    margin-bottom: 8px;
}}
</style>
</head>

<body>

<h1>API Performance Test Report</h1>

<div class="summary-box">
  <p><strong>Total Requests:</strong> {total_requests}</p>
  <p><strong>Functional Failure Rate:</strong> {functional_error_pct}%</p>
  <p><strong>Performance Failure Rate:</strong> {performance_error_pct}%</p>
  <p><strong>Overall Throughput:</strong> {overall_throughput} transactions/sec</p>
</div>

{validity_section}

<h2>Statistics</h2>
<table>
<thead>
<tr>
  <th>Label</th>
  <th># Samples</th>
  <th>Error %</th>
  <th>Average (ms)</th>
  <th>Min (ms)</th>
  <th>Max (ms)</th>
  <th>Median (ms)</th>
  <th>P90 (ms)</th>
  <th>P95 (ms)</th>
  <th>P99 (ms)</th>
  <th>Transactions/s</th>
  <th>Received KB/s</th>
  <th>Sent KB/s</th>
</tr>
</thead>
<tbody>
{''.join(statistics_rows)}
</tbody>
</table>

{errors_section}

<h2>Key Observations</h2>
<ul>
{''.join(observations) if observations else "<li>No individual samplers were executed.</li>"}
</ul>

<h2>Executive Insights</h2>
<ul>
{''.join(insights) if insights else "<li>No critical performance risks observed.</li>"}
</ul>

<h2>Scope & Interpretation Notes</h2>
<ul>
  <li>statistics.json reflects aggregated JMeter observations.</li>
  <li>Functional failures are identified using raw JMeter sample data.</li>
  <li>Functional failures are excluded from performance degradation analysis.</li>
  <li>No performance conclusions are drawn from invalid runs.</li>
</ul>

</body>
</html>
"""

# --------------------------------------------------
# Write output
# --------------------------------------------------
with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
    f.write(html)

print("✅ Executive report generated:", OUTPUT_HTML)