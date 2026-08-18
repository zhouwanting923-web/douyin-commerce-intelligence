#!/usr/bin/env python3
"""Build a polished Chinese PDF report from validated analysis JSON."""

from __future__ import annotations

import argparse
import html
import os
from pathlib import Path
from typing import Any

from PIL import Image as PILImage
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    KeepTogether,
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from _common import format_timestamp, read_json, resolve_artifact_path


FONT = "CodexCJK"
FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
]
SLOT_LABELS = {
    "cover": "封面",
    "product_alone": "产品单独展示",
    "product_detail": "产品细节/质地",
    "selling_point": "核心卖点",
    "use_process_1": "使用过程一",
    "use_process_2": "使用过程二",
    "after_effect": "使用后效果",
}
NAVY = colors.HexColor("#18324A")
BLUE = colors.HexColor("#2F6FA3")
PALE_BLUE = colors.HexColor("#EAF2F8")
PALE_GREEN = colors.HexColor("#EAF6F1")
LIGHT_GRAY = colors.HexColor("#F4F6F8")
MID_GRAY = colors.HexColor("#667085")
GRID = colors.HexColor("#D5DCE3")


def register_cjk_font() -> None:
    candidates = []
    if os.environ.get("CODEX_CJK_FONT"):
        candidates.append(os.environ["CODEX_CJK_FONT"])
    candidates.extend(FONT_CANDIDATES)
    errors = []
    for candidate in candidates:
        path = Path(candidate)
        if not path.is_file():
            continue
        try:
            pdfmetrics.registerFont(TTFont(FONT, str(path)))
            return
        except Exception as exc:
            errors.append(f"{path}: {exc}")
    detail = "; ".join(errors) or "no candidate font file found"
    raise RuntimeError(
        "No embeddable CJK font is available. Set CODEX_CJK_FONT to a Chinese TTF/TTC font. "
        + detail
    )


def esc(value: Any) -> str:
    return html.escape(str(value or "")).replace("\n", "<br/>")


def insight_text(value: Any, product_names: set[str]) -> str:
    """Replace exact product names only in section 3 Product Marketing insights."""
    text = str(value or "")
    for product_name in sorted(product_names, key=len, reverse=True):
        if product_name and product_name != "产品":
            text = text.replace(product_name, "产品")
    return text


def format_precise_timestamp(seconds: float) -> str:
    total_tenths = max(0, int(round(float(seconds) * 10)))
    hours, remainder = divmod(total_tenths, 36000)
    minutes, tenths = divmod(remainder, 600)
    secs = tenths / 10
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:04.1f}"
    return f"{minutes:02d}:{secs:04.1f}"


def normalized_ad_intervals(ads: list[dict], video_duration: float) -> list[tuple[float, float]]:
    intervals = []
    for ad in ads:
        start = max(0.0, min(video_duration, float(ad.get("start", 0))))
        end = max(0.0, min(video_duration, float(ad.get("end", 0))))
        if end > start:
            intervals.append((start, end))
    return sorted(intervals)


def merge_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[list[float]] = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(start, end) for start, end in merged]


def product_ad_metrics(ads: list[dict], video_duration: float) -> tuple[float, float]:
    merged = merge_intervals(normalized_ad_intervals(ads, video_duration))
    total_seconds = sum(end - start for start, end in merged)
    share = total_seconds / video_duration * 100 if video_duration > 0 else 0.0
    return total_seconds, share


def timeline_axis(video_duration: float, width: float) -> Drawing:
    drawing = Drawing(width, 7 * mm)
    labels = (
        (0, format_precise_timestamp(0), "start"),
        (width / 2, format_precise_timestamp(video_duration / 2), "middle"),
        (width, format_precise_timestamp(video_duration), "end"),
    )
    for x, label, anchor in labels:
        drawing.add(
            String(
                x,
                2 * mm,
                label,
                fontName=FONT,
                fontSize=7,
                fillColor=MID_GRAY,
                textAnchor=anchor,
            )
        )
    return drawing


