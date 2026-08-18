#!/usr/bin/env python3
"""Extract a small set of original-resolution frames at exact timestamps."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from _common import find_binary, probe_duration, read_json, run_command, write_json


def safe_name(value: str, fallback: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    return normalized or fallback


def load_requests(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.requests_json:
        payload = read_json(args.requests_json.resolve())
        values = payload.get("requests", payload) if isinstance(payload, dict) else payload
        if not isinstance(values, list):
            raise ValueError("requests JSON must be a list or contain requests.")
        return [dict(item) for item in values]
    timestamps = [
        float(value.strip())
        for value in str(args.timestamps or "").split(",")
        if value.strip()
    ]
    return [
        {"timestamp": timestamp, "name": f"frame-{index:03d}"}
        for index, timestamp in enumerate(timestamps, start=1)
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--timestamps")
    group.add_argument("--requests-json", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    video = args.video.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    duration = probe_duration(video)
    requests = load_requests(args)
    if not requests:
        raise RuntimeError("At least one timestamp is required.")
    ffmpeg = find_binary("ffmpeg")
    frames: list[dict[str, Any]] = []
    for index, item in enumerate(requests, start=1):
        timestamp = max(0.0, min(duration, float(item.get("timestamp", 0))))
        name = safe_name(
            str(item.get("name", "")),
            f"frame-{index:03d}",
        )
        if not name.lower().endswith(".jpg"):
            name += ".jpg"
        output = output_dir / name
        if args.force or not output.is_file():
            run_command(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-ss",
                    f"{timestamp:.3f}",
                    "-i",
                    str(video),
                    "-frames:v",
                    "1",
                    "-q:v",
                    "2",
                    "-y",
                    str(output),
                ]
            )
        frames.append(
            {
                "timestamp": timestamp,
                "path": str(output),
                "name": output.stem,
            }
        )
    payload = {
        "video_path": str(video),
        "duration_seconds": duration,
        "frames": frames,
    }
    write_json(output_dir / "index.json", payload)
    print(output_dir / "index.json")


if __name__ == "__main__":
    main()
