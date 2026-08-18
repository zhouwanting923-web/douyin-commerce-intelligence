# Standard analysis brief

Use this compact reference for ordinary Standard runs. Keep the transcript
external, reuse the evidence registry, write `analysis.json` once, and let the
validator identify any omitted mechanical field.

Start from `draft_assistance`: review the three chronological label-evidence
candidates, trim and confirm or reject each merged ad search interval, and
accept or replace the screenshot suggestions. Never copy a `review_required` ad into
`product_ads` until deliberate presentation, a spoken product name or alias,
and a selling point or usage experience are confirmed in one continuous
context.

## Classification

Apply the primary priority exactly:

`DRAMA -> SEEDING -> LIFESTYLE -> BRANDING -> OFFER -> OTHERS`

Within the chosen primary, test secondary labels top to bottom:

- DRAMA: `剧情演绎/短剧`; `连续剧集/IP人物`.
- SEEDING: `知识科普/搜索答疑`; `使用教程/方法演示`;
  `产品推荐/好物合集`; `测评/真实体验`; `效果展示/前后改造`;
  `场景化/沉浸式种草`.
- LIFESTYLE: `日常Vlog/生活记录`; `生活方式/场景内容`;
  `探店/服务体验`.
- BRANDING: `品牌广告/Campaign`; `代言人/IP/联名`;
  `品牌故事/科技/事件`.
- OFFER: `优惠促销/直接售卖`; `直播预告`; `直播切片/成交高光`.
- OTHERS: `非相关内容`.

Key boundaries:

- DRAMA requires character performance, plot, conflict, or reversal as the main
  viewing value. If drama is only the hook and the remainder explains a product,
  use SEEDING.
- SEEDING requires product decision information, teaching, testing, effects, or
  immersive product experience as the main line.
- LIFESTYLE keeps the person, routine, service, or life scene as the main line.
- BRANDING centers brand proposition, campaign assets, IP collaboration, brand
  history, technology, or event rather than product decision information.
- OFFER requires conversion mechanics such as price, discount, urgency, cart,
  live-room direction, or explicit purchase action as the main line.

Record positive timestamped evidence and the decisive exclusion boundary.

## Confirmed product advertisement

Confirm an interval only when one continuous context contains all three:

1. deliberate hand-held display, close-up, application, packshot, or product card;
2. spoken product name or unambiguous alias;
3. introduction, efficacy, selling point, or usage experience.

Start at the earliest qualifying event and end at the last related presentation
or statement. Split after a clear topic change or over one second with neither
product display nor product speech. Keep verbatim claims separate from the
normalized summary and attribute efficacy statements to the video.

## Required reasoning

For every non-`OTHERS` result, commit to:

- one demonstrated creator asset;
- one opening hook and one situated audience/occasion/pain point;
- one viewer payoff and consumer need;
- one product role and entry bridge when an ad is confirmed;
- one core product perception and one core selling point;
- one strongest RTB chosen by fit;
- one causal integration mechanism and a three-to-five-node observed chain;
- one or two natural hashtags.

Evidence types are `observed_action`, `spoken_claim`, `user_feedback`,
`displayed_data`, `external_proof`, and `analyst_inference`. Every marketing
evidence item needs timestamps, `source` (`subtitle`, `ocr`, or `visual`), its
type, and a quote or frame path.

RTB categories:

- `sensoriality`: visible texture, dispensing, spread, finish, or comfort.
- `scientific_language`: ingredient, technology, specification, or mechanism.
- `proof`: repeated use, time-separated check-in, comparison, reading,
  before/after, or independently verified support.

An ingredient mention is scientific language, not proof. If no CTA exists, keep
the CTA arrays and barrier string empty.

Add the chosen evidence item to its RTB category first, then reuse that item for
`strongest_rtb`. The finalize preflight synchronizes its mechanical evidence
fields while preserving `category` and `why_it_persuades`.

## Three report paragraphs

Write exactly three positive paragraphs:

1. `content_value`: creator asset + familiar theme + distinctive angle + viewing
   value. Begin with the creator asset, not “视频用/把/以”.
2. `product_perception`: situated product role + the phrase `核心卖点` + need
   evidence + primary use or proof.
3. `activation_implication`: explain causality first, then include the exact
   `integration_chain` joined with `—`.

Use `产品` instead of the exact product name only in these three paragraph texts.
Do not use future-planning, external-review, negative critique, traffic,
conversion, sales, budget, or media-allocation claims. Attach timestamped
evidence to every paragraph.

## Seven screenshots

Output exactly, in order:

1. `cover`
2. `product_alone`
3. `product_detail`
4. `selling_point`
5. `use_process_1`
6. `use_process_2`
7. `after_effect`

Each selected slot needs a valid path, timestamp, scene description, and evidence.
Use `not_detected` with an empty path when the required scene is absent; never
substitute an unrelated frame.

## QA

Finalize once. In Standard mode inspect the single full-detail QA board for
clipping, overlap, missing images, unreadable text, and incorrect screenshots.
If clean, record manual review immediately. Open an original PDF page only when
the board shows a concrete ambiguity.
