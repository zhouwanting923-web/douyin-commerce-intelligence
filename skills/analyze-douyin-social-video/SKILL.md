---
name: analyze-douyin-social-video
description: "Analyze authorized, subtitled Douyin social seeding and ecommerce videos from local MP4 files or an explicitly configured link adapter. Use when Codex needs to recover visible subtitles with local OCR, stop clearly when complete subtitles are unavailable, prefill auditable label/ad/screenshot drafts, classify the video with the supplied DRAMA/SEEDING/LIFESTYLE/BRANDING/OFFER rules, confirm product-ad segments, select seven evidence screenshots, explain why the content and product integration work, derive an evidence-ranked skincare selling-point strategy, and deliver a visually verified PDF report plus key screenshots."
---

# Douyin Social Commerce Intelligence

Turn each authorized, subtitled Douyin video into one evidence-backed PDF report
and seven key screenshots. Default to the fast, auditable Standard path. Never
infer product claims that are absent from the video.

## Choose the mode

- Use `standard` unless the user explicitly asks for逐帧、法证级、极高精度，or
  the Standard evidence is too weak to support a decision.
- Use `forensic` for denser subtitle sampling, more candidate frames, and manual
  full-detail inspection of every report page.
- Record the selected mode in `analysis.json`, `run-state.json`, and `qa.json`.

## Preconditions

- Prefer a local MP4 that the user is authorized to access and analyze.
- Treat URL resolution as optional. Use it only when the user has explicitly
  configured an authorized adapter through `DOUYIN_DOWNLOADER`; this public
  package does not bundle a downloader or remote transcription service.
- Require FFmpeg, FFprobe, Poppler, and macOS Apple Vision.
- Use the bundled workspace Python when available; it must provide Pillow and
  ReportLab.
- Require complete visible subtitles. Do not transcribe audio or call any remote
  speech-recognition service.
- Apple Vision may reject OCR calls inside the filesystem sandbox. Run the
  `prepare` command outside that sandbox on macOS. If permission is unavailable,
  let the command fail clearly, request approval, and rerun the same command;
  completed stages are cached.

## Prepare evidence

Create a unique output directory for each video and run:

```bash
<workspace-python> scripts/run_analysis.py prepare \
  --video "<video.mp4>" \
  --output-dir "<video-dir>" \
  --mode standard \
  --artifact-python "<workspace-python>"
```

For an authorized URL adapter, set `DOUYIN_DOWNLOADER` to its Python module and
replace `--video` with `--url "<douyin-url>"`. If no adapter is configured, ask
the user for a local MP4. Do not add `--force` unless invalidating a known-bad
cache.

The command performs one local-video import or authorized adapter call, one
FFmpeg candidate decode, change-aware local subtitle OCR, a strict
subtitle-coverage gate, chronological evidence indexing, compact review-packet
creation, product-signal frame pre-extraction, available metadata prefill, and
analysis skeleton creation. Do not add a separate creator lookup. Each automated
stage records status, timing, cache use, and errors in `run-state.json`; the
review-and-analysis timer starts when preparation finishes and closes when
finalization begins.

Subtitle gate:

- Continue only when local OCR reports `coverage=complete`.
- If coverage is `partial`, `none`, `unknown`, or otherwise not complete, stop
  before building evidence or initializing analysis.
- Tell the user that complete visible subtitles could not be recovered and ask
  for a version with complete burned-in subtitles.
- Never extract audio, inspect API keys, or send audio to a remote service.

When processing multiple videos, keep separate output directories. Prepare at
most two independent videos concurrently; complete evidence review and report
reasoning one video at a time.

## Standard fast lane

For Standard mode, keep evidence review to one visual pass and one authoring
pass:

1. Read `review-packet.txt`.
2. Inspect `review/review-board.jpg` once at original detail.
3. Read `references/standard-analysis-brief.md`; it contains the required
   classification order, ad rule, evidence fields, prose rules, and screenshot
   contract for ordinary runs.
