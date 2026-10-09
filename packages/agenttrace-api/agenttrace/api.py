from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
from contextlib import asynccontextmanager
from importlib.metadata import version
from pathlib import Path
from typing import Callable

from commsfail import Trace, run, validate_record
from commsfail.annotators import registry
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .models import AnalysisRun, Analyzer, Provenance, now
from .sources import MAX_SOURCE_BYTES, Source, load_source
from .store import Store
from .view_model import build_view_model, trace_id

logger = logging.getLogger(__name__)
REPOSITORY = Path(__file__).resolve().parents[3]
SCOUT = "scout_collaboration_v1"
DEFAULT_SCOUT_MODEL = "openai/gpt-5.4-mini"


def default_scout_model() -> str:
    return os.getenv("AGENTTRACE_SCOUT_MODEL", "").strip() or DEFAULT_SCOUT_MODEL


def scout_setup(model: str) -> dict:
    issues = []
    if importlib.util.find_spec("inspect_scout") is None:
        issues.append({"code": "scout_not_installed", "message": "Install the Scout extra in the API server's Python environment."})
    if model.startswith("openai/") and not os.getenv("OPENAI_API_KEY", "").strip():
        issues.append({"code": "openai_api_key_missing", "message": "OPENAI_API_KEY is not set in the API server's environment."})
    return {
        "model": model, "ready": not issues, "issues": issues,
        "install_command": 'python -m pip install -e "./packages/agenttrace-api[scout]"',
        "start_command": "agenttrace",
    }


def analyzer_catalog(trace: Trace | None = None) -> list[dict]:
    available = []
    for name, cls in registry().items():
        requires_ops = getattr(cls, "requires_ops", False)
        supported = trace is None or not requires_ops or trace.has_ops
        available.append({
            "name": name, "version": cls.version, "kind": "offline",
            "available": supported, "requires_ops": requires_ops,
            "unavailable_reason": (
                "Requires per-agent execution logs from a local goal-run record; "
                "this trace contains only conversation data."
            ) if not supported else None,
        })
    available.append({
        "name": SCOUT, "version": "2.0.0", "kind": "pipeline",
        "available": importlib.util.find_spec("inspect_scout") is not None,
        "default_model": default_scout_model(),
    })
    return available


class TraceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Source | None = None
    url: str | None = None


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str | None = Field(default=None, min_length=1, max_length=200)


async def scout_pipeline(report: dict, model: str, artifacts: Path) -> dict:
    from .scout.adapter import transcript_from_report
    from .scout.scanners import analyze_collaboration

    return await analyze_collaboration(
        transcript_from_report(report), model=model, artifacts=artifacts
    )


