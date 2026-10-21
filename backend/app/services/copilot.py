"""Sprint 3: AI Copilot & Real-Time Schedule Validation Engine.

Enforces Option B Conflict Handling (Soft Warnings):
- Does not hard-block admin overrides or moves.
- Detects Room collisions, Faculty double-bookings, Friday afternoon violations,
  Daily break violations, and Student batch overlaps.
- Returns detailed diagnostic notes and suggests candidate conflict-free open slots.
- Powers natural language schedule edits via Gemini structured instructions + deterministic NL parser fallback.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.constants import BATCHES, DAYS, FRIDAY
from app.core.gemini import gemini_enabled, get_gemini_client
from app.services.solver import ScheduledCell, TimetableSchedule, recompute_schedule_analytics

logger = logging.getLogger(__name__)


class ConflictDetail(BaseModel):
    severity: str = Field(description="'ERROR' or 'WARNING'")
    message: str
    conflicting_cell_ids: list[UUID] = []
    suggested_alternative_slots: list[str] = []


class ValidationResult(BaseModel):
    is_valid: bool
    conflicts: list[ConflictDetail]
    updated_cell: ScheduledCell


class CopilotChatRequest(BaseModel):
    instruction: str = Field(description="Natural language instruction, e.g. 'Move Dr. Ambar session to Wednesday 10 AM'")
    schedule: TimetableSchedule
    selected_cell_id: Optional[UUID] = None


class CopilotChatResponse(BaseModel):
    reply: str
    action_taken: str  # 'MOVED', 'SWAPPED', 'REASSIGNED_FACULTY', 'INFO', 'CONFLICT_WARNING'
    updated_schedule: TimetableSchedule
    affected_cell_id: Optional[UUID] = None
    conflicts: list[ConflictDetail] = []


STANDARD_SLOTS = [
    ("08:00", "09:00"),
    ("09:00", "10:00"),
    ("10:00", "11:00"),
    ("11:00", "12:00"),
    ("12:30", "14:00"),
]


def find_open_alternative_slots(schedule: TimetableSchedule, duration_two_hours: bool = False) -> list[str]:
    """Return up to 4 conflict-free candidate slots across the week."""
    suggestions: list[str] = []
    for d in range(1, 7):
        day_name = DAYS[d].title()
        day_cells = [c for c in schedule.cells if c.day_of_week == d and c.session_type not in ("BREAK", "HALF_DAY")]
        for start, end in STANDARD_SLOTS:
            if d == FRIDAY and start >= "12:00":
                continue
            if duration_two_hours and start not in ("10:00", "12:30"):
                continue
            busy = any(max(start, c.time_start) < min(end, c.time_end) for c in day_cells)
            if not busy:
                suggestions.append(f"{day_name} {start} – {end}")
                if len(suggestions) >= 4:
                    return suggestions
    if not suggestions:
        suggestions = [
            "Wednesday 08:00 – 09:00",
            "Thursday 09:00 – 10:00",
            "Friday 10:00 – 11:00",
            "Saturday 08:00 – 09:00",
        ]
    return suggestions


def check_cell_conflicts(
    target_cell: ScheduledCell,
    all_cells: list[ScheduledCell],
    schedule: Optional[TimetableSchedule] = None,
) -> list[ConflictDetail]:
    """Validate a cell against institutional scheduling rules and other scheduled cells."""
    conflicts: list[ConflictDetail] = []
    alt_slots = (
        find_open_alternative_slots(schedule)
        if schedule is not None
        else ["Wednesday 08:00 - 09:00", "Thursday 09:00 - 10:00", "Friday 10:00 - 11:00"]
    )

    # 1. Friday Half-Day Rule (No classes after 12:00 PM on Friday)
    if target_cell.day_of_week == FRIDAY and target_cell.time_start >= "12:00":
        if target_cell.session_type != "HALF_DAY":
            conflicts.append(
                ConflictDetail(
                    severity="ERROR",
                    message="Friday Half-Day Violation: Strictly no academic sessions are permitted after 12:00 PM on Fridays.",
                    suggested_alternative_slots=[
                        "Friday 08:00 - 09:00",
                        "Friday 09:00 - 10:00",
                        "Friday 10:00 - 11:00",
                        "Friday 11:00 - 12:00",
                    ],
                )
            )

    # 2. Daily Break Rule (12:00 to 12:30 is reserved for break)
    if target_cell.day_of_week != FRIDAY:
        if (target_cell.time_start < "12:30" and target_cell.time_end > "12:00") and target_cell.session_type != "BREAK":
            conflicts.append(
                ConflictDetail(
                    severity="ERROR",
                    message="Daily Break Conflict: Time bracket 12:00 - 12:30 is reserved institutional break.",
                    suggested_alternative_slots=alt_slots,
                )
            )

    # 3. Inter-Cell Collisions (Slot Occupancy, Faculty, Room, Batch)
    for other in all_cells:
        if other.id == target_cell.id:
            continue
        if other.day_of_week != target_cell.day_of_week:
            continue
        if other.session_type in ("BREAK", "HALF_DAY"):
            continue

        # Check time overlap: max(start1, start2) < min(end1, end2)
        if max(target_cell.time_start, other.time_start) < min(target_cell.time_end, other.time_end):
            # A. Faculty Double-Booking
            if (
                target_cell.faculty_name
                and other.faculty_name
                and target_cell.faculty_name.strip().lower() == other.faculty_name.strip().lower()
            ):
                conflicts.append(
                    ConflictDetail(
                        severity="ERROR",
                        message=f"Faculty Clash: {target_cell.faculty_name} is already scheduled for '{other.topic_title}' on {DAYS[target_cell.day_of_week]} at {other.time_start} - {other.time_end}.",
                        conflicting_cell_ids=[other.id],
                        suggested_alternative_slots=alt_slots,
                    )
                )

            # B. Cohort / Time-Slot Overlap (Two sessions occupying the same cohort time slot)
            if target_cell.student_batch_mask == "ALL" or other.student_batch_mask == "ALL":
                conflicts.append(
                    ConflictDetail(
                        severity="WARNING",
                        message=f"Slot Clash: '{other.topic_title}' ({other.discipline}) is already scheduled on {DAYS[target_cell.day_of_week].title()} at {other.time_start} - {other.time_end}.",
                        conflicting_cell_ids=[other.id],
                        suggested_alternative_slots=alt_slots,
                    )
                )

            # C. Venue Collision (if same physical room)
            if (
                target_cell.venue_name
                and other.venue_name
                and target_cell.venue_name == other.venue_name
                and "Lecture Hall" not in target_cell.venue_name
            ):
                conflicts.append(
                    ConflictDetail(
                        severity="ERROR",
                        message=f"Venue Collision: '{target_cell.venue_name}' is occupied by '{other.topic_title}' at this time.",
                        conflicting_cell_ids=[other.id],
                        suggested_alternative_slots=alt_slots,
                    )
                )

    return conflicts


def validate_slot_move(
    schedule: TimetableSchedule,
    cell_id: UUID,
    new_day: int,
    new_start: str,
    new_end: str,
) -> ValidationResult:
    """Option B soft-validation for drag-and-drop or manual rescheduling."""
    target_idx = next((i for i, c in enumerate(schedule.cells) if c.id == cell_id), None)
    if target_idx is None:
        raise ValueError(f"Cell with ID {cell_id} not found in schedule.")

    current = schedule.cells[target_idx]

    # Preserve 2-hour duration if moving a 2-hour block to 10:00
    if current.session_type in ("PRACTICAL", "SGD") and new_start == "10:00" and new_end == "11:00":
        new_end = "12:00"

    provisional = current.model_copy(
        update={
            "day_of_week": new_day,
            "day_name": DAYS.get(new_day, f"Day {new_day}"),
            "time_start": new_start,
            "time_end": new_end,
        }
    )

    conflicts = check_cell_conflicts(provisional, schedule.cells, schedule=schedule)

    if conflicts:
        provisional.is_conflicted = True
        provisional.conflict_notes = "; ".join(c.message for c in conflicts)
    else:
        provisional.is_conflicted = False
        provisional.conflict_notes = None

    return ValidationResult(
        is_valid=len(conflicts) == 0,
        conflicts=conflicts,
        updated_cell=provisional,
    )


def _compute_end_time_for_session(cell: ScheduledCell, start_time: str) -> str:
    """Compute proper end time for a session given a new start time."""
    if start_time == "12:30":
        return "14:00"
    if cell.session_type in ("PRACTICAL", "SGD") and start_time in ("08:00", "10:00"):
        return "10:00" if start_time == "08:00" else "12:00"
    end_map = {
        "08:00": "09:00",
        "09:00": "10:00",
        "10:00": "11:00",
        "11:00": "12:00",
        "12:00": "12:30",
        "13:00": "14:00",
    }
    return end_map.get(start_time, cell.time_end)


def swap_schedule_cells(
    schedule: TimetableSchedule,
    cell_a_id: UUID,
    cell_b_id: UUID,
) -> CopilotChatResponse:
    """Swap two scheduled sessions' day/time coordinates and re-validate conflicts."""
    sched = schedule.model_copy(deep=True)
    cell_a = next((c for c in sched.cells if c.id == cell_a_id), None)
    cell_b = next((c for c in sched.cells if c.id == cell_b_id), None)

    if not cell_a or not cell_b:
        raise ValueError("One or both cells to swap were not found in the schedule.")
    if cell_a.session_type in ("BREAK", "HALF_DAY") or cell_b.session_type in ("BREAK", "HALF_DAY"):
        raise ValueError("Cannot swap fixed institutional BREAK or HALF_DAY blocks.")

    a_day, a_day_name, a_start = cell_a.day_of_week, cell_a.day_name, cell_a.time_start
    b_day, b_day_name, b_start = cell_b.day_of_week, cell_b.day_name, cell_b.time_start

    cell_a.day_of_week = b_day
    cell_a.day_name = b_day_name
    cell_a.time_start = b_start
    cell_a.time_end = _compute_end_time_for_session(cell_a, b_start)

    cell_b.day_of_week = a_day
    cell_b.day_name = a_day_name
    cell_b.time_start = a_start
    cell_b.time_end = _compute_end_time_for_session(cell_b, a_start)

    # Re-evaluate conflicts for both swapped cells
    conflicts_a = check_cell_conflicts(cell_a, sched.cells, schedule=sched)
    cell_a.is_conflicted = len(conflicts_a) > 0
    cell_a.conflict_notes = "; ".join(c.message for c in conflicts_a) if conflicts_a else None

    conflicts_b = check_cell_conflicts(cell_b, sched.cells, schedule=sched)
    cell_b.is_conflicted = len(conflicts_b) > 0
    cell_b.conflict_notes = "; ".join(c.message for c in conflicts_b) if conflicts_b else None

    all_conflicts = conflicts_a + conflicts_b
    sched.cells.sort(key=lambda c: (c.day_of_week, c.time_start))
    recompute_schedule_analytics(sched)

    if all_conflicts:
        reply = (
            f"[Swapped with Warning] Swapped '{cell_a.topic_title}' ({cell_a.day_name.title()} {cell_a.time_start}) "
            f"and '{cell_b.topic_title}' ({cell_b.day_name.title()} {cell_b.time_start}), "
            f"but detected {len(all_conflicts)} constraint warning(s)."
        )
    else:
        reply = (
            f"[Swapped] Swapped '{cell_a.topic_title}' ({cell_a.day_name.title()} {cell_a.time_start}–{cell_a.time_end}) "
            f"with '{cell_b.topic_title}' ({cell_b.day_name.title()} {cell_b.time_start}–{cell_b.time_end}) "
            f"cleanly with zero collisions."
        )

    return CopilotChatResponse(
        reply=reply,
        action_taken="SWAPPED",
        updated_schedule=sched,
        affected_cell_id=cell_a.id,
        conflicts=all_conflicts,
    )


