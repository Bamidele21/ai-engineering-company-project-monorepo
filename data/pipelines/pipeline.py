"""CLI entrypoint for the Nexova weekly performance pipeline.

Run from the repository root:

    python data/pipelines/pipeline.py
    python data/pipelines/pipeline.py --week-start 2026-10-19 --weeks 1
    python data/pipelines/pipeline.py --weeks 2 --trigger-type scheduled

The module also exposes ``weekly_office_program_performance_flow`` for the
Prefect deployment entrypoint ``pipeline.py:weekly_office_program_performance_flow``.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data.pipelines.weekly_office_program_performance.flow import (  # noqa: E402
    weekly_office_program_performance_flow,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compute the Nexova weekly office and programme performance report."
        )
    )
    parser.add_argument(
        "--week-start",
        type=date.fromisoformat,
        default=None,
        help="First target Monday (UTC ISO date). Defaults to the most recent "
        "completed week or the start of the requested range.",
    )
    parser.add_argument(
        "--weeks",
        type=int,
        default=None,
        help="Number of consecutive completed weeks (1-52). Defaults to 2 for "
        "a scheduled run and 1 when --week-start is supplied.",
    )
    parser.add_argument(
        "--trigger-type",
        choices=("scheduled", "manual", "backfill", "recompute"),
        default="scheduled",
        help="Why the run is happening (default: scheduled).",
    )
    parser.add_argument(
        "--requested-by",
        default=None,
        help="Sanitized operator identity for a manual/backfill run.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Adopt an API-created queued run id instead of creating a new row.",
    )
    parser.add_argument(
        "--fail-snapshot",
        action="store_true",
        help="Inject a failure in the optional eval snapshot for demonstration.",
    )
    parser.add_argument(
        "--resume-from",
        default=None,
        help="Resume a failed run: skip committed weeks and recompute the failed one.",
    )
    parser.add_argument(
        "--health-check",
        action="store_true",
        help="Run the freshness/silence/baseline health checks instead of the ETL.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.health_check:
        from data.pipelines.weekly_office_program_performance.monitoring import (
            weekly_performance_health_flow,
        )

        result = weekly_performance_health_flow()
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0

    weeks = args.weeks
    if weeks is None:
        weeks = 1 if args.week_start is not None else 2

    result = weekly_office_program_performance_flow(
        week_start=args.week_start,
        weeks=weeks,
        trigger_type=args.trigger_type,
        requested_by=args.requested_by,
        run_id=args.run_id,
        snapshot_failure_injection=args.fail_snapshot,
        resume_from=args.resume_from,
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
