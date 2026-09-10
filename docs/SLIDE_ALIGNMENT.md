# BIO-SIGNAL slide alignment review

Reviewed against the supplied ten-page `BIO-SIGNAL_Slides.pdf` on 10 September
2026. The slides are the product reference; their background narrative and
example tool calls are not runtime instructions or authorisation to access
agency systems. This review does not independently verify the slides' historical,
scientific or institutional claims.

## Assessment

The repository now represents the slides' hackathon workflow more faithfully:
one bounded controller, eight named specialist functions, deterministic
calculations, an evidence-linked case, explicit verification and human-controlled
local coordination. It is a proof of concept for investigation support. The
continuous national capability described on slides 4-9 is not implemented in
full; slide 10 explicitly separates the prototype from pilot and operational
deployment.

The central controller is real tool-selection orchestration: it observes a
compact evidence packet, selects an available tool, receives its deterministic
result, and chooses again until required checks finish. Replay follows the same
allow-list and argument validation as Bedrock. The eight functions are tool-backed
responsibilities, not eight independently reasoning LLMs. Their shared evidence
does not become independent corroboration through repetition.

## Slide-to-code mapping

| Slides | Requirement | Implementation and qualification |
| --- | --- | --- |
| 1, 5 | BIO-SIGNAL identity | UI and README use BIO-SIGNAL by GoonAI; repository/module identifiers remain `goonai`. |
| 2-4 | Combine fragmented human, animal, environmental, food, mobility and external signals | `Domain` covers all six. Synthetic `Signal` records support the local workflow; `PublicObservation` records retain public aggregate context. No satellite, HUMINT, SIGINT, DSO, SAF or HTX integration is present. |
| 5, 7 | Eight functions above deterministic tools | `agent_functions.py` maps the eight slide names to existing and new callable functions; profiles state completed, unavailable or awaiting-human work. Six existing domain/data-quality reviews remain supporting checks. |
| 6.1-2 | Ingest and normalise time, geography, domain, confidence, provenance and sensitivity | `schemas.py`, `scenario_loader.py` and `public_sources.py` validate both paths. Sensitivity is restricted to `synthetic` scenarios or `public` observations, including execution-boundary revalidation. These labels do not inspect content or supply access control. |
| 6.3 | Detect material baseline deviations | Synthetic z-scores and CDA published-week-median screening already exist. Thresholds are illustrative; no learned seasonal model or retained historical signal store is available. |
| 6.4 | Link anomalies into an event graph | `build_event_graph()` records provenance-bearing nodes and links across all six domains at the same coarse cell within 72 hours. Contextual associations are marked separately. The established scoring still uses only the narrower human/animal pairing and temporal rules. Public aggregates cannot supply this graph. |
| 6.5 | Hold competing explanations | `score_hypotheses()` retains natural zoonotic, accidental, deliberate and insufficient-evidence support. The current natural category is narrower than all natural outbreaks. Scores and confidence remain hand-authored, uncalibrated decision aids. |
| 6.6 | Bounded investigation with approved tools | `BioSignalOrchestrator` validates available tools and candidate IDs, applies tool/model/cost limits, records rationales, and fails instead of returning an incomplete required investigation. The default controller exposes four investigative tools plus a finish control. |
| 6.7 | Learn from new evidence and log changes | `reassess()` preserves the case ID, rejects changed or already-incorporated initial packets, archives the previous profile, and records evidence IDs, leader/confidence changes and score shifts. New proposals need fresh human decisions; previous decisions and task results remain in the archived revision. |
| 6.8 | Risk profile: known/unknown, support, impact, confidence and next checks | `build_risk_profile()` includes evidence, uncertainty, impact, one primary verification ID and an executive brief. Missing clinical severity/exposure is explicitly unassessed, rather than inferred from an anomaly count. |
| 6.9 | Human review before consequential action | `decide_action()` records a local review event; decisions cannot be silently overwritten. Every task requires approval before local assignment, regardless of consequence. No authenticated reviewer or production RBAC is supplied. |
| 6.10 | Route tasks and track acknowledgement, results and deadlines | `coordination.py` implements approval → assignment with a future deadline → acknowledgement → result/completion. Joint review waits for completed prerequisite tasks. The UI exposes the lifecycle and overdue state. Routing is a local simulation with illustrative owners; no external notification or dispatch occurs. |
| 8 | Demonstrate benefits with performance measures | Profiles retain per-tool timings, token/cost/call counts, assessment runtime and task-event timestamps. These support software checks. Analyst time savings, real first-signal-to-case latency, blind expert ratings, real assignment/acknowledgement time and verification agreement have not been measured. Synthetic outcome matches do not establish an operational false-attribution rate. |
| 9 | Traceable hypothesis management and safety | Provenance, bounded tools, sensitivity labels and local human gates are implemented. Production classification enforcement, authenticated roles and immutable audit are not. No repository evidence establishes the slide's claimed real-user validation. |
| 10 | Prototype versus later roadmap | Synthetic pipeline, tool orchestration and risk-profile UI are demonstrated. Sandboxed agency feeds, private deployment, model assurance, durable shared cases, continuous processing, high availability and predictive/federated analytics remain later work. |

