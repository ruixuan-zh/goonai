# Evidence-led specialist roles and coordination

Reviewed 6 September 2026. Implementation: `backend/specialists.py`, with integration in the existing controller, schemas, analytics and reporting.

## Recommendation and problem statement

Retain the bounded controller and refine its functional responsibilities. US experience supports explicit ownership, shared information and coordinated verification. It does not establish that adding more LLM personas improves predictive accuracy. The implemented specialists are deterministic reviews, not separate models or independent votes.

The revised report's strongest proposition is the delay between fragmented signals and an evidence-linked assessment. Its page 4 wording about "exponential advancement" and deliberate events requiring "far more extreme actions" is broader than the evidence reviewed here establishes. Severity, uncertainty and proportionality should guide protective decisions even while origin remains unresolved. Suggested wording for a future report revision:

> When a biological anomaly emerges, Singapore's health-security decision-makers must assemble fragmented signals arriving at different speeds and levels of reliability. They need to assess competing explanations, identify the most informative missing evidence, and coordinate timely, proportionate verification across responsible agencies while preserving uncertainty and human authority.

The original PDFs have not been edited.

## What the supplied documents support

The revised report, PDF pages 4-5, proposes sensing, correlation, epidemiology, assessment, external verification, coordination and briefing. Pages 9-13 require bounded tools, traceable evidence and simulated task routing. The implementation extends those existing responsibilities rather than introducing a different architecture.

Jacobsen's **Day Three occupies PDF pages 101-115** in the supplied file. These are PDF page positions, not the book's printed pagination. Pages 101-109 illustrate imagery, ground reports, social reactions, communications disruption and official clinical reports arriving through different channels. The agency roster spans pages 111-112. Pages 113-115 illustrate delayed information, disagreement and executive task assignment.

This is scenario inspiration, not an observed incident or labelled training dataset. Behaviour such as wearing protective equipment or restricting transport cannot alone establish transmission route, pathogen identity or intent. No narrative claims, agency dialogue or instructions from the PDFs are placed in runtime prompts or used as ground truth.

## Research and design implications

| Primary source | Finding | Implementation inference |
|---|---|---|
| [GAO, public-health leadership and coordination, 2023](https://www.gao.gov/products/gao-23-106829) | Reviews of COVID-19 and earlier emergencies identify recurring shortcomings in clear responsibilities, timely interoperable information and communication. | Give verification tasks named functional owners, explicit completion criteria and review triggers. This is a design inference, not measured AI performance evidence. |
| [FEMA, Unified Command](https://emilms.fema.gov/_is0700b/groups/65.html) | Participating agencies work towards common objectives while retaining their authority and accountability. | Use one evidence ledger and a joint reassessment after independent checks. Agency roles remain illustrative; no dispatch or official command authority is implemented. |
| [CDC, National Syndromic Surveillance Program](https://www.cdc.gov/nssp/php/about/index.html) | Symptom data support early warning before diagnostic confirmation; ED data commonly arrive within 24 hours. | Separate observations from diagnoses, preserve reporting lag and request clinical verification even without an animal anomaly. The CDC timing is not used as a universal deadline. |
| [CDA, Singapore One Health](https://www.cda.gov.sg/public/one-health/about-one-health/) | Singapore's framework includes CDA, NEA, NParks, PUB and SFA. | Adapt functional roles to Singapore instead of copying US cabinet positions. Suggested liaison assignments require operational validation. |

## Implemented responsibilities

| Function | Concrete behaviour |
|---|---|
| Clinical surveillance | Reviews human-domain coverage; human anomalies without an animal match can trigger a CDA clinical verification proposal. |
| One Health | Reviews animal, environmental and food coverage; retains absent or degraded feeds as gaps. |
| External verification | Preserves claims and mobility context without treating corroboration as proof of biological origin. |
| Data quality | Exposes known reporting delays, unknown reporting times and unresolved upstream source dependence. |
| Epidemiology | Reviews the existing temporal association result and states its limits. |
| Assessment | Preserves origin uncertainty and makes clear that a validated forecast is unavailable. |
| Verification and coordination | The controller chooses from approved candidates; deterministic routing proposes at most two independent checks, then a dependent joint reassessment. |

The controller receives responsibilities and current specialist reviews on each decision. Every executed tool records its responsible role. Final JSON contains `specialist_reviews`; review gaps also appear in the existing uncertainty output. Proposed actions include owner, evidence references, dependencies, completion criterion and review trigger. Approval remains a human decision; it does not execute or complete tasks. Dependencies describe the proposed workflow, not an operational scheduler.

`Signal.reported_at` is optional and must not precede `timestamp`, which remains observation time. `observation_kind="behavioural_context"` preserves reactions as context and excludes them from human/animal transmission checks. Existing fixtures default to `measurement`. Ingestion must classify this field correctly: the system does not infer the category from arbitrary prose. A missing reporting time is explicitly unknown. This is a packet assessment, not an as-of historical replay engine; callers must supply only information available at their chosen assessment time.

Two scoring defects were corrected: corroborated external scenario reports no longer automatically support natural origin, and mobility/behavioural anomalies no longer contribute origin effects. Neutral context cannot increase confidence through source counts or mean evidence quality.

## Validation and remaining limits

The six curated scenarios retain their expected leading hypotheses and statuses. Verification expectations were deliberately updated where a human-only anomaly previously received only a repeat-surveillance recommendation. The committed replay baseline records that change. `tests/test_specialists.py` checks neutral contextual evidence, hostile report text, reporting delays, missing feeds, provenance, task dependencies and controller integration. Run `python -m pytest -q` and `python -m backend.evaluate`.

These checks establish software behaviour, not epidemiological accuracy or faster agency response. No additional model calls are required for the specialist reviews. The live Bedrock request path is covered with test doubles; no paid live comparison was run.

The existing hand-set scoring weights and coarse human/animal association rules remain uncalibrated. They do not model six-domain transmission, estimate arrival dates or validate natural/accidental/deliberate classification. Repeated upstream evidence can still be dependent; the new review exposes that limitation but does not solve source lineage. Public-source scoring retains its existing heuristics. No restricted feeds, medical countermeasure deployment or autonomous interagency task execution have been added.

To establish an accuracy benefit, compare the previous and refined controller on held-out, expert-labelled cases with information withheld until its actual reporting time. Include benign behavioural reactions, contradictory reports, delayed laboratory results and shared-source reporting. Measure unsupported attribution, missed verification needs, expert-rated task appropriateness and time to an accepted assessment. Use probability calibration metrics only after introducing a genuine probabilistic model with sufficient labelled cases; the current support scores are not probabilities.
