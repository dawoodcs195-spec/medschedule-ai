"""SQLAlchemy ORM models mirroring supabase/migrations/001_initial_schema.sql."""
from __future__ import annotations

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, Float, ForeignKey, Integer, String, Text, Time, func,
)
from sqlalchemy.dialects.postgresql import UUID

from app.core.config import settings
from app.core.database import Base


def _pk():
    return Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class AcademicProgram(Base):
    __tablename__ = "academic_programs"
    id = _pk()
    code = Column(String(20), nullable=False, unique=True)
    title = Column(String(250), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Module(Base):
    __tablename__ = "modules"
    id = _pk()
    program_id = Column(UUID(as_uuid=True), ForeignKey("academic_programs.id", ondelete="CASCADE"), nullable=False)
    code = Column(String(50), nullable=False)
    title = Column(String(250), nullable=False)
    academic_year = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ClinicalDepartment(Base):
    __tablename__ = "clinical_departments"
    id = _pk()
    name = Column(String(150), nullable=False, unique=True)
    code = Column(String(50))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Room(Base):
    __tablename__ = "rooms"
    id = _pk()
    name = Column(String(100), nullable=False, unique=True)
    room_type = Column(String(50), nullable=False)
    capacity = Column(Integer, nullable=False, default=100)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LearningObjective(Base):
    __tablename__ = "learning_objectives"
    id = _pk()
    module_id = Column(UUID(as_uuid=True), ForeignKey("modules.id", ondelete="CASCADE"))
    topic_title = Column(String(250), nullable=False)
    description = Column(Text, nullable=False, default="")
    discipline = Column(String(100), nullable=False, default="General")
    session_type = Column(String(50), nullable=False)
    organ_system = Column(String(100))
    faculty_name = Column(String(150))
    duration_minutes = Column(Integer, nullable=False, default=60)
    embedding = Column(Vector(settings.EMBEDDING_DIMENSION))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CurriculumIntegration(Base):
    __tablename__ = "curriculum_integrations"
    __table_args__ = (
        CheckConstraint("source_objective_id <> target_objective_id", name="chk_different_objectives"),
    )
    id = _pk()
    source_objective_id = Column(UUID(as_uuid=True), ForeignKey("learning_objectives.id", ondelete="CASCADE"), nullable=False)
    target_objective_id = Column(UUID(as_uuid=True), ForeignKey("learning_objectives.id", ondelete="CASCADE"), nullable=False)
    integration_type = Column(String(20), nullable=False)
    similarity_score = Column(Float, nullable=False)
    is_approved = Column(Boolean, default=False)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ScheduleSlot(Base):
    __tablename__ = "schedule_slots"
    id = _pk()
    objective_id = Column(UUID(as_uuid=True), ForeignKey("learning_objectives.id", ondelete="CASCADE"), nullable=False)
    room_id = Column(UUID(as_uuid=True), ForeignKey("rooms.id", ondelete="SET NULL"))
    week_number = Column(Integer, nullable=False, default=1)
    day_of_week = Column(Integer, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    student_batch_mask = Column(String(20), nullable=False, default="ALL")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
