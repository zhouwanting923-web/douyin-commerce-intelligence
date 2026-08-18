# Analysis JSON schema

Use UTF-8 JSON. Paths may be absolute or relative to the JSON file.

## Contents

1. Top-level structure
2. Evidence objects
3. Classification
4. Product advertising
5. Marketing insight
6. Screenshots
7. Transcript compatibility
8. Validation rules

## Top-level structure

```json
{
  "runtime": {
    "mode": "standard|forensic",
    "version": 2
  },
  "video": {
    "source_url": "",
    "normalized_url": "",
    "video_id": "",
    "title": "",
    "creator": "",
    "duration_seconds": 0,
    "local_video_path": ""
  },
  "classification": {
    "primary": "SEEDING",
    "secondary": "产品推荐/好物合集",
    "confidence": "high",
    "rationale": "",
    "positive_evidence": [
      {"start": 0, "end": 0, "source": "subtitle|ocr|visual", "quote": "", "frame_path": ""}
    ],
    "exclusion_rationale": ""
  },
  "product_ads": [
    {
      "start": 0,
      "end": 0,
      "product_name": "",
      "holding_or_presenting": true,
      "product_name_quote": "",
      "efficacy_quotes": [""],
      "efficacy_summary": "",
      "usage_action": "",
      "evidence_screenshots": [""],
      "confidence": "high"
    }
  ],
  "marketing_insight": {
    "content_value": {
      "text": "",
      "evidence": [
        {"start": 0, "end": 0, "source": "subtitle|ocr|visual", "quote": "", "frame_path": ""}
      ]
    },
    "product_perception": {
      "text": "",
      "evidence": [
        {"start": 0, "end": 0, "source": "subtitle|ocr|visual", "quote": "", "frame_path": ""}
      ]
    },
    "activation_implication": {
      "text": "",
      "evidence": [
        {"start": 0, "end": 0, "source": "subtitle|ocr|visual", "quote": "", "frame_path": ""}
      ]
    },
    "hook": {
      "mechanism": "",
      "target_circle": "emotion|problem|mixed",
      "familiar_motif": "",
      "distinctive_angle": "",
      "narrative_devices": [""],
      "evidence": [
        {
          "start": 0,
          "end": 0,
          "source": "subtitle|ocr|visual",
          "quote": "",
          "frame_path": "",
          "evidence_type": "observed_action|spoken_claim|user_feedback|displayed_data|external_proof|analyst_inference"
        }
      ]
    },
    "scene": {
      "audience": "",
      "occasion": "",
      "pain_point": "",
      "evidence": []
    },
    "product_entry": {
      "identity": "",
      "persona_fit": "",
      "integration_bridge": "",
      "evidence": []
    },
    "creator_assets_observed": "",
    "core_product_perception": "",
    "selling_point_strategy": {
      "core_selling_point": "",
      "supporting_points": [""],
      "strongest_rtb": {
        "category": "sensoriality|scientific_language|proof",
        "summary": "",
        "why_it_persuades": "",
        "evidence_type": "observed_action|spoken_claim|user_feedback|displayed_data|external_proof|analyst_inference",
        "start": 0,
        "end": 0,
        "source": "subtitle|ocr|visual",
        "quote": "",
        "frame_path": ""
      },
      "deprioritized_mentions": [""]
    },
    "rtb": {
      "sensoriality": [],
      "scientific_language": [],
      "proof": []
    },
    "cta": {
      "detected": false,
      "types": [],
      "purchase_barrier_reduced": "",
      "evidence": []
    },
    "viewer_payoff": "",
    "consumer_need": "",
    "product_role": "",
    "core_effective_mechanism": "",
    "integration_naturalness_basis": "",
    "integration_chain": ["", "", ""],
    "potential_topics": ["#标签一", "#标签二"],
    "confidence": "high"
  },
  "screenshots": [
    {
      "slot": "cover",
      "timestamp": 0,
      "path": "",
      "scene_description": "",
      "product_name": "",
      "evidence": "",
      "status": "selected"
    }
  ],
  "transcript": {
    "path": "transcript.json",
    "coverage": "complete|partial|none|unknown",
    "segment_count": 0
  },
  "evidence": {
    "path": "evidence.json"
  },
  "review": {
    "path": "review-packet.json",
    "board_path": "review/review-board.jpg",
    "product_signal_windows": [],
    "review_frames": [],
    "note": ""
  },
  "evidence_registry": {
    "opening": {
      "summary": "",
      "evidence_type": "observed_action",
      "start": 0,
      "end": 2,
      "source": "ocr",
      "quote": "",
      "frame_path": ""
    }
  },
  "draft_assistance": {
    "status": "review_required",
    "classification_evidence": [],
    "product_ads": [],
    "screenshots": [],
    "instructions": ""
  },
  "limitations": []
}
```

