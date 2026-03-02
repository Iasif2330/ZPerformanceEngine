# scripts/test_reporting.py
import argparse
from reporting.orchestrator import ReportOrchestrator

parser = argparse.ArgumentParser()
parser.add_argument("--workspace", default=".")
args = parser.parse_args()

orch = ReportOrchestrator(args.workspace)
report = orch.generate()

print(report)