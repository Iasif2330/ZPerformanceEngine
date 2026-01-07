import json
import sys
import os
from collections import Counter

# --------------------------------------------------
# Inputs
# --------------------------------------------------
if len(sys.argv) != 3:
    raise SystemExit(
        "Usage: generate_executive_report.py <statistics.json> <output_dir>"
    )

STATISTICS_JSON = sys.argv[1]
OUTPUT_DIR = sys.argv[2]
OUTPUT_HTML = os.path.join(OUTPUT_DIR, "index.html")

if not os.path.exists(STATISTICS_JSON):
    raise FileNotFoundError(
        f"statistics.json not found at {STATISTICS_JSON}. "
        "Generate the JMeter HTML dashboard first."
    )

os.makedirs(OUTPUT_DIR, exist_ok=True)

# --------------------------------------------------
# Load statistics.json (AUTHORITATIVE SOURCE)
# --------------------------------------------------
with open(STATISTICS_JSON, "r", encoding="utf-8") as f:
    stats = json.load(f)

# --------------------------------------------------
# Helpers
# --------------------------------------------------
def r(v, d=2):
    return round(v, d) if isinstance(v, (int, float)) else v

# --------------------------------------------------
# Error classification rules (LOCKED)
# --------------------------------------------------
FUNCTIONAL_ERROR_CODES = {"401", "403", "404"}

# --------------------------------------------------
# Extract totals
# --------------------------------------------------
total = stats.get("Total", {})

total_requests = total.get("sampleCount", 0)
observed_error_count = total.get("errorCount", 0)
observed_error_pct = r(total.get("errorPct", 0))
overall_throughput = r(total.get("throughput", 0), 2)

# --------------------------------------------------
# Build Statistics table + Observations
# --------------------------------------------------
statistics_rows = []
observations = []

# Track error classification
functional_errors = Counter()
performance_errors = Counter()

for label, m in stats.items():
    if label == "Total":
        continue

    # -----------------------------
    # Statistics table row
    # -----------------------------
    statistics_rows.append(f"""
    <tr>
      <td>{label}</td>
      <td>{m['sampleCount']}</td>
      <td>{r(m['errorPct'])}%</td>
      <td>{r(m['meanResTime'])}</td>
      <td>{r(m['minResTime'])}</td>
      <td>{r(m['maxResTime'])}</td>
      <td>{r(m['medianResTime'])}</td>
      <td>{r(m['pct1ResTime'])}</td>
      <td>{r(m['pct2ResTime'])}</td>
      <td>{r(m['pct3ResTime'])}</td>
      <td>{r(m['throughput'], 2)}</td>
      <td>{r(m['receivedKBytesPerSec'], 2)}</td>
      <td>{r(m['sentKBytesPerSec'], 2)}</td>
    </tr>
    """)

    error_count = m.get("errorCount", 0)

    # -----------------------------
    # Quantitative Key Observations
    # -----------------------------
    obs_lines = [
        f"<li>Requests executed: {m['sampleCount']}.</li>",
        f"<li>Request failures: {error_count} ({r(m['errorPct'])}%).</li>",
        f"<li>P95 response time: {r(m['pct2ResTime'])} ms.</li>",
        f"<li>Observed throughput: {r(m['throughput'], 2)} transactions/sec.</li>",
    ]

    observations.append(f"""
    <li><strong>{label}</strong>
      <ul>
        {''.join(obs_lines)}
      </ul>
    </li>
    """)

# --------------------------------------------------
# Errors Section (CONDITIONAL, EXECUTIVE-SAFE)
# --------------------------------------------------
errors_section = ""

if observed_error_count > 0:
    errors_section = f"""
<h2>Errors Observed</h2>

<p>
A total of <strong>{observed_error_count}</strong> request failures were recorded,
representing <strong>{observed_error_pct}%</strong> of all requests executed during the test.
</p>

<p>
Observed failures include all client-observed request outcomes.
Functional errors (e.g., authentication or authorization failures) are
reported separately from performance-related failures.
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
  <p><strong>Observed Failure Rate:</strong> {observed_error_pct}%</p>
  <p><strong>Overall Throughput:</strong> {overall_throughput} transactions/sec</p>
</div>

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
{''.join(observations)}
</ul>

<h2>Scope & Interpretation Notes</h2>
<ul>
  <li>All metrics in this report are derived directly from JMeter <code>statistics.json</code>.</li>
  <li>Observed failures include all client-observed request outcomes.</li>
  <li>Functional errors (e.g., HTTP 401/403) are not indicative of system performance under load.</li>
  <li>No baselines, thresholds, or service-side metrics are applied.</li>
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