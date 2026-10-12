from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Analyzer(BaseModel):
    name: str
    version: str
    kind: Literal["offline", "pipeline"]


class Provenance(BaseModel):
    created_at: str = Field(default_factory=now)
    started_at: str | None = None
    completed_at: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    input_schema: str = "commsfail/trace.v1"
    package_versions: dict[str, str] = Field(default_factory=dict)


class AnalysisRun(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    schema_version: Literal["agenttrace/analysis-run.v1"] = Field(
        default="agenttrace/analysis-run.v1", alias="schema"
    )
    id: str = Field(default_factory=lambda: f"run_{uuid4().hex}")
    trace_id: str
    analyzer: Analyzer
    status: Literal["queued", "running", "completed", "failed"] = "queued"
    provenance: Provenance = Field(default_factory=Provenance)
    output: dict | None = None
    error: str | None = None

    def record(self) -> dict:
        return self.model_dump(mode="json", by_alias=True)
