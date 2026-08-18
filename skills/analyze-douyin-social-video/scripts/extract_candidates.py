#!/usr/bin/env python3
"""Extract global candidates and cropped subtitle frames in one decode pass."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from _common import (
    file_fingerprint,
    find_binary,
    format_timestamp,
    probe_duration,
    read_json,
    run_command,
    stable_fingerprint,
    write_json,
)


MODE_DEFAULTS = {
    "standard": {"subtitle_fps": 2.0, "max_frames": 40},
    "forensic": {"subtitle_fps": 4.0, "max_frames": 60},
}


def make_contact_sheets(frames: list[dict], output_dir: Path) -> list[str]:
    columns, rows_per_sheet = 4, 5
    thumb_w, thumb_h, label_h = 240, 360, 28
    per_sheet = columns * rows_per_sheet
    font = ImageFont.load_default()
    outputs: list[str] = []

    for sheet_number, start in enumerate(range(0, len(frames), per_sheet), start=1):
        group = frames[start : start + per_sheet]
        rows = math.ceil(len(group) / columns)
        canvas = Image.new(
            "RGB",
            (columns * thumb_w, rows * (thumb_h + label_h)),
            "white",
        )
        draw = ImageDraw.Draw(canvas)
        for index, item in enumerate(group):
            with Image.open(item["path"]) as opened:
                source = opened.convert("RGB")
            source.thumbnail(
                (thumb_w - 8, thumb_h - 8),
                Image.Resampling.LANCZOS,
            )
            x = (index % columns) * thumb_w
            y = (index // columns) * (thumb_h + label_h)
            paste_x = x + (thumb_w - source.width) // 2
            paste_y = y + (thumb_h - source.height) // 2
            canvas.paste(source, (paste_x, paste_y))
            label = f"#{item['index']:02d}  {format_timestamp(item['timestamp'])}"
            draw.rectangle(
                (x, y + thumb_h, x + thumb_w, y + thumb_h + label_h),
                fill="#F3F4F6",
            )
            draw.text(
                (x + 8, y + thumb_h + 7),
                label,
                fill="#111827",
                font=font,
            )
        path = output_dir / f"contact-sheet-{sheet_number:02d}.jpg"
        canvas.save(path, quality=88, optimize=True)
        outputs.append(str(path))
    return outputs


def cache_is_valid(index_path: Path, fingerprint: str) -> bool:
    if not index_path.is_file():
        return False
    try:
        cached = read_json(index_path)
    except (OSError, ValueError, TypeError):
        return False
    if cached.get("cache_fingerprint") != fingerprint:
        return False
    paths = [
        Path(item.get("path", ""))
        for item in cached.get("frames", [])
        + cached.get("subtitle_frames", [])
    ]
    paths.extend(Path(value) for value in cached.get("contact_sheets", []))
    return bool(paths) and all(path.is_file() for path in paths)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--mode", choices=sorted(MODE_DEFAULTS), default="standard")
    parser.add_argument("--max-frames", type=int)
    parser.add_argument("--interval", type=float)
    parser.add_argument("--subtitle-fps", type=float)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    video = args.video.resolve()
    output_dir = args.output_dir.resolve()
    subtitle_dir = output_dir / "subtitles"
    output_dir.mkdir(parents=True, exist_ok=True)
    subtitle_dir.mkdir(parents=True, exist_ok=True)

    defaults = MODE_DEFAULTS[args.mode]
    max_frames = args.max_frames or int(defaults["max_frames"])
    subtitle_fps = args.subtitle_fps or float(defaults["subtitle_fps"])
    duration = probe_duration(video)
    interval = args.interval or max(1.0, duration / max(1, max_frames - 1))
    settings = {
        "version": 2,
        "mode": args.mode,
        "max_frames": max_frames,
        "interval": round(interval, 6),
        "subtitle_fps": subtitle_fps,
        "candidate_width": 540,
        "subtitle_width": 640,
        "subtitle_crop": [0.04, 0.48, 0.92, 0.42],
        "video": file_fingerprint(video),
    }
    fingerprint = stable_fingerprint(settings)
    index_path = output_dir / "index.json"
    if not args.force and cache_is_valid(index_path, fingerprint):
        print(f"CACHED {index_path}")
        return

    for pattern in ("candidate-*.jpg", "contact-sheet-*.jpg"):
        for path in output_dir.glob(pattern):
            path.unlink(missing_ok=True)
    for path in subtitle_dir.glob("subtitle-*.jpg"):
        path.unlink(missing_ok=True)

    ffmpeg = find_binary("ffmpeg")
    candidate_pattern = output_dir / "candidate-%04d.jpg"
    subtitle_pattern = subtitle_dir / "subtitle-%06d.jpg"
    subtitle_filter = (
        f"fps={subtitle_fps:.6f},"
        "crop=trunc(iw*0.92/2)*2:trunc(ih*0.42/2)*2:"
        "trunc(iw*0.04/2)*2:trunc(ih*0.48/2)*2,"
        "scale=640:-2:flags=lanczos"
    )
    run_command(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video),
            "-map",
            "0:v:0",
            "-vf",
            f"fps=1/{interval:.6f},scale=540:-2:flags=lanczos",
            "-q:v",
            "2",
            "-vsync",
            "vfr",
            "-y",
            str(candidate_pattern),
            "-map",
            "0:v:0",
            "-vf",
            subtitle_filter,
            "-q:v",
            "6",
            "-vsync",
            "vfr",
            "-y",
            str(subtitle_pattern),
        ]
    )

    paths = sorted(output_dir.glob("candidate-*.jpg"))[:max_frames]
    subtitle_paths = sorted(subtitle_dir.glob("subtitle-*.jpg"))
    if not paths:
        raise RuntimeError("No candidate frames were extracted.")
    if not subtitle_paths:
        raise RuntimeError("No subtitle-region frames were extracted.")
    frames = [
        {
            "index": index,
            "timestamp": min((index - 1) * interval, duration),
            "path": str(path),
        }
        for index, path in enumerate(paths, start=1)
    ]
    subtitle_frames = [
        {
            "index": index,
            "timestamp": min((index - 1) / subtitle_fps, duration),
            "path": str(path),
        }
        for index, path in enumerate(subtitle_paths, start=1)
    ]
    contact_sheets = make_contact_sheets(frames, output_dir)
    write_json(
        index_path,
        {
            "cache_fingerprint": fingerprint,
            "settings": settings,
            "video_path": str(video),
            "duration_seconds": duration,
            "interval_seconds": interval,
            "subtitle_fps": subtitle_fps,
            "frames": frames,
            "subtitle_frames": subtitle_frames,
            "contact_sheets": contact_sheets,
        },
    )
    print(index_path)


if __name__ == "__main__":
    main()