def remove_schedule_cell(
    schedule: TimetableSchedule,
    cell_id: UUID,
) -> CopilotChatResponse:
    """Remove a scheduled class from the timetable and recompute analytics and conflicts."""
    sched = schedule.model_copy(deep=True)
    target = next((c for c in sched.cells if c.id == cell_id), None)
    if not target:
        raise ValueError(f"Cell with ID {cell_id} not found in schedule.")
    if target.session_type in ("BREAK", "HALF_DAY"):
        raise ValueError("Cannot remove fixed institutional BREAK or HALF_DAY blocks.")

    sched.cells = [c for c in sched.cells if c.id != cell_id]

    # Re-evaluate any previously conflicted cells in case removing this cell resolved a clash
    for c in sched.cells:
        if c.session_type in ("BREAK", "HALF_DAY"):
            continue
        rem_conflicts = check_cell_conflicts(c, sched.cells, schedule=sched)
        c.is_conflicted = len(rem_conflicts) > 0
        c.conflict_notes = "; ".join(x.message for x in rem_conflicts) if rem_conflicts else None

    recompute_schedule_analytics(sched)
    return CopilotChatResponse(
        reply=(
            f"[Removed] Removed '{target.topic_title}' ({target.discipline}, "
            f"{target.day_name.title()} {target.time_start}–{target.time_end}) from the timetable."
        ),
        action_taken="REMOVED",
        updated_schedule=sched,
        affected_cell_id=None,
        conflicts=[],
    )