def create_app(
    data_dir: Path | None = None,
    source_root: Path | None = None,
    web_dist: Path | None = None,
    scout_runner: Callable = scout_pipeline,
) -> FastAPI:
    data_dir = data_dir or Path(os.getenv("AGENTTRACE_DATA_DIR", Path.cwd() / ".agenttrace"))
    if source_root is None and os.getenv("AGENTTRACE_SOURCE_ROOT"):
        source_root = Path(os.environ["AGENTTRACE_SOURCE_ROOT"])
    tasks: set[asyncio.Task] = set()
    semaphore = asyncio.Semaphore(1)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.store = Store(data_dir)
        app.state.store.interrupt_pending()
        yield
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(title="AgentTrace API", version="0.1.0", lifespan=lifespan)

    @app.middleware("http")
    async def body_limit(request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH"):
            # Read the stream incrementally, including requests without Content-Length.
            chunks = []
            size = 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_SOURCE_BYTES:
                    from fastapi.responses import JSONResponse
                    return JSONResponse(status_code=413, content={"detail": "Request exceeds 5 MB."})
                chunks.append(chunk)
            request._body = b"".join(chunks)
        return await call_next(request)

    def store() -> Store:
        return app.state.store

    def require_trace(identifier: str):
        trace = store().get_trace(identifier)
        if trace is None:
            raise HTTPException(status_code=404, detail="Trace not found.")
        return trace

    def report_for(identifier: str) -> dict:
        trace = require_trace(identifier)
        analyses = {
            analysis["analyzer"]["name"]: analysis
            for analysis in store().list_runs(identifier)
        }
        report = build_view_model(trace, analyses)
        report["analyzers"] = analyzer_catalog(trace)
        return report

    def offline_analysis(identifier: str, name: str) -> dict:
        trace = require_trace(identifier)
        cls = registry().get(name)
        if cls is None:
            raise HTTPException(status_code=404, detail=f"Unknown offline annotator: {name}")
        if getattr(cls, "requires_ops", False) and not trace.has_ops:
            raise HTTPException(
                status_code=422,
                detail=f"{name} requires per-agent execution logs from a local goal-run record. "
                       "Public share links and share JSON do not contain those logs. Use regex_v1 instead.",
            )
        analysis = AnalysisRun(
            trace_id=identifier,
            analyzer=Analyzer(name=name, version=cls.version, kind="offline"),
            provenance=Provenance(
                started_at=now(), package_versions={"commsfail": version("commsfail")}
            ),
            status="running",
        )
        try:
            record = run(name, trace)
            errors = validate_record(record)
            if errors:
                raise ValueError("; ".join(errors))
            analysis.output = record
            analysis.status = "completed"
        except Exception as error:
            logger.exception("Offline analysis %s failed", analysis.id)
            analysis.status = "failed"
            analysis.error = str(error)
        analysis.provenance.completed_at = now()
        store().save_run(analysis.record())
        return analysis.record()

    async def run_scout(analysis: AnalysisRun):
        try:
            async with semaphore:
                analysis.status = "running"
                analysis.provenance.started_at = now()
                store().save_run(analysis.record())
                report = report_for(analysis.trace_id)
                artifacts = data_dir / "runs" / analysis.id
                artifacts.mkdir(parents=True, exist_ok=True)
                analysis.output = await scout_runner(
                    report, analysis.provenance.model, artifacts
                )
                analysis.status = "completed"
        except asyncio.CancelledError:
            analysis.status = "failed"
            analysis.error = "API stopped before this analysis completed. Start a new run."
            raise
        except Exception as error:
            logger.exception("Scout analysis %s failed", analysis.id)
            analysis.status = "failed"
            analysis.error = str(error)
        finally:
            analysis.provenance.completed_at = now()
            store().save_run(analysis.record())

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/analyzers")
    def analyzers(trace_id: str | None = None):
        return analyzer_catalog(require_trace(trace_id) if trace_id else None)

    @app.get("/api/scout/setup")
    def get_scout_setup(model: str | None = None):
        selected = default_scout_model() if model is None else model.strip()
        if not selected:
            raise HTTPException(status_code=422, detail="Enter a non-empty provider/model identifier.")
        return scout_setup(selected)

    @app.post("/api/analyze")
    @app.post("/api/traces")
    def ingest(request: TraceRequest):
        if bool(request.source) == bool(request.url):
            raise HTTPException(status_code=422, detail="Provide exactly one source or url.")
        source = request.source or Source(type="sharednet_share", value=request.url)
        try:
            trace = load_source(source, source_root)
            build_view_model(trace)  # Validate before persistence or analysis.
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        identifier = trace_id(trace)
        store().save_trace(identifier, trace)
        existing = {analysis["analyzer"]["name"] for analysis in store().list_runs(identifier)}
        for name in ("agenttrace_heuristics_v1", "regex_v1"):
            if name not in existing:
                offline_analysis(identifier, name)
        return report_for(identifier)

    @app.get("/api/traces/{identifier}")
    def get_trace(identifier: str):
        return report_for(identifier)

    @app.get("/api/traces/{identifier}/raw")
    def raw_trace(identifier: str):
        return {"schema": "commsfail/trace.v1", **require_trace(identifier).to_dict()}

    @app.get("/api/traces/{identifier}/analyses")
    def list_analyses(identifier: str):
        require_trace(identifier)
        return store().list_runs(identifier)

    @app.post("/api/traces/{identifier}/analyses/{name}", status_code=202)
    async def start_analysis(identifier: str, name: str, request: AnalysisRequest):
        require_trace(identifier)
        if name != SCOUT:
            return await asyncio.to_thread(offline_analysis, identifier, name)
        model = request.model.strip() if request.model is not None else default_scout_model()
        if not model:
            raise HTTPException(status_code=422, detail="Enter a non-empty provider/model identifier.")
        # Reuse an active run to avoid accidental duplicate model charges.
        for previous in store().list_runs(identifier):
            if previous["analyzer"]["name"] == SCOUT and previous["status"] in ("queued", "running"):
                return previous
        if scout_runner is scout_pipeline:
            setup = scout_setup(model)
            if not setup["ready"]:
                missing_package = any(issue["code"] == "scout_not_installed" for issue in setup["issues"])
                raise HTTPException(status_code=503 if missing_package else 422, detail={
                    "code": "scout_setup_required",
                    "message": " ".join(issue["message"] for issue in setup["issues"]),
                    "setup": setup,
                })
        analysis = AnalysisRun(
            trace_id=identifier,
            analyzer=Analyzer(name=SCOUT, version="2.0.0", kind="pipeline"),
            provenance=Provenance(
                model=model, prompt_version="2",
                package_versions={
                    package: version(package) for package in ("commsfail", "agenttrace-api")
                },
            ),
        )
        if importlib.util.find_spec("inspect_scout") is not None:
            analysis.provenance.package_versions["inspect-scout"] = version("inspect-scout")
        store().save_run(analysis.record())
        task = asyncio.create_task(run_scout(analysis))
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        return analysis.record()

    @app.get("/api/analysis-runs/{identifier}")
    def get_analysis(identifier: str):
        analysis = store().get_run(identifier)
        if analysis is None:
            raise HTTPException(status_code=404, detail="Analysis run not found.")
        return analysis

    # Unknown API paths must not be mistaken for SPA routes.
    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
    def missing_api(path: str):
        raise HTTPException(status_code=404, detail="API endpoint not found.")

    dist = (web_dist or Path(os.getenv("AGENTTRACE_WEB_DIST", REPOSITORY / "apps/web/dist"))).resolve()
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        candidate = (dist / path).resolve()
        if not candidate.is_relative_to(dist):
            raise HTTPException(status_code=404, detail="Not found.")
        if candidate.is_file():
            return FileResponse(candidate)
        if path and "." in Path(path).name:
            raise HTTPException(status_code=404, detail="Asset not found.")
        if not (dist / "index.html").exists():
            raise HTTPException(status_code=503, detail="Build the frontend with npm run build.")
        return FileResponse(dist / "index.html")

    return app


def main():
    import uvicorn

    uvicorn.run("agenttrace.api:create_app", factory=True, host="127.0.0.1",
                port=int(os.getenv("PORT", "3000")), workers=1)
