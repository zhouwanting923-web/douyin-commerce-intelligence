#!/usr/bin/env python3
"""Repair deterministic analysis wiring before strict schema validation."""

from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
from typing import Any

from _common import read_json, write_json


RTB_EVIDENCE_FIELDS = (
    "summary",
    "evidence_type",
    "start",
    "end",
    "source",
    "quote",
    "frame_path",
)


def _number(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _matching_rtb_item(
    strongest: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    start = _number(strongest.get("start"))
    end = _number(strongest.get("end"))
    evidence_type = strongest.get("evidence_type")
    summary = str(strongest.get("summary", "")).strip()

    exact = [
        item
        for item in candidates
        if str(item.get("summary", "")).strip() == summary
        and _number(item.get("start")) == start
        and _number(item.get("end")) == end
        and item.get("evidence_type") == evidence_type
    ]
    if len(exact) == 1:
        return exact[0]

    timestamp_match = [
        item
        for item in candidates
        if _number(item.get("start")) == start
        and _number(item.get("end")) == end
        and item.get("evidence_type") == evidence_type
    ]
    if len(timestamp_match) == 1:
        return timestamp_match[0]

    summary_match = [
        item
        for item in candidates
        if summary
        and str(item.get("summary", "")).strip() == summary
        and item.get("evidence_type") == evidence_type
    ]
    if len(summary_match) == 1:
        return summary_match[0]

    if len(candidates) == 1:
        return candidates[0]
    return None


def apply_preflight_repairs(
    data: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    repaired = deepcopy(data)
    changes: list[str] = []
    insight = repaired.setdefault("marketing_insight", {})
    registry = repaired.get("evidence_registry", {})

    if repaired.get("classification", {}).get("primary") != "OTHERS":
        hook = insight.get("hook", {})
        if isinstance(hook, dict):
            evidence = hook.get("evidence", [])
            if not isinstance(evidence, list):
                evidence = []
            valid_opening = [
                item
                for item in evidence
                if isinstance(item, dict)
                and (_number(item.get("start")) is not None)
                and float(item["start"]) <= 3.0
            ]
            late = [
                item
                for item in evidence
                if item not in valid_opening
            ]
            opening = (
                registry.get("opening")
                if isinstance(registry, dict)
                else None
            )
            if late and isinstance(opening, dict):
                opening_item = deepcopy(opening)
                opening_start = _number(opening_item.get("start"))
                if opening_start is not None and opening_start <= 3.0:
                    signature = (
                        opening_item.get("start"),
                        opening_item.get("end"),
                        opening_item.get("quote"),
                        opening_item.get("frame_path"),
                    )
                    existing_signatures = {
                        (
                            item.get("start"),
                            item.get("end"),
                            item.get("quote"),
                            item.get("frame_path"),
                        )
                        for item in valid_opening
                    }
                    if signature not in existing_signatures:
                        valid_opening.insert(0, opening_item)
                    hook["evidence"] = valid_opening
                    assistance = repaired.setdefault("draft_assistance", {})
                    assistance.setdefault(
                        "preflight_removed_late_hook_evidence",
                        [],
                    ).extend(deepcopy(late))
                    changes.append(
                        "replaced hook evidence outside the first three seconds"
                    )

    strategy = insight.get("selling_point_strategy", {})
    rtb = insight.get("rtb", {})
    if isinstance(strategy, dict) and isinstance(rtb, dict):
        strongest = strategy.get("strongest_rtb", {})
        if isinstance(strongest, dict):
            category = strongest.get("category")
            raw_candidates = rtb.get(category, [])
            candidates = [
                item
                for item in raw_candidates
                if isinstance(item, dict)
            ] if isinstance(raw_candidates, list) else []
            selected = _matching_rtb_item(strongest, candidates)
            if selected is not None:
                before = tuple(strongest.get(key) for key in RTB_EVIDENCE_FIELDS)
                for key in RTB_EVIDENCE_FIELDS:
                    strongest[key] = deepcopy(selected.get(key, ""))
                after = tuple(strongest.get(key) for key in RTB_EVIDENCE_FIELDS)
                if before != after:
                    changes.append(
                        "synchronized strongest_rtb with its selected RTB item"
                    )

    return repaired, changes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("analysis", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    analysis_path = args.analysis.resolve()
    output_path = (args.output or analysis_path).resolve()
    data = read_json(analysis_path)
    repaired, changes = apply_preflight_repairs(data)
    if not changes and output_path == analysis_path:
        print(f"CACHED no preflight repairs needed in {analysis_path}")
        return
    write_json(output_path, repaired)
    print(f"{output_path} ({'; '.join(changes) if changes else 'no changes'})")


if __name__ == "__main__":
    main()
