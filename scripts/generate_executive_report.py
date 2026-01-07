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
# Group by label (JMETER SEMANTICS)
# --------------------------------------------------
apis = defaultdict(lambda: {
    "elapsed": [],
    "success": [],
    "bytes": [],
    "sent": [],
    "codes": [],
    "messages": [],
    "start_ts": [],
    "end_ts": []
})

for r in rows:
    api = r.get("label", "UNKNOWN")

    end_ts = to_int(r.get("timeStamp", 0))
    elapsed = to_int(r.get("elapsed", 0))
    start_ts = end_ts - elapsed

    apis[api]["elapsed"].append(elapsed)
    apis[api]["success"].append(r.get("success", "").lower() == "true")
    apis[api]["bytes"].append(to_int(r.get("bytes", 0)))
    apis[api]["sent"].append(to_int(r.get("sentBytes", 0)))
    apis[api]["codes"].append(r.get("responseCode", ""))
    apis[api]["messages"].append(r.get("responseMessage", ""))

    if start_ts > 0 and end_ts > 0:
        apis[api]["start_ts"].append(start_ts)
        apis[api]["end_ts"].append(end_ts)

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
# Per-API analysis (EXACT JMETER LOGIC)
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
    # JMETER-EXACT THROUGHPUT WINDOW
    # --------------------------------------------------
    label_start = min(d["start_ts"])
    label_end = max(d["end_ts"])
    duration_sec = (label_end - label_start) / 1000

    # Safety only for pathological data
    if duration_sec <= 0:
        duration_sec = 0.0001

    throughput = round(samples / duration_sec, 2)
    recv_kb = round(sum(d["bytes"]) / 1024 / duration_sec, 2)
    sent_kb = round(sum(d["sent"]) / 1024 / duration_sec, 2)

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
        text = "This endpoint was intentionally excluded from evaluation."
    elif failures == 0:
        status = "No Anomalies Observed"
        text = "All requests completed successfully."
    elif effective_failures == 0:
        status = "Functional Errors Observed"
        text = "Failures were limited to authentication/authorization." + error_details
    else:
        status = "Errors Observed"
        text = "Request failures were observed." + error_details

    observations[api] = f"""
<li>
  <strong>{api}</strong> — {status}
  <div>{text}</div>
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

# --------------------------------------------------
# HTML
# --------------------------------------------------
html = f"""
<!DOCTYPE html>
<html>
<head><title>API Performance Test Report</title></head>
<body>

<h1>API Performance Test Report</h1>

<p>Total requests: {TOTAL_REQUESTS}</p>
<p>Effective error rate: {TOTAL_ERROR_RATE}%</p>
<p>Critical API error rate: {CRITICAL_ERROR_RATE}%</p>

<h3>Key Observations</h3>
<ul>{''.join(observations.values())}</ul>

<h2>Aggregate Metrics</h2>
<table border="1">
<tr>
<th>Label</th><th>#</th><th>Avg</th><th>Median</th>
<th>P90</th><th>P95</th><th>P99</th>
<th>Min</th><th>Max</th><th>Error%</th>
<th>TPS</th><th>Recv KB/s</th><th>Sent KB/s</th>
</tr>
{aggregate_rows}
</table>

<h2>Summary Metrics</h2>
<table border="1">
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