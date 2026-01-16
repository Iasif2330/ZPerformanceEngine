# reasoning/baselines/baseline_store.py

import json
from pathlib import Path
from statistics import median, mean
from datetime import datetime
from typing import Optional


class BaselineStore:
    """
    Stores and computes rolling or snapshot baselines for performance metrics.

    Baselines are scoped by:
      - environment
      - load_profile

    Rolling baseline semantics:
      - Uses a sliding window of the most recent completed runs
      - Excludes the current run to avoid self-poisoning
      - Window advances on every run

    Snapshots are:
      - auto-created per run
      - retention bounded
      - metadata-driven (filenames are for humans only)
    """

    def __init__(self, policy: dict, environment: str, load_profile: str):
        if not environment or not load_profile:
            raise ValueError("Environment and load_profile must be provided")

        self.policy = policy
        self.environment = environment
        self.load_profile = load_profile

        self.storage_path = Path(policy["storage"]["path"]).resolve()
        self.storage_path.mkdir(parents=True, exist_ok=True)

    # -------------------------
    # Public API
    # -------------------------

    def save_run(self, run_id: str, client_metrics: dict) -> str:
        """
        Save metrics for a single successful run and enforce retention.

        Returns:
            The snapshot filename created (for logging/debugging).
        """
        timestamp = datetime.utcnow().isoformat(timespec="seconds").replace(":", "-")

        record = {
            "run_id": run_id,
            "timestamp": timestamp,
            "environment": self.environment,
            "load_profile": self.load_profile,
            "client_metrics": client_metrics,
        }

        filename = (
            f"{timestamp}__"
            f"{self.environment}__"
            f"{self.load_profile}__"
            f"{run_id}.json"
        )

        path = self.storage_path / filename
        with path.open("w") as f:
            json.dump(record, f, indent=2)

        self._enforce_retention()
        return filename

    def load_baseline(self) -> Optional[dict]:
        """
        Load baseline according to policy.

        Returns:
            Baseline metrics dict or None (learning phase).
        """
        baseline_type = self.policy["baseline"]["type"]

        if baseline_type == "rolling":
            return self._compute_rolling_baseline()

        if baseline_type == "snapshot":
            return self._load_snapshot_baseline()

        raise ValueError(f"Unsupported baseline type: {baseline_type}")

    # -------------------------
    # Internal helpers
    # -------------------------

    def _compute_rolling_baseline(self) -> Optional[dict]:
        rolling = self.policy["baseline"]["rolling"]
        window_size = rolling["window_size"]
        min_required = rolling["min_required"]
        aggregation = rolling["aggregation"]

        snapshots = self._load_scoped_snapshots()
        total_available = len(snapshots)

        # Need at least (min_required + 1) snapshots
        # because the most recent snapshot is excluded
        if total_available < min_required + 1:
            return None

        # ------------------------------------------------
        # TRUE ROLLING WINDOW
        #
        # snapshots are sorted: newest → oldest
        # Exclude the most recent snapshot (current run)
        # and take the next `window_size` snapshots
        #
        # Example:
        # snapshots = [R5, R4, R3, R2]
        # selected  = [R4, R3]  (window_size = 2)
        # ------------------------------------------------
        selected = snapshots[1 : window_size + 1]

        if len(selected) < min_required:
            return None

        metrics = [s["client_metrics"] for s in selected]

        return {
            "metrics": self._aggregate(metrics, aggregation),
            "meta": {
                "type": "rolling",
                "window_size": window_size,
                "aggregation": aggregation,
                "sample_count": len(metrics),
                "snapshot_ids": [s["run_id"] for s in selected],
            },
        }

    def _load_snapshot_baseline(self) -> dict:
        snapshot_name = self.policy["baseline"]["snapshot"]["name"]
        if not snapshot_name:
            raise ValueError("Snapshot baseline requested but no snapshot name provided")

        path = self.storage_path / snapshot_name
        if not path.exists():
            raise FileNotFoundError(f"Snapshot baseline not found: {path}")

        with path.open() as f:
            data = json.load(f)

        return {
            "metrics": data["client_metrics"],
            "meta": {
                "type": "snapshot",
                "name": snapshot_name,
                "sample_count": 1,
            },
        }

    def _load_scoped_snapshots(self) -> list[dict]:
        """
        Load snapshots matching current environment & load profile.
        Sorted newest → oldest.
        """
        snapshots = []

        for path in self.storage_path.glob("*.json"):
            try:
                with path.open() as f:
                    data = json.load(f)
            except Exception:
                # Skip unreadable / corrupt files safely
                continue

            if (
                data.get("environment") == self.environment
                and data.get("load_profile") == self.load_profile
            ):
                data["_filename"] = path.name
                snapshots.append(data)

        snapshots.sort(key=lambda x: x["timestamp"], reverse=True)
        return snapshots

    def _aggregate(self, metrics: list[dict], aggregation: str) -> dict:
        """
        Aggregate metrics into a baseline using median or average.
        """
        agg_fn = median if aggregation == "median" else mean

        return {
            "latency": {
                "avg_ms": agg_fn([m["latency"]["avg_ms"] for m in metrics]),
                "p95_ms": agg_fn([m["latency"]["p95_ms"] for m in metrics]),
                "p99_ms": agg_fn([m["latency"]["p99_ms"] for m in metrics]),
            },
            "throughput": {
                "tps": agg_fn([m["throughput"]["tps"] for m in metrics]),
            },
            "errors": {
                "error_rate_pct": agg_fn(
                    [m["errors"]["error_rate_pct"] for m in metrics]
                ),
            },
        }

    def _enforce_retention(self):
        """
        Enforce max snapshot retention per environment + load profile.
        """
        retention_cfg = self.policy["baseline"]["rolling"].get("retention", {})
        max_snapshots = retention_cfg.get("max_snapshots")

        if not max_snapshots:
            return

        snapshots = self._load_scoped_snapshots()

        if len(snapshots) <= max_snapshots:
            return

        # snapshots are sorted newest → oldest
        # delete anything beyond max_snapshots
        for snapshot in snapshots[max_snapshots:]:
            path = self.storage_path / snapshot["_filename"]
            if path.exists():
                path.unlink()