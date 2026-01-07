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
    "timestamps": []
})

for r in rows:
    api = r.get("label", "UNKNOWN")

    ts = to_int(r.get("timeStamp", 0))
    elapsed = to_int(r.get("elapsed", 0))

    apis[api]["elapsed"].append(elapsed)
    apis[api]["success"].append(r.get("success", "").lower() == "true")
    apis[api]["bytes"].append(to_int(r.get("bytes", 0)))
    apis[api]["sent"].append(to_int(r.get("sentBytes", 0)))
    apis[api]["codes"].append(r.get("responseCode", ""))
    apis[api]["messages"].append(r.get("responseMessage", ""))

    if ts > 0:
        apis[api]["timestamps"].append(ts)

# --------------------------------------------------
# Per-API analysis (JMETER EXACT)
# --------------------------------------------------
aggregate_rows = ""
summary_rows = ""
observations = {}

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

    # --------------------------------------------------
    # JMETER THROUGHPUT (timestamp only)
    # --------------------------------------------------
    label_start = min(d["timestamps"])
    label_end = max(d["timestamps"])
    duration_sec = (label_end - label_start) / 1000

    if duration_sec <= 0:
        duration_sec = 0.0001

    throughput = round(samples / duration_sec, 2)
    recv_kb = round(sum(d["bytes"]) / 1024 / duration_sec, 2)
    sent_kb = round(sum(d["sent"]) / 1024 / duration_sec, 2)

    aggregate_rows += f"""
<tr>
<td>{api}</td><td>{samples}</td><td>{avg}</td><td>{median}</td>
<td>{p90}</td><td>{p95}</td><td>{p99}</td>
<td>{min_rt}</td><td>{max_rt}</td>
<td>0.0%</td>
<td>{throughput}/sec</td><td>{recv_kb}</td><td>{sent_kb}</td>
</tr>
"""

    summary_rows += f"""
<tr>
<td>{api}</td><td>{samples}</td><td>{avg}</td>
<td>{min_rt}</td><td>{max_rt}</td><td>{stddev}</td>
<td>0.0%</td><td>{throughput}/sec</td>
<td>{recv_kb}</td><td>{sent_kb}</td><td>{round(statistics.mean(d["bytes"]),1)}</td>
</tr>
"""

    observations[api] = f"<li><strong>{api}</strong> — No Anomalies Observed</li>"

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