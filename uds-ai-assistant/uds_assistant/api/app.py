"""FastAPI app: profiles, ingestion, RAG Q&A, test generation, review, execution, exports."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import Body, Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from .. import __version__
from ..config import get_settings
from ..coverage import compute_coverage
from ..generator.builder import build_request
from ..generator.exporters import export_all
from ..generator.intent import parse_requirement, select_tests
from ..generator.models import TestCase
from ..generator.suites import build_suite
from ..knowledge.service import KnowledgeService
from ..llm.base import get_llm
from ..protocol.profile import ECUProfile, parse_profile
from ..protocol.validator import validate_request
from ..runner.report import to_junit, to_markdown
from ..runner.runner import Runner
from ..runner.transport import IsoTpTransport, SafetyGuard, SimTransport
from ..store import ProjectStore
from ..graph import GraphStore
from .auth import Principal, get_current_user
from .schemas import AskRequest, BuildRequest, GenerateRequest, ProjectCreate, ReviewRequest, RunRequest, ValidateRequest

app = FastAPI(title="UDS Diagnostics and Automated Test Generation Assistant", version=__version__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_settings = get_settings()
_store = ProjectStore(_settings)
_llm = get_llm(_settings)
_knowledge = KnowledgeService(_settings, _llm)
_graph = GraphStore()


def _project(name: str):
    if not _store.exists(name):
        raise HTTPException(404, f"project {name!r} not found")
    return _store.load(name)


def _profile(name: str) -> ECUProfile:
    p = _store.get_profile(name)
    if p is None:
        raise HTTPException(400, f"project {name!r} has no ECU profile yet; POST /projects/{name}/profile first")
    return p


@app.get("/health")
def health():
    return {"status": "ok", "version": __version__, "llm": _llm.name, "store_backend": _settings.store_backend}


# ================================================================================================
# Projects
# ================================================================================================
@app.get("/projects")
def list_projects(me: Principal = Depends(get_current_user)):
    return {"projects": _store.list_projects()}


@app.post("/projects", status_code=201)
def create_project(body: ProjectCreate, me: Principal = Depends(get_current_user)):
    me.require("engineer")
    if _store.exists(body.name):
        raise HTTPException(409, f"project {body.name!r} already exists")
    _store.create(body.name)
    _store.audit(body.name, me.user, me.role, "create_project")
    return {"name": body.name}


@app.get("/projects/{project}")
def get_project(project: str, me: Principal = Depends(get_current_user)):
    st = _project(project)
    profile = ECUProfile.model_validate(st.profile) if st.profile else None
    return {"name": st.name, "created_ts": st.created_ts,
            "profile": {"name": profile.name, "oem": profile.oem, "version": profile.version} if profile else None,
            "test_count": len(st.tests), "run_count": len(st.runs)}


@app.post("/projects/{project}/profile")
async def upload_profile(project: str, file: UploadFile = File(...), me: Principal = Depends(get_current_user)):
    me.require("engineer")
    _project(project)
    text = (await file.read()).decode("utf-8", errors="replace")
    try:
        profile = parse_profile(text)
    except Exception as e:
        raise HTTPException(422, f"invalid ECU profile: {e}") from e
    _store.set_profile(project, profile, f"upload:{file.filename}", me.user, me.role)
    n = _knowledge.ingest_profile(project, profile, source=f"ECU profile {profile.name} v{profile.version}")
    return {"name": profile.name, "oem": profile.oem, "version": profile.version,
            "services": len(profile.services), "dids": len(profile.dids), "routines": len(profile.routines),
            "knowledge_chunks_indexed": n}


@app.get("/projects/{project}/profile")
def get_profile(project: str, me: Principal = Depends(get_current_user)):
    return _profile(project).model_dump(mode="json")


# ================================================================================================
# Knowledge base
# ================================================================================================
@app.post("/projects/{project}/documents")
async def upload_document(project: str, layer: str = Query("project"), version: str = Query(""),
                          file: UploadFile = File(...), me: Principal = Depends(get_current_user)):
    me.require("engineer")
    _project(project)
    if layer not in ("standard", "oem", "ecu", "project"):
        raise HTTPException(422, "layer must be one of standard, oem, ecu, project")
    tmp = Path(_settings.projects_dir / project / "uploads")
    tmp.mkdir(parents=True, exist_ok=True)
    dest = tmp / file.filename
    dest.write_bytes(await file.read())
    try:
        n = _knowledge.ingest_file(project, dest, layer, version, source_name=file.filename)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    _store.audit(project, me.user, me.role, "ingest_document", f"{file.filename} ({layer}): {n} chunk(s)")
    return {"source": file.filename, "layer": layer, "chunks": n}


@app.get("/projects/{project}/documents")
def list_documents(project: str, me: Principal = Depends(get_current_user)):
    _project(project)
    return {"sources": _knowledge.sources(project)}


@app.delete("/projects/{project}/documents/{source}")
def delete_document(project: str, source: str, me: Principal = Depends(get_current_user)):
    me.require("engineer")
    _project(project)
    n = _knowledge.delete_source(project, source)
    if n == 0:
        raise HTTPException(404, f"source {source!r} not found")
    _store.audit(project, me.user, me.role, "delete_document", source)
    return {"deleted_chunks": n}


@app.post("/projects/{project}/ask")
def ask(project: str, body: AskRequest, me: Principal = Depends(get_current_user)):
    _project(project)
    answer = _knowledge.ask(project, body.question, k=body.k, layers=body.layers)
    return answer.model_dump()


# ================================================================================================
# Request validator / builder (sandbox for engineers)
# ================================================================================================
@app.post("/projects/{project}/validate")
def validate(project: str, body: ValidateRequest, me: Principal = Depends(get_current_user)):
    p = _profile(project)
    try:
        return validate_request(p, body.request, body.session, body.unlocked, body.seed_requested).model_dump()
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@app.post("/projects/{project}/build_request")
def build(project: str, body: BuildRequest, me: Principal = Depends(get_current_user)):
    p = _profile(project)
    return build_request(p, body.text).model_dump()


# ================================================================================================
# Test generation
# ================================================================================================
@app.post("/projects/{project}/generate")
def generate(project: str, body: GenerateRequest, me: Principal = Depends(get_current_user)):
    me.require("engineer")
    p = _profile(project)
    full = build_suite(p)
    if not body.requirement:
        for t in full:
            t.created_by = me.user
        _store.save_tests(project, full, me.user, me.role, origin="full systematic suite")
        return {"generated": len(full), "coverage": compute_coverage(p, full)}
    intent = parse_requirement(p, body.requirement, _llm if body.use_llm else None)
    selected = select_tests(p, full, intent)
    if not selected:
        return {"generated": 0, "intent": intent.__dict__, "message": "No matching systematic tests were found "
                "for this requirement; nothing was added. Try naming a DID, routine, service or session."}
    for t in selected:
        t.requirement_id = t.requirement_id or body.requirement[:120]
        t.origin = "requirement"
        t.created_by = me.user
    _store.save_tests(project, selected, me.user, me.role, origin=f"requirement: {body.requirement[:80]!r}")
    
    try:
        _graph.add_requirement_trace(project, body.requirement[:120], body.requirement, [t.id for t in selected])
    except Exception as e:
        print(f"Graph store error: {e}")
        
    return {"generated": len(selected), "test_ids": [t.id for t in selected],
            "intent": {"services": sorted(intent.services), "dids": sorted(intent.dids),
                      "routines": sorted(intent.routines), "source": intent.source, "notes": intent.notes}}


@app.get("/projects/{project}/tests")
def list_tests(project: str, status: Optional[str] = None, category: Optional[str] = None,
              service: Optional[str] = None, me: Principal = Depends(get_current_user)):
    tests = _store.list_tests(project)
    if status:
        tests = [t for t in tests if t.status == status]
    if category:
        tests = [t for t in tests if t.category == category]
    if service:
        sid = int(service, 16) if service.lower().startswith("0x") else int(service)
        tests = [t for t in tests if t.service == sid]
    return {"count": len(tests), "tests": [t.model_dump(mode="json") for t in tests]}


@app.get("/projects/{project}/tests/{test_id}")
def get_test(project: str, test_id: str, me: Principal = Depends(get_current_user)):
    t = _store.get_test(project, test_id)
    if t is None:
        raise HTTPException(404, f"test {test_id!r} not found")
    return t.model_dump(mode="json")


@app.put("/projects/{project}/tests/{test_id}")
def edit_test(project: str, test_id: str, body: TestCase, me: Principal = Depends(get_current_user)):
    me.require("engineer")
    if _store.get_test(project, test_id) is None:
        raise HTTPException(404, f"test {test_id!r} not found")
    body.id = test_id
    body.status = "draft"   # any edit resets approval
    body.origin = body.origin or "manual"
    _store.update_test(project, body, me.user, me.role)
    return body.model_dump(mode="json")


@app.post("/projects/{project}/tests/{test_id}/review")
def review_test(project: str, test_id: str, body: ReviewRequest, me: Principal = Depends(get_current_user)):
    me.require("lead")
    if body.decision not in ("approved", "rejected", "changes_requested"):
        raise HTTPException(422, "decision must be approved, rejected or changes_requested")
    try:
        tc = _store.review_test(project, test_id, me.user, me.role, body.decision, body.comment, _settings.four_eyes)
    except KeyError:
        raise HTTPException(404, f"test {test_id!r} not found")
    except PermissionError as e:
        raise HTTPException(403, str(e))
    return tc.model_dump(mode="json")


@app.get("/projects/{project}/coverage")
def coverage(project: str, approved_only: bool = False, me: Principal = Depends(get_current_user)):
    p = _profile(project)
    tests = _store.list_tests(project)
    if approved_only:
        tests = [t for t in tests if t.status == "approved"]
    return compute_coverage(p, tests)


# ================================================================================================
# Execution
# ================================================================================================
@app.post("/projects/{project}/run")
def run_tests(project: str, body: RunRequest, me: Principal = Depends(get_current_user)):
    me.require("engineer")
    p = _profile(project)
    tests = _store.list_tests(project)
    if body.test_ids:
        wanted = set(body.test_ids)
        tests = [t for t in tests if t.id in wanted]
        missing = wanted - {t.id for t in tests}
        if missing:
            raise HTTPException(404, f"unknown test id(s): {sorted(missing)}")
    if not body.include_draft:
        tests = [t for t in tests if t.status == "approved"]
    if not tests:
        raise HTTPException(400, "no tests match the run request (approve tests first, or set include_draft=true)")

    guard = SafetyGuard(_settings.allow_hardware, _settings.target_environment, _settings.allow_state_changing_on_hw)
    kind = "hardware" if body.target == "hardware" else "simulator"
    problems = guard.check(kind, tests)
    if problems:
        raise HTTPException(403, {"message": "execution blocked by safety guard", "problems": problems})

    if kind == "hardware":
        if not body.hw_interface:
            raise HTTPException(422, "hw_interface (e.g. 'can0') is required for hardware runs")
        transport = IsoTpTransport(body.hw_interface, p.request_id, p.response_id)
    else:
        transport = SimTransport(p, faults=body.faults)
    try:
        summary = Runner(p, transport).run(tests, faults=body.faults)
    finally:
        transport.close()
    entry = _store.record_run(project, summary, me.user, me.role, [t.id for t in tests])
    return {"run_id": entry["run_id"], **summary.model_dump(mode="json")}


@app.post("/projects/{project}/run_stream")
def run_tests_stream(project: str, body: RunRequest, me: Principal = Depends(get_current_user)):
    import json
    me.require("engineer")
    p = _profile(project)
    tests = _store.list_tests(project)
    if body.test_ids:
        wanted = set(body.test_ids)
        tests = [t for t in tests if t.id in wanted]
        missing = wanted - {t.id for t in tests}
        if missing:
            raise HTTPException(404, f"unknown test id(s): {sorted(missing)}")
    if not body.include_draft:
        tests = [t for t in tests if t.status == "approved"]
    if not tests:
        raise HTTPException(400, "no tests match the run request")

    guard = SafetyGuard(_settings.allow_hardware, _settings.target_environment, _settings.allow_state_changing_on_hw)
    kind = "hardware" if body.target == "hardware" else "simulator"
    if guard.check(kind, tests):
        raise HTTPException(403, "execution blocked by safety guard")

    def event_stream():
        if kind == "hardware":
            transport = IsoTpTransport(body.hw_interface, p.request_id, p.response_id)
        else:
            transport = SimTransport(p, faults=body.faults)
        try:
            runner = Runner(p, transport)
            for event in runner.run_stream(tests, faults=body.faults):
                if hasattr(event, "verdict"):  # TestResult
                    yield json.dumps({"type": "test_result", "data": event.model_dump(mode="json")}) + "\n"
                else:  # RunSummary
                    entry = _store.record_run(project, event, me.user, me.role, [t.id for t in tests])
                    yield json.dumps({"type": "summary", "run_id": entry["run_id"], "data": event.model_dump(mode="json")}) + "\n"
        finally:
            transport.close()

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


@app.get("/projects/{project}/runs")
def list_runs(project: str, me: Principal = Depends(get_current_user)):
    return {"runs": _store.list_runs(project)}


@app.get("/projects/{project}/runs/{run_id}/report.{fmt}")
def run_report(project: str, run_id: str, fmt: str, me: Principal = Depends(get_current_user)):
    from ..runner.runner import RunSummary
    runs = _store.list_runs(project)
    entry = next((r for r in runs if r["run_id"] == run_id), None)
    if entry is None:
        raise HTTPException(404, f"run {run_id!r} not found")
    summary = RunSummary.model_validate(entry["summary"])
    if fmt == "md":
        return PlainTextResponse(to_markdown(summary, f"Run report {run_id}"), media_type="text/markdown")
    if fmt == "xml":
        return PlainTextResponse(to_junit(summary), media_type="application/xml")
    if fmt == "json":
        return JSONResponse(entry)
    raise HTTPException(404, "format must be md, xml or json")


# ================================================================================================
# Exports
# ================================================================================================
@app.get("/projects/{project}/export/{fmt}")
def export(project: str, fmt: str, approved_only: bool = True, me: Principal = Depends(get_current_user)):
    p = _profile(project)
    tests = _store.list_tests(project)
    if approved_only:
        tests = [t for t in tests if t.status == "approved"]
    if not tests:
        raise HTTPException(400, "no tests to export (approve tests first, or set approved_only=false)")
    try:
        files = export_all(fmt, p, tests)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    if len(files) == 1:
        name, content = next(iter(files.items()))
        media = "application/json" if name.endswith(".json") else "text/csv" if name.endswith(".csv") else \
                "text/markdown" if name.endswith(".md") else "text/x-python"
        return PlainTextResponse(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in files.items():
            z.writestr(name, content)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{project}_{fmt}_export.zip"'})


@app.get("/projects/{project}/audit")
def audit(project: str, me: Principal = Depends(get_current_user)):
    me.require("lead")
    return {"audit": _store.audit_log(project)}
