#!/usr/bin/env python3
"""Validate public-release structure without reading generated output folders."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / ".codex-plugin" / "plugin.json"
SKILLS = ROOT / "skills"
FORBIDDEN_SUFFIXES = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".pdf", ".zip"}
FORBIDDEN_NAMES = {".DS_Store"}
SECRET_PATTERNS = {
    "OpenAI-like secret": re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private key": re.compile(r"BEGIN (?:RSA|OPENSSH|EC|DSA) PRIVATE KEY"),
    "personal macOS path": re.compile(r"/" + "Users/" + r"[^/\s]+/"),
}
SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$")


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def validate_plugin(errors: list[str]) -> None:
    try:
        payload = json.loads(PLUGIN.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(errors, f"invalid plugin manifest: {exc}")
        return
    if payload.get("name") != ROOT.name:
        fail(errors, "plugin name must match its directory")
    if not SEMVER.fullmatch(str(payload.get("version", ""))):
        fail(errors, "plugin version must use semantic versioning")
    if not str(payload.get("description", "")).strip():
        fail(errors, "plugin description is required")
    if not str(payload.get("author", {}).get("name", "")).strip():
        fail(errors, "plugin author.name is required")
    if payload.get("skills") != "./skills/":
        fail(errors, "plugin skills path must be ./skills/")


def validate_skill(errors: list[str], skill_dir: Path) -> None:
    manifest = skill_dir / "SKILL.md"
    try:
        text = manifest.read_text(encoding="utf-8")
    except OSError as exc:
        fail(errors, f"missing {manifest}: {exc}")
        return
    match = re.match(r"^---\n(.*?)\n---\n", text, flags=re.DOTALL)
    if not match:
        fail(errors, f"invalid front matter: {manifest}")
        return
    metadata = yaml.safe_load(match.group(1))
    if not isinstance(metadata, dict):
        fail(errors, f"front matter must be a mapping: {manifest}")
        return
    if metadata.get("name") != skill_dir.name:
        fail(errors, f"skill name must match directory: {skill_dir.name}")
    if not str(metadata.get("description", "")).strip():
        fail(errors, f"skill description is required: {skill_dir.name}")
    unexpected = set(metadata) - {"name", "description"}
    if unexpected:
        fail(errors, f"unsupported skill front-matter keys: {sorted(unexpected)}")


def validate_files(errors: list[str]) -> None:
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or ".venv" in path.parts:
            continue
        relative = path.relative_to(ROOT)
        if path.name in FORBIDDEN_NAMES or path.suffix.lower() in FORBIDDEN_SUFFIXES:
            fail(errors, f"forbidden release artifact: {relative}")
        if path.suffix.lower() not in {".md", ".py", ".json", ".yaml", ".yml", ".txt", ".toml", ".m"}:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(content):
                fail(errors, f"{label} found in {relative}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--public",
        action="store_true",
        help="also enforce author, repository URL, and license release gates",
    )
    args = parser.parse_args()
    errors: list[str] = []
    warnings: list[str] = []
    validate_plugin(errors)
    skill_dirs = sorted(path for path in SKILLS.iterdir() if path.is_dir())
    if not skill_dirs:
        fail(errors, "at least one skill is required")
    for skill_dir in skill_dirs:
        validate_skill(errors, skill_dir)
    validate_files(errors)
    plugin_payload = json.loads(PLUGIN.read_text(encoding="utf-8"))
    author_name = str(plugin_payload.get("author", {}).get("name", "")).strip()
    if author_name == "Local developer":
        warnings.append("replace the placeholder plugin author before public release")
    if not plugin_payload.get("repository"):
        warnings.append("add the GitHub repository URL before public release")
    if not (ROOT / "LICENSE").is_file():
        warnings.append("choose a license and add LICENSE before public release")
    if args.public and warnings:
        errors.extend(f"public release gate: {warning}" for warning in warnings)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    for warning in warnings:
        print(f"WARNING: {warning}")
    print(f"Validated {ROOT.name}: {len(skill_dirs)} skill(s), release hygiene clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
