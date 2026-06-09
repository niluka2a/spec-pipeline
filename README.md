# AI-native Spec-driven Development Pipeline

A prototype pipeline that transforms a structured feature specification into implementation code,
automated tests, and deployment artefacts — using Claude (Anthropic SDK) and deterministic
quality controls.

---

## Architecture Overview

```
Feature Spec (YAML/JSON/MD)
        │
        ▼
┌─────────────────┐
│  1. Spec Intake │  ← Validate required fields, parse format
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  2. Planning    │  ← Claude generates implementation plan (JSON)
└────────┬────────┘
         │
         ▼
┌──────────────────────┐
│  ⏸ Approval Gate 1   │  ← Human reviews plan before code is written
└────────┬─────────────┘
         │
         ▼
┌────────────────────────┐
│  3. AI Implementation  │  ← Claude generates code (sandbox/src/ only)
└────────┬───────────────┘
         │
         ▼
┌──────────────────────┐
│  4. Test Generation  │  ← Claude generates pytest tests mapped to AC IDs
└────────┬─────────────┘
         │
         ▼
┌──────────────────┐
│  5. Quality Gates│  ← ruff lint + mypy typecheck + pytest + bandit
└────────┬─────────┘
         │
         ▼
┌──────────────────────┐
│  ⏸ Approval Gate 2   │  ← Human reviews before deployment
└────────┬─────────────┘
         │
         ▼
┌──────────────────────────┐
│  6. Deployment Manifest  │  ← Deployment evidence JSON written
└──────────────────────────┘
         │
         ▼
  audit_logs/run_<id>.json   ← Full audit trail (prompts, responses, approvals)
```

---

## Setup

### Docker

```bash
docker build -t spec-pipeline .
docker run -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY spec-pipeline
# Or with your own spec:
docker run -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY -v $(pwd)/specs:/app/specs spec-pipeline specs/my_feature.yaml
```

---

## Usage

```
python run_pipeline.py <spec-file> [options]

Arguments:
  spec              Path to spec file (.yaml, .json, or .md)

Options:
  --run-id ID       Custom run identifier (default: auto-generated)
  --skip-gates      Skip quality gates (development/debug mode only)
```

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | Anthropic API key |
| `PIPELINE_AUTO_APPROVE` | ❌ | Set to `true` to skip interactive prompts (CI mode) |

---

## Spec Format

Specs can be written in **YAML**, **JSON**, or **Markdown** (with YAML front-matter).

### Required Fields

| Field | Description |
|---|---|
| `feature_objective` | What the feature achieves |
| `user_story` | As a / I want / So that |
| `business_rules` | List of constraints and rules |
| `acceptance_criteria` | List of `{id, description}` objects |
| `non_functional_requirements` | Performance, security, reliability requirements |
| `out_of_scope` | Explicit exclusions |

See [`specs/example_spec.yaml`](specs/example_spec.yaml) for a full example.

---

## Output Artefacts

After a successful run, the following are produced:

| Artefact | Location | Description |
|---|---|---|
| Implementation code | `sandbox/src/` | AI-generated Python files |
| Test files | `tests/` | pytest unit + integration + acceptance tests |
| Audit log | `audit_logs/run_<id>.json` | Full trace: prompts, responses, approvals |
| Deployment manifest | `audit_logs/deployment_manifest_<id>.json` | Deployment evidence |

---

## Design Decisions

### Why Anthropic Python SDK (not raw API)?
The SDK provides type-safe client construction, built-in retry/backoff, and cleaner message
construction. For a pipeline that makes sequential calls across stages, this reduces boilerplate
and improves reliability.

### Why a single JSON audit log per run?
A flat JSON file per run is the simplest structure that satisfies auditability requirements
(traceability, reproducibility) without introducing a database dependency. Each entry is
timestamped and tagged with `run_id`, making it trivially searchable and self-contained.

### Why sandbox enforcement at the file-write layer?
Allowing an LLM to write to arbitrary paths is a governance risk. The `implementer.py` module
enforces that all generated files are resolved under `sandbox/src/` before being written, regardless
of what the model returns. This is deterministic and cannot be bypassed by prompt manipulation.

### Why are prompts in a separate `prompts/templates.py`?
Prompt text is a first-class artefact in an AI-native system — it should be versionable,
reviewable, and auditable separately from orchestration logic. Externalising prompts also makes
A/B testing and iterative prompt improvement straightforward.

### Why two approval gates (not one)?
The two checkpoints map to the two highest-risk transitions in the pipeline:
1. **Pre-implementation**: Once code is written, there is work to discard. Reviewing the plan first is cheap.
2. **Pre-deployment**: The final gate before changes reach production. Quality gates pass, but a human confirms intent.

---

## Trade-offs

| Decision | Trade-off |
|---|---|
| Single-model pipeline | Simple and fast, but no agent specialisation. A multi-agent setup (planner agent, coder agent, test agent) would improve quality at the cost of complexity. |
| CLI approvals | Easy to understand and audit; not suitable for async team workflows. A Slack/webhook approval system would be better for teams. |
| Pytest + ruff + mypy | Opinionated Python stack. Works well for the prototype; a polyglot pipeline would need configurable gate runners. |
| Sandbox enforced at write time | Simple and robust; but a more complete solution would also lint generated paths before writing. |

---

## Limitations

- **No memory across runs** — each pipeline run is stateless. There is no diffing against previous runs.
- **Sandbox is Python-only** — the quality gates assume Python. A production system would need language-agnostic gate configuration.
- **Tests may not run against real generated code** — if the generated code has import issues or missing stubs, tests will fail in quality gates. This is by design (the gate catches it), but it means the pipeline may need a retry mechanism.
- **Single approval actor** — the prototype assumes one approver. A real governance system would require multiple reviewers and quorum.

---

## Future Improvements

- **Agent orchestration** — replace the sequential LLM calls with a proper agent loop (e.g. using tool use / function calling) so the AI can self-correct when quality gates fail.
- **Prompt versioning** — store prompts with semantic versions and link each audit log entry to the exact prompt version used.
- **Evaluation metrics** — measure AC coverage per test run, track quality gate pass rates over time.
- **Observability dashboard** — parse audit logs and surface a run-level dashboard (e.g. with Streamlit or a simple HTML report).
- **PR-based approval workflow** — replace CLI prompts with GitHub PR review gates triggered by the pipeline.
- **Retry loop** — if quality gates fail, re-prompt the implementation stage with the failure output as context.

---

## CI/CD

GitHub Actions workflow is included at `.github/workflows/pipeline.yml`.

Add `ANTHROPIC_API_KEY` as a repository secret, then push to `main` or `develop` to trigger a pipeline run. Audit logs are uploaded as build artefacts.
