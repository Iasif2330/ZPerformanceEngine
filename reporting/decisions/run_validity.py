# reporting/decisions/run_validity.py
from reporting.models.report_model import ReportModel


class RunValidity:
    @staticmethod
    def evaluate(report: ReportModel) -> bool:
        if report.run_metrics is None:
            return False

        if report.run_metrics.total_requests <= 0:
            return False

        return True