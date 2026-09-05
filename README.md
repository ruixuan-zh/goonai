# BIO-SIGNAL

BIO-SIGNAL implements the target stated in the Agentic AI Biodefence problem statement: when a biological anomaly is detected in Singapore, help government health-security decision-makers correlate fragmented human, animal, environmental, food, mobility and external-intelligence signals; compare natural, accidental and deliberate explanations; identify the most valuable missing evidence; and prepare a timely, evidence-linked risk profile for human action.

The prototype's point-of-view statement is: **a Singapore public-health surveillance duty officer responding to a suspected cross-domain anomaly needs a quick way to assemble traceable evidence and identify the next verification step, because the relevant public indicators are published separately and important animal-health and wastewater measurements may be unavailable publicly.** The repository demonstrates the technical fragmentation through its source manifest and coverage reporting. This statement is not presented as interview-validated or as a measured operational baseline; those claims require evidence from the intended users.

The system is a differential-assessment and investigation prototype, not an attack classifier. It does **not** identify a pathogen, claim causality, attribute intent, or dispatch an operational action. If public evidence cannot distinguish competing explanations, `insufficient_evidence` must remain a valid leading result.

The repository is sized for a hackathon build that can be understood, run and demonstrated in a few days. Claude Sonnet 5 on Amazon Bedrock is the optional decision controller; deterministic Python performs every calculation that affects evidence and support scores. A keyless replay controller makes the submitted demo reproducible.

## Demonstrated outcome

The primary path uses current public Singapore sources. Curated synthetic cases remain available to test spillover, benign and contradictory situations that public aggregate feeds cannot safely expose:

```text
allow-listed Singapore public sources
        ↓
validated aggregate observations + provenance
        ↓
deterministic screening and compact evidence
        ↓
bounded Sonnet/replay controller chooses approved tools
        ↓
natural / accidental / deliberate / insufficient differential
        ↓
coverage gaps + recommended verification → human approval gate
```

Six scenarios are supplied:

| Scenario | Purpose | Expected outcome |
|---|---|---|
| `zoonotic_spillover` | Animal anomaly precedes a nearby human cluster | Investigate; natural zoonotic is leading |
| `seasonal_outbreak` | Human rise without an animal anomaly | Monitor; insufficient evidence is leading |
| `contradictory_evidence` | Correlated signals, reversed temporal order and an uncorroborated report | Verify; medium confidence |
| `geographic_mismatch` | Human and animal anomalies occur in different locations | Monitor; insufficient evidence is leading |
| `human_only_signal` | Human anomaly lacks animal-domain corroboration | Monitor; insufficient evidence is leading |
| `imported_outbreak_context` | Regional outbreak context accompanies a local human signal | Monitor; insufficient evidence is leading |

Support scores are transparent decision aids. They are **not probabilities** and have not been clinically calibrated.

## Repository layout

```text
goonai/
├── README.md
├── requirements.txt
├── .env.example
├── backend/
│   ├── schemas.py              # Validated synthetic and public data contracts
│   ├── scenario_loader.py      # Safe JSON loading and validation
│   ├── public_sources.py       # Allow-listed Singapore public-data ingestion
│   ├── analytics.py            # Deterministic analytical tools
│   ├── hypothesis_scoring.py   # Evidence-weighted support scoring
│   ├── orchestrator.py         # Replay/Bedrock controller and limits
│   ├── reporting.py            # Risk brief and approval gate
│   ├── evaluate.py             # Deterministic scenario evaluation
│   └── run_demo.py             # Command-line demonstration
├── frontend/
│   └── app.py                  # Streamlit operator interface
├── data/scenarios/             # Six synthetic JSON scenarios
├── data/public_sources.json    # Auditable public-source manifest
├── docs/TESTING_AND_HANDOVER.md # Reviewer and maintainer guide
├── evals/replay_baseline.json  # Reproducible regression baseline
├── examples/                   # Validated example risk profile, including its trace
├── tests/                      # Schema, analytics, scoring and E2E tests
└── .github/workflows/tests.yml # Offline continuous integration
```

