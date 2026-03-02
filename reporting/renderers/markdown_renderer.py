class MarkdownRenderer:
    def render(self, report, output_path):
        lines = []
        lines.append(f"# Performance Report ({report.context.environment})")
        lines.append(f"**Regression:** {report.regression_label}")
        lines.append("")

        if report.executive_summary:
            lines.append("## Executive Summary")
            lines.append(report.executive_summary)
            lines.append("")

        lines.append("## Key Metrics")
        lines.append(f"- P95 latency: {report.run_metrics.p95_ms} ms")
        lines.append(f"- Throughput: {report.run_metrics.throughput_rps} rps")
        lines.append(f"- Error rate: {report.run_metrics.error_rate_pct}%")

        output_path.write_text("\n".join(lines))