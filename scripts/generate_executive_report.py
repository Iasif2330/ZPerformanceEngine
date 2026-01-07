import csv
import json
import sys
import os
import statistics
from collections import defaultdict, Counter

# --------------------------------------------------
# Inputs
# --------------------------------------------------
RESULTS_JTL = sys.argv[1]
OUTPUT_DIR = sys.argv[2]
STATS_JSON = os.path.join(OUTPUT_DIR, "statistics.json")
OUTPUT_HTML = os.path.join(OUTPUT_DIR, "index.html")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# --------------------------------------------------
# Config
# --------------------------------------------------
SUPPRESS_ERROR_CODES = {"401", "403"}
NON_EVALUABLE_LABELS = {"accepttac"}
LOW_SAMPLE_THRESHOLD = 50

# --------------------------------------------------
# Helpers
# --------------------------------------------------
def to_int(v):
    try:
        return int(float(v))
    except:
        return 0

# --------------------------------------------------
# Load statistics.json (SOURCE OF TRUTH)
# --------------------------------------------------
if not os.path.exists(STATS_JSON):
    raise FileNotFoundError(
        f"statistics.json not found at {STATS_JSON}. "
        "Run JMeter HTML report generation first."
    )

with open(STATS_JSON) as f:
    stats = json.load(f)

# --------------------------------------------------
# Load JTL (for error breakdown only)
# --------------------------------------------------
with open(RESULTS_JTL, newline="") as f:
    jtl_rows = list(csv.DictReader(f))

TOTAL_REQUESTS = len(jtl_rows)
LOW_SAMPLE = TOTAL_REQUESTS < LOW_SAMPLE_THRESHOLD

# --------------------------------------------------
# Group JTL errors by label
# --------------------------------------------------
errors_by_api = defaultdict(list)

for r in jtl_rows:
    api = r.get("label", "UNKNOWN")
    success = r.get("success", "").lower() == "true"
    code = r.get("responseCode", "")
    msg = r.get("responseMessage", "")

    if not success and code and code not in SUPPRESS_ERROR_CODES:
        errors_by_api[api].append(f"{code} {msg}")

# --------------------------------------------------
# HTML sections
# --------------------------------------------------
aggregate_rows = ""
summary_rows = ""
observations = {}

apis_with_errors = 0

# --------------------------------------------------
# Per-API (statistics.json driven)
# --------------------------------------------------
for api, s in stats.items():
    if api == "Total":
        continue

    samples = s["sampleCount"]

    # Response times
    avg = round(s["meanResTime"])
    median = round(s["medianResTime"])
    p90 = round(s["pct1ResTime"])
    p95 = round(s["pct2ResTime"])
    p99 = round(s["pct3ResTime"])
    min_rt = round(s["minResTime"])
    max_rt = round(s["maxResTime"])
    stddev = round(statistics.pstdev([min_rt, max_rt]), 3)

    # Error %
    error_pct = round(s["errorPct"], 2)

    # Throughput & network (EXACT JMETER)
    throughput = round(s["throughput"], 2)
    recv_kb = round(s["receivedKBytesPerSec"], 2)
    sent_kb = round(s["sentKBytesPerSec"], 2)
    avg_bytes = round((recv_kb * 1024) / throughput, 1) if throughput > 0 else 0

    # Error breakdown
    error_counter = Counter(errors_by_api.get(api, []))
    error_details = ""
    if error_counter:
        apis_with_errors += 1
        error_details = "<ul>" + "".join(
            f"<li>{k} ({v}x)</li>" for k, v in error_counter.items()
        ) + "</ul>"

    # Status
    if api in NON_EVALUABLE_LABELS:
        status = "Not Evaluated"
        text = "This endpoint was intentionally excluded from evaluation."
    elif s["errorCount"] == 0:
        status = "No Anomalies Observed"
        text = "All requests completed successfully."
    else:
        status = "Errors Observed"
        text = "Request failures were observed." + error_details

    observations[api] = f"""
<li>
  <strong>{api}</strong> — {status}
  <div>{text}</div>
</li>
"""

    # Aggregate table
    aggregate_rows += f"""
<tr>
<td>{api}</td><td>{samples}</td><td>{avg}</td><td>{median}</td>
<td>{p90}</td><td>{p95}</td><td>{p99}</td>
<td>{min_rt}</td><td>{max_rt}</td>
<td>{error_pct}%</td>
<td>{throughput}/sec</td><td>{recv_kb}</td><td>{sent_kb}</td>
</tr>
"""

    # Summary table
    summary_rows += f"""
<tr>
<td>{api}</td><td>{samples}</td><td>{avg}</td>
<td>{min_rt}</td><td>{max_rt}</td><td>{stddev}</td>
<td>{error_pct}%</td><td>{throughput}/sec</td>
<td>{recv_kb}</td><td>{sent_kb}</td><td>{avg_bytes}</td>
</tr>
"""

# --------------------------------------------------
# Totals (from statistics.json)
# --------------------------------------------------
total_stats = stats["Total"]
TOTAL_ERROR_RATE = round(total_stats["errorPct"], 2)

indicative_notice = ""
if LOW_SAMPLE:
    indicative_notice = (
        f"<p><strong>⚠ Indicative Results:</strong> "
        f"Fewer than {LOW_SAMPLE_THRESHOLD} total samples were collected.</p>"
    )

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
    padding: 20px;
    background: #f4f4f4;
}}
table {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 30px;
}}
th {{
    background: #273043;
    color: #fff;
    padding: 8px;
}}
td {{
    padding: 6px;
    border-bottom: 1px solid #ccc;
    text-align: center;
}}
th:first-child, td:first-child {{
    text-align: left;
}}
</style>
</head>
<body>

<h1>API Performance Test Report</h1>

<p><strong>Total requests:</strong> {TOTAL_REQUESTS}</p>
<p><strong>Effective error rate:</strong> {TOTAL_ERROR_RATE}%</p>

{indicative_notice}

<h3>Key Observations</h3>
<ul>{''.join(observations.values())}</ul>

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
<th>Min</th><th>Max</th><th>StdDev</th>
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