## Quick start

Python 3.11 or newer is recommended.

### Windows PowerShell

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m backend.run_demo --scenario zoonotic_spillover --mode replay
streamlit run frontend/app.py
```

### macOS or Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m backend.run_demo --scenario zoonotic_spillover --mode replay
streamlit run frontend/app.py
```

Replay mode does not contact AWS and requires no credentials or `.env` file. To save a machine-readable result:

```powershell
python -m backend.run_demo --scenario zoonotic_spillover --mode replay --include-new-evidence --output output/risk-profile.json
```

To retrieve current Singapore public information without spending on Bedrock:

```powershell
python -m backend.run_demo --public-data --mode replay `
  --snapshot-output output/singapore-public-snapshot.json `
  --output output/public-risk-profile.json
```

Public-source collection needs outbound HTTPS access. Individual failures are recorded as `unavailable`; they do not silently remove other sources.

## Running with Sonnet 5 on Amazon Bedrock

The default model is `global.anthropic.claude-sonnet-5`, invoked through the Bedrock Converse API. Model availability and inference-profile identifiers can vary by AWS account and region, so replace `BEDROCK_MODEL_ID` in `.env` if the Bedrock console shows a different identifier.

Use an AWS profile or IAM role where possible:

```powershell
aws configure --profile bio-signal
# Set AWS_PROFILE=bio-signal in .env
python -m backend.run_demo --public-data --mode live
```

The runtime identity only needs permission to invoke the selected Bedrock model. Do not commit access keys. `.env` is ignored by Git, and `.env.example` contains blank credential fields; local `.env` contents are private configuration. The normal boto3 credential chain is used. See the [testing and handover guide](docs/TESTING_AND_HANDOVER.md) for API-key, profile and temporary-credential examples.

Live mode has these default guards:

- no more than four Sonnet decisions per case;
- no more than six deterministic tool executions;
- no more than 300 generated tokens per decision;
- provider-default sampling and exactly one locally validated, allow-listed tool per accepted decision;
- an estimated US$1 per-investigation stop;
- safe replay fallback if Bedrock is unavailable.

