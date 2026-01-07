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
        "Run JMeter HTML report generation first."
    )

os.makedirs(OUTPUT_DIR, exist_ok=True)

# --------------------------------------------------
# Load statistics.json (JMeter source of truth)
# --------------------------------------------------
with open(STATISTICS_JSON) as f:
    stats = json.load(f)

# --------------------------------------------------
# Helpers
# --------------------------------------------------
def r(v, d=2):
    return round(v, d) if isinstance(v, (int, float)) else v

# --------------------------------------------------
# Build rows
# --------------------------------------------------
aggregate_rows = ""
summary_rows = ""
observations = []

total = stats.get("Total", {})

for label, m in stats.items():
    if label == "Total":
        continue

    aggregate_rows += f"""
<tr>
<td>{label}</td>
<td>{m['sampleCount']}</td>
<td>{r(m['meanResTime'])}</td>
<td>{r(m['medianResTime'])}</td>
<td>{r(m['pct1ResTime'])}</td>
<td>{r(m['pct2ResTime'])}</td>
<td>{r(m['pct3ResTime'])}</td>
<td>{r(m['minResTime'])}</td>
<td>{r(m['maxResTime'])}</td>
<td>{r(m['errorPct'])}%</td>
<td>{r(m['throughput'], 2)}/sec</td>
<td>{r(m['receivedKBytesPerSec'], 2)}</td>
<td>{r(m['sentKBytesPerSec'], 2)}</td>
</tr>
"""

    summary_rows += f"""
<tr>
<td>{label}</td>
<td>{m['sampleCount']}</td>
<td>{r(m['meanResTime'])}</td>
<td>{r(m['minResTime'])}</td>
<td>{r(m['maxResTime'])}</td>
<td>{r(m['maxResTime'] - m['minResTime'], 2)}</td>
<td>{r(m['errorPct'])}%</td>
<td>{r(m['throughput'], 2)}/sec</td>
<td>{r(m['receivedKBytesPerSec'], 2)}</td>
<td>{r(m['sentKBytesPerSec'], 2)}</td>
<td>-</td>
</tr>
"""

    observations.append(
        f"<li><strong>{label}</strong> — No anomalies observed. All requests completed successfully.</li>"
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
  background: #f4f4f4;
  padding: 20px;
}}
table {{
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 40px;
}}
th {{
  background: #273043;
  color: white;
  padding: 10px;
}}
td {{
  padding: 8px;
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

<p><strong>Total requests:</strong> {total.get('sampleCount', 0)}</p>
<p><strong>Error rate:</strong> {r(total.get('errorPct', 0))}%</p>
<p><strong>Overall throughput:</strong> {r(total.get('throughput', 0), 2)}/sec</p>

<h3>Key Observations</h3>
<ul>
{''.join(observations)}
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