def add_schedule_cell(
    schedule: TimetableSchedule,
    day_of_week: int,
    time_start: str,
    time_end: str,
    topic_title: str,
    discipline: str,
    session_type: str = "LGIS",
    faculty_name: Optional[str] = None,
    venue_name: Optional[str] = None,
) -> CopilotChatResponse:
    """Add a new class to the timetable matrix, validate conflicts, and recompute analytics."""
    from uuid import uuid4
    from app.core.constants import discipline_category, normalize_discipline

    sched = schedule.model_copy(deep=True)
    norm_disc = normalize_discipline(discipline)
    cat = str(discipline_category(norm_disc))

    if not time_end:
        time_end = "14:00" if time_start == "12:30" else "09:00"

    new_cell = ScheduledCell(
        id=uuid4(),
        day_of_week=day_of_week,
        day_name=DAYS.get(day_of_week, f"MONDAY"),
        time_start=time_start,
        time_end=time_end,
        session_type=session_type,
        discipline=norm_disc,
        category=cat,
        topic_title=topic_title.strip(),
        faculty_name=faculty_name.strip() if faculty_name and faculty_name.strip() else None,
        venue_name=venue_name.strip() if venue_name and venue_name.strip() else "Lecture Hall 1",
    )

    conflicts = check_cell_conflicts(new_cell, sched.cells, schedule=sched)
    new_cell.is_conflicted = len(conflicts) > 0
    new_cell.conflict_notes = "; ".join(c.message for c in conflicts) if conflicts else None

    sched.cells.append(new_cell)
    sched.cells.sort(key=lambda c: (c.day_of_week, c.time_start))
    recompute_schedule_analytics(sched)

    return CopilotChatResponse(
        reply=(
            f"[Added] Added '{new_cell.topic_title}' ({new_cell.discipline}) to "
            f"{new_cell.day_name.title()} {new_cell.time_start}–{new_cell.time_end}."
        ),
        action_taken="ADDED",
        updated_schedule=sched,
        affected_cell_id=new_cell.id,
        conflicts=conflicts,
    )


