#!/usr/bin/env python3
"""Build one chronological evidence index shared by all analysis judgments."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from _common import file_fingerprint, read_json, stable_fingerprint, write_json


def nearby_segments(
    timestamp: float,
    segments: list[dict[str, Any]],
    tolerance: float = 2.0,
) -> list[dict[str, Any]]:
    matches = []
    for segment in segments:
        start = float(segment.get("start", 0))
        end = float(segment.get("end", start))
        if start - tolerance <= timestamp <= end + tolerance:
            matches.append(
                {
                    "start": start,
                    "end": end,
                    "text": str(segment.get("text", "")),
                    "source": str(segment.get("source", "")),
                }
            )
    return matches


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames-json", required=True, type=Path)
    parser.add_argument("--transcript-json", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", choices=["standard", "forensic"], default="standard")
    args = parser.parse_args()

    frames_path = args.frames_json.resolve()
    transcript_path = args.transcript_json.resolve()
    frames = read_json(frames_path)
    transcript = read_json(transcript_path)
    segments = sorted(
        transcript.get("segments", []),
        key=lambda item: float(item.get("start", 0)),
    )
    events: list[dict[str, Any]] = []

    for segment in segments:
        frame_path = str(segment.get("frame_path", ""))
        events.append(
            {
                "type": "transcript",
                "start": float(segment.get("start", 0)),
                "end": float(segment.get("end", 0)),
                "transcript": [
                    {
                        "text": str(segment.get("text", "")),
                        "source": str(segment.get("source", "")),
                    }
                ],
                "visible_text": (
                    [str(segment.get("text", ""))]
                    if segment.get("source") in {"ocr", "subtitle"}
                    else []
                ),
                "frame_paths": [frame_path] if frame_path else [],
            }
        )

    for item in frames.get("frames", []):
        timestamp = float(item.get("timestamp", 0))
        events.append(
            {
                "type": "visual_candidate",
                "start": timestamp,
                "end": timestamp,
                "transcript": nearby_segments(timestamp, segments),
                "visible_text": [],
                "frame_paths": [str(item.get("path", ""))],
                "candidate_index": item.get("index"),
            }
        )

    events.sort(
        key=lambda item: (
            float(item.get("start", 0)),
            0 if item.get("type") == "transcript" else 1,
        )
    )
    fingerprint = stable_fingerprint(
        {
            "version": 2,
            "mode": args.mode,
            "frames": file_fingerprint(frames_path),
            "transcript": file_fingerprint(transcript_path),
        }
    )
    payload = {
        "cache_fingerprint": fingerprint,
        "mode": args.mode,
        "video_path": frames.get("video_path", ""),
        "duration_seconds": float(frames.get("duration_seconds", 0)),
        "transcript_path": str(transcript_path),
        "transcript_coverage": transcript.get("coverage", "unknown"),
        "transcript_gaps": transcript.get("gaps", []),
        "contact_sheets": frames.get("contact_sheets", []),
        "candidate_frames": frames.get("frames", []),
        "metrics": {
            "candidate_frames": len(frames.get("frames", [])),
            "transcript_segments": len(segments),
            "ocr_source_frames": transcript.get("metrics", {}).get(
                "source_frames",
                0,
            ),
            "ocr_selected_frames": transcript.get("metrics", {}).get(
                "selected_frames",
                0,
            ),
        },
        "events": events,
    }
    write_json(args.output.resolve(), payload)
    print(args.output.resolve())


if __name__ == "__main__":
    main()
