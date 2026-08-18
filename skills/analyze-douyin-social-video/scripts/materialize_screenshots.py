#!/usr/bin/env python3
"""Copy selected evidence frames into the standard seven-screenshot folder."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from _common import read_json, resolve_artifact_path, write_json


FILENAMES = {
    "cover": "01-cover.jpg",
    "product_alone": "02-product-alone.jpg",
    "product_detail": "03-product-detail.jpg",
    "selling_point": "04-selling-point.jpg",
    "use_process_1": "05-use-process-1.jpg",
    "use_process_2": "06-use-process-2.jpg",
    "after_effect": "07-after-effect.jpg",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("analysis", type=Path)
    parser.add_argument("--screenshots-dir", type=Path)
    args = parser.parse_args()

    analysis_path = args.analysis.resolve()
    base_dir = analysis_path.parent
    screenshots_dir = (args.screenshots_dir or base_dir / "screenshots").resolve()
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    data = read_json(analysis_path)
    replacements: dict[str, str] = {}

    for item in data.get("screenshots", []):
        if item.get("status") != "selected":
            continue
        slot = item.get("slot")
        if slot not in FILENAMES:
            raise SystemExit(f"Unknown screenshot slot: {slot}")
        if not item.get("path"):
            raise SystemExit(f"Selected screenshot has no source path: {slot}")

        source = resolve_artifact_path(base_dir, item["path"])
        if not source.is_file():
            raise SystemExit(f"Screenshot source does not exist: {source}")
        destination = screenshots_dir / FILENAMES[slot]
        if source != destination:
            shutil.copy2(source, destination)
        relative_path = str(destination.relative_to(base_dir))
        replacements[str(source)] = relative_path
        replacements[item["path"]] = relative_path
        item["path"] = relative_path

    for ad in data.get("product_ads", []):
        ad["evidence_screenshots"] = [
            replacements.get(value, replacements.get(str(resolve_artifact_path(base_dir, value)), value))
            for value in ad.get("evidence_screenshots", [])
        ]

    write_json(analysis_path, data)
    print(screenshots_dir)


if __name__ == "__main__":
    main()
