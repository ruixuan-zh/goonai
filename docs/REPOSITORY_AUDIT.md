# BIO-SIGNAL repository audit

Audit date: 5 September 2026.

## Assessment

BIO-SIGNAL is a coherent, small decision-support demonstration. Its useful contribution is assembling fragmented observations into a traceable investigation brief, exposing missing evidence and giving an officer a bounded next verification step. It is suitable for continued prototype development. It is not yet a validated biological-risk assessment service, and passing its tests must not be presented as evidence of clinical or attribution accuracy.

This audit reviewed every tracked Python module, scenario, test file, dependency declaration, workflow and example, together with the README and handover guide. It covered data contracts, parsing, source boundaries, analytical assumptions, orchestration, cost accounting, output integrity, UI interactions, dependencies and documentation. Local credentials were not inspected or used for paid model calls.

## What the repository actually does

The goal documented in the README is to help a Singapore health-security duty officer correlate human, animal, environmental, food, mobility and external signals after a suspected anomaly, compare explanations and decide what evidence to obtain next.

There are two input paths:

1. **Public collection:** nine collectors retrieve official aggregate information. Seven can supply measurements or notices; AVS and wastewater currently supply programme descriptions without granular measurements. The code normalises records and provenance, screens CDA counts against published medians and summarises the other sources as context.
2. **Synthetic scenarios:** six local JSON cases contain aggregate observations with explicit synthetic markers, baselines, coarse locations and timestamps. Python detects anomalies, checks nearby animal/human pairs and their temporal order, and weights supplied external reports.

A controller chooses an allowed next tool. Replay uses a deterministic policy; live mode sends a compact evidence packet to Bedrock. Python, rather than the language model, calculates support scores. Reporting builds the findings, uncertainty, proposed action and trace. Streamlit and the command line expose the result and JSON downloads. Approval changes an in-memory status; it does not contact an agency or perform the action.

Public mode cannot run the same location-and-time correlation as the scenarios: national aggregates and missing animal measurements do not provide the necessary paired observations. It now moves directly from public evidence to verification selection rather than running synthetic tools on an empty signal list.

There is no model training, continuous monitoring, stored historical time series, outbreak forecasting, pathogen identification, validated intent attribution or operational dispatch in this repository.

## Defects and redundancies addressed

