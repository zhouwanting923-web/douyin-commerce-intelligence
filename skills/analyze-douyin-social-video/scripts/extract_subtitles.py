#!/usr/bin/env python3
"""Recover timestamped burned-in subtitles with local Apple Vision OCR."""

from __future__ import annotations

import argparse
import difflib
import math
import os
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageFilter, ImageOps

from _common import read_json, stable_fingerprint, write_json


MODE_DEFAULTS = {
    "standard": {
        "change_threshold": 0.020,
        "force_sample_seconds": 1.5,
        "recognition_level": "accurate",
        "gap_seconds": 12.0,
    },
    "forensic": {
        "change_threshold": 0.012,
        "force_sample_seconds": 0.75,
        "recognition_level": "accurate",
        "gap_seconds": 6.0,
    },
}


def normalize_text(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    return value.replace("丨", "I")


def compact_text(value: str) -> str:
    return re.sub(r"[\s，。！？、,.!?：:；;“”\"'（）()【】\[\]-]+", "", value)


def similar(left: str, right: str) -> bool:
    a = compact_text(left)
    b = compact_text(right)
    if not a or not b:
        return False
    if a in b or b in a:
        return min(len(a), len(b)) / max(len(a), len(b)) >= 0.72
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.86


def signature(path: Path) -> Image.Image:
    with Image.open(path) as image:
        gray = ImageOps.autocontrast(ImageOps.grayscale(image))
        edges = gray.filter(ImageFilter.FIND_EDGES)
        return edges.resize((64, 24), Image.Resampling.BILINEAR)


def change_score(left: Image.Image, right: Image.Image) -> float:
    difference = ImageChops.difference(left, right)
    histogram = difference.histogram()
    total = sum(index * count for index, count in enumerate(histogram))
    pixels = max(1, difference.width * difference.height)
    return total / (pixels * 255.0)


def select_changed_frames(
    frames: list[dict[str, Any]],
    *,
    threshold: float,
    force_sample_seconds: float,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    previous_signature: Image.Image | None = None
    last_selected = -math.inf
    for item in frames:
        path = Path(item.get("path", ""))
        if not path.is_file():
            continue
        current_signature = signature(path)
        timestamp = float(item.get("timestamp", 0))
        changed = (
            previous_signature is None
            or change_score(previous_signature, current_signature) >= threshold
            or timestamp - last_selected >= force_sample_seconds
        )
        previous_signature = current_signature
        if changed:
            selected.append(item)
            last_selected = timestamp
    return selected


def ensure_ocr_helper(skill_dir: Path, runtime_dir: Path) -> Path:
    source = skill_dir / "scripts" / "subtitle_ocr.m"
    if not source.is_file():
        raise RuntimeError(f"Missing Apple Vision OCR source: {source}")
    clang = shutil.which("clang")
    if not clang:
        raise RuntimeError("clang is required for local Apple Vision OCR.")
    runtime_dir.mkdir(parents=True, exist_ok=True)
    binary = runtime_dir / "subtitle_ocr"
    if binary.is_file() and binary.stat().st_mtime >= source.stat().st_mtime:
        return binary
    temporary = runtime_dir / f"subtitle_ocr.{os.getpid()}.tmp"
    command = [
        clang,
        "-fobjc-arc",
        "-O",
        str(source),
        "-framework",
        "Vision",
        "-framework",
        "ImageIO",
        "-framework",
        "CoreGraphics",
        "-framework",
        "Foundation",
        "-o",
        str(temporary),
    ]
    try:
        process = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=120,
        )
        if process.returncode != 0:
            raise RuntimeError(
                process.stderr.strip() or "Unable to compile OCR helper."
            )
        os.replace(temporary, binary)
        binary.chmod(0o755)
        return binary
    finally:
        temporary.unlink(missing_ok=True)


def usable_line(
    line: dict[str, Any],
    minimum_confidence: float,
    minimum_height: float,
) -> bool:
    text = normalize_text(str(line.get("text", "")))
    if not text or float(line.get("confidence", 0)) < minimum_confidence:
        return False
    try:
        height = float(line.get("height", 0))
    except (TypeError, ValueError):
        return False
    compact = compact_text(text)
    return (
        height >= minimum_height
        and (
            len(compact) >= 2
            or any("\u4e00" <= character <= "\u9fff" for character in compact)
        )
    )


def dominant_buckets(
    raw_frames: list[dict[str, Any]],
    *,
    minimum_confidence: float,
    minimum_height: float,
    bucket_width: float,
) -> set[int]:
    scores: Counter[int] = Counter()
    for frame in raw_frames:
        per_frame: dict[int, float] = {}
        for line in frame.get("lines", []):
            if not isinstance(line, dict) or not usable_line(
                line,
                minimum_confidence,
                minimum_height,
            ):
                continue
            center = float(line.get("y", 0)) + float(line.get("height", 0)) / 2
            bucket = round(center / bucket_width)
            score = (
                float(line.get("confidence", 0))
                * min(1.0, float(line.get("height", 0)) / 0.06)
                * min(1.0, float(line.get("width", 0)) / 0.45)
            )
            per_frame[bucket] = max(per_frame.get(bucket, 0.0), score)
        for bucket, score in per_frame.items():
            scores[bucket] += score
    if not scores:
        return set()
    best_bucket, best_score = max(scores.items(), key=lambda item: item[1])
    allowed = {best_bucket - 1, best_bucket, best_bucket + 1}
    for bucket, score in scores.items():
        if score >= best_score * 0.5 and abs(bucket - best_bucket) <= 4:
            allowed.add(bucket)
    return allowed


def build_segments(
    raw_frames: list[dict[str, Any]],
    *,
    minimum_confidence: float,
    frame_period: float,
    minimum_height: float = 0.025,
    bucket_width: float = 0.04,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    allowed = dominant_buckets(
        raw_frames,
        minimum_confidence=minimum_confidence,
        minimum_height=minimum_height,
        bucket_width=bucket_width,
    )
    prepared: list[dict[str, Any]] = []
    line_counts: Counter[str] = Counter()
    confidences: list[float] = []
    for frame in raw_frames:
        texts: list[str] = []
        seen: set[str] = set()
        for line in frame.get("lines", []):
            if not isinstance(line, dict) or not usable_line(
                line,
                minimum_confidence,
                minimum_height,
            ):
                continue
            text = normalize_text(str(line.get("text", "")))
            compact = compact_text(text)
            if not compact or compact in seen:
                continue
            seen.add(compact)
            line_counts[compact] += 1
            confidences.append(float(line.get("confidence", 0)))
            texts.append(text)
        prepared.append(
            {
                "timestamp": float(frame.get("timestamp", 0)),
                "path": str(frame.get("path", "")),
                "texts": texts,
            }
        )

    static_threshold = max(4, math.ceil(max(1, len(prepared)) * 0.55))
    static_lines = {
        text for text, count in line_counts.items() if count >= static_threshold
    }
    samples: list[dict[str, Any]] = []
    for frame in prepared:
        texts = [
            text
            for text in frame["texts"]
            if compact_text(text) not in static_lines
        ]
        text = normalize_text(" ".join(texts))
        if text:
            samples.append(
                {
                    "timestamp": frame["timestamp"],
                    "text": text,
                    "frame_path": frame["path"],
                }
            )

    segments: list[dict[str, Any]] = []
    for sample in samples:
        timestamp = float(sample["timestamp"])
        if (
            segments
            and similar(str(segments[-1]["text"]), str(sample["text"]))
            and timestamp - float(segments[-1]["end"])
            <= max(1.25, frame_period * 3)
        ):
            if len(compact_text(str(sample["text"]))) > len(
                compact_text(str(segments[-1]["text"]))
            ):
                segments[-1]["text"] = sample["text"]
                segments[-1]["frame_path"] = sample["frame_path"]
            segments[-1]["end"] = timestamp + frame_period
            continue
        segments.append(
            {
                "start": timestamp,
                "end": timestamp + frame_period,
                "text": sample["text"],
                "source": "ocr",
                "confidence": None,
                "frame_path": sample["frame_path"],
            }
        )

    metrics = {
        "ocr_frames": len(raw_frames),
        "usable_frames": len(samples),
        "unique_segments": len(segments),
        "text_characters": sum(
            len(compact_text(str(item["text"]))) for item in segments
        ),
        "mean_line_confidence": (
            sum(confidences) / len(confidences) if confidences else 0.0
        ),
        "static_lines_removed": len(static_lines),
        "caption_band_centers": [
            round(bucket * bucket_width, 3) for bucket in sorted(allowed)
        ],
    }
    return segments, metrics


def classify_coverage(
    segments: list[dict[str, Any]],
    metrics: dict[str, Any],
    duration: float,
) -> str:
    if not segments or metrics["text_characters"] < 4:
        return "none"
    minutes = max(1, math.ceil(duration / 60.0))
    enough_segments = metrics["unique_segments"] >= max(2, minutes * 2)
    enough_text = metrics["text_characters"] >= max(12, minutes * 12)
    enough_confidence = metrics["mean_line_confidence"] >= 0.35
    return (
        "complete"
        if enough_segments and enough_text and enough_confidence
        else "partial"
    )


def detect_gaps(
    segments: list[dict[str, Any]],
    duration: float,
    threshold: float,
) -> list[dict[str, float]]:
    if not segments:
        return [{"start": 0.0, "end": duration}] if duration > 0 else []
    ordered = sorted(segments, key=lambda item: float(item["start"]))
    gaps: list[dict[str, float]] = []
    cursor = 0.0
    for segment in ordered:
        start = max(0.0, float(segment["start"]))
        if start - cursor >= threshold:
            gaps.append({"start": cursor, "end": start})
        cursor = max(cursor, float(segment["end"]))
    if duration - cursor >= threshold:
        gaps.append({"start": cursor, "end": duration})
    return gaps


def write_transcript_text(path: Path, segments: list[dict[str, Any]]) -> None:
    lines = []
    for segment in segments:
        lines.append(
            f"[{segment['start']:.1f}-{segment['end']:.1f}] "
            f"{segment['text']}"
        )
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames-json", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--mode", choices=sorted(MODE_DEFAULTS), default="standard")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    frames_json = args.frames_json.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    ocr_dir = output_dir / "_ocr"
    runtime_dir = output_dir / "ocr_runtime"
    ocr_dir.mkdir(parents=True, exist_ok=True)
    frames = read_json(frames_json)
    defaults = MODE_DEFAULTS[args.mode]
    fingerprint = stable_fingerprint(
        {
            "version": 3,
            "mode": args.mode,
            "frames_fingerprint": frames.get("cache_fingerprint", ""),
            "change_threshold": defaults["change_threshold"],
            "force_sample_seconds": defaults["force_sample_seconds"],
            "recognition_level": defaults["recognition_level"],
        }
    )
    transcript_path = output_dir / "transcript.json"
    if not args.force and transcript_path.is_file():
        cached = read_json(transcript_path)
        if (
            cached.get("cache_fingerprint") == fingerprint
            and cached.get("source") in {"apple-vision-ocr", "hybrid"}
        ):
            print(f"CACHED {transcript_path}")
            return

    subtitle_frames = list(frames.get("subtitle_frames", []))
    selected = select_changed_frames(
        subtitle_frames,
        threshold=float(defaults["change_threshold"]),
        force_sample_seconds=float(defaults["force_sample_seconds"]),
    )
    if not selected:
        raise RuntimeError("No changed subtitle frames were found.")
    manifest_path = ocr_dir / "manifest.json"
    raw_path = ocr_dir / "raw.json"
    write_json(
        manifest_path,
        [
            {
                "path": str(item["path"]),
                "timestamp": float(item["timestamp"]),
            }
            for item in selected
        ],
    )
    helper = ensure_ocr_helper(Path(__file__).resolve().parent.parent, runtime_dir)
    process = subprocess.run(
        [
            str(helper),
            str(manifest_path),
            str(raw_path),
            str(defaults["recognition_level"]),
        ],
        text=True,
        capture_output=True,
        timeout=600,
    )
    if process.returncode != 0 or not raw_path.is_file():
        raise RuntimeError(
            process.stderr.strip() or "Apple Vision OCR did not produce output."
        )
    raw_frames = read_json(raw_path)
    failed_frames = [
        item for item in raw_frames if item.get("error") not in {None, ""}
    ]
    frames_with_text = [
        item for item in raw_frames if item.get("lines")
    ]
    if failed_frames and not frames_with_text:
        raise RuntimeError(
            "Apple Vision could not load its local recognition service. "
            "Rerun extract_subtitles.py outside the filesystem sandbox; "
            f"all {len(failed_frames)} OCR requests failed."
        )
    frame_period = 1.0 / max(0.1, float(frames.get("subtitle_fps", 1.0)))
    segments, metrics = build_segments(
        raw_frames,
        minimum_confidence=0.35,
        frame_period=frame_period,
    )
    duration = float(frames.get("duration_seconds", 0))
    coverage = classify_coverage(segments, metrics, duration)
    gaps = (
        []
        if coverage == "complete"
        else detect_gaps(
            segments,
            duration,
            float(defaults["gap_seconds"]),
        )
    )
    metrics.update(
        {
            "source_frames": len(subtitle_frames),
            "selected_frames": len(selected),
            "selection_ratio": len(selected) / max(1, len(subtitle_frames)),
            "failed_frames": len(failed_frames),
        }
    )
    payload = {
        "cache_fingerprint": fingerprint,
        "video_path": frames.get("video_path", ""),
        "duration_seconds": duration,
        "segment_seconds": frame_period,
        "model": "Apple Vision VNRecognizeTextRequest",
        "source": "apple-vision-ocr",
        "coverage": coverage,
        "gaps": gaps,
        "segments": segments,
        "metrics": metrics,
    }
    write_json(transcript_path, payload)
    write_transcript_text(output_dir / "transcript.txt", segments)
    print(transcript_path)


if __name__ == "__main__":
    main()
