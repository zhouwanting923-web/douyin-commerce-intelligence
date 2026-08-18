#!/usr/bin/env python3
"""Build a compact review packet, product-signal windows, and one visual board."""

from __future__ import annotations

import argparse
import math
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

from _common import (
    file_fingerprint,
    find_binary,
    format_timestamp,
    read_json,
    run_command,
    stable_fingerprint,
    write_json,
)


PRODUCT_RE = re.compile(
    r"神仙水|精华(?:水|液|油|棒)?|次抛|安瓶|冻干粉|面霜|乳液|水乳|洗面奶|面膜|防晒|口红|"
    r"粉底|眼霜|套装|礼盒|喷雾|洗发水|沐浴露|身体乳|香水|"
    r"产品|新品|这瓶|这一瓶|这款",
    re.IGNORECASE,
)
CLAIM_RE = re.compile(
    r"抗老|紧致|暗沉|细腻|嫩亮|出油|痘肌|油皮|毛孔|角质|成分|含量|以上|pitera|"
    r"保湿|修护|提亮|美白|舒缓|滋润|淡纹|肤感|质地|吸收|"
    r"不黏|功效|效果|坚持用|用下来|上脸",
    re.IGNORECASE,
)
HIGH_SIGNAL_CLAIM_RE = re.compile(
    r"控油|控痘|祛痘|抗痘|净痘|痘痘|痘循环|不易长痘|疏通角质|"
    r"调节微生态|人参皂苷|依克多因|乳铁蛋白|植萃|酸复配|"
    r"清爽不闷脸|根源祛痘|根源控油",
    re.IGNORECASE,
)
PRESENTATION_RE = re.compile(
    r"全靠|我用|用的|买的|新买|推荐|选择|做了很多功课|"
    r"给我底气|省了|瓶瓶罐罐|直接一瓶",
    re.IGNORECASE,
)
CTA_RE = re.compile(
    r"购物车|下单|直播间|领券|优惠|折扣|到手价|链接|点击|购买",
    re.IGNORECASE,
)


def normalize_text(value: str) -> str:
    normalized = re.sub(r"[\W_]+", "", value.lower(), flags=re.UNICODE)
    return (
        normalized.replace("sk-ii", "skii")
        .replace("skⅱ", "skii")
        .replace("sk2", "skii")
    )


def title_tokens(title: str) -> list[str]:
    values: list[str] = []
    for raw in re.findall(r"#([^\s#]+)", title):
        value = normalize_text(raw)
        if len(value) >= 2 and value not in values:
            values.append(value)
    return values


def score_segment(text: str, tokens: list[str]) -> tuple[int, list[str]]:
    normalized = normalize_text(text)
    reasons: list[str] = []
    score = 0
    matched_tokens = [token for token in tokens if token and token in normalized]
    if matched_tokens:
        score += 4
        reasons.append("title_hashtag:" + ",".join(matched_tokens))
    if PRODUCT_RE.search(text):
        score += 2
        reasons.append("product_term")
    if HIGH_SIGNAL_CLAIM_RE.search(text):
        score += 2
        reasons.append("high_signal_claim")
    if CLAIM_RE.search(text):
        score += 1
        reasons.append("claim_term")
    if PRESENTATION_RE.search(text):
        score += 1
        reasons.append("presentation_term")
    if CTA_RE.search(text):
        score += 1
        reasons.append("cta_term")
    return score, reasons