4. Review `analysis.json.draft_assistance`: keep relevant prefilled timeline
   evidence, promote only confirmed advertisement drafts, and accept or replace
   the seven screenshot suggestions.
5. Write the core judgment fields and three report paragraphs, finalize once,
   and fix only concrete validator or layout errors.

The review board prioritizes existing candidate timestamps inside detected
product windows. Reuse those review frames directly for the seven screenshot
slots when they are distinct and legible. Do not open individual frames or read
the long-form references merely to be thorough.

Target operating time for a typical two-to-three-minute Standard video:

- evidence review and analysis: at most about two minutes;
- manual visual QA: at most about thirty seconds.

These are operating targets, not reasons to weaken evidence requirements.

## Review one compact packet, then zoom selectively

Inspect:

1. `review-packet.txt` for opening evidence, 15-second timeline blocks, and
   unconfirmed product-signal windows.
2. `review/review-board.jpg` once at original detail. It combines every global
   contact sheet with precise frames sampled around product-language signals.
3. Targeted entries from `evidence.json` or one individual original frame only
   when a material product name, boundary, label, or screenshot remains
   unreadable after the board review.

Treat every product-signal window as a search hint, never as a confirmed ad.
Do not dump the full `evidence.events` array or inspect hundreds of frames one by
one. Reuse `review/precise-frames/` first. When a chosen moment still needs a
different timestamp, extract only that timestamp:

```bash
<workspace-python> scripts/extract_precise_frames.py \
  --video "<video-dir>/media/<video-id>.mp4" \
  --timestamps "12.4,36.8,51.2" \
  --output-dir "<video-dir>/precise-frames"
```

In Standard mode, use the classification order and boundary rules in
`references/standard-analysis-brief.md`. Read `references/tagging-rules.md` only
for a borderline classification. In Forensic mode, read the full tagging rules
immediately before classification. Always choose exactly one primary and one
secondary label, record positive evidence, and cite the decisive boundary or
exclusion rule.

Confirm a product-ad interval only when the same continuous context contains:

1. deliberate product presentation;
2. a spoken product name or unambiguous alias; and
3. product introduction, efficacy, selling point, or usage experience.

Start at the earliest qualifying event and end at the last related presentation
or statement. Split at a clear scene/topic change or when both product display
and product speech disappear for over one second. Merge gaps of at most one
second only for the same product and continuous context.

## Fill the analysis

In Standard mode, the compact brief is sufficient for an ordinary analysis.
Read the longer references only at the point they become necessary:

- `references/analysis-schema.md` after a schema validation error or for
  Forensic authoring.
- `references/report-rules.md` after a report-layout ambiguity or for Forensic
  authoring.
- `references/product-marketing-methodology.md` when the evidence hierarchy or
  integration mechanism remains uncertain.
- `references/product-marketing-examples.md` only when reasoning is uncertain or
  when running a regression review; do not imitate examples mechanically.

Fill every required field in `analysis.json`. Keep the full transcript external
at `transcript.json`; reference it with `transcript.path` instead of copying
hundreds of segments into the analysis file.

Use the auto-populated `evidence_registry` to avoid repeating evidence objects.
Any evidence field may contain `{"evidence_ref": "<id>"}` plus field-specific
overrides. Finalization expands these references before validation. Keep direct
evidence objects when a registry item does not express the required distinction.
The prefilled opening and product-signal items are unconfirmed inputs and must be
reviewed before reuse.

`draft_assistance` pre-populates three chronological classification-evidence
candidates, merges nearby product-language signals into review-required
advertisement search intervals, and adds timestamped screenshot suggestions.
Treat it as a review queue, not a decision: keep only evidence that supports the
chosen label, trim and move an advertisement draft into `product_ads` only after
the three-part ad rule is confirmed, and mark each final screenshot `selected`
or `not_detected`.