## Compact evidence references

`init_analysis.py` pre-populates `evidence_registry` from the compact review
packet. Reuse a registered item in any evidence field with:

```json
{"evidence_ref": "opening"}
```

Add field-specific values alongside the reference when needed:

```json
{
  "evidence_ref": "product_signal_1",
  "category": "proof",
  "why_it_persuades": "..."
}
```

`materialize_evidence_refs.py` expands references before ordinary schema
validation. Registry entries and product-signal windows remain review inputs;
they do not by themselves confirm a classification, advertisement, efficacy
claim, or screenshot slot.

`draft_assistance` is an auditable prefill queue. Its classification evidence,
ad search intervals, and screenshot paths are suggestions only. Nearby signal
windows may be merged so the reviewer can trim one continuous candidate instead
of manually joining fragments. Review them against the packet and board, keep
only supporting label evidence, promote only ads that pass the three-part rule,
and copy only verified screenshots into the canonical top-level fields.

After references are expanded, `preflight_analysis.py` repairs two mechanical
relationships before strict validation: every hook evidence item must begin
within the first three seconds, and `strongest_rtb` must inherit its evidence
fields from one matching item in the declared RTB category. It preserves the
chosen category and analyst-authored persuasion explanation.

## Reusable Product Marketing evidence item

Items inside `hook.evidence`, `scene.evidence`, `product_entry.evidence`, each RTB array, and `cta.evidence` use:

```json
{
  "summary": "",
  "evidence_type": "observed_action",
  "start": 0,
  "end": 0,
  "source": "visual",
  "quote": "",
  "frame_path": ""
}
```

`summary` is required for RTB items and optional elsewhere. At least one of `quote` or `frame_path` is required.

`selling_point_strategy.strongest_rtb` uses the same evidence fields and additionally requires:

- `category`: the matching RTB bucket: `sensoriality`, `scientific_language`, or `proof`;
- `why_it_persuades`: why this evidence is the strongest fit for the selected core selling point.

Choose the strongest RTB by fit with the selling point, not by a universal evidence ranking. Its `summary`, timestamps, and `evidence_type` must match one item in the declared `rtb` category; `why_it_persuades` explains the prioritization.

## Allowed values

- `classification.primary`: `DRAMA`, `SEEDING`, `LIFESTYLE`, `BRANDING`, `OFFER`, `OTHERS`.
- `confidence`: `high`, `medium`, `low`.
- `hook.target_circle`: `emotion`, `problem`, `mixed`.
- `evidence_type`: `observed_action`, `spoken_claim`, `user_feedback`, `displayed_data`, `external_proof`, `analyst_inference`.
- `selling_point_strategy.strongest_rtb.category`: `sensoriality`, `scientific_language`, `proof`.
- `cta.types`: `threshold_reduction`, `scene_summary`, `emotional_permission`, `direct_action`.
- Screenshot slots: `cover`, `product_alone`, `product_detail`, `selling_point`, `use_process_1`, `use_process_2`, `after_effect`.
- Screenshot status: `selected`, `not_detected`.

## Evidence requirements

