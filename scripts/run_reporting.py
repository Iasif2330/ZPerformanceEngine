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
        orchestrator = ReportOrchestrator(workspace_path)
        report = orchestrator.generate()

        print("\n" + "=" * 60)
        print("✅ REPORTING COMPLETE")
        print("=" * 60)
        print(f"Report validity: {report.is_valid}")
        print(f"Regression label: {report.regression_label}")
        print(f"Executive summary generated: {report.executive_summary is not None}")
        print(f"API summaries generated: {len(report.api_summaries or {})}")
        print(f"Infrastructure summary generated: {report.infra_summary is not None}")

    except Exception as e:
        print(f"\n❌ REPORTING FAILED: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
