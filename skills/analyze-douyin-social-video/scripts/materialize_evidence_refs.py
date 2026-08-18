#!/usr/bin/env python3
"""Expand compact evidence references inside an analysis JSON file."""

from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
from typing import Any

from _common import read_json, write_json


def hydrate_evidence_refs(
    value: Any,
    registry: dict[str, dict[str, Any]],
    *,
    used: list[str] | None = None,
) -> Any:
    if isinstance(value, list):
        return [
            hydrate_evidence_refs(item, registry, used=used)
            for item in value
        ]
    if not isinstance(value, dict):
        return value
    if "evidence_ref" in value:
        reference = str(value["evidence_ref"])
        if reference not in registry:
            raise KeyError(f"Unknown evidence_ref: {reference}")
        if used is not None:
            used.append(reference)
        hydrated = deepcopy(registry[reference])
        for key, item in value.items():
            if key == "evidence_ref":
                continue
            hydrated[key] = hydrate_evidence_refs(item, registry, used=used)
        return hydrated
    return {
        key: hydrate_evidence_refs(item, registry, used=used)
        for key, item in value.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("analysis", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    analysis_path = args.analysis.resolve()
    output_path = (args.output or analysis_path).resolve()
    data = read_json(analysis_path)
    registry = data.get("evidence_registry", {})
    if not isinstance(registry, dict):
        raise SystemExit("evidence_registry must be an object.")
    for key, value in registry.items():
        if not isinstance(value, dict):
            raise SystemExit(f"evidence_registry.{key} must be an object.")
    used: list[str] = []
    hydrated = hydrate_evidence_refs(data, registry, used=used)
    if not used and output_path == analysis_path:
        print(f"CACHED no evidence references in {analysis_path}")
        return
    write_json(output_path, hydrated)
    print(f"{output_path} ({len(used)} evidence references expanded)")


if __name__ == "__main__":
    main()
