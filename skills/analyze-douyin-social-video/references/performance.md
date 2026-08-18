# Performance and operating profile

Use this file for benchmarking, regression review, or tuning. It is not required
for ordinary video analysis.

## Contents

- Standard path
- Forensic path
- Stage timing
- Cache behavior
- Escalation criteria

## Standard path

Standard mode uses one FFmpeg decode pass for global candidates and subtitle
crops, 2 fps subtitle sampling, perceptual change selection, and accurate local
Apple Vision OCR. It inspects contact sheets before individual frames and keeps
the transcript external to `analysis.json`.

After OCR, Standard mode builds a compact review packet with 15-second transcript
blocks, unconfirmed product-language windows, a bounded set of exact frames, and
one visual board. Review this packet before opening the full evidence index. The
analysis skeleton also provides reusable evidence IDs so repeated evidence can
be authored once and expanded immediately before validation.

On the 249.7-second regression video used during the V2 upgrade:

| Stage | Cold time | Cached rerun |
|---|---:|---:|
| Local video preparation | 0.02 s | 0.02 s |
| Candidate and subtitle-frame decode | 4.11 s | 1.17 s |
| Apple Vision OCR | 28.51 s | 0.05 s |
| Evidence index | 0.05 s | 0.05 s |
| Complete preparation entry | about 33 s | 2.21 s |

The separate cold URL regression for the same video took 67.69 seconds:
40.40 seconds for link resolution and download, 4.25 seconds for candidate
decoding, 22.84 seconds for OCR, and less than 0.1 seconds for indexing and
skeleton creation. Network performance varies, so keep download time separate
from local processing time. Report reasoning and human/agent inspection time
depend on content complexity.

The regression produced 167 time-aligned subtitle segments and retained all
audited product claims. Treat these numbers as a reference point, not a universal
SLA.

The V3 compact-review regression used a 121.3-second local video with 68 visible
subtitle segments and one product-language window:

| Stage | Cold time | Cached rerun |
|---|---:|---:|
| Local video preparation | 0.21 s | 0.01 s |
| Candidate decode | 2.41 s | 0.14 s |
| Apple Vision OCR | 12.65 s | 0.04 s |
| Evidence index | 0.03 s | 0.03 s |
| Compact review packet and board | 0.67 s | 0.04 s |
| Analysis skeleton | 0.03 s | skipped |
| Complete preparation entry | 15.98 s | 0.24 s |

The packet combined two global contact sheets and eight exact review frames in
one board. The report regression selected PDF pages 1–4 plus the densest
transcript page, created one full-detail QA board in 1.82 seconds, and recorded a
single-board manual inspection in 13.15 seconds. These are regression observations,
not general SLAs.

## Forensic path

Forensic mode increases global candidate count, subtitle sampling to 4 fps,
lowers the perceptual-change threshold, forces more frequent OCR samples, and
requires original-detail inspection of every rendered report page. It is
intentionally slower.

The 34.1-second Forensic regression produced 30 global candidates, 120 subtitle
frames, 99 OCR requests, and 21 transcript segments in 8.28 seconds end to end.

Do not select Forensic mode merely because it sounds more thorough. Escalate only
when Standard evidence cannot resolve a material label, product-ad boundary,
spoken claim, screenshot, or layout decision.

## Stage timing

Read exact observed timings from `<video-dir>/run-state.json`. Each stage records:

- `status`
- `started_at` and `finished_at`
- `elapsed_seconds`
- `cached`
- command and bounded output tail

The pipeline also records two manual stages:

- `evidence_review_and_analysis` starts after preparation and closes when
  finalization begins.
- `manual_visual_qa` starts when QA assets are ready and closes through
  `complete_manual_review.py`.

Do not combine these stages or infer manual QA time from the gap between
preparation and finalization.

If a stage fails, rerun the same entry after fixing the cause. Successful
fingerprinted stages should be reused automatically.

## Cache behavior

- Video preparation reuses matching metadata and media.
- Candidate extraction fingerprints the source video and mode settings.
- Subtitle OCR fingerprints candidate frames and OCR settings.
- Precise frame extraction skips already-created filenames.
- Existing `analysis.json` is never overwritten without `--force`.
- Review packets and boards reuse a fingerprint of video metadata, transcript,
  candidate frames, and mode.
- Evidence-reference materialization is idempotent.

Use `--force` only after identifying a stale or invalid artifact. A normal rerun
should be cheap and resumable.

## Escalation criteria

Stop the workflow when OCR coverage is anything other than `complete` and tell
the user to provide a version with complete burned-in subtitles. Do not
transcribe audio. Use Forensic mode only when complete subtitle evidence exists
but a material visual decision remains unresolved.