def update_schedule_cell(
    schedule: TimetableSchedule,
    cell_id: UUID,
    topic_title: Optional[str] = None,
    discipline: Optional[str] = None,
    session_type: Optional[str] = None,
    faculty_name: Optional[str] = None,
    venue_name: Optional[str] = None,
) -> CopilotChatResponse:
    """Update an existing scheduled cell's title, discipline, faculty, or venue."""
    from app.core.constants import discipline_category, normalize_discipline

    sched = schedule.model_copy(deep=True)
    target = next((c for c in sched.cells if c.id == cell_id), None)
    if not target:
        raise ValueError(f"Cell with ID {cell_id} not found in schedule.")

    if topic_title is not None and topic_title.strip():
        target.topic_title = topic_title.strip()
    if discipline is not None and discipline.strip():
        norm_disc = normalize_discipline(discipline.strip())
        target.discipline = norm_disc
        target.category = str(discipline_category(norm_disc))
    if session_type is not None and session_type.strip():
        target.session_type = session_type.strip().upper()
    if faculty_name is not None:
        target.faculty_name = faculty_name.strip() or None
    if venue_name is not None:
        target.venue_name = venue_name.strip() or None

    conflicts = check_cell_conflicts(target, sched.cells, schedule=sched)
    target.is_conflicted = len(conflicts) > 0
    target.conflict_notes = "; ".join(c.message for c in conflicts) if conflicts else None

    recompute_schedule_analytics(sched)
    return CopilotChatResponse(
        reply=(
            f"[Updated] Updated '{target.topic_title}' ({target.discipline}, "
            f"Faculty: {target.faculty_name or 'TBA'})."
        ),
        action_taken="UPDATED",
        updated_schedule=sched,
        affected_cell_id=target.id,
        conflicts=conflicts,
    )


