#!/usr/bin/env python3
"""Fast unit checks for subtitle extraction and the subtitle coverage gate."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw


SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from build_review_packet import (  # noqa: E402
    build_timeline_blocks,
    detect_product_signal_windows,
    review_timestamps,
    reuse_candidate_frame_paths,
)
from extract_subtitles import build_segments  # noqa: E402
from init_analysis import build_prefill_assistance  # noqa: E402
from materialize_evidence_refs import hydrate_evidence_refs  # noqa: E402
from preflight_analysis import apply_preflight_repairs  # noqa: E402
from qa_report import select_manual_review_indices  # noqa: E402
from run_analysis import (  # noqa: E402
    StateRecorder,
    require_complete_visible_subtitles,
)


def line(text: str, y: float = 0.5) -> dict[str, object]:
    return {
        "text": text,
        "confidence": 0.9,
        "x": 0.1,
        "y": y,
        "width": 0.8,
        "height": 0.08,
    }


class SubtitleTests(unittest.TestCase):
    def test_static_ui_is_removed_and_dialogue_is_merged(self) -> None:
        raw = [
            {
                "timestamp": 0.0,
                "path": "a.jpg",
                "lines": [line("关注账号", 0.2), line("你好")],
            },
            {
                "timestamp": 0.5,
                "path": "b.jpg",
                "lines": [line("关注账号", 0.2), line("你好")],
            },
            {
                "timestamp": 1.0,
                "path": "c.jpg",
                "lines": [line("关注账号", 0.2), line("世界")],
            },
            {
                "timestamp": 1.5,
                "path": "d.jpg",
                "lines": [line("关注账号", 0.2), line("世界")],
            },
        ]
        segments, metrics = build_segments(
            raw,
            minimum_confidence=0.35,
            frame_period=0.5,
        )
        self.assertEqual([item["text"] for item in segments], ["你好", "世界"])
        self.assertEqual(metrics["static_lines_removed"], 1)


class SubtitleGateTests(unittest.TestCase):
    def write_transcript(self, directory: str, coverage: str) -> Path:
        path = Path(directory) / "transcript.json"
        path.write_text(
            json.dumps(
                {
                    "coverage": coverage,
                    "gaps": [] if coverage == "complete" else [{"start": 2, "end": 8}],
                    "segments": [],
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_complete_subtitles_continue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            transcript = self.write_transcript(directory, "complete")
            payload = require_complete_visible_subtitles(transcript)
        self.assertEqual(payload["coverage"], "complete")

    def test_incomplete_subtitles_stop_before_analysis(self) -> None:
        for coverage in ("partial", "none", "unknown"):
            with self.subTest(coverage=coverage):
                with tempfile.TemporaryDirectory() as directory:
                    transcript = self.write_transcript(directory, coverage)
                    with self.assertRaisesRegex(
                        RuntimeError,
                        f"未能恢复完整的画面字幕.*coverage='{coverage}'",
                    ):
                        require_complete_visible_subtitles(transcript)


class ReviewPacketTests(unittest.TestCase):
    def test_title_alias_and_claims_form_one_unconfirmed_window(self) -> None:
        segments = [
            {"start": 0, "end": 2.5, "text": "半夜饿的睡不着"},
            {
                "start": 85.5,
                "end": 87.5,
                "text": "全靠SK-II神仙水给我底气",
                "frame_path": "product.jpg",
            },
            {
                "start": 88.5,
                "end": 89,
                "text": "90%以上的传奇PITERA 少出油暗沉高活抗老",
            },
            {
                "start": 89.5,
                "end": 91.5,
                "text": "一瓶稳住细腻皮肤，省了其他瓶瓶罐罐",
            },
            {"start": 93, "end": 95, "text": "到点啦第一口粉丝先吃"},
        ]
        windows = detect_product_signal_windows(
            segments,
            title="晚上12点的食物#sk2神仙水",
            duration=121.254,
        )
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0]["status"], "review_required")
        self.assertEqual(windows[0]["signal_start"], 85.5)
        self.assertEqual(windows[0]["signal_end"], 91.5)
        self.assertEqual(windows[0]["context_start"], 84.0)
        self.assertEqual(windows[0]["context_end"], 93.0)

    def test_timeline_is_compacted_into_fixed_blocks(self) -> None:
        segments = [
            {"start": 0, "end": 1, "text": "开场"},
            {"start": 16, "end": 17, "text": "第二段"},
        ]
        blocks = build_timeline_blocks(
            segments,
            duration=31,
            block_seconds=15,
        )
        self.assertEqual(len(blocks), 3)
        self.assertEqual(blocks[0]["text"], "开场")
        self.assertEqual(blocks[1]["text"], "第二段")

    def test_acne_ampoule_claims_create_a_review_window(self) -> None:
        segments = [
            {"start": 89.0, "end": 89.5, "text": "小宝是油痘肌"},
            {"start": 92.5, "end": 93.0, "text": "终结反复痘循环"},
            {"start": 96.0, "end": 96.5, "text": "根源控油祛痘"},
            {"start": 101.5, "end": 102.0, "text": "舒缓减红 调节微生态"},
        ]
        windows = detect_product_signal_windows(
            segments,
            title="#可复美秩序次抛 #可复美祛痘次抛",
            duration=166.367,
        )
        self.assertEqual(len(windows), 2)
        self.assertEqual(windows[0]["signal_start"], 89.0)
        self.assertEqual(windows[1]["signal_end"], 102.0)

    def test_review_timestamps_prioritize_existing_candidate_frames(self) -> None:
        windows = [
            {
                "context_start": 88.0,
                "context_end": 108.0,
            }
        ]
        candidates = [
            {"timestamp": 89.582},
            {"timestamp": 93.848},
            {"timestamp": 98.114},
            {"timestamp": 102.380},
            {"timestamp": 106.646},
        ]
        timestamps = review_timestamps(
            windows,
            duration=166.367,
            mode="standard",
            candidate_frames=candidates,
        )
        for timestamp in (89.582, 93.848, 98.114, 102.380, 106.646):
            self.assertIn(timestamp, timestamps)

    def test_review_frames_reuse_exact_candidate_images(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "candidate.jpg"
            candidate.write_bytes(b"candidate")
            review_frames = [{"timestamp": 89.582, "path": "reextracted.jpg"}]
            result = reuse_candidate_frame_paths(
                review_frames,
                [{"timestamp": 89.582, "path": str(candidate)}],
            )
        self.assertEqual(result[0]["path"], str(candidate))
        self.assertEqual(result[0]["source"], "candidate")


class EvidenceReferenceTests(unittest.TestCase):
    def test_reference_is_expanded_with_field_overrides(self) -> None:
        registry = {
            "claim": {
                "summary": "产品主张",
                "evidence_type": "spoken_claim",
                "start": 10,
                "end": 12,
                "source": "ocr",
                "quote": "一瓶完成护理",
                "frame_path": "claim.jpg",
            }
        }
        used: list[str] = []
        hydrated = hydrate_evidence_refs(
            {
                "strongest_rtb": {
                    "evidence_ref": "claim",
                    "category": "proof",
                    "why_it_persuades": "直接支持核心卖点",
                }
            },
            registry,
            used=used,
        )
        strongest = hydrated["strongest_rtb"]
        self.assertEqual(used, ["claim"])
        self.assertEqual(strongest["quote"], "一瓶完成护理")
        self.assertEqual(strongest["category"], "proof")

    def test_unknown_reference_fails(self) -> None:
        with self.assertRaisesRegex(KeyError, "Unknown evidence_ref"):
            hydrate_evidence_refs({"evidence_ref": "missing"}, {})


class AnalysisPrefillTests(unittest.TestCase):
    def test_prefill_builds_review_required_drafts_and_evidence_refs(self) -> None:
        review_packet = {
            "video": {"duration_seconds": 100},
            "opening": {
                "start": 0,
                "end": 2,
                "quote": "开场",
                "frame_path": "opening.jpg",
            },
            "timeline_blocks": [
                {"start": 0, "end": 15, "text": "开场生活"},
                {"start": 15, "end": 30, "text": "中段产品"},
                {"start": 30, "end": 45, "text": "结尾生活"},
            ],
            "product_signal_windows": [
                {
                    "id": "product-signal-1",
                    "signal_start": 16,
                    "signal_end": 18,
                    "context_start": 15,
                    "context_end": 20,
                    "signals": [
                        {"text": "这是某某眼霜"},
                        {"text": "电动按摩头很方便"},
                    ],
                    "review_frames": [
                        {"timestamp": 16, "path": "review-product.jpg"},
                    ],
                },
                {
                    "id": "product-signal-2",
                    "signal_start": 31,
                    "signal_end": 32,
                    "context_start": 30,
                    "context_end": 34,
                    "signals": [
                        {"text": "使用后眼周更润"},
                    ],
                    "review_frames": [
                        {"timestamp": 32, "path": "review-after.jpg"},
                    ],
                }
            ],
            "review_frames": [
                {"timestamp": 0.5, "path": "opening.jpg"},
                {"timestamp": 16, "path": "review-product.jpg"},
            ],
        }
        frames = [
            {"timestamp": 7.5, "path": "early.jpg"},
            {"timestamp": 16.0, "path": "product-1.jpg"},
            {"timestamp": 22.0, "path": "product-2.jpg"},
            {"timestamp": 37.5, "path": "late.jpg"},
        ]
        prefill = build_prefill_assistance(review_packet, frames)

        self.assertEqual(len(prefill["classification_evidence"]), 3)
        self.assertEqual(
            prefill["draft_assistance"]["product_ads"][0]["status"],
            "review_required",
        )
        self.assertEqual(
            prefill["draft_assistance"]["product_ads"][0]["candidate_start"],
            15,
        )
        self.assertEqual(
            prefill["draft_assistance"]["product_ads"][0]["candidate_end"],
            64,
        )
        self.assertEqual(
            prefill["draft_assistance"]["product_ads"][0]["source_window_ids"],
            ["product-signal-1", "product-signal-2"],
        )
        self.assertEqual(
            len(prefill["draft_assistance"]["product_ads"]),
            1,
        )
        screenshots = prefill["draft_assistance"]["screenshots"]
        self.assertEqual(screenshots[0]["suggested"]["path"], "opening.jpg")
        self.assertEqual(screenshots[1]["suggested"]["path"], "product-1.jpg")
        self.assertEqual(
            prefill["evidence_registry"]["timeline_sample_2"]["quote"],
            "中段产品",
        )


class AnalysisPreflightTests(unittest.TestCase):
    def test_preflight_repairs_hook_and_synchronizes_strongest_rtb(self) -> None:
        payload = {
            "classification": {"primary": "LIFESTYLE"},
            "evidence_registry": {
                "opening": {
                    "summary": "开场同框",
                    "evidence_type": "observed_action",
                    "start": 0,
                    "end": 2,
                    "source": "visual",
                    "quote": "女孩日常",
                    "frame_path": "opening.jpg",
                }
            },
            "marketing_insight": {
                "hook": {
                    "evidence": [
                        {
                            "summary": "迟到的钩子证据",
                            "evidence_type": "spoken_claim",
                            "start": 8,
                            "end": 10,
                            "source": "ocr",
                            "quote": "想吃什么",
                            "frame_path": "late.jpg",
                        }
                    ]
                },
                "selling_point_strategy": {
                    "strongest_rtb": {
                        "category": "proof",
                        "summary": "发生漂移的摘要",
                        "why_it_persuades": "最贴合核心卖点",
                        "evidence_type": "user_feedback",
                        "start": 20,
                        "end": 24,
                        "source": "ocr",
                        "quote": "短引文",
                        "frame_path": "proof.jpg",
                    }
                },
                "rtb": {
                    "proof": [
                        {
                            "summary": "规范证据摘要",
                            "evidence_type": "user_feedback",
                            "start": 20,
                            "end": 24,
                            "source": "ocr",
                            "quote": "完整的用户反馈",
                            "frame_path": "proof.jpg",
                        }
                    ]
                },
            },
        }

        repaired, changes = apply_preflight_repairs(payload)
        hook_evidence = repaired["marketing_insight"]["hook"]["evidence"]
        strongest = repaired["marketing_insight"]["selling_point_strategy"][
            "strongest_rtb"
        ]
        self.assertEqual([item["start"] for item in hook_evidence], [0])
        self.assertEqual(strongest["summary"], "规范证据摘要")
        self.assertEqual(strongest["quote"], "完整的用户反馈")
        self.assertEqual(strongest["why_it_persuades"], "最贴合核心卖点")
        self.assertEqual(len(changes), 2)
        self.assertEqual(
            len(
                repaired["draft_assistance"][
                    "preflight_removed_late_hook_evidence"
                ]
            ),
            1,
        )


class ManualQaSelectionTests(unittest.TestCase):
    def test_standard_selects_cover_screenshot_pages_and_densest_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pages = []
            for index in range(7):
                path = Path(directory) / f"page-{index + 1}.png"
                image = Image.new("RGB", (120, 160), "white")
                if index == 6:
                    draw = ImageDraw.Draw(image)
                    draw.rectangle((10, 10, 110, 150), fill="black")
                image.save(path)
                pages.append(path)
            self.assertEqual(
                select_manual_review_indices(pages, "standard"),
                [0, 1, 2, 3, 6],
            )
            self.assertEqual(
                select_manual_review_indices(pages, "forensic"),
                list(range(7)),
            )


class ManualTimingTests(unittest.TestCase):
    def test_review_and_analysis_stage_is_recorded_separately(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "run-state.json"
            state = StateRecorder(state_path, "standard")
            state.start_manual(
                "evidence_review_and_analysis",
                artifacts=["review-packet.json"],
            )
            state.complete_manual("evidence_review_and_analysis")
            payload = json.loads(state_path.read_text(encoding="utf-8"))
        stage = payload["stages"]["evidence_review_and_analysis"]
        self.assertEqual(stage["status"], "completed")
        self.assertTrue(stage["manual"])
        self.assertGreaterEqual(stage["elapsed_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