def timeline_bar(start: float, end: float, video_duration: float, width: float) -> Drawing:
    drawing = Drawing(width, 7 * mm)
    track_y = 2 * mm
    track_height = 3 * mm
    drawing.add(Rect(0, track_y, width, track_height, fillColor=LIGHT_GRAY, strokeColor=GRID, strokeWidth=0.4))
    if video_duration > 0 and end > start:
        x = width * start / video_duration
        bar_width = max(1.2, width * (end - start) / video_duration)
        bar_width = min(bar_width, width - x)
        drawing.add(Rect(x, track_y, bar_width, track_height, fillColor=BLUE, strokeColor=BLUE, strokeWidth=0))
    return drawing


def product_ad_timeline(ads: list[dict], video_duration: float, styles: dict) -> Table:
    timeline_width = 126 * mm
    rows = [[Paragraph("确认广告片段", styles["small"]), timeline_axis(video_duration, timeline_width)]]
    ordered_ads = sorted(ads, key=lambda item: float(item.get("start", 0)))
    if ordered_ads:
        for index, ad in enumerate(ordered_ads, start=1):
            start = max(0.0, min(video_duration, float(ad.get("start", 0))))
            end = max(0.0, min(video_duration, float(ad.get("end", 0))))
            product_name = ad.get("product_name") or "未识别产品"
            label = (
                f"{index}. {esc(product_name)}<br/>"
                f"{format_precise_timestamp(start)}–{format_precise_timestamp(end)}"
            )
            rows.append(
                [
                    Paragraph(label, styles["small"]),
                    timeline_bar(start, end, video_duration, timeline_width),
                ]
            )
    else:
        rows.append(
            [
                Paragraph("未检测到", styles["small"]),
                timeline_bar(0, 0, video_duration, timeline_width),
            ]
        )

    table = Table(rows, colWidths=[44 * mm, timeline_width], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), PALE_BLUE),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
                ("GRID", (0, 0), (-1, -1), 0.4, GRID),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def image_flowable(path: Path, max_width: float, max_height: float) -> Image:
    with PILImage.open(path) as source:
        width, height = source.size
    scale = min(max_width / width, max_height / height)
    return Image(str(path), width=width * scale, height=height * scale)


def load_transcript(data: dict, analysis_dir: Path) -> list[dict]:
    transcript = data.get("transcript", {})
    segments = transcript.get("segments", [])
    if segments:
        return segments
    path_value = transcript.get("path", "")
    if path_value:
        payload = read_json(resolve_artifact_path(analysis_dir, path_value))
        return payload.get("segments", [])
    return []


def build_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "TitleCN",
            parent=base["Title"],
            fontName=FONT,
            fontSize=22,
            leading=28,
            textColor=NAVY,
            spaceAfter=8,
            wordWrap="CJK",
        ),
        "subtitle": ParagraphStyle(
            "SubtitleCN",
            parent=base["Normal"],
            fontName=FONT,
            fontSize=9.5,
            leading=14,
            textColor=MID_GRAY,
            spaceAfter=12,
            wordWrap="CJK",
        ),
        "h1": ParagraphStyle(
            "H1CN",
            parent=base["Heading1"],
            fontName=FONT,
            fontSize=15,
            leading=20,
            textColor=NAVY,
            spaceBefore=10,
            spaceAfter=7,
            wordWrap="CJK",
        ),
        "h2": ParagraphStyle(
            "H2CN",
            parent=base["Heading2"],
            fontName=FONT,
            fontSize=11.5,
            leading=16,
            textColor=BLUE,
            spaceBefore=7,
            spaceAfter=5,
            wordWrap="CJK",
        ),
        "body": ParagraphStyle(
            "BodyCN",
            parent=base["BodyText"],
            fontName=FONT,
            fontSize=9.5,
            leading=15,
            textColor=colors.HexColor("#20262E"),
            spaceAfter=5,
            wordWrap="CJK",
        ),
        "small": ParagraphStyle(
            "SmallCN",
            parent=base["BodyText"],
            fontName=FONT,
            fontSize=8,
            leading=11,
            textColor=MID_GRAY,
            wordWrap="CJK",
        ),
        "center": ParagraphStyle(
            "CenterCN",
            parent=base["BodyText"],
            fontName=FONT,
            fontSize=9,
            leading=13,
            alignment=TA_CENTER,
            wordWrap="CJK",
        ),
    }


