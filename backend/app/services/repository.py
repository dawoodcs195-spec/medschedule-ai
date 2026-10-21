"""Persistence helpers. All functions degrade gracefully when the DB is unreachable."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import CLINICAL_DEPARTMENTS
from app.models import db_models as m
from app.models.schemas import Department, DepartmentCreate, ParseResponse

# In-memory fallback so the admin UI works before Supabase is wired up.
_memory_departments: list[Department] = [Department(name=n) for n in CLINICAL_DEPARTMENTS]


def persist_parse_result(db: Session, result: ParseResponse, program_code: str, academic_year: int) -> UUID:
    from uuid import uuid4
    from app.services.integrator import compute_embeddings

    program = db.scalar(select(m.AcademicProgram).where(m.AcademicProgram.code == program_code))
    if program is None:
        program = m.AcademicProgram(id=uuid4(), code=program_code, title=program_code)
        db.add(program)

    code = result.meta.module_code or "UNSPECIFIED"
    title = result.meta.module_title or "Untitled Module"
    module = db.scalar(select(m.Module).where(m.Module.program_id == program.id, m.Module.code == code))
    if module is None:
        module = m.Module(
            id=uuid4(),
            program_id=program.id,
            code=code,
            title=title,
            academic_year=result.meta.academic_year or academic_year,
        )
        db.add(module)

    descriptions = [f"{t.topic_title} {t.description or ''}".strip() for t in result.topics]
    embeddings, _ = compute_embeddings(descriptions) if descriptions else ([], "none")

    rows: list[m.LearningObjective] = []
    for idx, topic in enumerate(result.topics):
        emb = embeddings[idx] if idx < len(embeddings) else None
        row_id = topic.id or uuid4()
        topic.id = row_id
        rows.append(
            m.LearningObjective(
                id=row_id,
                module_id=module.id,
                topic_title=topic.topic_title[:250],
                description=topic.description,
                discipline=topic.discipline,
                session_type=topic.session_type.value,
                organ_system=topic.organ_system,
                faculty_name=topic.faculty_name,
                duration_minutes=topic.duration_minutes,
                embedding=emb,
            )
        )
    if rows:
        db.add_all(rows)
    db.commit()
    return module.id


def list_departments(db: Session | None) -> list[Department]:
    if db is None:
        return _memory_departments
    rows = db.scalars(select(m.ClinicalDepartment).order_by(m.ClinicalDepartment.name)).all()
    return [Department(id=r.id, name=r.name, code=r.code, is_active=bool(r.is_active)) for r in rows]


def add_department(db: Session | None, payload: DepartmentCreate) -> Department:
    name = payload.name.strip().upper()
    if db is None:
        existing = next((d for d in _memory_departments if d.name == name), None)
        if existing:
            return existing
        dept = Department(name=name, code=payload.code)
        _memory_departments.append(dept)
        return dept
    row = db.scalar(select(m.ClinicalDepartment).where(m.ClinicalDepartment.name == name))
    if row is None:
        row = m.ClinicalDepartment(name=name, code=payload.code)
        db.add(row)
        db.commit()
        db.refresh(row)
    return Department(id=row.id, name=row.name, code=row.code, is_active=bool(row.is_active))
