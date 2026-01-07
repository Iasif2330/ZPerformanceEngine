import csv
import sys
import os
import statistics
from collections import defaultdict, Counter

# --------------------------------------------------
# Inputs
# --------------------------------------------------
RESULTS_JTL = sys.argv[1]
OUTPUT_DIR = sys.argv[2]
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

def percentile(data, p):
    if not data:
        return 0
    data = sorted(data)
    k = (len(data) - 1) * (p / 100)
    f = int(k)
    c = min(f + 1, len(data) - 1)
    if f == c:
        return data[f]
    return round(data[f] + (data[c] - data[f]) * (k - f))

# --------------------------------------------------
# Load JTL
# --------------------------------------------------
with open(RESULTS_JTL, newline="") as f:
    rows = list(csv.DictReader(f))

TOTAL_REQUESTS = len(rows)
LOW_SAMPLE = TOTAL_REQUESTS < LOW_SAMPLE_THRESHOLD

# --------------------------------------------------
# GLOBAL TEST DURATION (JMeter semantics)
# --------------------------------------------------
all_timestamps = [
    to_int(r.get("timeStamp", 0))
    for r in rows
    if r.get("timeStamp")
]

GLOBAL_DURATION_SEC = (
    (max(all_timestamps) - min(all_timestamps)) / 1000
    if all_timestamps else 1
)

# --------------------------------------------------
# Group by label
# --------------------------------------------------
apis = defaultdict(lambda: {
    "elapsed": [],
    "success": [],
    "bytes": [],
    "sent": [],
    "codes": [],
    "messages": []
})

for r in rows:
    api = r.get("label", "UNKNOWN")
    apis[api]["elapsed"].append(to_int(r.get("elapsed", 0)))
    apis[api]["success"].append(r.get("success", "").lower() == "true")
    apis[api]["bytes"].append(to_int(r.get("bytes", 0)))
    apis[api]["sent"].append(to_int(r.get("sentBytes", 0)))
    apis[api]["codes"].append(r.get("responseCode", ""))
    apis[api]["messages"].append(r.get("responseMessage", ""))

# --------------------------------------------------
# Analysis containers
# --------------------------------------------------
aggregate_rows = ""
summary_rows = ""
observations = {}

total_effective_failures = 0
critical_requests = 0
critical_failures = 0
apis_with_errors = 0