def detect_product_signal_windows(
    segments: list[dict[str, Any]],
    *,
    title: str,
    duration: float,
    cluster_gap: float = 3.0,
    context_seconds: float = 1.5,
) -> list[dict[str, Any]]:
    tokens = title_tokens(title)
    hits: list[dict[str, Any]] = []
    for segment in segments:
        text = str(segment.get("text", "")).strip()
        score, reasons = score_segment(text, tokens)
        if score < 1:
            continue
        hits.append(
            {
                "start": float(segment.get("start", 0)),
                "end": float(segment.get("end", segment.get("start", 0))),
                "text": text,
                "score": score,
                "reasons": reasons,
                "frame_path": str(segment.get("frame_path", "")),
            }
        )

    clusters: list[list[dict[str, Any]]] = []
    for hit in hits:
        if not clusters or hit["start"] - clusters[-1][-1]["end"] > cluster_gap:
            clusters.append([hit])
        else:
            clusters[-1].append(hit)

    windows: list[dict[str, Any]] = []
    for index, cluster in enumerate(clusters, start=1):
        if max(int(item["score"]) for item in cluster) < 2:
            continue
        start = min(item["start"] for item in cluster)
        end = max(item["end"] for item in cluster)
        windows.append(
            {
                "id": f"product-signal-{index}",
                "status": "review_required",
                "signal_start": start,
                "signal_end": end,
                "context_start": max(0.0, start - context_seconds),
                "context_end": min(duration, end + context_seconds),
                "score": sum(int(item["score"]) for item in cluster),
                "signals": cluster,
            }
        )
    return windows