def key_value_table(rows: list[tuple[str, Any]], styles: dict) -> Table:
    data = [
        [Paragraph(esc(label), styles["small"]), Paragraph(esc(value), styles["body"])]
        for label, value in rows
    ]
    table = Table(data, colWidths=[34 * mm, 136 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), PALE_BLUE),
                ("GRID", (0, 0), (-1, -1), 0.4, GRID),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def make_screenshot_card(item: dict, analysis_dir: Path, styles: dict) -> list:
    label = SLOT_LABELS.get(item.get("slot", ""), item.get("slot", ""))
    if item.get("status") != "selected" or not item.get("path"):
        return [
            Spacer(1, 18 * mm),
            Paragraph(f"{esc(label)}<br/>未检测到", styles["center"]),
            Spacer(1, 18 * mm),
        ]
    path = resolve_artifact_path(analysis_dir, item["path"])
    image = image_flowable(path, 72 * mm, 68 * mm)
    caption = (
        f"{esc(label)} | {format_timestamp(float(item.get('timestamp', 0)))}<br/>"
        f"{esc(item.get('scene_description', ''))}"
    )
    return [image, Spacer(1, 2 * mm), Paragraph(caption, styles["small"])]


def header_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont(FONT, 8)
    canvas.setFillColor(MID_GRAY)
    canvas.drawString(18 * mm, 12 * mm, "抖音 Social 种草视频拆解")
    canvas.drawRightString(A4[0] - 18 * mm, 12 * mm, f"第 {doc.page} 页")
    canvas.setStrokeColor(GRID)
    canvas.setLineWidth(0.4)
    canvas.line(18 * mm, 16 * mm, A4[0] - 18 * mm, 16 * mm)
    canvas.restoreState()