# --------------------------------------------------
# Per-API analysis (MATCHES JMETER)
# --------------------------------------------------
for api, d in apis.items():
    samples = len(d["elapsed"])
    if samples == 0:
        continue

    elapsed = d["elapsed"]

    avg = round(statistics.mean(elapsed))
    median = percentile(elapsed, 50)
    p90 = percentile(elapsed, 90)
    p95 = percentile(elapsed, 95)
    p99 = percentile(elapsed, 99)
    min_rt = min(elapsed)
    max_rt = max(elapsed)
    stddev = round(statistics.pstdev(elapsed), 3)

    failures = sum(1 for s in d["success"] if not s)

    effective_failures = sum(
        1 for s, c in zip(d["success"], d["codes"])
        if not s and c not in SUPPRESS_ERROR_CODES
    )

    effective_error_rate = round((effective_failures / samples) * 100, 3)

    total_effective_failures += effective_failures

    if api not in NON_EVALUABLE_LABELS:
        critical_requests += samples
        critical_failures += effective_failures

    if effective_failures > 0:
        apis_with_errors += 1

    # --------------------------------------------------
    # JMETER-EXACT THROUGHPUT & NETWORK RATE
    # --------------------------------------------------
    throughput = round(samples / GLOBAL_DURATION_SEC, 2)
    recv_kb = round(sum(d["bytes"]) / 1024 / GLOBAL_DURATION_SEC, 2)
    sent_kb = round(sum(d["sent"]) / 1024 / GLOBAL_DURATION_SEC, 2)

    # --------------------------------------------------
    # Error breakdown
    # --------------------------------------------------
    error_counter = Counter()
    for code, msg, success in zip(d["codes"], d["messages"], d["success"]):
        if not success and code:
            error_counter[f"{code} {msg}"] += 1

    error_details = ""
    if error_counter:
        error_details = "<ul>" + "".join(
            f"<li>{k} ({v}x)</li>" for k, v in error_counter.items()
        ) + "</ul>"

    # --------------------------------------------------
    # Status & observations
    # --------------------------------------------------
    if api in NON_EVALUABLE_LABELS:
        status = "Not Evaluated"
        text = (
            "This endpoint represents a technical or consent-related flow and was "
            "intentionally excluded from request-level evaluation."
        )
    elif failures == 0:
        status = "No Anomalies Observed"
        text = (
            "All requests completed successfully with stable response times "
            "and no observed errors."
        )
    elif effective_failures == 0:
        status = "Functional Errors Observed"
        text = (
            "Request failures were limited to authentication or authorization responses."
            + error_details
        )
    else:
        status = "Errors Observed"
        text = (
            "Request failures were observed under test load."
            + error_details
        )

    observations[api] = f"""
<li class="obs-item">
  <div class="obs-api">{api}</div>
  <div class="obs-status"><strong>Status:</strong> {status}</div>
  <div class="obs-text">{text}</div>
</li>
"""

    aggregate_rows += f"""
<tr>
<td>{api}</td><td>{samples}</td><td>{avg}</td><td>{median}</td>
<td>{p90}</td><td>{p95}</td><td>{p99}</td>
<td>{min_rt}</td><td>{max_rt}</td>
<td>{effective_error_rate}%</td>
<td>{throughput}/sec</td><td>{recv_kb}</td><td>{sent_kb}</td>
</tr>
"""

    summary_rows += f"""
<tr>
<td>{api}</td><td>{samples}</td><td>{avg}</td>
<td>{min_rt}</td><td>{max_rt}</td><td>{stddev}</td>
<td>{effective_error_rate}%</td><td>{throughput}/sec</td>
<td>{recv_kb}</td><td>{sent_kb}</td><td>{round(statistics.mean(d["bytes"]),3)}</td>
</tr>
"""

# --------------------------------------------------
# Totals
# --------------------------------------------------
TOTAL_ERROR_RATE = round((total_effective_failures / TOTAL_REQUESTS) * 100, 3) if TOTAL_REQUESTS else 0
CRITICAL_ERROR_RATE = (
    round((critical_failures / critical_requests) * 100, 3)
    if critical_requests else 0
)

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
    background: #f4f4f4;
    font-family: Arial, sans-serif;
    padding: 20px;
}}
.summary-box {{
    background: #fff;
    padding: 18px;
    border-radius: 10px;
    margin-bottom: 30px;
}}
table {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 40px;
}}
th {{
    background: #273043;
    color: #fff;
    padding: 10px;
}}
td {{
    padding: 8px;
    border-bottom: 1px solid #ddd;
    text-align: center;
}}
th:first-child,
td:first-child {{
    text-align: left;
}}
</style>
</head>
<body>

<h1>API Performance Test Report</h1>

<div class="summary-box">
<p><strong>Total requests:</strong> {TOTAL_REQUESTS}</p>
<p><strong>Effective error rate:</strong> {TOTAL_ERROR_RATE}%</p>
<p><strong>Critical API error rate:</strong> {CRITICAL_ERROR_RATE}%</p>
{indicative_notice}

<h4>Key Observations</h4>
<ul>
{''.join(observations.values())}
</ul>
</div>

<h2>Aggregate Metrics</h2>
<table>
<tr>
<th>Label</th><th># Samples</th><th>Avg</th><th>Median</th>
<th>P90</th><th>P95</th><th>P99</th>
<th>Min</th><th>Max</th><th>Error %</th>
<th>Throughput</th><th>Recv KB/s</th><th>Sent KB/s</th>
</tr>
{aggregate_rows}
</table>

<h2>Summary Metrics</h2>
<table>
<tr>
<th>Label</th><th># Samples</th><th>Avg</th>
<th>Min</th><th>Max</th><th>Std Dev</th>
<th>Error %</th><th>Throughput</th>
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