from pathlib import Path
from reporting.aggregators.baseline_aggregator import BaselineAggregator

path = Path("output/reasoning/reasoning_report.json")

agg = BaselineAggregator(path)
baseline = agg.aggregate()

print("\nBASELINE METRICS:")
print(baseline)