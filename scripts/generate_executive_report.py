import csv
import sys
import os
import json
from collections import defaultdict

# --------------------------------------------------
# Inputs
# --------------------------------------------------
RESULTS_JTL = sys.argv[1]
OUTPUT_DIR = sys.argv[2]

DASHBOARD_DIR = os.path.join("output", "dashboard")
STATS_JSON = os.path.join(DASHBOARD_DIR, "statistics.json")
OUTPUT_HTML = os.path.join(OUTPUT_DIR, "index.html")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# --------------------------------------------------
# Validate statistics.json (SOURCE OF TRUTH)
# --------------------------------------------------
if not os.path.exists(STATS_JSON):
    raise FileNotFoundError(
        f"statistics.json not found at {STATS_JSON}. "
        "Run JMeter HTML report generation first (-g results.jtl -o output/dashboard)."
    )

with open(STATS_JSON) as f:
    stats = json.load(f)

# --------------------------------------------------
# Load JTL (ONLY for labels & observations)
# --------------------------------------------------
with open(RESULTS_JTL, newline="") as f:
    rows = list(csv.DictReader(f))

TOTAL_REQUESTS = len(rows)

# --------------------------------------------------
# Group failures by label (for observations only)
# --------------------------------------------------
failures_by_label = defaultdict(list)

for r in rows:
    label = r.get("label", "UNKNOWN")
    success = r.get("success", "").lower() == "true"
    if not success:
        code = r.get("responseCode", "")
        msg = r.get("responseMessage", "")
        failures_by_label[label].append(f"{code} {msg}".strip())

# --------------------------------------------------
# Build tables from statistics.json (AUTHORITATIVE)
# --------------------------------------------------
aggregate_rows = ""
summary_rows = ""
observations = ""

apis_with_errors = 0

for label, data in stats.items():
    if label == "Total":
        continue

    samples = data["sampleCount"]
    error_pct = round(data["errorPct"], 2)

    if data["errorCount"] > 0:
        apis_with_errors += 1

    aggregate_rows += f"""
    <tr>
      <td>{label}</td>
      <td>{samples}</td>
      <td>{round(data['meanResTime'])}</td>
      <td>{round(data['medianResTime'])}</td>
      <td>{round(data['pct1ResTime'])}</td>
      <td>{round(data['pct2ResTime'])}</td>
      <td>{round(data['pct3ResTime'])}</td>
      <td>{round(data['minResTime'])}</td>
      <td>{round(data['maxResTime'])}</td>
      <td>{error_pct}%</td>
      <td>{round(data['throughput'], 2)}/sec</td>
      <td>{round(data['receivedKBytesPerSec'], 2)}</td>
      <td>{round(data['sentKBytesPerSec'], 2)}</td>
    </tr>
    """

    summary_rows += f"""
    <tr>
      <td>{label}</td>
      <td>{samples}</td>
      <td>{round(data['meanResTime'])}</td>
      <td>{round(data['minResTime'])}</td>
      <td>{round(data['maxResTime'])}</td>
      <td>{round((data['pct3ResTime'] - data['pct1ResTime']), 2)}</td>
      <td>{error_pct}%</td>
      <td>{round(data['throughput'], 2)}/sec</td>
      <td>{round(data['receivedKBytesPerSec'], 2)}</td>
      <td>{round(data['sentKBytesPerSec'], 2)}</td>
      <td>-</td>
    </tr>
    """

    if label in failures_by_label:
        obs_text = "<br>".join(failures_by_label[label])
        status = "Errors Observed"
    else:
        obs_text = "All requests completed successfully."
        status = "No Anomalies Observed"

    observations += f"""
    <li>
      <strong>{label}</strong> — {status}
      <div>{obs_text}</div>
    </li>
    """

# --------------------------------------------------
# Totals
# --------------------------------------------------
total_stats = stats["Total"]

# --------------------------------------------------
# Final HTML
# --------------------------------------------------
html = f"""
<!DOCTYPE html>
<html>
<head>
  <title>API Performance Test Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; padding: 20px; }}
    table {{ width: 100%; border-collapse: collapse; margin-bottom: 30px; }}
    th, td {{ border: 1px solid #ccc; padding: 8px; text-align: center; }}
    th {{ background: #273043; color: #fff; }}
    th:first-child, td:first-child {{ text-align: left; }}
  </style>
</head>
<body>

<h1>API Performance Test Report</h1>

<p><strong>Total requests:</strong> {TOTAL_REQUESTS}</p>
<p><strong>Overall throughput:</strong> {round(total_stats['throughput'], 2)}/sec</p>
<p><strong>Overall error rate:</strong> {round(total_stats['errorPct'], 2)}%</p>

<h3>Key Observations</h3>
<ul>
{observations}
</ul>

<h2>Aggregate Metrics</h2>
<table>
<tr>
<th>Label</th><th>#</th><th>Avg</th><th>Median</th>
<th>P90</th><th>P95</th><th>P99</th>
<th>Min</th><th>Max</th><th>Error%</th>
<th>TPS</th><th>Recv KB/s</th><th>Sent KB/s</th>
</tr>
{aggregate_rows}
</table>

<h2>Summary Metrics</h2>
<table>
<tr>
<th>Label</th><th>#</th><th>Avg</th>
<th>Min</th><th>Max</th><th>Spread</th>
<th>Error%</th><th>TPS</th>
<th>Recv KB/s</th><th>Sent KB/s</th><th>Avg Bytes</th>
</tr>
{summary_rows}
</table>

</body>
</html>
"""

with open(OUTPUT_HTML, "w") as f:
    f.write(html)

print("✅ Executive report generated:", OUTPUT_HTML)