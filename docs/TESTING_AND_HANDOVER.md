# BIO-SIGNAL testing and project handover

This guide is for reviewers who want to test BIO-SIGNAL and contributors who
need to continue the project. Start with replay mode: it is deterministic,
offline and does not require an AWS account. Public-data and Bedrock modes are
optional integration tests.

## Scope and safety boundary

BIO-SIGNAL is a Singapore-focused hackathon proof of concept for biological
anomaly decision support. It correlates evidence, compares natural, accidental,
deliberate and insufficient-evidence explanations, and recommends a next
verification step. It is not a diagnostic system, an attack-attribution model
or an operational alerting service.

The application must preserve these constraints:

- only public aggregate or explicitly synthetic input data;
- no patient-level, classified or private agency data;
- no autonomous notifications, enforcement or laboratory tasking;
- evidence provenance and limitations remain visible;
- deliberate release is never inferred from missing evidence;
- every proposed action remains pending until a person approves or rejects it;
- model and tool loops remain bounded.

## Prerequisites

- Git
- Python 3.11 or 3.12
- PowerShell on Windows, or a POSIX shell on macOS/Linux
- outbound HTTPS only for the current-public-data path
- an AWS account with Bedrock access only for live decision mode

## Fresh-clone setup

### Windows PowerShell

```powershell
git clone <repository-url>
cd goonai
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### macOS or Linux

```bash
git clone <repository-url>
cd goonai
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Replay mode does not need a `.env` file.

## Acceptance test sequence

Run these commands from the repository root.

### 1. Offline automated tests

```powershell
python -m unittest discover -s tests -v
python -m backend.evaluate
```

Expected baseline:

- 22 tests pass;
- all six curated scenarios match their expected screening outcome;
- task-completion, tool-call success, tool-rationale completeness and verification-recommendation rates are 1.0;
- no loop-limit violations;
- no automatically approved or rejected actions.

These are regression results on a small, hand-authored six-scenario suite. They are
not clinical accuracy, epidemiological validation or calibrated attribution
metrics.

### 2. Offline command-line demonstration

```powershell
python -m backend.run_demo --scenario zoonotic_spillover --mode replay
```

Expected leading fields:

```text
Status: investigate
Leading hypothesis: natural_zoonotic
Confidence: high
```

To exercise an update after new evidence:

```powershell
python -m backend.run_demo --scenario contradictory_evidence --mode replay --include-new-evidence
```

### 3. User-interface demonstration

```powershell
streamlit run frontend/app.py
```

Open the displayed local URL. For the first run choose:

- **Input source:** Curated scenario
- **Scenario:** Zoonotic spillover early warning
- **Decision mode:** replay

Confirm that the page shows hypothesis support, evidence provenance, the tool
trace, uncertainty, a proposed action and the human approval gate. Then use
**Inject new synthetic evidence** on a scenario that provides an evidence
packet and confirm the change log updates.

### 4. Singapore public-data integration

```powershell
python -m backend.run_demo --public-data --mode replay `
  --snapshot-output output/singapore-public-snapshot.json `
  --output output/public-risk-profile.json
```

This path needs outbound HTTPS. Source pages change and an individual source
may be temporarily unavailable. The expected behaviour is graceful
degradation: the source should be marked `partial` or `unavailable`, while
other sources continue to be assessed. Do not assert a fixed observation count
for a live collection.

Generated files under `output/` are intentionally ignored by Git.

## Optional Amazon Bedrock configuration

Copy the example only when testing live mode:

```powershell
Copy-Item .env.example .env
```

Choose one authentication method. Do not combine credentials from several
methods and never commit `.env`.

### Bedrock API key

This is the simplest method for a short-lived hackathon test:

```dotenv
AWS_REGION=us-east-1
AWS_BEARER_TOKEN_BEDROCK=<private-key>
BEDROCK_MODEL_ID=global.anthropic.claude-sonnet-5
```

### Existing AWS profile

```dotenv
AWS_REGION=us-east-1
AWS_PROFILE=bio-signal
BEDROCK_MODEL_ID=global.anthropic.claude-sonnet-5
```