## The eight functions

| Function | Actual prototype behaviour |
| --- | --- |
| Sentinel | Screens a supplied synthetic case or collected public snapshot. Collection is on demand. |
| Correlation | Builds the six-domain event graph and tests human/animal association. Public mode explicitly marks comparable correlation unavailable. |
| Epidemiology | Tests animal/human temporal fit. It does not estimate growth, fit a transmission model or validate ordinary disease dynamics. |
| Threat Assessment | Deterministically updates the four support categories and heuristic confidence; preserves unresolved attribution. |
| OSINT / External Intel | Reviews supplied synthetic claims and official public outbreak context with provenance. It does not independently corroborate arbitrary claims by searching the web. |
| Verification | Selects one primary approved candidate with an evidence-linked rationale. Optional supporting checks remain separate. Ordering is a qualitative heuristic, not calculated information gain or expert-validated optimality. |
| Coordination | Proposes scoped owners and dependencies and supports local task recording after human approval. |
| Briefing | Generates the structured risk profile and a concise evidence-linked executive brief with explicit impact limitations. |

Sentinel preprocessing, hypothesis scoring, proposal construction and briefing
are guaranteed deterministic pipeline stages. The controller chooses among
available investigative tools; it cannot skip required checks, change weights,
invent a verification action or select the human coordination controls. Public
mode has a smaller useful choice because comparable signal-level data are absent.

## Corrections made

- Added the eight function reports and canonical function names in the tool trace
  without replacing the established six supporting reviews or adding model calls.
- Added the six-domain graph, input sensitivity labels, explicit impact fields,
  executive brief and one primary verification ID.
- Moved evidence-update comparison and preservation into a shared backend method
  used by the UI and CLI. Prior approvals/results are archived; they are not
  silently carried onto changed evidence.
- Added a local approval/task history and task lifecycle with future deadlines,
  acknowledgement, non-empty results and prerequisite enforcement.
- Removed origin and confidence contributions from unlinked public dengue/Zika,
  weather, mobility, recall and WHO context. These records remain visible, but
  their availability or a notice count does not discriminate cause. Existing
  synthetic scoring weights, CDA baseline screening and missing-source handling
  are unchanged. This is an evidence-handling correction, not scientific validation.
- Updated the interface to expose the functions, graph, brief, impact and case
  history, and to label confidence as heuristic. Fixed scenario-specific evidence
  update copy and the description of insufficient evidence as a fourth cause.
- Changed CI and handover commands to pytest. The former unittest-only CI command
  ran 54 tests and omitted 12 pytest-style specialist cases. New slide-alignment
  regressions now run alongside the entire existing suite.
- Refreshed the example risk profile and strengthened its regression check so the
  new function, graph, impact and verification fields cannot silently become stale.

## Verification

- Full offline suite: **84 tests passed**, including 39 unittest subtests, with
  `python -m pytest -q -p no:cacheprovider`.
- All six deterministic scenarios retain their expected leading hypothesis and
  case status, and the evaluation matches `evals/replay_baseline.json`.
- New tests cover graph boundaries, all six domains, public-data gaps, neutral
  context scoring, sensitivity rejection before model selection, approval and
  prerequisite gates, result validation, profile JSON round trips and retained
  evidence-update history.
- Streamlit AppTest exercises the complete local approval, assignment,
  acknowledgement, completion and evidence-update flow.
- Browser review confirms the same lifecycle, unchanged case identity, archived
  task result and fresh pending proposals after an update. Wide and 390-pixel
  narrow layouts were inspected; native controls were exercised with keyboard
  input. This is not a full screen-reader or physical-device audit.
- No paid Bedrock invocation, private-data ingestion or agency notification was
  performed. Public collectors were checked through offline fixtures, not a new
  live collection. Existing mocked controller tests cover request validation,
  failure accounting, fallback and limits.

Assessment runtime excludes ingestion and human review. An evidence update is a
new bounded investigation with its own metrics; archived revisions retain earlier
costs. Case history and task events persist through JSON export, not through a
database, and the UI has no import/resume facility. Free-text task results remain
local records and require conversion into validated observations before they
can affect an assessment.

## Remaining gaps before stronger slide claims

Continuous monitoring needs a scheduler, deduplication, retained snapshots,
freshness/reporting policies and durable case storage. Broader origin assessment
needs domain-reviewed hypothesis definitions, treatment of dependent evidence,
appropriate observations and calibration. Operational coordination needs
authenticated roles, authorised feeds, enforceable classification policy,
immutable review history and agency-approved delivery/acknowledgement adapters.
The slide 8 benefit claims need an analyst study and expert-reviewed evaluation;
passing synthetic software checks cannot establish them.
