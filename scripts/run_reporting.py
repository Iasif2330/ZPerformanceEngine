#!/usr/bin/env python3
"""
Entry point for the new AI-powered reporting system.

Usage:
    python3 scripts/run_reporting.py <workspace_path>

Example:
    python3 scripts/run_reporting.py /Users/Shared/ZPerformanceEngine
"""

import sys
import os
from pathlib import Path

# Add repo to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from reporting.orchestrator import ReportOrchestrator


def main():
    if len(sys.argv) != 2:
        print("Usage: run_reporting.py <workspace_path>")
        print("Example: run_reporting.py /Users/Shared/ZPerformanceEngine")
        sys.exit(1)

    workspace_path = sys.argv[1]

    print("\n" + "=" * 60)
    print("PERFORMANCE REPORTING ENGINE (AI-POWERED)")
    print("=" * 60)
    print(f"Workspace: {workspace_path}\n")

    try:
        # Check if output directory exists
        output_dir = Path(workspace_path) / "output"
        if not output_dir.exists():
            print("⚠️  Output directory not found. Test may not have run.")
            print(f"   Expected: {output_dir}")
            print("   Creating minimal report...\n")

        orchestrator = ReportOrchestrator(workspace_path)
        report = orchestrator.generate()

        print("\n" + "=" * 60)
        print("✅ REPORTING COMPLETE")
        print("=" * 60)
        print(f"Report validity: {report.is_valid}")
        print(f"Total requests: {report.run_metrics.total_requests if report.run_metrics else 'N/A'}")
        print(f"Regression label: {report.regression_label}")
        print(f"Executive summary generated: {report.executive_summary is not None}")
        print(f"API summaries generated: {len(report.api_summaries or {})}")
        print(f"Infrastructure summary generated: {report.infra_summary is not None}")
        print()

        if report.run_metrics.total_requests == 0:
            print("⚠️  No test data found. Ensure:")
            print("   1. JMeter test ran successfully")
            print("   2. statistics.json was generated")
            print("   3. Reasoning report was generated")
            print()

    except Exception as e:
        print(f"\n❌ REPORTING FAILED: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
