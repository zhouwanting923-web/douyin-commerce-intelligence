#!/usr/bin/env python3
"""Record completion and elapsed time for the required manual PDF review."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _common import read_json, write_json


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def elapsed_seconds(started_at: str, finished_at: str) -> float:
    start = datetime.fromisoformat(started_at)
    finish = datetime.fromisoformat(finished_at)
    return round(max(0.0, (finish - start).total_seconds()), 3)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa", required=True, type=Path)
    parser.add_argument("--status", required=True, choices=["passed", "failed"])
    parser.add_argument("--reviewed", action="append", default=[])
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    qa_path = args.qa.resolve()
    data = read_json(qa_path)
    if data.get("errors") and args.status == "passed":
        raise SystemExit("Cannot pass manual review while deterministic QA errors remain.")
    manual = data.setdefault("manual_review", {})
    started_at = str(manual.get("started_at") or utc_now())
    finished_at = utc_now()
    assets = args.reviewed or list(manual.get("assets", []))
    manual.update(
        {
            "status": args.status,
            "started_at": started_at,
            "finished_at": finished_at,
            "elapsed_seconds": elapsed_seconds(started_at, finished_at),
            "reviewed_assets": assets,
            "notes": args.notes,
        }
    )
    data["status"] = "passed" if args.status == "passed" else "failed"
    write_json(qa_path, data)

    run_state_path = qa_path.parent.parent / "run-state.json"
    if run_state_path.is_file():
        state: dict[str, Any] = read_json(run_state_path)
        state.setdefault("stages", {})["manual_visual_qa"] = {
            "status": "completed" if args.status == "passed" else "failed",
            "manual": True,
            "started_at": started_at,
            "finished_at": finished_at,
            "elapsed_seconds": manual["elapsed_seconds"],
            "reviewed_assets": assets,
            "notes": args.notes,
        }
        state["updated_at"] = finished_at
        write_json(run_state_path, state)
    print(qa_path)
    if args.status == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
