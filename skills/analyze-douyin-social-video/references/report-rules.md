# PDF and screenshot rules

## Required PDF sections

1. Basic video information.
2. Video classification with evidence and exclusion rationale.
3. Confirmed product-ad timeline plus merged ad duration and share of total video duration.
4. Three-paragraph Product Marketing insight.
5. Seven key screenshots with labels.
6. Full visible-subtitle transcript with timestamps.

## Seven screenshot slots

Output exactly these slots in order:

1. `cover` - One cover or opening-hook frame.
2. `product_alone` - Product shown clearly on its own.
3. `product_detail` - Packaging, applicator, texture, ingredient, or detail close-up.
4. `selling_point` - Frame where a product selling point is visually or textually presented.
5. `use_process_1` - First clear application/use step.
6. `use_process_2` - A distinct second use step or application angle.
7. `after_effect` - Post-use effect, state, or before/after evidence.

For each slot record:

- Timestamp.
- Type.
- Scene description.
- Product name when known.
- Related transcript or visible-text evidence.
- Status: `selected` or `not_detected`.

Do not fill absent categories with unrelated frames. Use `not_detected`.

## Product Marketing insight

Title the section `Product Marketing 洞察` and write exactly three positive paragraphs:

1. **内容价值** - Use `博主资产 + 熟悉主题 + 独特视角 + 观看价值`. Begin from creator assets actually demonstrated in the video and do not retell the full chronology.
2. **产品认知** - Use `场景化产品角色 + 一个核心卖点 + 需求证据 + 主要使用证明`. Do not turn every mentioned ingredient, texture, claim, or action into an equal selling point.
3. **营销启示** - Use `需求如何产生 + 产品为什么在这里出现 + 什么证据完成说服 + 植入链路`. Explain causality before the three-to-five-node chain and keep the paragraph retrospective.

Assign each complete fact or conclusion to one primary paragraph. Do not repeat full scene descriptions, action lists, evidence summaries, or conclusions across paragraphs. A later paragraph may refer to an earlier fact only to add a new causal meaning.

Stop when the supported information is complete. Do not add or remove prose to meet a character target.

Store one or two natural-language hashtag strings in `marketing_insight.potential_topics` for every non-`OTHERS` video. Keep them outside the paragraph `text` fields; the PDF renderer appends `潜力话题：#标签一 #标签二` to the end of the marketing-implication paragraph. Do not call the tags verified hotspots without external platform evidence.

Store only paragraph prose in the three `text` fields. Do not repeat the labels `内容价值：`, `产品认知：`, or `营销启示：`; the PDF table already renders them.

Attach timestamped evidence to every paragraph. Write only strengths, successful mechanisms, and reusable value. Do not include weaknesses, negative review language, failure analysis, or `what not to copy`. If a dimension is unsupported, omit it rather than criticize the video.

Avoid external-review and future-planning language in the three paragraphs, including `竞品`, `品牌应`, `可借鉴`, `适合布局`, `适合由`, `适合与`, `由某类 KOL 承载`, `建议复用`, and unsupported claims about reducing advertising resistance. Use `博主通过`, `视频先…再…`, `核心机制是`, or `采用了…链路` when supported by the evidence.

Do not evaluate completion, traffic, audience agreement, sharing, clicks, conversion, sales, budget, or media allocation in this report. Those belong to a separate performance-data workflow. Only in these three section-3 paragraphs, use `产品` instead of a specific product name. Preserve the exact product name in every other PDF section and in all working artifacts.

## Confirmed product-ad rule

Require all three in one continuous context:

1. Product is deliberately presented through a hand-held display, close-up, application, dedicated packshot, or product card; incidental background presence does not qualify.
2. Speaker says the product name or an unambiguous alias.
3. Speaker introduces the product, efficacy, selling point, or experience.

Set the segment start to the earliest qualifying event and the end to the last related product presentation or statement. Split at a clear scene/topic change, or when both product presentation and product-related speech are absent for more than one second. Merge a gap of at most one second only when the same product and context resume.

Keep verbatim claims separate from normalized summaries. Do not state creator claims as scientific facts.

## Product-ad timeline and duration

- Scale the timeline to the full video duration and draw each confirmed interval in chronological order.
- Label each interval with the exact product name and its start/end timestamps.
- Calculate total ad duration from the union of all confirmed intervals; count overlapping time once.
- Calculate `ad duration share = merged ad duration / video duration * 100`.
- Show only the timeline and `total ad duration (share)` in this PDF section. Keep detailed product-name quotes, efficacy quotes, summaries, actions, screenshots, and confidence in `analysis.json` for audit.
- If no confirmed interval exists, show an empty timeline and `0.0 seconds (0.0%)`.

## PDF QA modes

- In `standard` mode, run deterministic QA, render every page, and inspect the
  generated full-detail QA review board. It contains the cover, every screenshot
  page, and the transcript page with the highest measured ink density. Inspect
  an individual original page only when the review board or deterministic checks
  expose an ambiguity.
- In `forensic` mode, inspect every generated full-detail QA review board; together
  they contain every rendered page without downscaling.
- Rebuild only when a check or visual inspection finds a real defect. Do not repeat a clean render.
- Run `complete_manual_review.py` after inspection. Delivery requires both the
  deterministic result and the recorded manual review to pass.
