from pathlib import Path
from reporting.aggregators.infra_aggregator import InfraAggregator

path = Path("output/reasoning/reasoning_report.json")

agg = InfraAggregator(path)
infra = agg.aggregate()

print("\nINFRA METRICS:")
print(infra)