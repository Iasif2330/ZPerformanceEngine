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
# Config (FINAL, INTENT-BASED)
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
rows = []
with open(RESULTS_JTL, newline="") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

TOTAL_REQUESTS = len(rows)
LOW_SAMPLE = TOTAL_REQUESTS < LOW_SAMPLE_THRESHOLD

timestamps = [to_int(r.get("timeStamp", 0)) for r in rows if r.get("timeStamp")]
duration_sec = max((max(timestamps) - min(timestamps)) / 1000, 1) if timestamps else 1

# --------------------------------------------------
# Group by API label
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

total_effective_errors = 0
critical_requests = 0
critical_errors = 0

# --------------------------------------------------
# Per-API analysis
# --------------------------------------------------
for api, d in apis.items():
    samples = len(d["elapsed"])
    elapsed = d["elapsed"]

    if samples == 0:
        continue

    avg = round(statistics.mean(elapsed))
    median = percentile(elapsed, 50)
    p90 = percentile(elapsed, 90)
    p95 = percentile(elapsed, 95)
    p99 = percentile(elapsed, 99)
    min_rt = min(elapsed)
    max_rt = max(elapsed)
    stddev = round(statistics.pstdev(elapsed), 2)

    failures = d["success"].count(False)
    suppressed = sum(1 for c in d["codes"] if c in SUPPRESS_ERROR_CODES)
    effective_errors = max(failures - suppressed, 0)
    effective_error_rate = round((effective_errors / samples) * 100, 2)

    total_effective_errors += effective_errors

    if api not in NON_EVALUABLE_LABELS:
        critical_requests += samples
        critical_errors += effective_errors

    recv_kb = round(sum(d["bytes"]) / 1024 / duration_sec, 2)
    sent_kb = round(sum(d["sent"]) / 1024 / duration_sec, 2)
    throughput = round(samples / duration_sec, 2)

    # --------------------------------------------------
    # Error breakdown (exact, JTL-backed)
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
    # Status & observation
    # --------------------------------------------------
    if api in NON_EVALUABLE_LABELS:
        status = "⚪ Not Evaluated"
        text = (
            "This endpoint represents a technical or consent flow and was "
            "intentionally excluded from performance evaluation."
        )
    elif failures > 0 and failures == suppressed:
        status = "🟡 Functional Failure"
        text = (
            "Authentication or authorization failures were observed. "
            "These are functional issues and NOT related to performance."
            + error_details
        )
    elif effective_errors > 0:
        status = "🔴 Performance Failure"
        text = (
            "Backend or network failures were observed impacting performance."
            + error_details
        )
    else:
        status = "🟢 Healthy"
        text = "Requests completed successfully with stable response times and no errors."

    observations[api] = f"""
<li class="obs-item">
  <div class="obs-api">{api}</div>
  <div class="obs-status">{status}</div>
  <div class="obs-text">{text}</div>
</li>
"""

    # --------------------------------------------------
    # Tables
    # --------------------------------------------------
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
<td>{recv_kb}</td><td>{sent_kb}</td><td>{round(statistics.mean(d["bytes"]),1)}</td>
</tr>
"""

# --------------------------------------------------
# Totals
# --------------------------------------------------
TOTAL_ERROR_RATE = round((total_effective_errors / TOTAL_REQUESTS) * 100, 2) if TOTAL_REQUESTS else 0
CRITICAL_ERROR_RATE = (
    round((critical_errors / critical_requests) * 100, 2)
    if critical_requests else 0
)

low_sample_notice = (
    f"<p><strong>⚠ Low sample size:</strong> This test contains fewer than "
    f"{LOW_SAMPLE_THRESHOLD} total samples. Findings are indicative.</p>"
    if LOW_SAMPLE else ""
)

# --------------------------------------------------
# Final HTML
# --------------------------------------------------
html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Performance Test Report</title>
<style>
body {{
    background: #f4f4f4;
    font-family: Arial, sans-serif;
    padding: 20px;
}}
.summary-box {{
    background: #fff;
    padding: 15px;
    border-radius: 10px;
    margin-bottom: 25px;
}}
table {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 40px;
    table-layout: fixed;
}}
th {{
    background: #273043;
    color: #fff;
    padding: 10px;
    font-size: 14px;
    text-align: center;
}}
td {{
    padding: 8px;
    border-bottom: 1px solid #ddd;
    font-size: 13px;
    text-align: center;
    vertical-align: middle;
}}
th:first-child,
td:first-child {{
    text-align: left;
}}
.obs-item {{ margin-bottom: 14px; }}
.obs-api {{ font-weight: bold; }}
.obs-status {{ margin-left: 8px; font-size: 13px; }}
.obs-text {{ margin-left: 20px; font-size: 13px; }}
</style>
</head>
<body>

<h1>API Performance Test Report</h1>

<div class="summary-box">
{low_sample_notice}
<p><strong>Total requests:</strong> {TOTAL_REQUESTS}</p>
<p><strong>Effective performance error rate:</strong> {TOTAL_ERROR_RATE}%</p>
<p><strong>Critical API error rate (excluding login/accepttac):</strong> {CRITICAL_ERROR_RATE}%</p>

<h4>Key Observations</h4>
<ul>
{''.join(observations.values())}
</ul>
</div>

<h2>Aggregate Report</h2>
<table>
<tr>
<th>Label</th><th># Samples</th><th>Avg</th><th>Median</th>
<th>P90</th><th>P95</th><th>P99</th>
<th>Min</th><th>Max</th><th>Error %</th>
<th>Throughput</th><th>Recv KB/s</th><th>Sent KB/s</th>
</tr>
{aggregate_rows}
</table>

<h2>Summary Report</h2>
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