The cost estimator retains conservative planning rates of US$3 per million input tokens and US$15 per million output tokens. At four calls of 3,000 input and 300 output tokens each, the estimate is about **US$0.054 per case**. These are planning assumptions, not a verified current Sonnet 5 tariff. The guard checks a conservative request estimate before each call and reported usage afterwards; provider tokenisation, failed requests without usage and billing can differ. This is not an AWS billing control: confirm current rates on the [Amazon Bedrock pricing page](https://aws.amazon.com/bedrock/pricing/) and configure an [AWS Budget](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html) for the account.

Sonnet is used because the controller benefits from strong instruction following and tool selection, while using a larger model for deterministic maths would add cost without improving auditability. The controller cannot alter scoring weights or execute arbitrary functions.

## Data: what is used and where it goes

No personal, patient-level, classified, proprietary or non-public operational data is collected. The live path currently integrates:

| Source | Public fields used | Access/cadence |
|---|---|---|
| [CDA Weekly Infectious Diseases Bulletin](https://www.cda.gov.sg/resources/weekly-infectious-diseases-bulletin-2026/) | Notifiable-disease counts, corresponding-week medians, polyclinic attendances, influenza and COVID positivity | Weekly PDF |
| [NEA dengue cases](https://www.nea.gov.sg/dengue-zika/dengue/dengue-cases) | Latest completed-week cases, active clusters and red-alert clusters | Daily HTML |
| [NEA Zika cases and clusters](https://www.nea.gov.sg/dengue-zika/zika/zika-cases-and-clusters) | Public cumulative case situation | Daily HTML |
| [data.gov.sg rainfall API](https://api-open.data.gov.sg/v2/real-time/api/rainfall), [temperature API](https://api-open.data.gov.sg/v2/real-time/api/air-temperature), [humidity API](https://api-open.data.gov.sg/v2/real-time/api/relative-humidity) | Current station-level measurements, reduced locally to national minimum/mean/maximum | Near-real-time JSON |
| [SFA food alerts and recalls](https://www.sfa.gov.sg/news-publications/circulars-and-notices/food-alerts-and-recalls) | Twenty latest alert titles, dates and source URLs | Structured public search endpoint |
| [Changi traffic statistics](https://www.changiairport.com/en/corporate/about-us/traffic-statistics.html) | Latest monthly passenger movements | Monthly HTML |
| [WHO Disease Outbreak News](https://www.who.int/emergencies/disease-outbreak-news) | Latest twenty official outbreak reports; locally screened for regional relevance to Singapore | Event-driven JSON API |
| [AVS biosurveillance](https://avs.nparks.gov.sg/about-us/what-we-do/animal-health/biosurveillance/) | Programme scope only | No granular public measurements found |
| [NEA wastewater surveillance](https://www.nea.gov.sg/corporate-functions/resources/research/environmental_health_institute/wastewater-surveillance-programme) | Programme scope only | No current site-level measurements found |

| Layer | Data used | Destination |
|---|---|---|
| Source documents | Official public HTML, JSON and CDA PDF content | Retrieved and parsed locally from fixed allow-listed hosts |
| Normalised public snapshot | Aggregate observations, timestamps, source URLs, quality and limitations | Validated locally by Pydantic; downloadable from UI/CLI |
| Scenario inputs | Synthetic timestamps, coarse grid cells, aggregate counts, baselines, source confidence and provenance | Offline evaluation path only |
| Analytics | All normalised observations and scenario signals | Deterministic local Python only |
| Sonnet packet | Compact evidence findings, source coverage, support scores, open questions, and permitted tools | Bedrock only in `live` mode |
| Risk brief | Evidence records, uncertainty, support scores, trace, proposed action and run metrics | Streamlit/JSON output locally |

Raw webpages, PDFs, complete observation arrays and credentials are **not** sent directly to Sonnet. Short public notice titles and supplied synthetic external-report summaries can appear in evidence findings sent to the controller. Deterministic code consumes all observations and compresses them into at most a handful of labelled, provenance-bearing evidence items. The system prompt explicitly treats supplied content as data rather than instructions.

The Sonnet model is **not trained or fine-tuned** on these feeds. Public observations are retrieved at assessment time and used as evidence for tool selection and explanation. Training an attack-attribution model on these sparse aggregates would be unsupported: no appropriate labelled Singapore deliberate-event dataset exists. Repeated public snapshots could later form a time series for validated statistical forecasting, but not for autonomous attribution.

Every operational observation under `data/scenarios/` remains synthetic and is marked `synthetic: true`. Public observations use a separate aggregate-only schema. The definitive source manifest is `data/public_sources.json`.

For a later pilot, add ingestion adapters outside the orchestration loop, retain source licences and collection timestamps, aggregate locations, remove identifiers, and require data-owner approval before any Bedrock transfer.

## How orchestration works

1. `public_sources.py` checks fixed HTTPS hosts before every request and redirect, limits response sizes, retrieves sources concurrently, validates normalised aggregate observations and records partial failures.
2. The CDA parser compares the current week with CDA's corresponding-week 2021-2025 median. Other feeds are treated as contextual/corroborating observations unless they publish a defensible baseline.
3. Full source observations are compressed into evidence records. Missing public AVS and wastewater measurements actively increase the `insufficient_evidence` support rather than being imputed.
4. For synthetic scenarios, `analytics.py` performs z-score, time, geography and temporal checks. Public aggregates lack comparable signal-level locations and times, so public mode proceeds from its compact source evidence directly to verification selection. The controller sees only a compact packet and chooses an available approved tool with a concise rationale.
5. The application derives a bounded list of safe verification candidates from the current evidence. The controller may select among them but cannot invent or dispatch an operational action.
6. `hypothesis_scoring.py` combines visible weights and evidence quality. No model-generated number enters the score.
7. `reporting.py` caps confidence when critical public domains are missing and requires a person to approve or reject every proposed action.

Sonnet 5 rejects non-default sampling settings, so the request omits `temperature`; automatic tool selection avoids forcing a tool while thinking is enabled. Responses without exactly one valid choice trigger the configured fallback. See the [Sonnet 5 migration notes](https://platform.claude.com/docs/en/models/sonnet-5/whats-new-sonnet-5) and [Bedrock thinking constraints](https://docs.aws.amazon.com/bedrock/latest/userguide/claude-messages-extended-thinking.html). The 300-token default includes any thinking output and may need adjustment after a live smoke test.

The replay policy follows the same available-tool rules as Sonnet. It is not a prerecorded answer: the deterministic tools still execute against the selected scenario.

## Tests and evaluation

The suite uses standard-library `unittest`, with Pydantic required by the core. Install `requirements.txt` to run the complete suite, including PDF parser and Streamlit checks. Pytest also discovers the tests. The synthetic replay runtime does not import the optional PDF reader, Streamlit or boto3.

```powershell
python -m unittest discover -s tests -v
# or
pytest -q

# Reproduce the committed scenario-evaluation baseline
python -m backend.evaluate
```

The current deterministic baseline is stored in `evals/replay_baseline.json`. It reports expected-hypothesis and expected-status match rates, task completion, tool success, controller-rationale completeness, verification selection, provenance completeness, limit violations and automatic-action count. These are regression metrics on six hand-authored synthetic cases, not clinical accuracy or calibrated attribution performance.

The suite covers:

- strict schemas and rejection of non-synthetic records;
- anomaly and cross-domain correlation behaviour;
- score normalisation and evidence links;
- expected outcomes across all six scenarios;
- safe handling of the contradictory case;
- pending/approved human action state;
- evidence injection and change recording;
- mocked live-mode call, token and cost accounting;
- public-source host allow-listing and compact evidence transformation;
- preservation of AVS/wastewater coverage gaps;
- a bounded current-public-data assessment path;
- completion within model/tool limits.

GitHub Actions repeats the offline test and evaluation commands on Python 3.11 and 3.12. Full setup, live-mode checks, extension guidance and release checks are in [docs/TESTING_AND_HANDOVER.md](docs/TESTING_AND_HANDOVER.md).

Useful demonstration metrics are already included in each JSON risk profile: model calls, tool calls, token usage, estimated cost, replay fallback and completion within limits. For a fuller evaluation, run each scenario repeatedly in live mode and compare tool-sequence completion, expected leading hypothesis, unsupported-claim count, total tokens, latency and human-review agreement.

## Scope and limitations

- This is a hackathon prototype, not a diagnostic system or deployable public-health product.
- The hand-authored weights demonstrate explainability; domain experts would need to design and validate a real scoring method.
- Z-score screening assumes a meaningful baseline and does not handle seasonality, reporting delay or small-count statistics rigorously.
- Public pages can change structure; source failures are visible, but parsers require maintenance.
- The public-data path is a current differential risk screen, not a validated incidence or spread forecast.
- AVS animal-surveillance measurements and NEA wastewater viral measurements are not publicly exposed at useful granularity. Without authorised access, BIO-SIGNAL cannot perform the full cross-domain assessment described in the national-scale vision.
- Current environmental readings are contextual snapshots. Reliable lagged weather features require regular snapshot collection or an approved historical archive.
- The prototype does not identify pathogens, infer intent from absence of evidence, or automate notifications.
- AWS availability, privacy classification, retention, encryption, audit logging and cross-border transfer require separate production review.
- Evidence suggesting deliberate release is never treated as attribution; the prototype can only recommend further human-led verification.

## Repository audit

See [the repository audit and next-step assessment](docs/REPOSITORY_AUDIT.md) for verified fixes, checks performed, remaining limitations and how this implementation supports the biodefence decision-support goal.
