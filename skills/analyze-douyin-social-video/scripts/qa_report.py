#!/usr/bin/env python3
"""Render a report, run deterministic PDF checks, and build a QA contact sheet."""

from __future__ import annotations

import argparse
import math
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

from _common import read_json, resolve_artifact_path, write_json


def run_optional(binary: str, arguments: list[str]) -> subprocess.CompletedProcess[str] | None:
    executable = shutil.which(binary)
    if not executable:
        return None
    return subprocess.run(
        [executable, *arguments],
        text=True,
        capture_output=True,
    )


def build_contact_sheet(pages: list[Path], output: Path) -> None:
    columns = 3
    thumb_w, thumb_h, label_h = 300, 424, 28
    rows = max(1, math.ceil(len(pages) / columns))
    canvas = Image.new(
        "RGB",
        (columns * thumb_w, rows * (thumb_h + label_h)),
        "white",
    )
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    for index, path in enumerate(pages):
        with Image.open(path) as opened:
            image = ImageOps.contain(
                opened.convert("RGB"),
                (thumb_w - 12, thumb_h - 12),
                Image.Resampling.LANCZOS,
            )
        x = (index % columns) * thumb_w
        y = (index // columns) * (thumb_h + label_h)
        canvas.paste(
            image,
            (
                x + (thumb_w - image.width) // 2,
                y + (thumb_h - image.height) // 2,
            ),
        )
        draw.rectangle(
            (x, y + thumb_h, x + thumb_w, y + thumb_h + label_h),
            fill="#F3F4F6",
        )
        draw.text(
            (x + 8, y + thumb_h + 7),
            f"Page {index + 1}",
            fill="#111827",
            font=font,
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, quality=88, optimize=True)


def page_ink_density(path: Path) -> float:
    with Image.open(path) as opened:
        image = opened.convert("L")
        image.thumbnail((320, 480), Image.Resampling.LANCZOS)
        histogram = image.histogram()
    dark_pixels = sum(histogram[:245])
    total = max(1, image.width * image.height)
    return dark_pixels / total


def select_manual_review_indices(pages: list[Path], mode: str) -> list[int]:
    if mode == "forensic":
        return list(range(len(pages)))
    if not pages:
        return []
    selected = list(range(min(4, len(pages))))
    transcript_candidates = list(range(4, len(pages)))
    if transcript_candidates:
        densest = max(
            transcript_candidates,
            key=lambda index: page_ink_density(pages[index]),
        )
        selected.append(densest)
    return list(dict.fromkeys(selected))


def build_full_detail_review_boards(
    pages: list[Path],
    indices: list[int],
    output_dir: Path,
    *,
    chunk_size: int = 5,
) -> list[Path]:
    for path in output_dir.glob("qa-review-board-*.jpg"):
        path.unlink(missing_ok=True)
    outputs: list[Path] = []
    font = ImageFont.load_default()
    for chunk_index in range(0, len(indices), chunk_size):
        chunk = indices[chunk_index : chunk_index + chunk_size]
        opened_pages: list[tuple[int, Image.Image]] = []
        for page_index in chunk:
            with Image.open(pages[page_index]) as opened:
                opened_pages.append((page_index, opened.convert("RGB").copy()))
        if not opened_pages:
            continue
        label_h = 34
        width = max(image.width for _, image in opened_pages)
        height = sum(image.height + label_h for _, image in opened_pages)
        canvas = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(canvas)
        y = 0
        for page_index, image in opened_pages:
            draw.rectangle((0, y, width, y + label_h), fill="#F3F4F6")
            draw.text(
                (10, y + 10),
                f"Full-detail PDF page {page_index + 1}",
                fill="#111827",
                font=font,
            )
            canvas.paste(image, ((width - image.width) // 2, y + label_h))
            y += image.height + label_h
        output = output_dir / f"qa-review-board-{len(outputs) + 1:02d}.jpg"
        canvas.save(output, quality=92, optimize=True)
        outputs.append(output)
    return outputs


def transcript_segments(data: dict[str, Any], base_dir: Path) -> list[dict[str, Any]]:
    transcript = data.get("transcript", {})
    embedded = transcript.get("segments", []) if isinstance(transcript, dict) else []
    if embedded:
        return embedded
    path_value = transcript.get("path", "") if isinstance(transcript, dict) else ""
    if not path_value:
        return []
    path = resolve_artifact_path(base_dir, str(path_value))
    if not path.is_file():
        return []
    payload = read_json(path)
    values = payload.get("segments", [])
    return values if isinstance(values, list) else []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--analysis", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--mode",
        choices=["standard", "forensic"],
        default="standard",
    )
    args = parser.parse_args()

    report = args.report.resolve()
    analysis_path = args.analysis.resolve()
    output_dir = args.output_dir.resolve()
    pages_dir = output_dir / "pdf-pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    for path in pages_dir.glob("page-*.png"):
        path.unlink(missing_ok=True)
    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, Any] = {}

    checks["report_exists"] = report.is_file() and report.stat().st_size > 0
    if not checks["report_exists"]:
        errors.append("PDF does not exist or is empty.")

    data = read_json(analysis_path)
    base_dir = analysis_path.parent
    selected = [
        item
        for item in data.get("screenshots", [])
        if item.get("status") == "selected"
    ]
    missing_screenshots = [
        item.get("slot", "")
        for item in selected
        if not resolve_artifact_path(base_dir, str(item.get("path", ""))).is_file()
    ]
    checks["selected_screenshots"] = len(selected)
    checks["missing_selected_screenshots"] = missing_screenshots
    if missing_screenshots:
        errors.append(
            "Missing selected screenshots: " + ", ".join(missing_screenshots)
        )

    segments = transcript_segments(data, base_dir)
    checks["transcript_segments"] = len(segments)
    if not segments:
        errors.append("Transcript is empty or unavailable.")

    page_count = 0
    info = run_optional("pdfinfo", [str(report)])
    if info is None:
        warnings.append("pdfinfo is unavailable.")
    elif info.returncode != 0:
        errors.append(info.stderr.strip() or "pdfinfo failed.")
    else:
        match = re.search(r"^Pages:\s+(\d+)", info.stdout, re.MULTILINE)
        page_count = int(match.group(1)) if match else 0
        if page_count <= 0:
            errors.append("PDF has no readable pages.")
    checks["pdf_pages"] = page_count

    fonts = run_optional("pdffonts", [str(report)])
    if fonts is None:
        warnings.append("pdffonts is unavailable.")
    elif fonts.returncode != 0:
        warnings.append(fonts.stderr.strip() or "pdffonts failed.")
    else:
        font_rows = [
            line
            for line in fonts.stdout.splitlines()
            if line.strip() and not line.startswith(("name", "-"))
        ]
        embedded = any(re.search(r"\byes\b", line) for line in font_rows)
        checks["font_rows"] = len(font_rows)
        checks["font_embedded"] = embedded
        if not embedded:
            warnings.append("No embedded font was reported by pdffonts.")

    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        errors.append("pdftoppm is unavailable.")
    elif report.is_file():
        render = subprocess.run(
            [
                pdftoppm,
                "-png",
                "-r",
                "110",
                str(report),
                str(pages_dir / "page"),
            ],
            text=True,
            capture_output=True,
        )
        if render.returncode != 0:
            errors.append(render.stderr.strip() or "PDF rendering failed.")
    pages = sorted(pages_dir.glob("page-*.png"))
    checks["rendered_pages"] = len(pages)
    if page_count and len(pages) != page_count:
        errors.append(
            f"Rendered {len(pages)} pages but pdfinfo reported {page_count}."
        )
    if pages:
        build_contact_sheet(pages, output_dir / "report-contact-sheet.jpg")
    review_indices = select_manual_review_indices(pages, args.mode)
    review_boards = build_full_detail_review_boards(
        pages,
        review_indices,
        output_dir,
    )
    checks["manual_review_pages"] = [index + 1 for index in review_indices]

    payload = {
        "status": "failed" if errors else "pending_manual_review",
        "mode": args.mode,
        "manual_review_scope": (
            "all_pages_full_detail"
            if args.mode == "forensic"
            else "contact_sheet_plus_key_pages"
        ),
        "report": str(report),
        "analysis": str(analysis_path),
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
        "manual_review": {
            "status": "blocked" if errors else "pending",
            "started_at": (
                ""
                if errors
                else datetime.now(timezone.utc).isoformat()
            ),
            "finished_at": None,
            "elapsed_seconds": None,
            "pages": [index + 1 for index in review_indices],
            "assets": [str(path) for path in review_boards],
            "reviewed_assets": [],
            "notes": "",
        },
    }
    write_json(output_dir / "qa.json", payload)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(1)
    print(output_dir / "qa.json")


if __name__ == "__main__":
    main()