| Priority | Finding and impact | Change |
| --- | --- | --- |
| P1 | HTTP redirects were checked only after following them, so an unapproved destination could receive a request. Responses were unbounded. | Validate each redirect before following it; reject embedded credentials and non-standard ports; cap responses at 10 MiB. |
| P1 | Public runs added correlation and temporal findings from an empty synthetic signal list. A total collection failure could return medium confidence and routine monitoring. | Separate required tools by input path; treat absent critical sources as gaps; return low confidence and verification when there is no usable public evidence. |
| P1 | Inputs admitted non-finite measurements, ambiguous timestamps, implicit synthetic markers and duplicate signal IDs that could inflate support. | Require finite values, timezone-aware timestamps, explicit boolean synthetic markers, unique IDs and consistent public source counts/provenance. |
| P1 | Sonnet requests set a sampling parameter rejected by Sonnet 5. Permitted tool rules were not enforced uniformly for custom controllers. | Omit non-default sampling, use automatic tool selection and enforce one available tool, bounded rationale and approved arguments locally. |
| P1 | Failed model attempts were not counted; invalid responses could lose reported usage; public initial fallback and reused-controller fallback could be hidden. | Count attempts before invoking, retain usage supplied with rejected responses, persist fallback state and expose it in UI/CLI. |
| P2 | Model-call exhaustion could stop a case before checks completed even when replay fallback was enabled. SDK retries were outside the application call counter. | Complete remaining checks through explicit replay fallback, otherwise fail; disable SDK retries and set connection/read timeouts. |
| P2 | The budget was checked only after a paid response, and documentation claimed an unverified current tariff. | Add conservative preflight estimation, retain post-response checking and label rates as planning assumptions. |
| P2 | CDA units depended on whether a value exceeded 1,000. Wrapped COVID positivity text was missed. Some empty parses appeared available. | Use row structure for attendance units, accept comma-separated counts and decimal/wrapped positivity, require the reporting date, derive median reference years when present and report empty parses as partial. Include the year in CDA IDs. |
| P2 | A single failed weather endpoint discarded successful readings; the first reading was assumed newest. | Preserve successful endpoints, select the latest timestamp and expose partial failures. |
| P2 | Failed sources lost their publisher, domain and URL. Unknown red-cluster words became zero; country substrings could misclassify regional reports; future notices counted as recent. | Reuse manifest metadata on failure, avoid fabricated zero counts, match whole country terms and bound the recent window on both sides. Label SFA counts as counts within the retrieved sample. |
| P2 | Simultaneous animal/human observations counted as animal-before-human evidence. | Require strict temporal precedence; simultaneous observations may still correlate. |
| P1 | The custom light background conflicted with native dark-theme controls, making labels difficult to read. | Configure the incumbent colours through Streamlit's native theme rather than overriding only the page background. |
| P2 | Failed public refreshes could pair an old profile with a new snapshot; repeated evidence injection reran an identical assessment. | Commit profile and snapshot together after success, stop result rendering on refresh failure and disable repeated injection until a new investigation. |
| P2 | UI headings skipped a level and desktop metrics could truncate the leading hypothesis. | Use second-level section headings, wrap metric values, label support bars and expose source retrieval notes. |
| P2 | Conflicting CLI output paths could overwrite the snapshot; unrelated options were silently ignored. Evaluation always exited successfully. | Reject invalid option combinations and identical output paths; return a failing evaluation exit code when acceptance metrics fail. |
| P2 | The illustrative risk example had stale scores and was not a valid `RiskProfile`; a separate handwritten trace duplicated it. | Generate a full current example, remove the duplicate trace and regression-check the example and committed evaluation baseline. |
| P2 | The local virtual environment's pip 25.0.1 had public vulnerability advisories. | Upgrade that environment's pip to 26.2.1 and repeat the advisory check. Runtime dependency pins were unchanged. |

Other cleanup removed an unused endpoint and import, centralised the critical-source gap rule and required-tool definitions, deferred the PDF import until PDF ingestion, and removed duplicate support-label rendering. Separate analytical modules, tests and the synthetic cases were retained because they have distinct responsibilities.

