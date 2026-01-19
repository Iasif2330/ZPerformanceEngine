# reasoning/baselines/baseline_store.py

import json
from pathlib import Path
from statistics import median, mean
from datetime import datetime
from typing import Optional, List


class BaselineStore:
    """
    Stores and computes rolling or snapshot baselines for performance metrics.
    """

    def __init__(self, policy: dict, environment: str, load_profile: str):
        if not environment or not load_profile:
            raise ValueError("Environment and load_profile must be provided")

        self.policy = policy
        self.environment = environment
        self.load_profile = load_profile
        self.verbose = True

        self.storage_path = Path(policy["storage"]["path"]).resolve()
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self._validate_policy()

    # -------------------------
    # Public API
    # -------------------------

    def save_run(self, run_id: str, client_metrics: dict) -> str:
        ts_dt = datetime.utcnow()
        timestamp = ts_dt.isoformat(timespec="seconds").replace(":", "-")

        record = {
            "run_id": run_id,
            "timestamp": timestamp,
            "timestamp_epoch": ts_dt.timestamp(),
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
        baseline_type = self.policy["baseline"]["type"]

        if baseline_type == "rolling":
            return self._compute_rolling_baseline()

        if baseline_type == "snapshot":
            return self._load_snapshot_baseline()

        raise ValueError(f"Unsupported baseline type: {baseline_type}")

    # -------------------------
    # Internal helpers
    # -------------------------

    def _validate_policy(self):
        baseline = self.policy.get("baseline", {})
        rolling = baseline.get("rolling", {})
        retention = rolling.get("retention", {})

        max_snapshots = retention.get("max_snapshots")
        min_required = rolling.get("min_required")

        if max_snapshots and min_required:
            if max_snapshots < min_required + 1:
                raise ValueError(
                    "Invalid policy: retention.max_snapshots must be "
                    ">= min_required + 1 for rolling baseline"
                )

    def _compute_rolling_baseline(self) -> Optional[dict]:
        rolling = self.policy["baseline"]["rolling"]
        window_size = rolling["window_size"]
        min_required = rolling["min_required"]
        aggregation = rolling["aggregation"]

        snapshots = self._load_scoped_snapshots()
        total_available = len(snapshots)

        if total_available < min_required + 1:
            return None

        selected = snapshots[1 : window_size + 1]

        if len(selected) < min_required:
            return None

        print("\n[Baseline] Rolling baseline selected runs:")
        for s in selected:
            print(f"  - run_id={s['run_id']} timestamp={s['timestamp']}")

        metrics_with_ids = [
            (s["run_id"], s["client_metrics"]) for s in selected
        ]

        aggregated = self._aggregate(metrics_with_ids, aggregation)

        return {
            # Human / explainable view
            "metrics": aggregated,

            # 🔹 Numeric view for detectors (ONLY what is needed)
            "numeric": {
                "latency": {
                    "p95_ms": aggregated["latency"]["p95_ms"]["value"],
                },
                "errors": {
                    "error_rate_pct": aggregated["errors"]["error_rate_pct"]["value"],
                },
            },

            "meta": {
                "type": "rolling",
                "window_size": window_size,
                "aggregation": aggregation,
                "sample_count": len(metrics_with_ids),
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

        if (
            data.get("environment") != self.environment
            or data.get("load_profile") != self.load_profile
        ):
            raise ValueError("Snapshot baseline scope mismatch")

        print(f"\n[Baseline] Using snapshot baseline: {snapshot_name}")

        return {
            "metrics": data["client_metrics"],
            "numeric": {
                "latency": {
                    "p95_ms": data["client_metrics"]["latency"]["p95_ms"],
                },
                "errors": {
                    "error_rate_pct": data["client_metrics"]["errors"]["error_rate_pct"],
                },
            },
            "meta": {
                "type": "snapshot",
                "name": snapshot_name,
                "sample_count": 1,
            },
        }

    def _load_scoped_snapshots(self) -> List[dict]:
        snapshots = []

        for path in self.storage_path.glob("*.json"):
            try:
                with path.open() as f:
                    data = json.load(f)
            except Exception:
                continue

            if (
                data.get("environment") == self.environment
                and data.get("load_profile") == self.load_profile
            ):
                data["_filename"] = path.name

                if "timestamp_epoch" in data:
                    data["_sort_ts"] = data["timestamp_epoch"]
                else:
                    try:
                        date, time = data["timestamp"].split("T")
                        time = time.replace("-", ":")
                        data["_sort_ts"] = datetime.fromisoformat(
                            f"{date}T{time}"
                        ).timestamp()
                    except Exception:
                        data["_sort_ts"] = 0

                snapshots.append(data)

        snapshots.sort(key=lambda x: x["_sort_ts"], reverse=True)
        return snapshots

    def _aggregate(self, metrics_with_ids: List[tuple], aggregation: str) -> dict:
        agg_fn = median if aggregation == "median" else mean

        def explain(label: str, values: List[tuple], should_print: bool) -> dict:
            numeric = [v for _, v in values]
            value = agg_fn(numeric)

            if should_print:
                print(f"\n[Baseline Evidence] {label}")
                for run_id, v in values:
                    print(f"  - {run_id}: {v}")
                print(f"  => {aggregation} = {value}")

            return {
                "aggregation": aggregation,
                "samples": [{"run_id": rid, "value": v} for rid, v in values],
                "value": value,
            }

        def collect(path):
            collected = []
            for run_id, m in metrics_with_ids:
                try:
                    collected.append((run_id, path(m)))
                except Exception:
                    continue
            return collected

        return {
            "latency": {
                "avg_ms": explain(
                    "latency.avg_ms",
                    collect(lambda m: m["latency"]["avg_ms"]),
                    should_print=False,   # 👈 hidden
                ),
                "p95_ms": explain(
                    "latency.p95_ms",
                    collect(lambda m: m["latency"]["p95_ms"]),
                    should_print=True,    # 👈 shown
                ),
                "p99_ms": explain(
                    "latency.p99_ms",
                    collect(lambda m: m["latency"]["p99_ms"]),
                    should_print=False,   # 👈 hidden
                ),
            },
            "throughput": {
                "tps": explain(
                    "throughput.tps",
                    collect(lambda m: m["throughput"]["tps"]),
                    should_print=False,   # 👈 hidden
                ),
            },
            "errors": {
                "error_rate_pct": explain(
                    "errors.error_rate_pct",
                    collect(lambda m: m["errors"]["error_rate_pct"]),
                    should_print=True,    # 👈 shown
                ),
            },
        }


    def _enforce_retention(self):
        retention_cfg = self.policy["baseline"]["rolling"].get("retention", {})
        max_snapshots = retention_cfg.get("max_snapshots")

        if not max_snapshots:
            return

        snapshots = self._load_scoped_snapshots()

        if len(snapshots) <= max_snapshots:
            return

        for snapshot in snapshots[max_snapshots:]:
            path = self.storage_path / snapshot["_filename"]
            if path.exists():
                print(f"[Retention] Deleting snapshot {path.name}")
                path.unlink()