- Classification requires at least one positive-evidence item and a non-empty exclusion rationale.
- A confirmed product-ad item requires `holding_or_presenting=true`, a product name, a spoken product-name quote, at least one efficacy/introduction quote, and at least one screenshot. Interpret deliberate presentation as a hand-held display, close-up, application, dedicated packshot, or product card; exclude incidental background presence.
- For each confirmed product-ad item, set `start` to the earliest qualifying presentation/name/claim event and `end` to the last related presentation or statement in the continuous context. Split at a clear scene/topic change or after more than one second with neither product presentation nor product-related speech. Merge gaps of at most one second only for the same product and context, and store intervals in chronological order.
- Require `0 <= start < end <= video.duration_seconds`.
- Derive PDF ad duration from the union of all `product_ads` intervals and calculate its share of total video duration. Do not store redundant summary fields in the JSON.
- Each selected screenshot requires a valid path, timestamp, and scene description.
- Each missing screenshot requires `status=not_detected` and an empty path.
- The three report paragraphs each require non-empty text and at least one timestamped evidence item.
- Treat internal marketing fields as evidence inputs, not a prose checklist. Draft from a single creator-specific viewing value, a single product perception and selling point, one primary proof with subordinate support, and one causal mechanism.
- Use the fixed paragraph logic: `content_value = creator asset + familiar theme + distinctive angle + viewing value`; `product_perception = situated product role + one core selling point + need evidence + primary usage proof`; `activation_implication = need formation + product-entry reason + persuasive function + integration chain`.
- Assign each complete fact or conclusion to one primary paragraph. Do not repeat a full scene description, action list, proof, or conclusion across paragraphs.
- Require every selected detail to state or clearly support a persuasive job; chronology and equal-weight claim inventories do not satisfy the schema.
- Stop when the supported reasoning is complete. Do not add or trim prose to satisfy a character target.
- For every type except `OTHERS`, require a populated `hook` and `scene`.
- For every type except `OTHERS`, require `creator_assets_observed`, `core_effective_mechanism`, `integration_naturalness_basis`, and an `integration_chain` of three to five non-empty nodes.
- Require the exact `integration_chain` joined with `—` to appear in `activation_implication.text`.
- Require causal explanation before the exact chain in `activation_implication.text`; the chain must not open the paragraph.
- For every type except `OTHERS`, require `potential_topics` to contain one or two natural-language hashtag strings. Each string must begin with `#`, contain no whitespace or sentence punctuation, and derive from the observed scene, relationship, or consumer concern. Store the tags outside `activation_implication.text`; the PDF renderer appends them as `潜力话题：#标签一 #标签二`.
- When at least one confirmed product ad exists, require populated `product_entry`, `core_product_perception`, `selling_point_strategy.core_selling_point`, one fully evidenced `selling_point_strategy.strongest_rtb`, and at least one RTB item.
- `selling_point_strategy.supporting_points` and `deprioritized_mentions` are internal arrays and may be empty. Deprioritized mentions must not be framed as criticism and normally stay out of the report prose.
- Every new Product Marketing evidence item requires timestamps, source, evidence type, and a quote or frame.
- Hook evidence must begin in the opening three seconds.
- If `cta.detected=true`, require at least one CTA type, a purchase barrier, and evidence. If false, keep `types`, `purchase_barrier_reduced`, and `evidence` empty.
- `viewer_payoff`, `consumer_need`, and `product_role` remain required internal reasoning fields for every type except `OTHERS`.
- Report paragraphs must state only strengths, successful mechanisms, and reusable value. Omit unsupported dimensions instead of adding negative critique.
- The three report paragraphs must not use external-review or future-planning phrases such as `竞品`, `品牌应`, `可借鉴`, `适合布局`, `适合由`, `适合与`, `由某类 KOL 承载`, or `建议复用`.
- Do not evaluate actual completion, traffic, sharing, clicks, conversion, sales, budget, or media allocation in this report.
- Only the three report paragraph `text` fields replace specific product names with `产品`; preserve exact names in classification, transcript, spoken quotes, packaging observations, screenshot descriptions, product-ad details, and all other evidence or audit fields.
- Keep the canonical transcript in the file referenced by `transcript.path`; do not duplicate all segments inside `analysis.json`.
- The referenced transcript must preserve segments with `start`, `end`, `text`, `source`, and optional `confidence`. V1 analyses with embedded `transcript.segments` remain valid for backward compatibility.
- Keep the shared chronological evidence index in the file referenced by `evidence.path`. Use it for classification, ad detection, screenshot selection, and Product Marketing reasoning before requesting any additional exact frame.
- Start from the compact packet referenced by `review.path`; query the larger
  chronological index only for a disputed boundary, quote, or frame.