### Temporary AWS credentials

```dotenv
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=<temporary-access-key>
AWS_SECRET_ACCESS_KEY=<temporary-secret>
AWS_SESSION_TOKEN=<temporary-session-token>
BEDROCK_MODEL_ID=global.anthropic.claude-sonnet-5
```

Prefer a profile, role, Bedrock API key or temporary credentials over
long-lived IAM access keys. A first-time Anthropic user may also need to
complete the provider use-case form and enable the model in the Bedrock model
catalogue.

The remaining controls are:

| Variable | Default | Meaning |
|---|---:|---|
| `BIO_SIGNAL_MAX_MODEL_CALLS` | `4` | Maximum paid model decisions in one investigation |
| `BIO_SIGNAL_MAX_TOOL_CALLS` | `6` | Maximum local tool executions |
| `BIO_SIGNAL_MAX_OUTPUT_TOKENS` | `300` | Output-token cap per model decision |
| `BIO_SIGNAL_SESSION_BUDGET_USD` | `1.00` | Per-investigation estimated-cost guard |
| `BIO_SIGNAL_FALLBACK_TO_REPLAY` | `true` | Continue safely with replay if Bedrock fails |

The budget variable is not an AWS account-wide spending cap. Configure an AWS
Budget separately. The application estimates standard global Sonnet 5 usage at
US$3 per million input tokens and US$15 per million output tokens; confirm
current pricing before a demonstration.

Validate live mode with replay fallback disabled so a credential or model-access
problem cannot look like a successful model run:

```dotenv
BIO_SIGNAL_FALLBACK_TO_REPLAY=false
```

```powershell
python -m backend.run_demo --scenario zoonotic_spillover --mode live `
  --output output/live-smoke-test.json
```

In the JSON result, confirm that `model_calls` is greater than zero and
`fallback_used` is `false`. Restore fallback to `true` for a resilient public
demonstration.

## Architecture and data flow

```text
allow-listed public sources OR validated synthetic scenario
                           |
                           v
             normalised Pydantic contracts
                           |
                           v
           deterministic anomaly/correlation tools
                           |
                           v
       compact evidence and explicit source-coverage gaps
                           |
                           v
        replay or Bedrock controller selects allowed tools
                           |
                           v
       deterministic hypothesis scoring and risk-profile build
                           |
                           v
                Streamlit human approval gate