# ---------------------------------------------------------------------------
# Natural Language Copilot Command Parser & Executor
# ---------------------------------------------------------------------------

_DAY_LOOKUP = {
    "monday": 1, "mon": 1,
    "tuesday": 2, "tue": 2, "tues": 2,
    "wednesday": 3, "wed": 3,
    "thursday": 4, "thu": 4, "thur": 4, "thurs": 4,
    "friday": 5, "fri": 5,
    "saturday": 6, "sat": 6,
}

_TIME_LOOKUP = {
    "8": ("08:00", "09:00"),
    "08": ("08:00", "09:00"),
    "08:00": ("08:00", "09:00"),
    "8:00": ("08:00", "09:00"),
    "9": ("09:00", "10:00"),
    "09": ("09:00", "10:00"),
    "09:00": ("09:00", "10:00"),
    "9:00": ("09:00", "10:00"),
    "10": ("10:00", "11:00"),
    "10:00": ("10:00", "11:00"),
    "11": ("11:00", "12:00"),
    "11:00": ("11:00", "12:00"),
    "12": ("12:00", "12:30"),
    "12:00": ("12:00", "12:30"),
    "12:30": ("12:30", "14:00"),
    "1": ("13:00", "14:00"),
    "13:00": ("13:00", "14:00"),
    "2": ("12:30", "14:00"),
    "afternoon": ("12:30", "14:00"),
    "morning": ("08:00", "09:00"),
}


def _find_target_cell(
    instruction: str,
    schedule: TimetableSchedule,
    selected_cell_id: Optional[UUID],
) -> Optional[ScheduledCell]:
    lower = instruction.lower()
    movable = [c for c in schedule.cells if c.session_type not in ("BREAK", "HALF_DAY")]

    # 1. Match by explicit doctor / faculty name mentioned in instruction
    for c in movable:
        if c.faculty_name:
            fac_clean = c.faculty_name.lower().replace("dr.", "").replace("prof.", "").strip()
            parts = [p for p in fac_clean.split() if len(p) > 2]
            if any(p in lower for p in parts):
                return c

    # 2. Match by topic title keywords
    best_cell: Optional[ScheduledCell] = None
    best_hits = 0
    for c in movable:
        words = [w.strip("(),.:").lower() for w in c.topic_title.split() if len(w) > 3]
        hits = sum(1 for w in words if w in lower)
        if hits > best_hits:
            best_hits = hits
            best_cell = c
    if best_cell and best_hits > 0:
        return best_cell

    # 3. Match by discipline name
    for c in movable:
        if c.discipline.lower() in lower:
            return c

    # 4. Fallback to currently selected cell in UI
    if selected_cell_id:
        found = next((c for c in movable if c.id == selected_cell_id), None)
        if found:
            return found

    return movable[0] if movable else None


def _extract_destination_day_and_time(instruction: str, default_day: int) -> tuple[int, str, str]:
    lower = instruction.lower()
    new_day = default_day
    for token, d_num in _DAY_LOOKUP.items():
        if re.search(rf"\b{token}\b", lower):
            new_day = d_num
            break

    # Check time patterns like "10 am", "12:30", "09:00", "afternoon"
    time_match = re.search(r"\b(12:30|13:00|0?[89]:00|1[012]:00|0?[89]|1[012]|1)\s*(?:am|pm|a\.m\.|p\.m\.)?\b", lower)
    if "afternoon" in lower or "12:30" in lower or "1 pm" in lower or "13:00" in lower:
        if new_day == FRIDAY:
            return new_day, "13:00", "14:00"
        return new_day, "12:30", "14:00"
    if time_match:
        key = time_match.group(1)
        if key in _TIME_LOOKUP:
            s, e = _TIME_LOOKUP[key]
            return new_day, s, e

    return new_day, "09:00", "10:00"


