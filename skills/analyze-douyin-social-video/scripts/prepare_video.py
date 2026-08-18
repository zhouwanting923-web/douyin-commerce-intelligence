#!/usr/bin/env python3
"""Resolve one authorized Douyin URL through a user-supplied adapter."""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from urllib.parse import parse_qs, urlparse

from _common import probe_duration, read_json, write_json


def normalize_douyin_url(url: str) -> str:
    parsed = urlparse(url.strip())
    query = parse_qs(parsed.query)
    modal_id = query.get("modal_id", [""])[0]
    if modal_id.isdigit():
        return f"https://www.douyin.com/video/{modal_id}"
    return url.strip()


def find_downloader() -> Path:
    override = os.environ.get("DOUYIN_DOWNLOADER")
    if not override:
        raise FileNotFoundError(
            "URL mode is optional and no downloader is bundled. Provide a local "
            "MP4 with --video, or explicitly set DOUYIN_DOWNLOADER to an "
            "authorized adapter module."
        )
    candidate = Path(override).expanduser().resolve()
    if not candidate.is_file():
        raise FileNotFoundError(
            f"DOUYIN_DOWNLOADER does not point to a file: {candidate}"
        )
    return candidate


def load_downloader(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("codex_douyin_downloader", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load downloader module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def valid_cached_video(output_dir: Path, normalized_url: str) -> Path | None:
    metadata_path = output_dir / "video.json"
    if not metadata_path.is_file():
        return None
    try:
        payload = read_json(metadata_path)
        if payload.get("normalized_url") != normalized_url:
            return None
        video_path = Path(payload.get("local_video_path", ""))
        if not video_path.is_file() or video_path.stat().st_size <= 0:
            return None
        if probe_duration(video_path) <= 0:
            return None
        return video_path
    except (OSError, ValueError, KeyError, TypeError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    normalized_url = normalize_douyin_url(args.url)
    output_dir = args.output_dir.resolve()
    media_dir = output_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    if not args.force:
        cached = valid_cached_video(output_dir, normalized_url)
        if cached:
            print(f"CACHED {output_dir / 'video.json'}")
            return

    downloader = load_downloader(find_downloader())
    processor = downloader.DouyinProcessor()
    info = processor.parse_share_url(normalized_url)
    expected = media_dir / f"{info['video_id']}.mp4"

    temporary_dir = Path(tempfile.mkdtemp(prefix=".download-", dir=media_dir))
    try:
        downloaded = processor.download_video(
            info,
            output_dir=temporary_dir,
            show_progress=False,
        )
        if not downloaded.is_file() or downloaded.stat().st_size <= 0:
            raise RuntimeError("Downloader completed but no valid MP4 was produced.")
        os.replace(downloaded, expected)
    finally:
        shutil.rmtree(temporary_dir, ignore_errors=True)

    duration = probe_duration(expected)
    payload = {
        "source_url": args.url,
        "normalized_url": normalized_url,
        "video_id": str(info["video_id"]),
        "title": str(info.get("title", "")),
        "creator": str(info.get("creator", "")),
        "download_url": str(info.get("url", "")),
        "local_video_path": str(expected),
        "duration_seconds": duration,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(output_dir / "video.json", payload)
    print(output_dir / "video.json")


if __name__ == "__main__":
    main()