The Sonnet request changes follow [the provider's migration notes](https://platform.claude.com/docs/en/models/sonnet-5/whats-new-sonnet-5) and [AWS tool-use constraints with thinking](https://docs.aws.amazon.com/bedrock/latest/userguide/claude-messages-extended-thinking.html). The configured global model identifier is listed in [AWS's model documentation](https://docs.aws.amazon.com/en_en/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5.html). These checks do not establish access for this AWS account.

## Verification

- The original 22 tests passed before changes. The expanded suite has 54 tests covering the fixes, including parser fixtures, rejected redirects, malformed input, unavailable tools, budget preflight, degraded public collection and Streamlit state transitions.
- All six curated scenarios retain their expected leading hypothesis and case status. The current evaluation matches the committed baseline exactly; the audit did not retune synthetic scoring weights to make tests pass.
- Live public collection after the final parser changes returned **98 observations**, **seven available measurement/notice sources** and **two context-only sources**. The public report contained eight compact evidence records and one verification-selection tool call, with zero model calls. Counts describe this audit snapshot and will change as sources publish updates.
- The final public result was `insufficient_evidence`, low confidence, with verification required. This is a software integration result, not an independent assessment of Singapore's biological risk.
- `pip check` found no incompatible installed requirements. A public OSV query of all **53 installed distributions** initially flagged only pip; the repeat query after updating pip returned no advisories. This is a point-in-time database check, not a security certification.
- A tracked-file credential-pattern scan found no matching AWS access IDs, private-key blocks, GitHub personal tokens or Anthropic key patterns. `.env` and generated outputs are ignored; no `.env` history was found in the local Git history. This is not an exhaustive secret or remote-history audit.
- Browser review exercised the curated workflow, including keyboard focus between approval buttons. A narrow viewport was inspected, but mobile-specific fixes were excluded at the user's request. Automated UI checks cover initial load, source switching, approval state, repeat-injection prevention and failed refreshes. The UI detector reported no findings for the Python target; this detector has limited coverage of Streamlit-generated markup.

Temporary integration evidence is in ignored `output/audit-public-snapshot.json`, `output/audit-public-profile.json` and `output/audit-dependency-advisories.json`.

## Remaining limitations and priorities

### P1: scientific validity and hypothesis meaning

The support weights and confidence thresholds are hand-authored. Anomaly, correlation and temporal evidence can reuse the same observations, so multiple evidence records are not necessarily independent corroboration. Source IDs do not establish source independence. Generic food, weather and mobility context can increase natural-zoonotic support without demonstrating zoonotic transmission; even the presence of a feed can affect support independently of its value. The natural category is specifically labelled `natural_zoonotic`, which does not encompass every natural outbreak.

These are limitations of the model's meaning, not ordinary refactoring defects with an established correct replacement. The audit preserved the original scoring rules and made the limitations explicit. A domain-reviewed hypothesis taxonomy, statistical approach and evidence-dependence policy are prerequisites for interpreting the scores beyond a demonstration. Adding more generated scenarios cannot substitute for this validation.

### P1: evidence coverage and timing

The public path lacks the animal-health and wastewater measurements needed for the intended cross-domain assessment. Sources have incompatible time resolutions, national aggregation and notification delays. Some HTML collectors use collection time as an approximation for observation time. There is no source-specific stale-data exclusion policy, year-rollover fallback for an unpublished CDA index, completeness guarantee for PDF rows, or retained history for trend estimation. Twenty recent notices are a sample, not a complete 90-day event census.

Extend ingestion with explicit reporting intervals, freshness policies, retained source snapshots and authorised cross-domain measurements before making stronger correlation claims. Preserve parser regression fixtures when source layouts change.

### P1 before a shared pilot: human decisions and access controls

Approval is a local UI state change. There is no authenticated reviewer identity, append-only decision history, durable case storage, role-based access or multi-user case ownership. Restarting or losing a Streamlit session loses its working state unless a JSON output was saved. These features are needed before treating the interface as a shared approval system.

### P2: live-controller validation and cost estimates

No paid Bedrock invocation was made during this audit. Mocks validate request construction, usage accounting, tool validation and fallback, but not account credentials, permissions, actual latency or model behaviour. Run the documented smoke test with fallback disabled to establish those properties. The default 300-token ceiling includes thinking and can truncate a decision. The preflight token estimate and US$3/US$15 planning rates are not an account-wide spending cap or verified current tariff; requests that fail without usage information cannot be billed accurately from local counters.

### P2: release reproducibility and accessibility

Direct dependencies are pinned, but transitive dependencies are not locked. CI covers Python 3.11/3.12 on Linux; this audit's local run does not replace that matrix. Add reproducible dependency resolution and scheduled advisory checks when preparing a release. A licence and deployment/retention policy also need explicit maintainer choices before distribution or a pilot.

Native controls provide the basic keyboard/accessible-name behaviour, and the theme mismatch was fixed. A full screen-reader audit, every browser/theme override and every viewport have not been certified. Dense trace tables remain less convenient on a narrow screen than the primary investigation controls.

## How to move towards the goal

1. **Confirm the officer's decision and success measure.** Use the existing demo to test whether an officer can find the important evidence gap, understand its provenance and choose the next check faster and more reliably than with the separate source pages.
2. **Improve evidence before adding model complexity.** Add reporting intervals, retained snapshots, freshness checks and approved animal/wastewater data. These address the largest gap between the demonstration and its stated purpose.
3. **Validate the analytical meaning.** Have appropriate domain reviewers define the hypotheses, handle dependent evidence and evaluate meaningful missing, contradictory and benign cases. Report false alarms, missed signals, uncertainty handling and human-review agreement rather than only six expected-output matches.
4. **Measure the controller's added value.** Compare live tool selection with replay on those cases. The public path currently offers a very small choice of verification actions; a larger agent architecture is not justified unless it demonstrably improves that decision.
5. **Add pilot infrastructure only after that evidence.** Durable cases, authenticated review, decision history, observability and data-governance controls turn the validated workflow into a service. Continuous monitoring and operational integrations are separate additions, not capabilities already supplied by this repository.
