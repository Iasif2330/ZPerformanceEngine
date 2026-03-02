class RunAggregator:
    """
    Aggregates high-level run semantics.
    """

    @staticmethod
    def summarize(report):
        warnings = []

        if report.run_metrics.total_requests < 10:
            warnings.append("Very low sample count — results may be noisy.")

        if report.run_metrics.error_rate_pct > 0:
            warnings.append("Errors detected during run.")

        return {
            "warnings": warnings,
            "is_reliable": len(warnings) == 0
        }