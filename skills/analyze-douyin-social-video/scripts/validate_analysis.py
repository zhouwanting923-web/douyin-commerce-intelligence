#!/usr/bin/env python3
"""Validate the evidence and completeness of an analysis JSON file."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from _common import read_json, resolve_artifact_path


SECONDARY = {
    "DRAMA": ["剧情演绎/短剧", "连续剧集/IP人物"],
    "SEEDING": [
        "知识科普/搜索答疑",
        "使用教程/方法演示",
        "产品推荐/好物合集",
        "测评/真实体验",
        "效果展示/前后改造",
        "场景化/沉浸式种草",
    ],
    "LIFESTYLE": ["日常Vlog/生活记录", "生活方式/场景内容", "探店/服务体验"],
    "BRANDING": ["品牌广告/Campaign", "代言人/IP/联名", "品牌故事/科技/事件"],
    "OFFER": ["优惠促销/直接售卖", "直播预告", "直播切片/成交高光"],
    "OTHERS": ["非相关内容"],
}
SLOTS = [
    "cover",
    "product_alone",
    "product_detail",
    "selling_point",
    "use_process_1",
    "use_process_2",
    "after_effect",
]
CONFIDENCE = {"high", "medium", "low"}
TARGET_CIRCLES = {"emotion", "problem", "mixed"}
EVIDENCE_TYPES = {
    "observed_action",
    "spoken_claim",
    "user_feedback",
    "displayed_data",
    "external_proof",
    "analyst_inference",
}
EVIDENCE_SOURCES = {"subtitle", "ocr", "visual"}
CTA_TYPES = {
    "threshold_reduction",
    "scene_summary",
    "emotional_permission",
    "direct_action",
}
RTB_CATEGORIES = {"sensoriality", "scientific_language", "proof"}
FUTURE_PLANNING_PATTERNS = (
    r"适合布局",
    r"适合由",
    r"适合与",
    r"由[^，。；]{0,24}KOL承载",
    r"建议复用",
    r"选择优质达人",
    r"降低广告抵触",
    r"降低广告感",
)
EXTERNAL_REVIEW_PATTERNS = (
    r"竞品",
    r"品牌应",
    r"可借鉴",
)
MECHANISM_CUES = (
    "核心生效机制",
    "之所以",
    "因此",
    "使得",
    "让产品",
    "负责",
    "通过",
)
NEGATIVE_CRITIQUE_PHRASES = {
    "不能照搬",
    "不应照搬",
    "不建议复制",
    "而不是照搬",
    "而不是复制",
    "而非照搬",
    "而非复制",
    "若移除产品",
    "不足之处",
    "视频缺点",
    "植入生硬",
    "植入突兀",
    "广告感过强",
    "打断剧情",
    "破坏观看",
    "失败之处",
}
UNSUPPORTED_PERFORMANCE_PHRASES = {
    "提升完播率",
    "提高完播率",
    "拉高完播率",
    "提升停留时长",
    "提高停留时长",
    "提升自然流量",
    "拉高自然流量",
    "带来自然流量",
    "提升转化率",
    "提高转化率",
    "促进转化",
    "带来转化",
    "提升销量",
    "带来销量",
    "提升点击率",
    "提高点击率",
    "预算投入",
    "预算分配",
    "媒体投放",
    "媒介投放",
}


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate_marketing_evidence(
    items: object,
    prefix: str,
    duration: float,
    errors: list[str],
    *,
    require_summary: bool = False,
) -> None:
    if not isinstance(items, list):
        errors.append(f"{prefix} must be a list")
        return
    for index, item in enumerate(items, start=1):
        item_prefix = f"{prefix}[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{item_prefix} must be an object")
            continue
        if require_summary:
            require(bool(str(item.get("summary", "")).strip()), f"{item_prefix}.summary is required", errors)
        require(item.get("evidence_type") in EVIDENCE_TYPES, f"{item_prefix}.evidence_type is invalid", errors)
        require(item.get("source") in EVIDENCE_SOURCES, f"{item_prefix}.source is invalid", errors)
        require(bool(item.get("quote") or item.get("frame_path")), f"{item_prefix} needs a quote or frame_path", errors)
        try:
            start = float(item.get("start"))
            end = float(item.get("end"))
        except (TypeError, ValueError):
            errors.append(f"{item_prefix}: start and end must be numeric")
        else:
            require(0 <= start <= end <= duration, f"{item_prefix}: timestamps are outside video duration", errors)


def load_transcript_segments(
    data: dict,
    base_dir: Path,
    errors: list[str],
) -> list[dict]:
    transcript = data.get("transcript", {})
    if not isinstance(transcript, dict):
        errors.append("transcript must be an object")
        return []
    embedded = transcript.get("segments", [])
    if embedded:
        return embedded if isinstance(embedded, list) else []
    path_value = str(transcript.get("path", "")).strip()
    require(bool(path_value), "transcript.path is required", errors)
    if not path_value:
        return []
    transcript_path = resolve_artifact_path(base_dir, path_value)
    require(transcript_path.is_file(), "transcript.path does not exist", errors)
    if not transcript_path.is_file():
        return []
    try:
        payload = read_json(transcript_path)
    except (OSError, ValueError, TypeError):
        errors.append("transcript.path is not valid JSON")
        return []
    segments = payload.get("segments", [])
    require(isinstance(segments, list), "external transcript.segments must be a list", errors)
    return segments if isinstance(segments, list) else []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("analysis", type=Path)
    args = parser.parse_args()
    analysis_path = args.analysis.resolve()
    base_dir = analysis_path.parent
    data = read_json(analysis_path)
    errors: list[str] = []

    video = data.get("video", {})
    require(bool(video.get("video_id")), "video.video_id is required", errors)
    require(bool(video.get("title")), "video.title is required", errors)
    require(float(video.get("duration_seconds", 0)) > 0, "video.duration_seconds must be > 0", errors)

    classification = data.get("classification", {})
    primary = classification.get("primary")
    secondary = classification.get("secondary")
    require(primary in SECONDARY, "classification.primary is invalid", errors)
    if primary in SECONDARY:
        require(secondary in SECONDARY[primary], "classification.secondary does not match primary", errors)
    require(classification.get("confidence") in CONFIDENCE, "classification.confidence is invalid", errors)
    require(bool(classification.get("rationale")), "classification.rationale is required", errors)
    require(bool(classification.get("positive_evidence")), "classification.positive_evidence is required", errors)
    require(bool(classification.get("exclusion_rationale")), "classification.exclusion_rationale is required", errors)

    insight = data.get("marketing_insight", {})
    insight_fields = (
        "content_value",
        "product_perception",
        "activation_implication",
    )
    insight_texts: list[tuple[str, str]] = []
    for field in insight_fields:
        block = insight.get(field, {})
        text = str(block.get("text", "")).strip() if isinstance(block, dict) else ""
        evidence = block.get("evidence", []) if isinstance(block, dict) else []
        require(bool(text), f"marketing_insight.{field}.text is required", errors)
        require(
            not text.startswith(("内容价值：", "产品认知：", "营销启示：")),
            f"marketing_insight.{field}.text must not repeat its PDF label",
            errors,
        )
        if field == "content_value":
            require(
                not text.startswith(("视频用", "视频把", "视频以")),
                "marketing_insight.content_value.text must begin from the demonstrated creator asset, not a video-summary formula",
                errors,
            )
        if field == "product_perception":
            require(
                "核心卖点" in text,
                "marketing_insight.product_perception.text must explicitly state one core selling point",
                errors,
            )
        require(bool(evidence), f"marketing_insight.{field}.evidence is required", errors)
        insight_texts.append((field, text))
        for index, item in enumerate(evidence, start=1):
            prefix = f"marketing_insight.{field}.evidence[{index}]"
            require("start" in item and "end" in item, f"{prefix} needs timestamps", errors)
            require(bool(item.get("source")), f"{prefix}.source is required", errors)
            require(bool(item.get("quote") or item.get("frame_path")), f"{prefix} needs a quote or frame_path", errors)

    duration = float(video.get("duration_seconds", 0))
    if primary != "OTHERS":
        for field in (
            "viewer_payoff",
            "consumer_need",
            "product_role",
            "creator_assets_observed",
            "core_effective_mechanism",
            "integration_naturalness_basis",
        ):
            require(bool(str(insight.get(field, "")).strip()), f"marketing_insight.{field} is required", errors)

        integration_chain = insight.get("integration_chain", [])
        require(isinstance(integration_chain, list), "marketing_insight.integration_chain must be a list", errors)
        if isinstance(integration_chain, list):
            require(
                3 <= len(integration_chain) <= 5,
                "marketing_insight.integration_chain must contain three to five nodes",
                errors,
            )
            require(
                all(bool(str(node).strip()) for node in integration_chain),
                "marketing_insight.integration_chain nodes must be non-empty",
                errors,
            )
            if 3 <= len(integration_chain) <= 5 and all(bool(str(node).strip()) for node in integration_chain):
                chain_text = "—".join(str(node).strip() for node in integration_chain)
                activation_text = dict(insight_texts).get("activation_implication", "")
                require(
                    chain_text in activation_text,
                    "marketing_insight.activation_implication.text must include the exact integration_chain joined with —",
                    errors,
                )
                require(
                    not activation_text.startswith(chain_text),
                    "marketing_insight.activation_implication.text must explain the causal mechanism before naming the integration chain",
                    errors,
                )

        potential_topics = insight.get("potential_topics", [])
        require(isinstance(potential_topics, list), "marketing_insight.potential_topics must be a list", errors)
        if isinstance(potential_topics, list):
            require(
                1 <= len(potential_topics) <= 2,
                "marketing_insight.potential_topics must contain one or two hashtags",
                errors,
            )
            for index, topic in enumerate(potential_topics, start=1):
                topic_text = str(topic).strip()
                require(bool(topic_text), f"marketing_insight.potential_topics[{index}] must be non-empty", errors)
                require(
                    topic_text.startswith("#"),
                    f"marketing_insight.potential_topics[{index}] must begin with #",
                    errors,
                )
                require(
                    re.search(r"\s|[，。；：！？,.!?]", topic_text) is None,
                    f"marketing_insight.potential_topics[{index}] must be a single hashtag without whitespace or sentence punctuation",
                    errors,
                )
                require(
                    "热点" not in topic_text,
                    f"marketing_insight.potential_topics[{index}] must not claim verified hotspot status",
                    errors,
                )

        hook = insight.get("hook", {})
        require(isinstance(hook, dict), "marketing_insight.hook must be an object", errors)
        if isinstance(hook, dict):
            require(bool(str(hook.get("mechanism", "")).strip()), "marketing_insight.hook.mechanism is required", errors)
            require(hook.get("target_circle") in TARGET_CIRCLES, "marketing_insight.hook.target_circle is invalid", errors)
            require(
                bool(str(hook.get("familiar_motif", "")).strip())
                or bool(str(hook.get("distinctive_angle", "")).strip()),
                "marketing_insight.hook needs a familiar_motif or distinctive_angle",
                errors,
            )
            require(bool(hook.get("narrative_devices")), "marketing_insight.hook.narrative_devices is required", errors)
            hook_evidence = hook.get("evidence", [])
            require(bool(hook_evidence), "marketing_insight.hook.evidence is required", errors)
            validate_marketing_evidence(hook_evidence, "marketing_insight.hook.evidence", duration, errors)
            for index, item in enumerate(hook_evidence, start=1):
                try:
                    start = float(item.get("start"))
                except (AttributeError, TypeError, ValueError):
                    continue
                require(start <= 3.0, f"marketing_insight.hook.evidence[{index}] must begin in the first three seconds", errors)

        scene = insight.get("scene", {})
        require(isinstance(scene, dict), "marketing_insight.scene must be an object", errors)
        if isinstance(scene, dict):
            for field in ("audience", "occasion", "pain_point"):
                require(bool(str(scene.get(field, "")).strip()), f"marketing_insight.scene.{field} is required", errors)
            scene_evidence = scene.get("evidence", [])
            require(bool(scene_evidence), "marketing_insight.scene.evidence is required", errors)
            validate_marketing_evidence(scene_evidence, "marketing_insight.scene.evidence", duration, errors)

    if data.get("product_ads"):
        product_entry = insight.get("product_entry", {})
        require(isinstance(product_entry, dict), "marketing_insight.product_entry must be an object", errors)
        if isinstance(product_entry, dict):
            for field in ("identity", "persona_fit", "integration_bridge"):
                require(
                    bool(str(product_entry.get(field, "")).strip()),
                    f"marketing_insight.product_entry.{field} is required",
                    errors,
                )
            product_entry_evidence = product_entry.get("evidence", [])
            require(bool(product_entry_evidence), "marketing_insight.product_entry.evidence is required", errors)
            validate_marketing_evidence(
                product_entry_evidence,
                "marketing_insight.product_entry.evidence",
                duration,
                errors,
            )

        require(
            bool(str(insight.get("core_product_perception", "")).strip()),
            "marketing_insight.core_product_perception is required",
            errors,
        )
        selling_point_strategy = insight.get("selling_point_strategy", {})
        require(
            isinstance(selling_point_strategy, dict),
            "marketing_insight.selling_point_strategy must be an object",
            errors,
        )
        if isinstance(selling_point_strategy, dict):
            require(
                bool(str(selling_point_strategy.get("core_selling_point", "")).strip()),
                "marketing_insight.selling_point_strategy.core_selling_point is required",
                errors,
            )
            supporting_points = selling_point_strategy.get("supporting_points", [])
            deprioritized_mentions = selling_point_strategy.get("deprioritized_mentions", [])
            require(
                isinstance(supporting_points, list),
                "marketing_insight.selling_point_strategy.supporting_points must be a list",
                errors,
            )
            if isinstance(supporting_points, list):
                require(
                    all(bool(str(item).strip()) for item in supporting_points),
                    "marketing_insight.selling_point_strategy.supporting_points must contain only non-empty strings",
                    errors,
                )
            require(
                isinstance(deprioritized_mentions, list),
                "marketing_insight.selling_point_strategy.deprioritized_mentions must be a list",
                errors,
            )
            if isinstance(deprioritized_mentions, list):
                require(
                    all(bool(str(item).strip()) for item in deprioritized_mentions),
                    "marketing_insight.selling_point_strategy.deprioritized_mentions must contain only non-empty strings",
                    errors,
                )
            strongest_rtb = selling_point_strategy.get("strongest_rtb", {})
            require(
                isinstance(strongest_rtb, dict),
                "marketing_insight.selling_point_strategy.strongest_rtb must be an object",
                errors,
            )
            if isinstance(strongest_rtb, dict):
                require(
                    strongest_rtb.get("category") in RTB_CATEGORIES,
                    "marketing_insight.selling_point_strategy.strongest_rtb.category is invalid",
                    errors,
                )
                require(
                    bool(str(strongest_rtb.get("why_it_persuades", "")).strip()),
                    "marketing_insight.selling_point_strategy.strongest_rtb.why_it_persuades is required",
                    errors,
                )
                validate_marketing_evidence(
                    [strongest_rtb],
                    "marketing_insight.selling_point_strategy.strongest_rtb",
                    duration,
                    errors,
                    require_summary=True,
                )
                strongest_category = strongest_rtb.get("category")
                category_items = insight.get("rtb", {}).get(strongest_category, [])
                if strongest_category in RTB_CATEGORIES and isinstance(category_items, list):
                    strongest_signature = (
                        str(strongest_rtb.get("summary", "")).strip(),
                        strongest_rtb.get("start"),
                        strongest_rtb.get("end"),
                        strongest_rtb.get("evidence_type"),
                    )
                    candidate_signatures = {
                        (
                            str(item.get("summary", "")).strip(),
                            item.get("start"),
                            item.get("end"),
                            item.get("evidence_type"),
                        )
                        for item in category_items
                        if isinstance(item, dict)
                    }
                    require(
                        strongest_signature in candidate_signatures,
                        "marketing_insight.selling_point_strategy.strongest_rtb must select an item from the matching rtb category",
                        errors,
                    )
        rtb = insight.get("rtb", {})
        require(isinstance(rtb, dict), "marketing_insight.rtb must be an object", errors)
        if isinstance(rtb, dict):
            rtb_count = 0
            for category in ("sensoriality", "scientific_language", "proof"):
                items = rtb.get(category, [])
                if isinstance(items, list):
                    rtb_count += len(items)
                validate_marketing_evidence(
                    items,
                    f"marketing_insight.rtb.{category}",
                    duration,
                    errors,
                    require_summary=True,
                )
            require(rtb_count > 0, "marketing_insight.rtb needs at least one evidence item", errors)

    cta = insight.get("cta", {})
    require(isinstance(cta, dict), "marketing_insight.cta must be an object", errors)
    if isinstance(cta, dict):
        detected = cta.get("detected")
        require(isinstance(detected, bool), "marketing_insight.cta.detected must be boolean", errors)
        types = cta.get("types", [])
        evidence = cta.get("evidence", [])
        barrier = str(cta.get("purchase_barrier_reduced", "")).strip()
        if detected is True:
            require(bool(types), "marketing_insight.cta.types is required when CTA is detected", errors)
            require(isinstance(types, list), "marketing_insight.cta.types must be a list", errors)
            if isinstance(types, list):
                require(all(item in CTA_TYPES for item in types), "marketing_insight.cta.types contains an invalid value", errors)
            require(bool(barrier), "marketing_insight.cta.purchase_barrier_reduced is required", errors)
            require(bool(evidence), "marketing_insight.cta.evidence is required", errors)
            validate_marketing_evidence(evidence, "marketing_insight.cta.evidence", duration, errors)
        elif detected is False:
            require(not types, "marketing_insight.cta.types must be empty when CTA is not detected", errors)
            require(not barrier, "marketing_insight.cta.purchase_barrier_reduced must be empty when CTA is not detected", errors)
            require(not evidence, "marketing_insight.cta.evidence must be empty when CTA is not detected", errors)

    require(insight.get("confidence") in CONFIDENCE, "marketing_insight.confidence is invalid", errors)

    exact_product_names = {
        str(ad.get("product_name", "")).strip()
        for ad in data.get("product_ads", [])
        if str(ad.get("product_name", "")).strip() not in {"", "产品"}
    }
    for field, text in insight_texts:
        for product_name in exact_product_names:
            require(product_name not in text, f"marketing_insight.{field}.text must replace the exact product name with 产品", errors)
        for phrase in NEGATIVE_CRITIQUE_PHRASES:
            require(phrase not in text, f"marketing_insight.{field}.text contains negative critique: {phrase}", errors)
        for phrase in UNSUPPORTED_PERFORMANCE_PHRASES:
            require(phrase not in text, f"marketing_insight.{field}.text makes an unsupported performance claim: {phrase}", errors)
        for pattern in EXTERNAL_REVIEW_PATTERNS:
            require(
                re.search(pattern, text) is None,
                f"marketing_insight.{field}.text contains external-review language: {pattern}",
                errors,
            )
        if field == "activation_implication":
            require(
                any(cue in text for cue in MECHANISM_CUES),
                "marketing_insight.activation_implication.text must explain why the integration works, not only name a chain",
                errors,
            )
            for pattern in FUTURE_PLANNING_PATTERNS:
                require(
                    re.search(pattern, text) is None,
                    f"marketing_insight.activation_implication.text contains future-planning language: {pattern}",
                    errors,
                )

    potential_topics = insight.get("potential_topics", [])
    if isinstance(potential_topics, list):
        for index, topic in enumerate(potential_topics, start=1):
            topic_text = str(topic).strip()
            for product_name in exact_product_names:
                require(
                    product_name not in topic_text,
                    f"marketing_insight.potential_topics[{index}] must not contain the exact product name",
                    errors,
                )

    screenshots = data.get("screenshots", [])
    require(len(screenshots) == len(SLOTS), "screenshots must contain exactly seven items", errors)
    slot_counts = {slot: 0 for slot in SLOTS}
    for item in screenshots:
        slot = item.get("slot")
        if slot in slot_counts:
            slot_counts[slot] += 1
        else:
            errors.append(f"invalid screenshot slot: {slot}")
            continue
        status = item.get("status")
        require(status in {"selected", "not_detected"}, f"{slot}: invalid status", errors)
        if status == "selected":
            require(bool(item.get("path")), f"{slot}: selected screenshot needs a path", errors)
            require(bool(item.get("scene_description")), f"{slot}: scene_description is required", errors)
            if item.get("path"):
                require(resolve_artifact_path(base_dir, item["path"]).is_file(), f"{slot}: file does not exist", errors)
        elif status == "not_detected":
            require(not item.get("path"), f"{slot}: missing screenshot path must be empty", errors)
    for slot, count in slot_counts.items():
        require(count == 1, f"screenshot slot {slot} must occur exactly once", errors)

    ad_starts: list[float] = []
    for index, ad in enumerate(data.get("product_ads", []), start=1):
        prefix = f"product_ads[{index}]"
        require(ad.get("holding_or_presenting") is True, f"{prefix}: holding_or_presenting must be true", errors)
        require(bool(ad.get("product_name")), f"{prefix}: product_name is required", errors)
        require(bool(ad.get("product_name_quote")), f"{prefix}: spoken product-name quote is required", errors)
        require(bool(ad.get("efficacy_quotes")), f"{prefix}: at least one efficacy/introduction quote is required", errors)
        require(bool(ad.get("evidence_screenshots")), f"{prefix}: evidence screenshot is required", errors)
        for screenshot in ad.get("evidence_screenshots", []):
            require(resolve_artifact_path(base_dir, screenshot).is_file(), f"{prefix}: evidence screenshot does not exist", errors)
        try:
            start = float(ad.get("start", 0))
            end = float(ad.get("end", 0))
        except (TypeError, ValueError):
            errors.append(f"{prefix}: start and end must be numeric")
        else:
            ad_starts.append(start)
            require(0 <= start < end, f"{prefix}: require 0 <= start < end", errors)
            require(end <= float(video.get("duration_seconds", 0)), f"{prefix}: end exceeds video duration", errors)
        require(ad.get("confidence") in CONFIDENCE, f"{prefix}: invalid confidence", errors)

    require(ad_starts == sorted(ad_starts), "product_ads must be ordered by start time", errors)

    segments = load_transcript_segments(data, base_dir, errors)
    require(bool(segments), "transcript.segments must not be empty", errors)
    for index, segment in enumerate(segments, start=1):
        require("start" in segment and "end" in segment, f"transcript segment {index} needs timestamps", errors)
        require("text" in segment and "source" in segment, f"transcript segment {index} needs text and source", errors)

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
    print(f"OK: {analysis_path}")


if __name__ == "__main__":
    main()