def build_report(analysis_path: Path, output_path: Path) -> None:
    register_cjk_font()
    data = read_json(analysis_path)
    analysis_dir = analysis_path.parent
    styles = build_styles()
    video = data["video"]
    classification = data["classification"]
    transcript = load_transcript(data, analysis_dir)
    product_names = {
        str(ad.get("product_name", "")).strip()
        for ad in data.get("product_ads", [])
        if str(ad.get("product_name", "")).strip()
    }

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=22 * mm,
        title=video.get("title") or "抖音 Social 种草视频拆解",
        author="Codex",
    )
    story: list = []

    story.append(Paragraph("抖音 Social 种草视频拆解", styles["title"]))
    story.append(Paragraph(esc(video.get("title", "")), styles["subtitle"]))
    story.append(
        key_value_table(
            [
                ("视频ID", video.get("video_id", "")),
                ("视频时长", f"{float(video.get('duration_seconds', 0)):.1f} 秒"),
                ("博主", video.get("creator") or "未识别"),
                ("原始链接", video.get("source_url", "")),
            ],
            styles,
        )
    )

    story.append(Paragraph("1. 视频打标", styles["h1"]))
    label = f"{classification.get('primary', '')} / {classification.get('secondary', '')}"
    story.append(
        key_value_table(
            [
                ("判定结果", label),
                ("置信度", classification.get("confidence", "")),
                ("判定理由", classification.get("rationale", "")),
                ("排除逻辑", classification.get("exclusion_rationale", "")),
            ],
            styles,
        )
    )
    evidence_rows = [[Paragraph("时间/来源", styles["small"]), Paragraph("证据", styles["small"])]]
    for item in classification.get("positive_evidence", []):
        timing = f"{format_timestamp(float(item.get('start', 0)))}-{format_timestamp(float(item.get('end', 0)))} / {item.get('source', '')}"
        quote = item.get("quote") or item.get("frame_path") or ""
        evidence_rows.append([Paragraph(esc(timing), styles["small"]), Paragraph(esc(quote), styles["body"])])
    evidence_table = LongTable(evidence_rows, colWidths=[45 * mm, 125 * mm], repeatRows=1)
    evidence_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, GRID),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend([Spacer(1, 4 * mm), evidence_table])

    story.append(Paragraph("2. 产品广告出现时间", styles["h1"]))
    ads = data.get("product_ads", [])
    video_duration = float(video.get("duration_seconds", 0))
    ad_seconds, ad_share = product_ad_metrics(ads, video_duration)
    story.append(product_ad_timeline(ads, video_duration, styles))
    story.append(Spacer(1, 3 * mm))
    story.append(
        Paragraph(
            f"广告片段总时长：<b>{ad_seconds:.1f} 秒</b>（占视频 <b>{ad_share:.1f}%</b>）",
            styles["body"],
        )
    )

    insight = data.get("marketing_insight", {})
    activation_text = insight_text(
        insight.get("activation_implication", {}).get("text", ""),
        product_names,
    )
    potential_topics = [
        str(topic).strip()
        for topic in insight.get("potential_topics", [])
        if str(topic).strip()
    ]
    if potential_topics:
        activation_text = f"{activation_text} 潜力话题：{' '.join(potential_topics)}"
    insight_table = Table(
        [
            [Paragraph("内容价值", styles["small"]), Paragraph(esc(insight_text(insight.get("content_value", {}).get("text", ""), product_names)), styles["body"])],
            [Paragraph("产品认知", styles["small"]), Paragraph(esc(insight_text(insight.get("product_perception", {}).get("text", ""), product_names)), styles["body"])],
            [Paragraph("营销启示", styles["small"]), Paragraph(esc(activation_text), styles["body"])],
        ],
        colWidths=[36 * mm, 134 * mm],
    )
    insight_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), PALE_GREEN),
                ("GRID", (0, 0), (-1, -1), 0.4, GRID),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(
        KeepTogether(
            [Paragraph("3. Product Marketing 洞察", styles["h1"]), insight_table]
        )
    )

    story.append(Paragraph("4. 关键截图", styles["h1"]))
    cards = [make_screenshot_card(item, analysis_dir, styles) for item in data.get("screenshots", [])]
    grid_rows = []
    for index in range(0, len(cards), 2):
        row = [cards[index]]
        row.append(cards[index + 1] if index + 1 < len(cards) else "")
        grid_rows.append(row)
    grid = Table(grid_rows, colWidths=[85 * mm, 85 * mm], hAlign="LEFT")
    grid.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, GRID),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, GRID),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(grid)

    story.append(PageBreak())
    story.append(Paragraph("5. 视频字幕文字稿", styles["h1"]))
    transcript_rows = [[Paragraph("时间", styles["small"]), Paragraph("文字稿", styles["small"])]]
    for segment in transcript:
        timing = f"{format_timestamp(float(segment.get('start', 0)))}-{format_timestamp(float(segment.get('end', 0)))}"
        source = segment.get("source", "")
        text = f"[{source}] {segment.get('text', '')}"
        transcript_rows.append([Paragraph(esc(timing), styles["small"]), Paragraph(esc(text), styles["body"])])
    transcript_table = LongTable(transcript_rows, colWidths=[32 * mm, 138 * mm], repeatRows=1)
    transcript_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
                ("GRID", (0, 0), (-1, -1), 0.35, GRID),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(transcript_table)

    limitations = data.get("limitations", [])
    if limitations:
        story.append(Paragraph("识别限制", styles["h2"]))
        for limitation in limitations:
            story.append(Paragraph(f"- {esc(limitation)}", styles["body"]))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    build_report(args.analysis.resolve(), args.output.resolve())
    print(args.output.resolve())


if __name__ == "__main__":
    main()
