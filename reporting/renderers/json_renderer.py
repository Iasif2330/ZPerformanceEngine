import json
from pathlib import Path

class JsonRenderer:
    def render(self, report, output_path: Path):
        output_path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "metadata": report.context.__dict__,
            "run_metrics": report.run_metrics.__dict__,
            "baseline": report.baseline_metrics.__dict__ if report.baseline_metrics else None,
            "regression_label": report.regression_label,
            "api_metrics": [a.__dict__ for a in report.api_metrics],
            "infra": report.infra_metrics.__dict__ if report.infra_metrics else None,
            "ai": {
                "executive_summary": report.executive_summary,
                "api_summaries": report.api_summaries,
                "infra_summary": report.infra_summary
            }
        }

        with open(output_path, "w") as f:
            json.dump(payload, f, indent=2, default=str)