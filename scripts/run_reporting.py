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


def check_pipeline_status(workspace_path):
    """Check if earlier pipeline stages completed successfully."""
    output_dir = Path(workspace_path) / "output"
    
    issues = []
    
    # Check if test ran
    if not (output_dir / "dashboard" / "statistics.json").exists() and \
       not (output_dir / "statistics.json").exists():
        issues.append("No statistics.json found - JMeter test did not run")
    
    # Check if reasoning completed
    if not (output_dir / "reasoning" / "reasoning_report.json").exists():
        issues.append("No reasoning_report.json found - reasoning engine did not complete")
    
    # Check functional test results
    if (output_dir / "functional_results.jtl").exists():
        try:
            with open(output_dir / "functional_results.jtl") as f:
                lines = f.readlines()
                # Count passing APIs
                passing = sum(1 for line in lines[1:] if "true" in line.lower())
                if passing == 0:
                    issues.append("Functional test: All APIs failed - load test was skipped")
        except:
            pass
    
    return issues


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

    # Check for known issues
    issues = check_pipeline_status(workspace_path)
    if issues:
        print("⚠️  PIPELINE STATUS ISSUES:")
        for issue in issues:
            print(f"   • {issue}")
        print()

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
        print(f"Environment: {report.context.environment}")
        print(f"Load Profile: {report.context.load_profile}")
        print(f"Report validity: {report.is_valid}")
        print(f"Total requests: {report.run_metrics.total_requests if report.run_metrics else 'N/A'}")
        print(f"APIs tested: {len(report.api_metrics)}")
        print(f"Regression label: {report.regression_label}")
        print()

        if report.run_metrics.total_requests == 0:
            print("⚠️  NO TEST DATA FOUND")
            print()
            print("This typically means:")
            print("   1. Functional test failed (all APIs rejected)")
            print("   2. Load test was skipped as a result")
            print("   3. JMeter never ran")
            print()
            print("NEXT STEPS:")
            print("   1. Check Stage 4C output for 'Eligible APIs'")
            print("   2. Review functional_results.jtl for API failures")
            print("   3. Verify target environment is reachable")
            print("   4. Check API credentials and payloads")
            print()

    except Exception as e:
        print(f"\n❌ REPORTING FAILED: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
