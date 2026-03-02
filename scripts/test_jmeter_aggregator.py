from pathlib import Path
from reporting.aggregators.jmeter_aggregator import JMeterAggregator

output_dir = Path("output")

agg = JMeterAggregator(output_dir)
api_metrics, run_metrics = agg.aggregate()

print("\nAPI METRICS:")
for api in api_metrics:
    print(api)

print("\nRUN METRICS:")
print(run_metrics)