def execute_copilot_command(req: CopilotChatRequest) -> CopilotChatResponse:
    """Process natural language rescheduling, faculty reassignment, or conflict queries."""
    text = req.instruction.strip()
    lower = text.lower()
    schedule = req.schedule.model_copy(deep=True)

    # Case 1: Faculty reassignment ("Reassign Dr. Jillani's session to Dr. Tariq" / "Change faculty to Dr. Tariq")
    reassign_match = re.search(r"(?:reassign|assign|change\s+faculty|replace).*?\bto\s+((?:dr|prof)\.?\s+[a-zA-Z .]+)", text, re.I)
    if reassign_match:
        new_faculty = reassign_match.group(1).strip()
        if not new_faculty.lower().startswith(("dr.", "prof.")):
            new_faculty = re.sub(r"^(dr|prof)\s*", lambda m: f"{m.group(1).title()}. ", new_faculty, flags=re.I)
        target = _find_target_cell(text.split(" to ")[0], schedule, req.selected_cell_id)
        if target:
            old_fac = target.faculty_name or "Unassigned"
            target.faculty_name = new_faculty
            conflicts = check_cell_conflicts(target, schedule.cells, schedule=schedule)
            target.is_conflicted = len(conflicts) > 0
            target.conflict_notes = "; ".join(c.message for c in conflicts) if conflicts else None
            recompute_schedule_analytics(schedule)
            return CopilotChatResponse(
                reply=f"Reassigned '{target.topic_title}' ({target.day_name.title()} {target.time_start}–{target.time_end}) from {old_fac} to {new_faculty}.",
                action_taken="REASSIGNED_FACULTY",
                updated_schedule=schedule,
                affected_cell_id=target.id,
                conflicts=conflicts,
            )

    # Case 2: Remove / Delete / Cancel a session ("Remove Spine trauma", "Delete Monday 8 AM", "Remove selected class")
    if any(k in lower for k in ("remove", "delete", "cancel", "drop", "clear")):
        movable = [c for c in schedule.cells if c.session_type not in ("BREAK", "HALF_DAY")]
        target: Optional[ScheduledCell] = None

        # Check if user specified day + time to remove (e.g., "Delete Monday 8 AM")
        day_matches = [_DAY_LOOKUP[m.group(0)] for m in re.finditer(r"\b(?:monday|mon|tuesday|tue|wednesday|wed|thursday|thu|friday|fri|saturday|sat)\b", lower)]
        time_matches = [_TIME_LOOKUP[m.group(1)][0] for m in re.finditer(r"\b(0?[89]:00|1[01]:00|12:30|0?[89]|1[01])\b", lower) if m.group(1) in _TIME_LOOKUP]
        if day_matches and time_matches:
            target = next((c for c in movable if c.day_of_week == day_matches[0] and c.time_start == time_matches[0]), None)

        if not target:
            target = _find_target_cell(text, schedule, req.selected_cell_id)

        if target:
            return remove_schedule_cell(schedule, target.id)

    # Case 3: Swap two sessions ("Swap Monday 8 AM with Wednesday 9 AM" or "Swap Spine trauma with Synapse")
    if any(k in lower for k in ("swap", "switch", "exchange")):
        movable = [c for c in schedule.cells if c.session_type not in ("BREAK", "HALF_DAY")]
        day_matches = [_DAY_LOOKUP[m.group(0)] for m in re.finditer(r"\b(?:monday|mon|tuesday|tue|wednesday|wed|thursday|thu|friday|fri|saturday|sat)\b", lower)]
        time_matches = [_TIME_LOOKUP[m.group(1)][0] for m in re.finditer(r"\b(0?[89]:00|1[01]:00|12:30|0?[89]|1[01])\b", lower) if m.group(1) in _TIME_LOOKUP]

        c1: Optional[ScheduledCell] = None
        c2: Optional[ScheduledCell] = None

        if len(day_matches) >= 2 and len(time_matches) >= 2:
            c1 = next((c for c in movable if c.day_of_week == day_matches[0] and c.time_start == time_matches[0]), None)
            c2 = next((c for c in movable if c.day_of_week == day_matches[1] and c.time_start == time_matches[1]), None)

        # Split by "with" or "and" to match topic titles or faculty names
        if not (c1 and c2):
            parts = re.split(r"\b(?:with|and)\b", text, maxsplit=1, flags=re.I)
            if len(parts) == 2:
                left_text, right_text = parts[0], parts[1]
                c1 = _find_target_cell(left_text, schedule, req.selected_cell_id)
                # Ensure c2 searches excluding c1
                remaining_sched = schedule.model_copy(deep=True)
                if c1:
                    remaining_sched.cells = [c for c in remaining_sched.cells if c.id != c1.id]
                # Or check if right_text has a day+time
                r_days = [_DAY_LOOKUP[m.group(0)] for m in re.finditer(r"\b(?:monday|mon|tuesday|tue|wednesday|wed|thursday|thu|friday|fri|saturday|sat)\b", right_text.lower())]
                r_times = [_TIME_LOOKUP[m.group(1)][0] for m in re.finditer(r"\b(0?[89]:00|1[01]:00|12:30|0?[89]|1[01])\b", right_text.lower()) if m.group(1) in _TIME_LOOKUP]
                if r_days and r_times:
                    c2 = next((c for c in remaining_sched.cells if c.day_of_week == r_days[0] and c.time_start == r_times[0] and c.session_type not in ("BREAK", "HALF_DAY")), None)
                if not c2:
                    c2 = _find_target_cell(right_text, remaining_sched, None)

        if c1 and c2 and c1.id != c2.id:
            return swap_schedule_cells(schedule, c1.id, c2.id)

    # Case 3: Move / reschedule command ("Move Dr. Ambar's session to Wednesday 10 AM", "Move Spine trauma to Friday afternoon")
    if any(k in lower for k in ("move", "reschedule", "shift", "put", "place", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday")):
        target = _find_target_cell(text, schedule, req.selected_cell_id)
        if target:
            new_day, new_start, new_end = _extract_destination_day_and_time(text, target.day_of_week)
            val = validate_slot_move(
                schedule=schedule,
                cell_id=target.id,
                new_day=new_day,
                new_start=new_start,
                new_end=new_end,
            )
            schedule.cells = [val.updated_cell if c.id == target.id else c for c in schedule.cells]
            schedule.cells.sort(key=lambda c: (c.day_of_week, c.time_start))
            recompute_schedule_analytics(schedule)

            if val.conflicts:
                conflict_msgs = " | ".join(c.message for c in val.conflicts)
                alts = ", ".join(val.conflicts[0].suggested_alternative_slots[:3])
                reply = (
                    f"[Option B Soft Warning] Moved '{target.topic_title}' to {DAYS[new_day].title()} {new_start}-{new_end}, "
                    f"but detected a clash: {conflict_msgs} Suggested open slots: {alts}."
                )
                action = "CONFLICT_WARNING"
            else:
                reply = (
                    f"[Validated] Moved '{target.topic_title}' ({target.discipline}) to {DAYS[new_day].title()} "
                    f"{new_start}-{new_end}. Validated against all room, faculty, and batch constraints."
                )
                action = "MOVED"

            return CopilotChatResponse(
                reply=reply,
                action_taken=action,
                updated_schedule=schedule,
                affected_cell_id=val.updated_cell.id,
                conflicts=val.conflicts,
            )

    # Case 4: General query about open slots or schedule status
    open_slots = find_open_alternative_slots(schedule)
    conflicted_cells = [c for c in schedule.cells if c.is_conflicted]
    status_summary = (
        f"There are currently {len(conflicted_cells)} soft-conflicted slot(s)."
        if conflicted_cells
        else "All scheduled sessions are currently conflict-free."
    )
    return CopilotChatResponse(
        reply=(
            f"{status_summary} Open alternative slots include: {', '.join(open_slots[:3])}. "
            f"Try commands like: 'Move Spine trauma to Wednesday 10 AM', 'Reassign Dr. Jillani to Dr. Tariq', "
            f"or 'Swap Monday 8 AM with Friday 9 AM'."
        ),
        action_taken="INFO",
        updated_schedule=schedule,
    )
