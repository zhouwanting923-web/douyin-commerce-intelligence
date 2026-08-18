#!/usr/bin/env python3
"""Create a complete analysis JSON skeleton from prepared artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from _common import probe_duration, read_json, write_json


SLOTS = [
    "cover",
    "product_alone",
    "product_detail",
    "selling_point",
    "use_process_1",
    "use_process_2",
    "after_effect",
]


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _sample_timeline_blocks(
    blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    non_empty = [
        block
        for block in blocks
        if str(block.get("text", "")).strip()
    ]
    if not non_empty:
        return []
    positions = {
        0,
        round((len(non_empty) - 1) / 2),
        len(non_empty) - 1,
    }
    return [non_empty[index] for index in sorted(positions)]


def _closest_frame(
    timestamp: float,
    frames: list[dict[str, Any]],
) -> dict[str, Any]:
    available = [
        item
        for item in frames
        if str(item.get("path", "")).strip()
    ]
    if not available:
        return {}
    return min(
        available,
        key=lambda item: abs(_float(item.get("timestamp")) - timestamp),
    )


def _group_product_windows(
    windows: list[dict[str, Any]],
    *,
    maximum_gap_seconds: float = 30.0,
) -> list[list[dict[str, Any]]]:
    grouped: list[list[dict[str, Any]]] = []
    for window in sorted(
        windows,
        key=lambda item: _float(item.get("context_start")),
    ):
        if (
            not grouped
            or _float(window.get("context_start"))
            - _float(grouped[-1][-1].get("context_end"))
            > maximum_gap_seconds
        ):
            grouped.append([window])
        else:
            grouped[-1].append(window)
    return grouped


def build_prefill_assistance(
    review_packet: dict[str, Any],
    frame_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build auditable draft fields without confirming labels or advertisements."""
    registry: dict[str, dict[str, Any]] = {}
    classification_refs: list[dict[str, str]] = []
    timeline_blocks = review_packet.get("timeline_blocks", [])
    if isinstance(timeline_blocks, list):
        for index, block in enumerate(
            _sample_timeline_blocks(timeline_blocks),
            start=1,
        ):
            start = _float(block.get("start"))
            end = _float(block.get("end"), start)
            frame = _closest_frame((start + end) / 2, frame_candidates)
            reference = f"timeline_sample_{index}"
            registry[reference] = {
                "summary": "自动预填的时间轴标签证据候选；提交前确认其与最终标签判断的关系。",
                "evidence_type": "spoken_claim",
                "start": start,
                "end": end,
                "source": "ocr",
                "quote": str(block.get("text", "")).strip(),
                "frame_path": str(frame.get("path", "")),
            }
            classification_refs.append({"evidence_ref": reference})

    product_windows = review_packet.get("product_signal_windows", [])
    if not isinstance(product_windows, list):
        product_windows = []
    duration = _float(
        review_packet.get("video", {}).get("duration_seconds"),
    )
    ad_drafts: list[dict[str, Any]] = []
    for index, window_group in enumerate(
        _group_product_windows(product_windows),
        start=1,
    ):
        signals = [
            signal
            for window in window_group
            for signal in (
                window.get("signals", [])
                if isinstance(window.get("signals", []), list)
                else []
            )
        ]
        quotes = [
            str(item.get("text", "")).strip()
            for item in signals
            if str(item.get("text", "")).strip()
        ]
        review_frames = [
            frame
            for window in window_group
            for frame in (
                window.get("review_frames", [])
                if isinstance(window.get("review_frames", []), list)
                else []
            )
        ]
        signal_start = min(
            (_float(window.get("signal_start")) for window in window_group),
            default=0.0,
        )
        signal_end = max(
            (_float(window.get("signal_end")) for window in window_group),
            default=signal_start,
        )
        candidate_start = min(
            (_float(window.get("context_start")) for window in window_group),
            default=signal_start,
        )
        candidate_end = max(
            (_float(window.get("context_end")) for window in window_group),
            default=signal_end,
        ) + 30.0
        if duration > 0:
            candidate_end = min(duration, candidate_end)
        ad_drafts.append(
            {
                "id": f"ad-draft-{index}",
                "status": "review_required",
                "candidate_start": candidate_start,
                "candidate_end": candidate_end,
                "signal_start": signal_start,
                "signal_end": signal_end,
                "source_window_ids": [
                    str(window.get("id", ""))
                    for window in window_group
                    if str(window.get("id", ""))
                ],
                "product_name": "",
                "product_name_quote": quotes[0] if quotes else "",
                "efficacy_quotes": quotes[1:],
                "holding_or_presenting": None,
                "review_frames": review_frames,
                "confirmation_rule": (
                    "Only promote to product_ads after confirming deliberate "
                    "presentation, spoken name or alias, and a selling point or "
                    "usage experience in one continuous context."
                ),
            }
        )

    review_frames = review_packet.get("review_frames", [])
    if not isinstance(review_frames, list):
        review_frames = []
    opening = review_packet.get("opening", {})
    opening_path = str(opening.get("frame_path", ""))
    opening_timestamp = 0.0
    for item in review_frames:
        if str(item.get("path", "")) == opening_path:
            opening_timestamp = _float(item.get("timestamp"))
            break

    product_frame_candidates: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for window in product_windows:
        start = _float(window.get("context_start"))
        end = _float(window.get("context_end")) + 15.0
        for item in frame_candidates:
            timestamp = _float(item.get("timestamp"))
            path = str(item.get("path", "")).strip()
            if path and start <= timestamp <= end and path not in seen_paths:
                seen_paths.add(path)
                product_frame_candidates.append(
                    {"timestamp": timestamp, "path": path, "source": "candidate"}
                )
    product_frame_candidates.sort(key=lambda item: item["timestamp"])

    preferred_suggestions: dict[str, dict[str, Any]] = {}
    for slot, item in zip(
        ("product_alone", "product_detail", "selling_point"),
        product_frame_candidates[:3],
    ):
        preferred_suggestions[slot] = item
    if product_windows:
        last_window = max(
            product_windows,
            key=lambda item: _float(item.get("context_end")),
        )
        last_start = _float(last_window.get("context_start"))
        last_end = _float(last_window.get("context_end"))
        last_review_frames = sorted(
            [
                {
                    "timestamp": _float(item.get("timestamp")),
                    "path": str(item.get("path", "")),
                    "source": str(item.get("source", "review")),
                }
                for item in last_window.get("review_frames", [])
                if str(item.get("path", "")).strip()
                and _float(item.get("timestamp")) >= last_start
            ],
            key=lambda item: item["timestamp"],
        )
        if last_review_frames:
            preferred_suggestions["use_process_1"] = last_review_frames[0]
        use_process_2 = [
            item
            for item in product_frame_candidates
            if item["timestamp"] <= last_end + 1.0
        ]
        if use_process_2:
            preferred_suggestions["use_process_2"] = use_process_2[-1]
        after_effect = [
            item
            for item in product_frame_candidates
            if item["timestamp"] >= last_end + 3.0
        ]
        if after_effect:
            preferred_suggestions["after_effect"] = after_effect[0]

    screenshot_drafts: list[dict[str, Any]] = []
    used_suggestion_paths: set[str] = set()
    for slot in SLOTS:
        if slot == "cover":
            suggested = (
                {
                    "timestamp": opening_timestamp,
                    "path": opening_path,
                    "source": "opening",
                }
                if opening_path
                else {}
            )
            alternates: list[dict[str, Any]] = []
        else:
            suggested = preferred_suggestions.get(slot, {})
            if (
                suggested
                and str(suggested.get("path", "")) in used_suggestion_paths
            ):
                suggested = {}
            if not suggested:
                suggested = next(
                    (
                        item
                        for item in product_frame_candidates
                        if str(item.get("path", ""))
                        not in used_suggestion_paths
                    ),
                    {},
                )
            if suggested:
                used_suggestion_paths.add(str(suggested.get("path", "")))
            alternates = [
                item
                for item in product_frame_candidates
                if item != suggested
                and str(item.get("path", "")) not in used_suggestion_paths
            ][:3]
        screenshot_drafts.append(
            {
                "slot": slot,
                "status": "review_required",
                "suggested": suggested,
                "alternates": alternates,
            }
        )

    return {
        "evidence_registry": registry,
        "classification_evidence": classification_refs,
        "draft_assistance": {
            "status": "review_required",
            "classification_evidence": classification_refs,
            "product_ads": ad_drafts,
            "screenshots": screenshot_drafts,
            "instructions": (
                "Confirm the primary/secondary label, promote only verified ad "
                "drafts to product_ads, and accept or replace each screenshot "
                "suggestion before finalization."
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-json", required=True, type=Path)
    parser.add_argument("--transcript-json", required=True, type=Path)
    parser.add_argument("--frames-json", required=True, type=Path)
    parser.add_argument("--evidence-json", type=Path)
    parser.add_argument("--review-packet-json", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--mode",
        choices=["standard", "forensic"],
        default="standard",
    )
    args = parser.parse_args()

    video = read_json(args.video_json)
    transcript = read_json(args.transcript_json)
    frames = read_json(args.frames_json)
    local_video = Path(video["local_video_path"])
    duration = transcript.get("duration_seconds") or frames.get("duration_seconds")
    if not duration and local_video.is_file():
        duration = probe_duration(local_video)

    output_path = args.output.resolve()
    output_dir = output_path.parent
    review_packet = (
        read_json(args.review_packet_json.resolve())
        if args.review_packet_json and args.review_packet_json.is_file()
        else {}
    )

    def artifact_path(path: Path) -> str:
        resolved = path.resolve()
        try:
            return str(resolved.relative_to(output_dir))
        except ValueError:
            return str(resolved)

    prefill = build_prefill_assistance(
        review_packet,
        frames.get("frames", []),
    )
    evidence_registry = dict(prefill["evidence_registry"])
    opening = review_packet.get("opening", {})
    if opening.get("quote") or opening.get("frame_path"):
        evidence_registry["opening"] = {
            "summary": "自动预填的开场字幕与候选帧；提交前结合画面确认其叙事作用。",
            "evidence_type": "observed_action",
            "start": min(3.0, max(0.0, _float(opening.get("start", 0)))),
            "end": float(opening.get("end", 0)),
            "source": "ocr",
            "quote": str(opening.get("quote", "")),
            "frame_path": str(opening.get("frame_path", "")),
        }
    for index, window in enumerate(
        review_packet.get("product_signal_windows", []),
        start=1,
    ):
        signals = window.get("signals", [])
        review_frames = window.get("review_frames", [])
        evidence_registry[f"product_signal_{index}"] = {
            "summary": "自动聚合的产品语言信号窗口；需人工确认产品展示、名称与卖点是否在同一连续语境。",
            "evidence_type": "spoken_claim",
            "start": float(window.get("signal_start", 0)),
            "end": float(window.get("signal_end", 0)),
            "source": "ocr",
            "quote": " / ".join(
                dict.fromkeys(
                    str(item.get("text", "")).strip()
                    for item in signals
                    if str(item.get("text", "")).strip()
                )
            ),
            "frame_path": (
                str(review_frames[0].get("path", ""))
                if review_frames
                else ""
            ),
        }

    payload = {
        "runtime": {
            "mode": args.mode,
            "version": 2,
        },
        "video": {
            "source_url": video.get("source_url", ""),
            "normalized_url": video.get("normalized_url", ""),
            "video_id": video.get("video_id", ""),
            "title": video.get("title", ""),
            "creator": video.get("creator", ""),
            "duration_seconds": duration or 0,
            "local_video_path": video.get("local_video_path", ""),
        },
        "classification": {
            "primary": "",
            "secondary": "",
            "confidence": "",
            "rationale": "",
            "positive_evidence": prefill["classification_evidence"],
            "exclusion_rationale": "",
        },
        "product_ads": [],
        "marketing_insight": {
            "content_value": {
                "text": "",
                "evidence": prefill["classification_evidence"],
            },
            "product_perception": {
                "text": "",
                "evidence": [
                    {"evidence_ref": f"product_signal_{index}"}
                    for index in range(
                        1,
                        len(review_packet.get("product_signal_windows", [])) + 1,
                    )
                ],
            },
            "activation_implication": {
                "text": "",
                "evidence": [
                    {"evidence_ref": f"product_signal_{index}"}
                    for index in range(
                        1,
                        len(review_packet.get("product_signal_windows", [])) + 1,
                    )
                ],
            },
            "hook": {
                "mechanism": "",
                "target_circle": "",
                "familiar_motif": "",
                "distinctive_angle": "",
                "narrative_devices": [],
                "evidence": (
                    [{"evidence_ref": "opening"}]
                    if "opening" in evidence_registry
                    else []
                ),
            },
            "scene": {
                "audience": "",
                "occasion": "",
                "pain_point": "",
                "evidence": prefill["classification_evidence"][:1],
            },
            "product_entry": {
                "identity": "",
                "persona_fit": "",
                "integration_bridge": "",
                "evidence": [
                    {"evidence_ref": f"product_signal_{index}"}
                    for index in range(
                        1,
                        len(review_packet.get("product_signal_windows", [])) + 1,
                    )
                ],
            },
            "creator_assets_observed": "",
            "core_product_perception": "",
            "selling_point_strategy": {
                "core_selling_point": "",
                "supporting_points": [],
                "strongest_rtb": {
                    "category": "",
                    "summary": "",
                    "why_it_persuades": "",
                    "evidence_type": "",
                    "start": 0,
                    "end": 0,
                    "source": "",
                    "quote": "",
                    "frame_path": "",
                },
                "deprioritized_mentions": [],
            },
            "rtb": {
                "sensoriality": [],
                "scientific_language": [],
                "proof": [],
            },
            "cta": {
                "detected": False,
                "types": [],
                "purchase_barrier_reduced": "",
                "evidence": [],
            },
            "viewer_payoff": "",
            "consumer_need": "",
            "product_role": "",
            "core_effective_mechanism": "",
            "integration_naturalness_basis": "",
            "integration_chain": [],
            "potential_topics": [],
            "confidence": "",
        },
        "screenshots": [
            {
                "slot": slot,
                "timestamp": 0,
                "path": "",
                "scene_description": "",
                "product_name": "",
                "evidence": "",
                "status": "not_detected",
            }
            for slot in SLOTS
        ],
        "transcript": {
            "path": artifact_path(args.transcript_json),
            "coverage": transcript.get("coverage", "unknown"),
            "segment_count": len(transcript.get("segments", [])),
        },
        "evidence": {
            "path": (
                artifact_path(args.evidence_json)
                if args.evidence_json
                else ""
            )
        },
        "review": {
            "path": (
                artifact_path(args.review_packet_json)
                if args.review_packet_json
                else ""
            ),
            "board_path": str(review_packet.get("review_board_path", "")),
            "product_signal_windows": review_packet.get(
                "product_signal_windows",
                [],
            ),
            "review_frames": review_packet.get("review_frames", []),
            "note": review_packet.get("review_note", ""),
        },
        "evidence_registry": evidence_registry,
        "draft_assistance": prefill["draft_assistance"],
        "frame_candidates": frames.get("frames", []),
        "limitations": [],
    }
    write_json(output_path, payload)
    print(output_path)


if __name__ == "__main__":
    main()