Select the seven fixed screenshot slots from observed evidence. Use
`not_detected` with an empty path when the required scene is absent. Never
substitute an unrelated frame. Preserve exact product names outside the three
analyst-authored Product Marketing paragraphs; use `产品` only inside those
paragraphs.

For every non-`OTHERS` video, commit to one creator asset, one core product
perception, one core selling point, one strongest RTB, one integration mechanism,
and one observed three-to-five-node integration chain. Keep spoken claims,
observed facts, and analyst inference separate. Do not claim traffic, conversion,
sales, or scientific efficacy without corresponding evidence.

## Validate, build, and QA

Run the single finalization entry:

```bash
<workspace-python> scripts/run_analysis.py finalize \
  --analysis "<video-dir>/analysis.json" \
  --artifact-python "<workspace-python>"
```

This materializes standard screenshot names, blocks on schema/evidence errors,
builds `report.pdf`, checks file/font/page/transcript integrity, renders every
page, and creates `qa/report-contact-sheet.jpg`, full-detail
`qa/qa-review-board-*.jpg`, and `qa.json`. Finalization leaves manual QA in
`pending` state.

Before strict validation, finalization runs a deterministic preflight. It
replaces hook evidence outside the first three seconds with the reviewed opening
evidence and synchronizes `strongest_rtb` evidence fields from its matching RTB
item. It does not infer labels, confirm ads, write insight prose, or weaken the
validator.

- In Standard mode, inspect every generated QA review board once at original
  detail. It contains the cover, all screenshot pages, and the densest transcript
  page. Check clipping, overlap, missing images, unreadable text, and wrong
  screenshots in that single pass. If clean, record the manual review
  immediately. Open an individual original page only when the board exposes a
  concrete warning or ambiguity.
- In Forensic mode, the QA review boards contain every rendered page at original
  detail.
- Correct analysis or layout defects and rerun `finalize`. Do not weaken the
  validator to obtain a pass.
- After a clean inspection, record the measured manual-review time:

```bash
<workspace-python> scripts/complete_manual_review.py \
  --qa "<video-dir>/qa/qa.json" \
  --status passed
```

Do not deliver the report until `qa.json` has `status=passed` and
`manual_review.status=passed`.

## Output contract

```text
<video-dir>/
├── report.pdf
├── analysis.json
├── video.json
├── transcript.json
├── transcript.txt
├── evidence.json
├── review-packet.json
├── review-packet.txt
├── run-state.json
├── media/<video-id>.mp4
├── frames/index.json
├── frames/contact-sheet-*.jpg
├── review/
│   ├── review-board.jpg
│   └── precise-frames/review-*.jpg
├── screenshots/01-cover.jpg ... 07-after-effect.jpg
└── qa/
    ├── qa.json
    ├── report-contact-sheet.jpg
    ├── qa-review-board-*.jpg
    └── pdf-pages/page-*.png
```

Deliver `report.pdf` and `screenshots/`. Keep JSON, transcripts, evidence,
candidate frames, and QA files as auditable working artifacts.

## Hard quality rules

- Preserve exact timestamped evidence for labels and confirmed ad intervals.
- Calculate total ad duration from the union of intervals; never double-count.
- Preserve uncertain names as uncertain; do not silently “correct” them.
- Prefer representative, distinct, high-value frames over evenly spaced frames.
- Write positive-only Product Marketing analysis: strengths, successful
  mechanisms, and reusable value.
- Do not add budget, media allocation, hypothetical KOL, or unsupported
  performance conclusions.
- A cached rerun must resume; it must not silently overwrite completed analysis.
- Preserve `product_signal_windows.status=review_required` until a human or agent
  independently confirms the full three-part ad rule.
- Keep separate measured stages for `evidence_review_and_analysis` and
  `manual_visual_qa`; do not infer either duration from an uninstrumented gap.