```

The model chooses which approved tool to execute. It cannot execute arbitrary
code, modify scoring weights, invent endpoints or dispatch an external action.
All calculations affecting anomaly evidence and support scores are deterministic
Python.

## Repository map

| Path | Responsibility |
|---|---|
| `backend/schemas.py` | Pydantic contracts and enumerations |
| `backend/public_sources.py` | Allow-listed collection, parsing and evidence compaction |
| `backend/analytics.py` | Deterministic analytical tools |
| `backend/hypothesis_scoring.py` | Transparent support scores and confidence |
| `backend/orchestrator.py` | Replay/Bedrock decisions, tool allow-list and loop limits |
| `backend/reporting.py` | Risk profiles, cost estimate and human decisions |
| `backend/evaluate.py` | Reproducible curated-scenario evaluation |
| `backend/run_demo.py` | Command-line entry point |
| `frontend/app.py` | Streamlit operator interface |
| `data/scenarios/` | Synthetic evaluation and demonstration cases |
| `data/public_sources.json` | Public-source catalogue and intended fields |
| `tests/` | Schema, analytics, orchestration, public-source and UI tests |
| `.github/workflows/tests.yml` | Offline GitHub Actions checks |

## Public data currently consumed

- CDA weekly infectious-disease bulletin;
- NEA dengue and Zika pages;
- data.gov.sg rainfall, temperature and humidity APIs;
- SFA food alerts and recalls;
- Changi Airport monthly passenger movements;
- WHO Disease Outbreak News;
- AVS animal biosurveillance programme coverage;
- NEA wastewater-surveillance programme coverage.

AVS and wastewater are currently programme-context sources because useful
granular measurements are not publicly exposed. Their absence must remain an
explicit evidence gap.

Raw pages and PDFs are parsed locally. Bedrock receives only compact evidence,
coverage status, scores, open questions and the list of permitted tools. It
does not receive credentials, full webpages or complete public observation
arrays.

## How to extend the project

### Add a curated scenario

1. Copy an existing JSON file under `data/scenarios/`.
2. Use a unique `scenario_id` and only synthetic, aggregate observations.
3. Set `expected_leading_hypothesis` and `expected_status`.
4. Validate with `python -m backend.evaluate`.
5. Add a focused test when the scenario covers a new failure mode.

Useful next scenarios are a laboratory-accident proxy, imported outbreak,
missing-data case and benign environmental anomaly. Avoid creating a supposed
real-world signature for deliberate release.

### Add a public source

1. Confirm it is an official, public, non-personal source with acceptable
   usage terms.
2. Add its fixed HTTPS host to the allow-list in `backend/public_sources.py`.
3. Add a collector that uses timeouts and returns validated aggregate
   `PublicObservation` records plus `SourceCoverage`.
4. Record provenance, collection time, cadence and limitations.
5. Add it to `data/public_sources.json`.
6. Extend evidence compaction without sending raw source content to the model.
7. Test parsing with stored representative content or mocks; automated tests
   must not depend on the live website.
8. Ensure a failed source remains visible and does not abort unrelated sources.

### Change scoring or thresholds

Treat this as a methodological change, not routine refactoring. Document the
rationale, add scenarios that would fail under the old behaviour, rerun the
evaluation, and avoid describing support scores as probabilities. Domain-expert
validation is required before any operational interpretation.

### Change the Bedrock model

Update `BEDROCK_MODEL_ID`, confirm the model supports Converse and forced tool
choice, update token prices in `backend/reporting.py`, and run both the mocked
tests and a paid smoke test. Keep the replay controller available.

## Known limitations and recommended next work

1. Expand the curated suite beyond six cases and obtain expert review of
   expected investigative steps.
2. Add parser retries with bounded exponential backoff and representative
   source fixtures.
3. Retain dated, licence-compatible public snapshots for time-series features
   and reproducible demonstrations.
4. Add structured logging with case ID, source ID, latency and redacted failure
   metadata.
5. Measure end-to-end latency and compare it with a documented manual baseline.
6. Validate confidence and scoring with domain experts; current weights are
   demonstrative.
7. Add authentication, role-based access control, retention rules and immutable
   audit logging before any pilot involving non-public data.

## Troubleshooting

**`ModuleNotFoundError` when running a module**

Run commands from the repository root and activate the virtual environment.

**Public collection returns unavailable sources**

Check outbound HTTPS, inspect the coverage notes and source URLs, then determine
whether the publisher changed its page or API structure. Do not remove the
coverage record to hide the failure.

**Live mode reports zero model calls**

Inspect `fallback_used`. If it is true, disable fallback temporarily and rerun
to expose the underlying credential, region or model-access error.

**Bedrock returns access denied**

Confirm the selected AWS identity, Region, Anthropic first-time-use completion,
model enablement and `bedrock:InvokeModel` permission.

## Before opening a pull request

```powershell
python -m unittest discover -s tests -v
python -m backend.evaluate
git diff --check
git status --short
```

Do not include `.env`, `.venv/`, `.sf/`, `output/`, credentials, patient data or
non-public operational information. Explain methodological changes and include
tests for new behaviours.

## First GitHub commit checklist

1. Review `git status --short`.
2. Confirm `.env` is ignored with `git check-ignore .env`.
3. Stage the repository with `git add .`.
4. Inspect staged names with `git diff --cached --name-only`.
5. Inspect the staged patch with `git diff --cached`.
6. Commit only after confirming there are no credentials or generated outputs.

The repository does not include a licence because choosing one determines how
others may reuse the project. The repository owner should select and add a
licence before making reuse claims.
