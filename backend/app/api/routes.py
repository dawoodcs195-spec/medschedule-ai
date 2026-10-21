"""REST endpoints for all 4 Sprints:
1. Ingestion (Text / File upload / Heuristic / Gemini)
2. Semantic Integration (Horizontal & Vertical clustering via 1536-dim vector similarity)
3. Timetable Constraint Solver (Google OR-Tools CP-SAT) & Option B Validation
4. Single-Page Landscape Word (.docx) Exporter
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.constants import CLINICAL_DEPARTMENTS, PRACTICAL_VENUES, SGD_STATIONS
from app.core.database import db_available, get_db
from app.core.gemini import gemini_enabled
from app.models.schemas import (
    Department, DepartmentCreate, ExtractedModuleMeta, IngestTextRequest, LegendEntry,
    ParsedTopic, ParseResponse,
)
from app.services import copilot, exporter, integrator, parser, repository, solver

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_UPLOAD_BYTES = 15 * 1024 * 1024


def _safe_db():
    """Yield a session only if the DB is reachable; otherwise None (offline mode)."""
    if not db_available():
        yield None
        return
    yield from get_db()


def _finalize(
    result: ParseResponse,
    persist: bool,
    program: str,
    academic_year: int,
) -> ParseResponse:
    from uuid import uuid4
    import threading
    from app.core.database import SessionLocal

    for t in result.topics:
        if t.id is None:
            t.id = uuid4()

    if not persist or SessionLocal is None:
        return result

    result.module_id = result.module_id or uuid4()
    result.persisted = True
    result_copy = result.model_copy(deep=True)

    def _bg_persist():
        if not db_available():
            return
        bg_db = SessionLocal()
        try:
            repository.persist_parse_result(bg_db, result_copy, program, academic_year)
        except Exception:
            bg_db.rollback()
            logger.exception("Background persistence failed")
        finally:
            bg_db.close()

    worker = threading.Thread(target=_bg_persist, daemon=True)
    worker.start()
    return result


# ---------------------------------------------------------------------------
# Sprint 1: System Health & Ingestion
# ---------------------------------------------------------------------------


@router.get("/health", tags=["system"])
def health():
    return {"status": "ok", "gemini": gemini_enabled(), "database": db_available()}


@router.post("/ingest/text", response_model=ParseResponse, tags=["ingestion"])
def ingest_text(req: IngestTextRequest):
    doc = parser.read_text(req.text)
    overrides = ExtractedModuleMeta(
        program=req.program,
        academic_year=req.academic_year,
        module_title=req.module_title,
        module_code=req.module_code,
    )
    result = parser.parse_document(doc, use_llm=req.use_llm, overrides=overrides)
    return _finalize(result, req.persist, req.program, req.academic_year)


@router.post("/ingest/file", response_model=ParseResponse, tags=["ingestion"])
async def ingest_file(
    file: UploadFile = File(...),
    program: str = Form("MBBS"),
    academic_year: int = Form(2),
    persist: bool = Form(False),
    use_llm: bool = Form(True),
):
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File exceeds 15 MB limit.")
    try:
        doc = parser.read_upload(file.filename or "upload", data)
    except ValueError as exc:
        raise HTTPException(415, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(422, f"Could not read document: {exc}") from exc

    from starlette.concurrency import run_in_threadpool

    result = await run_in_threadpool(parser.parse_document, doc, use_llm)
    if result.meta.program is None:
        result.meta.program = program
    if result.meta.academic_year is None:
        result.meta.academic_year = academic_year
    return _finalize(result, persist, result.meta.program, result.meta.academic_year)


@router.get("/departments", response_model=list[Department], tags=["reference"])
def get_departments(db: Optional[Session] = Depends(_safe_db)):
    return repository.list_departments(db)


@router.post("/departments", response_model=Department, status_code=201, tags=["reference"])
def create_department(payload: DepartmentCreate, db: Optional[Session] = Depends(_safe_db)):
    return repository.add_department(db, payload)


@router.get("/reference/facilities", tags=["reference"])
def facilities():
    return {
        "lecture_halls": [f"Lecture Hall {i}" for i in range(1, 9)],
        "practical_venues": PRACTICAL_VENUES,
        "sgd_stations": SGD_STATIONS,
        "clinical_departments": CLINICAL_DEPARTMENTS,
    }


# ---------------------------------------------------------------------------
# Sprint 2: Semantic Clustering (Horizontal & Vertical Linkages) & CRUD
# ---------------------------------------------------------------------------


class ClusterRequest(BaseModel):
    topics: list[ParsedTopic] = []
    module_id: Optional[UUID] = None


@router.post("/integrate/cluster", response_model=integrator.IntegrationClusterResult, tags=["integration"])
def cluster_topics(req: ClusterRequest):
    if req.topics and req.module_id is None:
        return integrator.cluster_and_integrate(req.topics, db=None, module_id=None)
    db = next(_safe_db(), None)
    try:
        return integrator.cluster_and_integrate(req.topics, db=db, module_id=req.module_id)
    finally:
        if db is not None:
            db.close()


@router.get("/integrations", response_model=integrator.IntegrationClusterResult, tags=["integration"])
def get_integrations(
    module_id: Optional[UUID] = None,
    auto_propose: bool = True,
    db: Optional[Session] = Depends(_safe_db),
):
    return integrator.list_integrations(db=db, module_id=module_id, auto_propose=auto_propose)


@router.post("/integrations", response_model=integrator.ProposedLink, status_code=201, tags=["integration"])
def create_integration_link(
    payload: integrator.IntegrationCreateRequest,
    db: Optional[Session] = Depends(_safe_db),
):
    return integrator.create_integration(db=db, payload=payload)


@router.patch("/integrations/{integration_id}", response_model=integrator.ProposedLink, tags=["integration"])
@router.put("/integrations/{integration_id}", response_model=integrator.ProposedLink, tags=["integration"])
def update_integration_link(
    integration_id: UUID,
    payload: integrator.IntegrationUpdateRequest,
    db: Optional[Session] = Depends(_safe_db),
):
    try:
        return integrator.update_integration(db=db, integration_id=integration_id, payload=payload)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


class SuggestClinicalRequest(BaseModel):
    topics: list[ParsedTopic] = []
    existing_links: list[integrator.ProposedLink] = []


@router.post("/integrate/suggest-clinical", response_model=integrator.ClinicalSuggestionResult, tags=["integration"])
def suggest_clinical_topics(req: SuggestClinicalRequest):
    return integrator.suggest_missing_clinical_topics(req.topics, req.existing_links)


@router.delete("/integrations/{integration_id}", status_code=204, tags=["integration"])
def delete_integration_link(
    integration_id: UUID,
    db: Optional[Session] = Depends(_safe_db),
):
    deleted = integrator.delete_integration(db=db, integration_id=integration_id)
    if not deleted:
        raise HTTPException(404, f"Integration {integration_id} not found")
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Sprint 2 & 3: Constraint Scheduling & Option B Soft Validation
# ---------------------------------------------------------------------------


class GenerateScheduleRequest(BaseModel):
    topics: list[ParsedTopic]
    approved_links: list[integrator.ProposedLink] = []
    module_code: str = "MODULE-07"
    module_title: str = "NEUROSCIENCES BLOCK-IV"
    academic_year: int = 2
    week_number: int = 1
    time_limit_seconds: float = 10.0


@router.post("/schedule/generate", response_model=solver.TimetableSchedule, tags=["scheduling"])
def generate_schedule(req: GenerateScheduleRequest):
    return solver.solve_schedule(
        topics=req.topics,
        approved_links=req.approved_links,
        module_code=req.module_code,
        module_title=req.module_title,
        academic_year=req.academic_year,
        week_number=req.week_number,
        time_limit_seconds=req.time_limit_seconds,
    )


@router.post("/schedule/original", response_model=solver.TimetableSchedule, tags=["scheduling"])
def get_original_uploaded_schedule(req: GenerateScheduleRequest):
    return solver.build_original_schedule(
        topics=req.topics,
        module_code=req.module_code,
        module_title=req.module_title,
        academic_year=req.academic_year,
        week_number=req.week_number,
    )


class ValidateMoveRequest(BaseModel):
    schedule: solver.TimetableSchedule
    cell_id: UUID
    new_day: int
    new_start: str
    new_end: str


@router.post("/schedule/validate-move", response_model=copilot.ValidationResult, tags=["scheduling"])
def validate_move(req: ValidateMoveRequest):
    try:
        return copilot.validate_slot_move(
            schedule=req.schedule,
            cell_id=req.cell_id,
            new_day=req.new_day,
            new_start=req.new_start,
            new_end=req.new_end,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


class SwapCellsRequest(BaseModel):
    schedule: solver.TimetableSchedule
    cell_a_id: UUID
    cell_b_id: UUID


@router.post("/schedule/swap", response_model=copilot.CopilotChatResponse, tags=["scheduling"])
def swap_cells_endpoint(req: SwapCellsRequest):
    try:
        return copilot.swap_schedule_cells(
            schedule=req.schedule,
            cell_a_id=req.cell_a_id,
            cell_b_id=req.cell_b_id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


class RemoveCellRequest(BaseModel):
    schedule: solver.TimetableSchedule
    cell_id: UUID


@router.post("/schedule/remove", response_model=copilot.CopilotChatResponse, tags=["scheduling"])
def remove_cell_endpoint(req: RemoveCellRequest):
    try:
        return copilot.remove_schedule_cell(
            schedule=req.schedule,
            cell_id=req.cell_id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


class AddCellRequest(BaseModel):
    schedule: solver.TimetableSchedule
    day_of_week: int
    time_start: str
    time_end: str
    topic_title: str
    discipline: str
    session_type: str = "LGIS"
    faculty_name: Optional[str] = None
    venue_name: Optional[str] = None


@router.post("/schedule/add-cell", response_model=copilot.CopilotChatResponse, tags=["scheduling"])
def add_cell_endpoint(req: AddCellRequest):
    try:
        return copilot.add_schedule_cell(
            schedule=req.schedule,
            day_of_week=req.day_of_week,
            time_start=req.time_start,
            time_end=req.time_end,
            topic_title=req.topic_title,
            discipline=req.discipline,
            session_type=req.session_type,
            faculty_name=req.faculty_name,
            venue_name=req.venue_name,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


class UpdateCellRequest(BaseModel):
    schedule: solver.TimetableSchedule
    cell_id: UUID
    topic_title: Optional[str] = None
    discipline: Optional[str] = None
    session_type: Optional[str] = None
    faculty_name: Optional[str] = None
    venue_name: Optional[str] = None


@router.post("/schedule/update-cell", response_model=copilot.CopilotChatResponse, tags=["scheduling"])
def update_cell_endpoint(req: UpdateCellRequest):
    try:
        return copilot.update_schedule_cell(
            schedule=req.schedule,
            cell_id=req.cell_id,
            topic_title=req.topic_title,
            discipline=req.discipline,
            session_type=req.session_type,
            faculty_name=req.faculty_name,
            venue_name=req.venue_name,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


# ---------------------------------------------------------------------------
# Saved Timetables Snapshot Store (Save & Load Past Timetables)
# ---------------------------------------------------------------------------

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

_SAVED_FILE = Path(__file__).resolve().parents[2] / ".saved_schedules.json"


class SavedScheduleEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    saved_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"))
    schedule: solver.TimetableSchedule


class SaveScheduleRequest(BaseModel):
    name: Optional[str] = None
    schedule: solver.TimetableSchedule


def _load_saved_schedules() -> list[SavedScheduleEntry]:
    if not _SAVED_FILE.exists():
        return []
    try:
        raw = json.loads(_SAVED_FILE.read_text(encoding="utf-8"))
        return [SavedScheduleEntry.model_validate(item) for item in raw]
    except Exception:
        logger.warning("Failed to read .saved_schedules.json; returning empty list")
        return []


def _write_saved_schedules(entries: list[SavedScheduleEntry]) -> None:
    try:
        payload = [e.model_dump(mode="json") for e in entries]
        _SAVED_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        logger.warning("Failed to write .saved_schedules.json")


@router.get("/schedules/saved", response_model=list[SavedScheduleEntry], tags=["scheduling"])
def list_saved_schedules():
    return _load_saved_schedules()


@router.post("/schedules/save", response_model=SavedScheduleEntry, status_code=201, tags=["scheduling"])
def save_schedule_snapshot(req: SaveScheduleRequest):
    entries = _load_saved_schedules()
    default_name = (
        req.name.strip()
        if req.name and req.name.strip()
        else f"{req.schedule.module_title} ({req.schedule.module_code}) — Week {req.schedule.week_number}"
    )
    entry = SavedScheduleEntry(
        name=default_name,
        schedule=req.schedule,
    )
    entries.insert(0, entry)
    entries = entries[:25]
    _write_saved_schedules(entries)
    return entry


@router.delete("/schedules/saved/{saved_id}", status_code=204, tags=["scheduling"])
def delete_saved_schedule(saved_id: str):
    entries = _load_saved_schedules()
    filtered = [e for e in entries if e.id != saved_id]
    _write_saved_schedules(filtered)
    return Response(status_code=204)


@router.post("/copilot/chat", response_model=copilot.CopilotChatResponse, tags=["copilot"])
def copilot_chat(req: copilot.CopilotChatRequest):
    return copilot.execute_copilot_command(req)


# ---------------------------------------------------------------------------
# Sprint 4: Landscape Word (.docx) Exporter
# ---------------------------------------------------------------------------


class ExportDocxRequest(BaseModel):
    schedule: solver.TimetableSchedule
    legend_entries: list[LegendEntry] = []


@router.post("/export/docx", tags=["export"])
def export_docx(req: ExportDocxRequest):
    docx_bytes = exporter.generate_landscape_docx(
        schedule=req.schedule,
        legend_entries=req.legend_entries,
    )
    filename = f"Timetable_{req.schedule.module_code}_Week{req.schedule.week_number:02d}.docx"
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
