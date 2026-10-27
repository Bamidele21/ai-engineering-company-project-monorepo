"""Container bootstrap: register the work pool/deployment and run the worker."""

from __future__ import annotations

import subprocess
import sys
import time

POOL = "nexova-data-pipelines"


def _run(command: list[str], *, check: bool = True) -> None:
    subprocess.run(command, check=check)


def _wait_for_prefect() -> None:
    for attempt in range(60):
        result = subprocess.run(
            ["prefect", "work-pool", "ls"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return
        if attempt == 59:
            print("Prefect API did not become available", file=sys.stderr)
            result.check_returncode()
        time.sleep(2)


def main() -> int:
    _wait_for_prefect()
    _run(["prefect", "work-pool", "create", POOL, "--type", "process", "--overwrite"])
    _run(
        [
            "prefect",
            "deploy",
            "--all",
            "--no-prompt",
            "--prefect-file",
            "data/pipelines/prefect.yaml",
        ]
    )
    _run(["prefect", "worker", "start", "--pool", POOL, "--type", "process"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
