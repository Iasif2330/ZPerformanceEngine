import json
import sys
import os

# --------------------------------------------------
# Inputs
# --------------------------------------------------
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
# Load JMeter statistics.json (SOURCE OF TRUTH)
# --------------------------------------------------
with open(STATISTICS_JSON) as f:
    stats = json.load(f)

# --------------------------------------------------
# Helpers
# --------------------------------------------------
def r(v, d=2):
    return round(v, d) if isinstance(v, (int, float)) else v

# --------------------------------------------------
# Prepare data
# --------------------------------------------------
total = stats.get("Total", {})
rows_html = []
observations = []

total_error_count = total.get("errorCount", 0)

# --------------------------------------------------
# Build Statistics table (JMeter parity)
# --------------------------------------------------
for label, m in stats.items():
    if label == "Total":
        continue

    rows_html.append(f"""
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

    # Executive-level observation
    if m.get("errorCount", 0) == 0:
        observations.append(
            f"<li><strong>{label}</strong>: No errors observed. "
            "Response times and throughput remained stable under test load.</li>"
        )
    else:
        observations.append(
            f"<li><strong>{label}</strong>: Errors were observed during execution. "
            "Further investigation is recommended.</li>"
        )

# --------------------------------------------------
# Conditional Errors section (executive-safe)
# --------------------------------------------------
error_section = ""
if total_error_count > 0:
    error_section = f"""
<h2>Errors Observed</h2>
<p>
A total of <strong>{total_error_count}</strong> request failures
({r(total.get('errorPct', 0))}%) were observed during test execution.
</p>
<p>
Errors are summarized at a high level here. Detailed error diagnostics
are available in the full JMeter HTML dashboard.
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

th {{
    background: #273043;
    color: #ffffff;
    padding: 10px;
    font-size: 13px;
}}

td {{
    padding: 8px;
    border-bottom: 1px solid #ddd;
    font-size: 13px;
    text-align: center;
}}

th:first-child,
td:first-child {{
    text-align: left;
}}

ul {{
    margin-top: 10px;
}}

li {{
    margin-bottom: 6px;
}}
</style>
</head>

<body>

<h1>API Performance Test Report</h1>

<div class="summary-box">
  <p><strong>Total Requests:</strong> {total.get('sampleCount', 0)}</p>
  <p><strong>Error Rate:</strong> {r(total.get('errorPct', 0))}%</p>
  <p><strong>Overall Throughput:</strong> {r(total.get('throughput', 0), 2)} transactions/sec</p>
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
{''.join(rows_html)}
</tbody>
</table>

{error_section}

<h2>Key Observations</h2>
<ul>
{''.join(observations)}
</ul>

</body>
</html>
"""

# --------------------------------------------------
# Write output
# --------------------------------------------------
with open(OUTPUT_HTML, "w") as f:
    f.write(html)

print("✅ Executive report generated:", OUTPUT_HTML)