# UDS Diagnostics and Automated Test Generation Assistant

An AI-assisted tool for UDS (unified diagnostic services, ISO 14229-style) test
engineering: it retrieves and explains diagnostic knowledge with citations, and
generates, reviews, runs and exports UDS test cases for an ECU.

**Design rule:** a language model (optional) proposes and explains. A deterministic
protocol rule engine — the "spec oracle" — always decides what the expected response
is. Test cases are correct by construction with respect to the ECU profile; no
expected value in a generated test was ever produced by an LLM.

## Why this design

Generic UDS knowledge (service structure, common negative response codes) is
paraphrased once in `protocol/catalog.py`. Everything project-specific — which
services, sub-functions, DIDs, routines, security levels and sessions a *particular*
ECU implements — comes from a machine-readable **ECU profile** (YAML), which is the
single source of truth. The oracle (`protocol/oracle.py`) walks the profile and
protocol state to compute the exact expected response for any request, following a
documented, consistent rule order (R1-R11, see the oracle's docstring).

Because generation is spec-driven rather than model-driven, the pipeline is checkable
end to end:

- **100% coverage against the sample profile** - every service/sub-function,
  DID/RID read-write-boundary-security path, session restriction and timing behaviour
  the profile implies is covered by at least one generated test
  (`uds_assistant/coverage.py`).
- **Fault-injection cross-check** - the mock ECU (`simulator/mock_ecu.py`) is an
  independent implementation of the same profile, with 8 injectable defects (e.g.
  "security check skipped", "invalid key accepted", "S3 timeout not enforced"). Every
  one of the 8 faults is caught by at least one generated test
  (`tests/test_runner_and_faults.py`), proving the tests are not vacuous.
- **Exported automation is genuinely independent** - `export_python` produces a
  standalone pytest file with its own harness; running it as a separate `pytest`
  process against the simulator reproduces the same pass/fail results as the
  in-process runner.

## Project layout

```
uds_assistant/
  protocol/      ECU profile model, spec oracle, NRC table, hex utilities, request validator
  simulator/     Independent mock ECU with fault injection, used for demos and cross-checking
  generator/     Test-case model, scenario builder, systematic suite generator,
                 plain-language request builder, requirement -> test-target intent parser,
                 exporters (pytest, CAPL template, JSON, CSV, Markdown)
  runner/        Transports (simulator, ISO-TP/SocketCAN), safety guard, executor, reports
  knowledge/     Document/profile ingestion & chunking, BM25 (default) and Chroma retrieval,
                 grounded Q&A with citations and a confidence score
  llm/           Optional LLM client (Ollama or any OpenAI-compatible server)
  coverage.py    Coverage universe derived from a profile + coverage computation
  store.py       Per-project state: profile, tests, reviews (four-eyes), runs, audit log
  api/           FastAPI app (auth, projects, ingestion, generation, review, execution, export)
  ui/            Streamlit UI
  cli.py         Command-line interface
data/samples/    A synthetic demo ECU profile (BCM-X1) - not real OEM data
docs/            A synthetic OEM notes document (second knowledge layer, for the RAG demo)
tests/           pytest suite (protocol, generator/coverage, runner/faults, exporters,
                 knowledge, store/API)
```

## Quick start

```bash
pip install -e .

# Generate the full systematic suite for the sample ECU and check coverage
uds-ai generate data/samples/bcm_ecu_profile.yaml -o tests.json
uds-ai coverage data/samples/bcm_ecu_profile.yaml tests.json

# Run against the built-in simulator; try injecting a fault to see a test catch it
uds-ai run data/samples/bcm_ecu_profile.yaml tests.json
uds-ai run data/samples/bcm_ecu_profile.yaml tests.json --faults accept_any_key

# Export to a standalone pytest file or a CANoe CAPL template
uds-ai export data/samples/bcm_ecu_profile.yaml tests.json --format python -o export/
uds-ai export data/samples/bcm_ecu_profile.yaml tests.json --format capl -o export/

# Full workflow: API + UI
uds-ai serve            # FastAPI on :8000  (docs at /docs)
uds-ai ui                # Streamlit on :8501
```

Or with Docker: `docker compose up` starts the API on `:8000` and the UI on `:8501`.

### Running the test suite

```bash
pip install -e ".[dev]"
pytest
```

## Roles and review workflow

Dev-mode auth (default) trusts `X-User` / `X-Role` headers (`viewer`, `engineer`,
`lead`, `admin`); set `UDS_AUTH_MODE=token` with `UDS_USERS` (a JSON map of bearer
token -> `{"name", "role"}`) for token auth instead. Engineers generate and edit
tests; leads approve or reject them. Set `UDS_FOUR_EYES=1` to require that the
approver differ from the test's author. Every mutating action is written to a
per-project audit log.

## Hardware execution

Test execution defaults to the in-process simulator. Running against real hardware
(`IsoTpTransport`, Linux SocketCAN via `can-isotp`) requires **all** of:
`UDS_ALLOW_HARDWARE=1`, `UDS_TARGET_ENV=bench`, and - for any state-changing service
(session control, reset, clear DTCs, communication control, write, routine control,
DTC setting) - `UDS_HW_ALLOW_STATE_CHANGING=1`. Flash/transfer services (0x34-0x38,
0x3D) are always blocked. The ISO-TP transport is written against the public
`can-isotp` socket API but has **not** been verified against real hardware in this
repository. The CAPL export is a structural template; `uds_helpers.cin` is a binding
stub that must be wired to your project's diagnostic layer and has **not** been
verified inside CANoe.

## Knowledge base and citations

Documents are ingested in layers (`standard`, `oem`, `ecu`, `project`) and chunked by
section so every retrieved passage is citeable to a source/section/page. The ECU
profile itself is converted into citeable chunks (`knowledge/ingest.py:chunk_profile`)
so profile facts and free-text documents are searchable together. Retrieval defaults
to a zero-dependency BM25 index; set `UDS_STORE_BACKEND=chroma` (with
`pip install ".[chroma]"`) for a persistent vector store instead.

An LLM is optional (`UDS_LLM_PROVIDER=none|ollama|openai_compat`). With no LLM
configured, questions get an **extractive** answer (the most relevant passages,
verbatim) rather than a fabricated one. With an LLM configured, answers must cite
retrieved passages by number; unsupported claims are stripped and the response is
marked `no_evidence` if the model reports insufficient context. Every answer carries a
confidence label (`high`/`medium`/`low`/`insufficient`) derived from lexical overlap
between the question and the retrieved passages, not from the LLM's own say-so.

## Sample data

`data/samples/bcm_ecu_profile.yaml` and `docs/oem_diagnostic_notes.md` are synthetic
and were written for this project; they are not real OEM specifications.
