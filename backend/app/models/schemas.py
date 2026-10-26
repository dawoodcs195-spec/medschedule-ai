"""Pydantic v2 API contracts and LLM structured-output schemas."""
from __future__ import annotations

from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SessionType(str, Enum):
    LGIS = "LGIS"
    PRACTICAL = "PRACTICAL"
    SGD = "SGD"
    DSL = "DSL"
    SDL = "SDL"
    RIPPLE = "RIPPLE"
    ISL = "ISL"
    MENTOR_MENTEE = "MENTOR_MENTEE"
    PAL = "PAL"
    SKILL_LAB = "SKILL_LAB"


# ---------------------------------------------------------------------------
# LLM structured output (kept flat & simple so it maps cleanly to JSON Schema)
# ---------------------------------------------------------------------------
class ExtractedTopic(BaseModel):
    topic_title: str = Field(description="Concise topic title, e.g. 'Organization of nervous system'.")
    description: str = Field(default="", description="Learning objective or extra detail, if any.")
    discipline: str = Field(
        description="Department label as written, e.g. 'NEURO ANAT', 'PHYSIO', 'HISTO', 'BIOCHEM', "
        "'CLINICAL FACULTY SURGERY'."
    )
    session_type: SessionType = Field(description="Teaching format of the session.")
    organ_system: Optional[str] = Field(
        default=None, description="Organ system / module theme, e.g. 'Neurosciences'."
    )
    faculty_name: Optional[str] = Field(
        default=None, description="Explicit faculty name, e.g. 'Dr. Ambar Saba'. Null if absent."
    )
    duration_minutes: Optional[int] = Field(
        default=None, description="Duration in minutes if stated (LGIS=60, PRACTICAL/SGD=90-120)."
    )
    practical_code: Optional[str] = Field(
        default=None, description="Practical/SGD legend code if present, e.g. 'HISTO P1', 'PHYSIO SGD'."
    )


class ExtractedModuleMeta(BaseModel):
    program: Optional[str] = Field(default=None, description="'MBBS' or 'BDS'.")
    academic_year: Optional[int] = Field(default=None, description="Year of study, e.g. 2.")
    module_title: Optional[str] = Field(default=None, description="e.g. 'NEUROSCIENCES BLOCK-IV'.")
    module_code: Optional[str] = Field(default=None, description="e.g. 'MODULE-07'.")
    session: Optional[str] = Field(default=None, description="Academic session, e.g. '2026-2027'.")


class SyllabusExtraction(BaseModel):
    meta: ExtractedModuleMeta
    topics: list[ExtractedTopic]


# ---------------------------------------------------------------------------
# API contracts
# ---------------------------------------------------------------------------
class ParsedTopic(ExtractedTopic):
    """Topic after normalization (canonical discipline + guaranteed duration)."""

    raw_discipline: str
    category: str = Field(description="UI colour group: ANATOMY|PHYSIOLOGY|BIOCHEMISTRY|CLINICAL|INSTITUTIONAL")
    duration_minutes: int  # type: ignore[assignment]
    id: Optional[UUID] = None
    original_week: Optional[int] = None
    original_day: Optional[int] = None
    original_start: Optional[str] = None
    original_end: Optional[str] = None
    program: Optional[str] = Field(default=None, description="'MBBS' or 'BDS'")
    academic_year: Optional[int] = Field(default=None, description="Year of study (1-5)")
    cohort: Optional[str] = Field(default=None, description="Class key, e.g. 'MBBS-2'")
    occurrences: int = Field(default=1, ge=1, description="Times the topic appears in the uploaded timetable")


class LegendEntry(BaseModel):
    code: str = Field(description="e.g. 'HISTO P1', 'PHYSIO SGD', 'SKILL LAB'")
    title: str
    cohort: Optional[str] = None


class CohortSummary(BaseModel):
    """One class (e.g. 2nd Year MBBS) found in an upload."""

    cohort: str = Field(description="e.g. 'MBBS-2'")
    label: str = Field(description="e.g. '2nd Year MBBS'")
    program: str
    academic_year: int
    module_title: Optional[str] = None
    module_code: Optional[str] = None
    session: Optional[str] = Field(default=None, description="Academic session from the header, e.g. '2026-2027'")
    class_detected: bool = Field(
        default=False, description="True when program/year came from the file (header or file name), not the form"
    )
    source: Optional[str] = Field(default=None, description="File name or 'pasted text'")
    topic_count: int = 0


class ParseResponse(BaseModel):
    meta: ExtractedModuleMeta
    topics: list[ParsedTopic]
    legend: list[LegendEntry] = []
    faculty: list[str] = []
    engine: str = Field(description="'gemini' or 'heuristic'")
    warnings: list[str] = []
    module_id: Optional[UUID] = None
    persisted: bool = False
    cohorts: list[CohortSummary] = []


class IngestTextRequest(BaseModel):
    text: str = Field(min_length=1)
    program: str = "MBBS"
    academic_year: int = 2
    module_title: Optional[str] = None
    module_code: Optional[str] = None
    persist: bool = False
    use_llm: bool = True


class DepartmentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    code: Optional[str] = Field(default=None, max_length=50)


class Department(DepartmentCreate):
    id: Optional[UUID] = None
    is_active: bool = True


class Room(BaseModel):
    id: Optional[UUID] = None
    name: str
    room_type: str
    capacity: int
