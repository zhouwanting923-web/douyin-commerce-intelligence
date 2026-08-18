#!/usr/bin/env python3
"""Resumable orchestration for the deterministic parts of video analysis."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from _common import (
    file_fingerprint,
    probe_duration,
    read_json,
    write_json,
)


SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StateRecorder:
    def __init__(self, path: Path, mode: str) -> None:
        self.path = path
        if path.is_file():
            try:
                self.data = read_json(path)
            except (OSError, ValueError, TypeError):
                self.data = {}
        else:
            self.data = {}
        self.data.setdefault("version", 2)
        self.data["mode"] = mode
        self.data.setdefault("stages", {})
        self.data.setdefault("created_at", utc_now())
        self.save()

    def save(self) -> None:
        self.data["updated_at"] = utc_now()
        write_json(self.path, self.data)

    def run_command(self, name: str, command: list[str]) -> str:
        started_at = utc_now()
        started = time.monotonic()
        print(f"[{name}] starting")
        process = subprocess.run(
            command,
            text=True,
            capture_output=True,
        )
        elapsed = time.monotonic() - started
        output = "\n".join(
            value.strip()
            for value in (process.stdout, process.stderr)
            if value.strip()
        )
        status = "completed" if process.returncode == 0 else "failed"
        self.data["stages"][name] = {
            "status": status,
            "started_at": started_at,
            "finished_at": utc_now(),
            "elapsed_seconds": round(elapsed, 3),
            "cached": "CACHED " in output,
            "command": command,
            "output_tail": output[-4000:],
        }
        self.save()
        if output:
            if len(output) > 6000:
                print(
                    "[stage output truncated; showing final 6000 characters]\n"
                    + output[-6000:]
                )
            else:
                print(output)
        if process.returncode != 0:
            raise subprocess.CalledProcessError(
                process.returncode,
                command,
                output=process.stdout,
                stderr=process.stderr,
            )
        print(f"[{name}] completed in {elapsed:.2f}s")
        return output

    def run_callable(self, name: str, callback: Callable[[], Any]) -> Any:
        started_at = utc_now()
        started = time.monotonic()
        print(f"[{name}] starting")
        try:
            result = callback()
        except Exception as exc:
            self.data["stages"][name] = {
                "status": "failed",
                "started_at": started_at,
                "finished_at": utc_now(),
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "error": f"{type(exc).__name__}: {exc}",
            }
            self.save()
            raise
        elapsed = time.monotonic() - started
        self.data["stages"][name] = {
            "status": "completed",
            "started_at": started_at,
            "finished_at": utc_now(),
            "elapsed_seconds": round(elapsed, 3),
        }
        self.save()
        print(f"[{name}] completed in {elapsed:.2f}s")
        return result

    def skip(self, name: str, reason: str) -> None:
        self.data["stages"][name] = {
            "status": "skipped",
            "finished_at": utc_now(),
            "elapsed_seconds": 0.0,
            "reason": reason,
        }
        self.save()
        print(f"[{name}] skipped: {reason}")

    def start_manual(
        self,
        name: str,
        *,
        artifacts: list[str] | None = None,
    ) -> None:
        existing = self.data["stages"].get(name, {})
        if existing.get("status") in {"pending", "completed"}:
            return
        self.data["stages"][name] = {
            "status": "pending",
            "manual": True,
            "started_at": utc_now(),
            "artifacts": artifacts or [],
        }
        self.save()
        print(f"[{name}] timing started")

    def complete_manual(
        self,
        name: str,
        *,
        fallback_started_at: str | None = None,
    ) -> None:
        existing = self.data["stages"].get(name, {})
        if existing.get("status") == "completed":
            return
        started_at = str(existing.get("started_at") or fallback_started_at or utc_now())
        finished_at = utc_now()
        try:
            elapsed = (
                datetime.fromisoformat(finished_at)
                - datetime.fromisoformat(started_at)
            ).total_seconds()
        except ValueError:
            elapsed = 0.0
        self.data["stages"][name] = {
            **existing,
            "status": "completed",
            "manual": True,
            "started_at": started_at,
            "finished_at": finished_at,
            "elapsed_seconds": round(max(0.0, elapsed), 3),
        }
        self.save()
        print(f"[{name}] completed in {elapsed:.2f}s")


def require_complete_visible_subtitles(transcript_path: Path) -> dict:
    transcript = read_json(transcript_path)
    coverage = str(transcript.get("coverage", "unknown")).strip().lower()
    if coverage != "complete":
        gaps = transcript.get("gaps", [])
        gap_count = len(gaps) if isinstance(gaps, list) else 0
        raise RuntimeError(
            "未能恢复完整的画面字幕：本地 OCR 报告 "
            f"coverage={coverage!r}，检测到 {gap_count} 处字幕缺口。"
            "流程已在证据和报告生成前终止。"
            "请提供带完整内嵌字幕的视频。"
        )
    return transcript


def prepare_local_video(
    source: Path,
    output_dir: Path,
    *,
    force: bool,
) -> Path:
    source = source.resolve()
    media_dir = output_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    destination = media_dir / source.name
    metadata_path = output_dir / "video.json"
    fingerprint = file_fingerprint(source)
    if not force and metadata_path.is_file() and destination.is_file():
        cached = read_json(metadata_path)
        if cached.get("source_fingerprint") == fingerprint:
            return metadata_path
    if source != destination:
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    duration = probe_duration(destination)
    write_json(
        metadata_path,
        {
            "source_url": "",
            "normalized_url": "",
            "video_id": source.stem,
            "title": source.stem,
            "download_url": "",
            "local_video_path": str(destination),
            "duration_seconds": duration,
            "source_fingerprint": fingerprint,
            "prepared_at": utc_now(),
        },
    )
    return metadata_path


def prepare_phase(args: argparse.Namespace) -> None:
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    state = StateRecorder(output_dir / "run-state.json", args.mode)
    python = str(args.artifact_python.resolve())

    if args.url:
        command = [
            python,
            str(SCRIPTS_DIR / "prepare_video.py"),
            "--url",
            args.url,
            "--output-dir",
            str(output_dir),
        ]
        if args.force:
            command.append("--force")
        state.run_command("prepare_video", command)
    else:
        state.run_callable(
            "prepare_video",
            lambda: prepare_local_video(
                args.video,
                output_dir,
                force=args.force,
            ),
        )

    video_json = output_dir / "video.json"
    video = read_json(video_json)
    video_path = Path(video["local_video_path"]).resolve()
    frames_json = output_dir / "frames" / "index.json"
    command = [
        python,
        str(SCRIPTS_DIR / "extract_candidates.py"),
        "--video",
        str(video_path),
        "--output-dir",
        str(output_dir / "frames"),
        "--mode",
        args.mode,
    ]
    if args.force:
        command.append("--force")
    state.run_command("extract_candidates", command)

    command = [
        python,
        str(SCRIPTS_DIR / "extract_subtitles.py"),
        "--frames-json",
        str(frames_json),
        "--output-dir",
        str(output_dir),
        "--mode",
        args.mode,
    ]
    if args.force:
        command.append("--force")
    state.run_command("extract_subtitles", command)

    transcript_path = output_dir / "transcript.json"
    state.run_callable(
        "subtitle_gate",
        lambda: require_complete_visible_subtitles(transcript_path),
    )

    evidence_path = output_dir / "evidence.json"
    state.run_command(
        "build_evidence",
        [
            python,
            str(SCRIPTS_DIR / "build_evidence.py"),
            "--frames-json",
            str(frames_json),
            "--transcript-json",
            str(transcript_path),
            "--output",
            str(evidence_path),
            "--mode",
            args.mode,
        ],
    )

    review_packet_path = output_dir / "review-packet.json"
    review_command = [
        python,
        str(SCRIPTS_DIR / "build_review_packet.py"),
        "--video-json",
        str(video_json),
        "--transcript-json",
        str(transcript_path),
        "--frames-json",
        str(frames_json),
        "--output-dir",
        str(output_dir / "review"),
        "--mode",
        args.mode,
    ]
    if args.force:
        review_command.append("--force")
    state.run_command("build_review_packet", review_command)

    analysis_path = output_dir / "analysis.json"
    if analysis_path.is_file() and not args.force:
        state.skip("init_analysis", "analysis.json already exists.")
    else:
        state.run_command(
            "init_analysis",
            [
                python,
                str(SCRIPTS_DIR / "init_analysis.py"),
                "--video-json",
                str(video_json),
                "--transcript-json",
                str(transcript_path),
                "--frames-json",
                str(frames_json),
                "--evidence-json",
                str(evidence_path),
                "--review-packet-json",
                str(review_packet_path),
                "--output",
                str(analysis_path),
                "--mode",
                args.mode,
            ],
        )

    state.start_manual(
        "evidence_review_and_analysis",
        artifacts=[
            str(review_packet_path),
            str(output_dir / "review" / "review-board.jpg"),
            str(analysis_path),
        ],
    )
    print(
        "PREPARED: inspect review/review-board.jpg and review-packet.json once, "
        "open original frames only when ambiguous, then fill analysis.json."
    )


def finalize_phase(args: argparse.Namespace) -> None:
    analysis_path = args.analysis.resolve()
    output_dir = analysis_path.parent
    data = read_json(analysis_path)
    mode = args.mode or data.get("runtime", {}).get("mode", "standard")
    state = StateRecorder(output_dir / "run-state.json", mode)
    python = str(args.artifact_python.resolve())
    report = (args.output or output_dir / "report.pdf").resolve()
    init_stage = state.data.get("stages", {}).get("init_analysis", {})
    state.complete_manual(
        "evidence_review_and_analysis",
        fallback_started_at=init_stage.get("finished_at"),
    )

    state.run_command(
        "materialize_evidence_refs",
        [
            python,
            str(SCRIPTS_DIR / "materialize_evidence_refs.py"),
            str(analysis_path),
        ],
    )
    state.run_command(
        "preflight_analysis",
        [
            python,
            str(SCRIPTS_DIR / "preflight_analysis.py"),
            str(analysis_path),
        ],
    )
    state.run_command(
        "materialize_screenshots",
        [
            python,
            str(SCRIPTS_DIR / "materialize_screenshots.py"),
            str(analysis_path),
        ],
    )
    state.run_command(
        "validate_analysis",
        [
            python,
            str(SCRIPTS_DIR / "validate_analysis.py"),
            str(analysis_path),
        ],
    )
    state.run_command(
        "build_report",
        [
            python,
            str(SCRIPTS_DIR / "build_report.py"),
            "--analysis",
            str(analysis_path),
            "--output",
            str(report),
        ],
    )
    state.run_command(
        "qa_report",
        [
            python,
            str(SCRIPTS_DIR / "qa_report.py"),
            "--report",
            str(report),
            "--analysis",
            str(analysis_path),
            "--output-dir",
            str(output_dir / "qa"),
            "--mode",
            mode,
        ],
    )
    print(f"FINALIZED_PENDING_REVIEW: {report}")
    print(
        "Inspect qa/qa-review-board-*.jpg, open original pages only when needed, "
        "then run complete_manual_review.py."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="phase", required=True)

    prepare = subparsers.add_parser("prepare")
    source = prepare.add_mutually_exclusive_group(required=True)
    source.add_argument("--url")
    source.add_argument("--video", type=Path)
    prepare.add_argument("--output-dir", required=True, type=Path)
    prepare.add_argument(
        "--mode",
        choices=["standard", "forensic"],
        default="standard",
    )
    prepare.add_argument(
        "--artifact-python",
        type=Path,
        default=Path(sys.executable),
    )
    prepare.add_argument("--force", action="store_true")
    prepare.set_defaults(handler=prepare_phase)

    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--analysis", required=True, type=Path)
    finalize.add_argument("--output", type=Path)
    finalize.add_argument(
        "--mode",
        choices=["standard", "forensic"],
    )
    finalize.add_argument(
        "--artifact-python",
        type=Path,
        default=Path(sys.executable),
    )
    finalize.set_defaults(handler=finalize_phase)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