def build_timeline_blocks(
    segments: list[dict[str, Any]],
    *,
    duration: float,
    block_seconds: float = 15.0,
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    block_count = max(1, math.ceil(duration / block_seconds))
    for index in range(block_count):
        start = index * block_seconds
        end = min(duration, start + block_seconds)
        texts = [
            str(item.get("text", "")).strip()
            for item in segments
            if float(item.get("start", 0)) < end
            and float(item.get("end", item.get("start", 0))) > start
            and str(item.get("text", "")).strip()
        ]
        blocks.append(
            {
                "start": start,
                "end": end,
                "text": " / ".join(dict.fromkeys(texts)),
            }
        )
    return blocks


def review_timestamps(
    windows: list[dict[str, Any]],
    *,
    duration: float,
    mode: str,
    candidate_frames: list[dict[str, Any]] | None = None,
) -> list[float]:
    values = [min(0.5, duration)]
    points = 9 if mode == "forensic" else 7
    candidates = candidate_frames or []
    for window in windows:
        start = float(window["context_start"])
        end = float(window["context_end"])
        if end <= start:
            values.append(start)
            continue
        in_window = [
            float(item.get("timestamp", 0))
            for item in candidates
            if start <= float(item.get("timestamp", 0)) <= end
        ]
        if in_window:
            if len(in_window) > points:
                selected_indices = {
                    round(index * (len(in_window) - 1) / (points - 1))
                    for index in range(points)
                }
                in_window = [
                    value
                    for index, value in enumerate(in_window)
                    if index in selected_indices
                ]
            values.extend(in_window)
            values.extend([start, end])
        else:
            for index in range(points):
                values.append(start + (end - start) * index / (points - 1))
    deduped: list[float] = []
    for value in sorted(values):
        rounded = round(max(0.0, min(duration, value)), 3)
        if not deduped or abs(rounded - deduped[-1]) >= 0.15:
            deduped.append(rounded)
    limit = 24 if mode == "forensic" else 15
    return deduped[:limit]


def extract_review_frames(
    video: Path,
    timestamps: list[float],
    output_dir: Path,
    *,
    force: bool,
) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = find_binary("ffmpeg")
    frames: list[dict[str, Any]] = []
    for index, timestamp in enumerate(timestamps, start=1):
        output = output_dir / f"review-{index:02d}.jpg"
        if force or not output.is_file():
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
        frames.append({"timestamp": timestamp, "path": str(output)})
    return frames


def reuse_candidate_frame_paths(
    review_frames: list[dict[str, Any]],
    candidate_frames: list[dict[str, Any]],
    *,
    tolerance_seconds: float = 0.01,
) -> list[dict[str, Any]]:
    candidates = [
        {
            "timestamp": float(item.get("timestamp", 0)),
            "path": str(item.get("path", "")),
        }
        for item in candidate_frames
        if str(item.get("path", ""))
    ]
    for item in review_frames:
        timestamp = float(item.get("timestamp", 0))
        if not candidates:
            break
        nearest = min(
            candidates,
            key=lambda candidate: abs(candidate["timestamp"] - timestamp),
        )
        if (
            abs(nearest["timestamp"] - timestamp) <= tolerance_seconds
            and Path(nearest["path"]).is_file()
        ):
            item["path"] = nearest["path"]
            item["source"] = "candidate"
        else:
            item["source"] = "precise"
    return review_frames


def _scaled(image: Image.Image, width: int, height: int) -> Image.Image:
    return ImageOps.contain(
        image.convert("RGB"),
        (width, height),
        Image.Resampling.LANCZOS,
    )


def build_review_board(
    contact_sheets: list[Path],
    review_frames: list[dict[str, Any]],
    output: Path,
) -> None:
    board_width = 1000
    margin = 16
    label_h = 30
    font = ImageFont.load_default()
    sections: list[Image.Image] = []

    for index, path in enumerate(contact_sheets, start=1):
        if not path.is_file():
            continue
        with Image.open(path) as opened:
            image = _scaled(opened, board_width - margin * 2, 2400)
        section = Image.new(
            "RGB",
            (board_width, image.height + label_h + margin),
            "white",
        )
        draw = ImageDraw.Draw(section)
        draw.text((margin, 8), f"Global contact sheet {index}", fill="#111827", font=font)
        section.paste(image, ((board_width - image.width) // 2, label_h))
        sections.append(section)

    if review_frames:
        columns = 4
        cell_w = board_width // columns
        image_h = 390
        cell_h = image_h + label_h
        rows = math.ceil(len(review_frames) / columns)
        grid = Image.new("RGB", (board_width, rows * cell_h + label_h), "white")
        draw = ImageDraw.Draw(grid)
        draw.text((margin, 8), "Product-signal review frames", fill="#111827", font=font)
        for index, item in enumerate(review_frames):
            path = Path(item["path"])
            if not path.is_file():
                continue
            with Image.open(path) as opened:
                image = _scaled(opened, cell_w - 12, image_h - 12)
            x = (index % columns) * cell_w
            y = label_h + (index // columns) * cell_h
            grid.paste(
                image,
                (x + (cell_w - image.width) // 2, y + (image_h - image.height) // 2),
            )
            draw.text(
                (x + 8, y + image_h + 7),
                format_timestamp(float(item["timestamp"])),
                fill="#111827",
                font=font,
            )
        sections.append(grid)

    if not sections:
        raise RuntimeError("No review images were available.")
    canvas = Image.new(
        "RGB",
        (board_width, sum(section.height for section in sections)),
        "white",
    )
    y = 0
    for section in sections:
        canvas.paste(section, (0, y))
        y += section.height
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, quality=90, optimize=True)


def write_text_packet(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        f"VIDEO: {payload['video']['title']}",
        f"DURATION: {payload['video']['duration_seconds']:.3f}s",
        f"SUBTITLE COVERAGE: {payload['transcript_coverage']}",
        "",
        "OPENING",
        str(payload.get("opening", {}).get("quote", "")),
        "",
        "TIMELINE BLOCKS",
    ]
    for block in payload.get("timeline_blocks", []):
        lines.append(
            f"[{format_timestamp(block['start'])}-{format_timestamp(block['end'])}] "
            f"{block['text']}"
        )
    lines.extend(["", "UNCONFIRMED PRODUCT-SIGNAL WINDOWS"])
    for window in payload.get("product_signal_windows", []):
        quote = " / ".join(item["text"] for item in window["signals"])
        lines.append(
            f"[{format_timestamp(window['context_start'])}-"
            f"{format_timestamp(window['context_end'])}] {quote}"
        )
    lines.extend(
        [
            "",
            "These windows are review hints only. Confirm product presentation,",
            "spoken product name, and selling-point or usage evidence before declaring an ad.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-json", required=True, type=Path)
    parser.add_argument("--transcript-json", required=True, type=Path)
    parser.add_argument("--frames-json", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--mode", choices=["standard", "forensic"], default="standard")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    video_path = args.video_json.resolve()
    transcript_path = args.transcript_json.resolve()
    frames_path = args.frames_json.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    packet_path = output_dir.parent / "review-packet.json"
    board_path = output_dir / "review-board.jpg"
    text_path = output_dir.parent / "review-packet.txt"
    fingerprint = stable_fingerprint(
        {
            "version": 2,
            "mode": args.mode,
            "video": file_fingerprint(video_path),
            "transcript": file_fingerprint(transcript_path),
            "frames": file_fingerprint(frames_path),
        }
    )
    if not args.force and packet_path.is_file() and board_path.is_file():
        cached = read_json(packet_path)
        if cached.get("cache_fingerprint") == fingerprint:
            print(f"CACHED {packet_path}")
            return

    video = read_json(video_path)
    transcript = read_json(transcript_path)
    frames = read_json(frames_path)
    duration = float(video.get("duration_seconds") or transcript.get("duration_seconds") or 0)
    segments = sorted(
        transcript.get("segments", []),
        key=lambda item: float(item.get("start", 0)),
    )
    windows = detect_product_signal_windows(
        segments,
        title=str(video.get("title", "")),
        duration=duration,
    )
    timestamps = review_timestamps(
        windows,
        duration=duration,
        mode=args.mode,
        candidate_frames=frames.get("frames", []),
    )
    review_frames = extract_review_frames(
        Path(video["local_video_path"]).resolve(),
        timestamps,
        output_dir / "precise-frames",
        force=args.force,
    )
    review_frames = reuse_candidate_frame_paths(
        review_frames,
        frames.get("frames", []),
    )
    for window in windows:
        window["review_frames"] = [
            item
            for item in review_frames
            if float(window["context_start"])
            <= float(item["timestamp"])
            <= float(window["context_end"])
        ]

    contact_sheets = [Path(value).resolve() for value in frames.get("contact_sheets", [])]
    build_review_board(contact_sheets, review_frames, board_path)
    opening_segments = [
        item for item in segments if float(item.get("start", 0)) <= 3.0
    ]
    opening = {
        "start": 0.0,
        "end": max(
            (float(item.get("end", item.get("start", 0))) for item in opening_segments),
            default=min(3.0, duration),
        ),
        "quote": " / ".join(
            dict.fromkeys(str(item.get("text", "")).strip() for item in opening_segments)
        ),
        "frame_path": str(review_frames[0]["path"]) if review_frames else "",
    }
    payload = {
        "cache_fingerprint": fingerprint,
        "version": 2,
        "mode": args.mode,
        "video": {
            "video_id": video.get("video_id", ""),
            "title": video.get("title", ""),
            "duration_seconds": duration,
            "local_video_path": video.get("local_video_path", ""),
        },
        "transcript_coverage": transcript.get("coverage", "unknown"),
        "metrics": {
            "transcript_segments": len(segments),
            "candidate_frames": len(frames.get("frames", [])),
            "product_signal_windows": len(windows),
            "review_frames": len(review_frames),
        },
        "opening": opening,
        "timeline_blocks": build_timeline_blocks(segments, duration=duration),
        "product_signal_windows": windows,
        "review_frames": review_frames,
        "global_contact_sheets": [str(path) for path in contact_sheets],
        "review_board_path": str(board_path),
        "review_note": (
            "Product-signal windows are unconfirmed hints. Apply the full product-ad "
            "rule before recording an interval."
        ),
    }
    write_json(packet_path, payload)
    write_text_packet(text_path, payload)
    print(packet_path)


if __name__ == "__main__":
    main()
