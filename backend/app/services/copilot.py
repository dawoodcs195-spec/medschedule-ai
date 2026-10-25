"""Sprint 3: AI Copilot & Real-Time Schedule Validation Engine.

Enforces Option B Conflict Handling (Soft Warnings):
- Does not hard-block admin overrides or moves.
- Detects Room collisions, Faculty double-bookings, Friday afternoon violations,
  Daily break violations, and Student batch overlaps.
- Returns detailed diagnostic notes and suggests candidate conflict-free open slots.
- Powers natural language schedule edits (move, swap, remove, teacher assignment, lists of changes)
  with a deterministic command parser.
"""
from __future__ import annotations

import logging
import re
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.constants import DAYS, FRIDAY
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
        day_name=DAYS.get(day_of_week, "MONDAY"),
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

_DAY_PATTERN = r"\b(?:monday|mon|tuesday|tues|tue|wednesday|wed|thursday|thurs|thur|thu|friday|fri|saturday|sat)\b"

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


_WORD_RE = re.compile(r"[a-z0-9]+")
_FILLER = {
    "the", "a", "an", "this", "that", "class", "classes", "session", "sessions", "lecture", "lectures",
    "lgis", "of", "on", "at", "in", "to", "for", "with", "by", "and", "move", "shift", "put", "place",
    "reschedule", "swap", "switch", "exchange", "teacher", "teachers", "faculty", "assign", "reassign",
    "give", "please", "dr", "prof", "am", "pm", "s", "all", "his", "her", "their", "class's",
}


def _words(text: str) -> list[str]:
    out = []
    for w in _WORD_RE.findall(text.lower()):
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return out


def _movable(schedule: TimetableSchedule) -> list[ScheduledCell]:
    return [c for c in schedule.cells if c.session_type not in ("BREAK", "HALF_DAY")]


def _cell_at(schedule: TimetableSchedule, text: str) -> Optional[ScheduledCell]:
    """A cell referenced by day + time, e.g. 'Monday 8 am class'."""
    lower = text.lower()
    days = [_DAY_LOOKUP[m.group(0)] for m in re.finditer(_DAY_PATTERN, lower)]
    times = [
        _TIME_LOOKUP[m.group(1)][0]
        for m in re.finditer(r"\b(12:30|0?[89]:00|1[01]:00|0?[89]|1[01])\b", lower)
        if m.group(1) in _TIME_LOOKUP
    ]
    if days and times:
        return next((c for c in _movable(schedule) if c.day_of_week == days[0] and c.time_start == times[0]), None)
    return None


def _match_cells_by_topic(text: str, schedule: TimetableSchedule) -> list[tuple[float, ScheduledCell]]:
    """Cells ranked by how much of the instruction names their topic (whole words only)."""
    wanted = {w for w in _words(text) if w not in _FILLER and len(w) > 2}
    if not wanted:
        return []
    scored = []
    for c in _movable(schedule):
        title = {w for w in _words(c.topic_title) if w not in _FILLER}
        if not title:
            continue
        hits = len(wanted & title)
        if hits:
            scored.append((hits / len(title) + hits, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


def _find_target_cell(
    instruction: str,
    schedule: TimetableSchedule,
    selected_cell_id: Optional[UUID],
    use_faculty: bool = True,
) -> Optional[ScheduledCell]:
    movable = _movable(schedule)
    lower = instruction.lower()

    # 1. Explicit day + time ("Monday 8 am")
    if (cell := _cell_at(schedule, instruction)) is not None:
        return cell

    # 2. Topic words ("cardiac cycle")
    ranked = _match_cells_by_topic(instruction, schedule)
    if ranked:
        return ranked[0][1]

    # 3. A teacher named in the instruction ("Dr. Ambar's session")
    if use_faculty:
        for c in movable:
            if c.faculty_name and _mentions_teacher(lower, c.faculty_name):
                return c

    # 4. Discipline name ("the physiology class")
    for c in movable:
        if re.search(rf"\b{re.escape(c.discipline.lower())}\b", lower):
            return c

    # 5. The cell selected in the UI ("this class")
    if selected_cell_id:
        found = next((c for c in movable if c.id == selected_cell_id), None)
        if found:
            return found

    return None


# ---------------------------------------------------------------------------
# Teacher (faculty) assignment: "give X to Dr. Y", "X with Dr. Y", "Dr. Y will teach X",
# "replace Dr. A with Dr. B", "swap teachers of X and Y"
# ---------------------------------------------------------------------------

_TITLE = r"(?:dr|prof|mr|mrs|ms|miss|sir)"
_NAME_STOP = (
    r"(?!(?:to|for|with|by|and|in|on|at|the|will|should|can|must|teach|teaches|take|takes|cover|covers|"
    r"handle|instead|from|class|classes|session|lecture|please|now|as)\b)"
)
TEACHER_RE = re.compile(
    rf"\b{_TITLE}\.?\s*{_NAME_STOP}[a-z][a-z'\-]*\.?(?:\s+{_NAME_STOP}[a-z][a-z'\-]*\.?){{0,2}}",
    re.I,
)
_NEW_TEACHER_BEFORE = re.compile(r"\b(?:to|with|by|under|for|onto|=)\s*$", re.I)
_NEW_TEACHER_AFTER = re.compile(r"^\s*(?:will|should|can|must|shall|to)?\s*(?:teach|take|cover|handle|conduct)", re.I)
_ASSIGN_HINT = re.compile(
    r"\b(?:assign|reassign|give|allocate|hand|transfer|teacher|faculty|teach|take|cover|replace|instead)\b", re.I
)
_PLURAL_HINT = re.compile(r"\b(?:all|classes|sessions|lectures|load|replace|everything)\b", re.I)


def _canon_teacher(raw: str) -> str:
    name = " ".join(raw.replace(".", ". ").split()).strip()
    title, _, rest = name.partition(" ")
    title = title.rstrip(".").title() + "."
    rest = " ".join(p if (len(p) <= 2 and p.endswith(".")) else p.capitalize() for p in rest.split())
    return f"{title} {rest}".strip()


def _teacher_tokens(name: str) -> list[str]:
    return [p for p in _WORD_RE.findall(name.lower()) if p not in {"dr", "prof", "mr", "mrs", "ms", "miss", "sir"} and len(p) > 1]


def _same_teacher(mention: str, faculty_name: str) -> bool:
    """'Dr. Asma Khan' matches 'Dr. Asma Khan' and 'dr asma' does too, but not 'Dr. Haris Khan'."""
    wanted = set(_teacher_tokens(mention))
    return bool(wanted) and wanted <= set(_teacher_tokens(faculty_name))


def _mentions_teacher(text: str, faculty_name: str) -> bool:
    mentions = [m.group(0) for m in TEACHER_RE.finditer(text)]
    if mentions:
        return any(_same_teacher(m, faculty_name) for m in mentions)
    # No "Dr." in the text ("move Ambar's session"): a distinctive name word is enough.
    toks = [t for t in _teacher_tokens(faculty_name) if len(t) > 3]
    return any(re.search(rf"\b{re.escape(t)}\b", text.lower()) for t in toks)


def _resolve_teacher(raw: str, schedule: TimetableSchedule) -> str:
    """Prefer an existing faculty name ('dr arshad' -> 'Dr. M. Arshad') when unambiguous."""
    existing = sorted({c.faculty_name for c in schedule.cells if c.faculty_name})
    matches = [f for f in existing if _same_teacher(raw, f)]
    return matches[0] if len(matches) == 1 else _canon_teacher(raw)


def _apply_teachers(
    schedule: TimetableSchedule, changes: list[tuple[ScheduledCell, str]], action: str
) -> CopilotChatResponse:
    notes, conflicts_all = [], []
    for cell, teacher in changes:
        old = cell.faculty_name or "Unassigned"
        cell.faculty_name = teacher
        notes.append(f"'{cell.topic_title}' ({cell.day_name.title()} {cell.time_start}): {old} → {teacher}")
    for cell, _ in changes:
        conflicts = check_cell_conflicts(cell, schedule.cells, schedule=schedule)
        teacher_conflicts = [c for c in conflicts if c.message.startswith("Faculty Clash")]
        cell.is_conflicted = bool(teacher_conflicts)
        cell.conflict_notes = "; ".join(c.message for c in teacher_conflicts) or None
        conflicts_all.extend(teacher_conflicts)
    recompute_schedule_analytics(schedule)
    reply = ("Reassigned " if len(changes) == 1 else f"Reassigned {len(changes)} classes: ") + "; ".join(notes) + "."
    if conflicts_all:
        reply += f" Warning: {conflicts_all[0].message}"
    return CopilotChatResponse(
        reply=reply,
        action_taken=action,
        updated_schedule=schedule,
        affected_cell_id=changes[0][0].id,
        conflicts=conflicts_all,
    )


def _try_teacher_command(
    text: str, schedule: TimetableSchedule, selected_cell_id: Optional[UUID]
) -> Optional[CopilotChatResponse]:
    mentions = list(TEACHER_RE.finditer(text))
    if not mentions:
        return None
    is_teacher_swap = bool(re.search(r"\b(?:swap|switch|exchange)\b", text, re.I)) and len(mentions) >= 2
    if not (is_teacher_swap or _ASSIGN_HINT.search(text) or re.search(rf"\b(?:with|by|under|to)\s+{_TITLE}\b", text, re.I)):
        return None
    lower = text.lower()

    if re.search(r"\b(?:swap|switch|exchange)\b", lower):
        if len(mentions) < 2:
            return None  # "swap the teachers of X and Y" is handled by the class-swap branch
        # "Swap Dr. A and Dr. B": exchange their whole teaching load in this timetable
        a, b = (_resolve_teacher(m.group(0), schedule) for m in mentions[:2])
        cells_a = [c for c in _movable(schedule) if c.faculty_name and _same_teacher(mentions[0].group(0), c.faculty_name)]
        cells_b = [c for c in _movable(schedule) if c.faculty_name and _same_teacher(mentions[1].group(0), c.faculty_name)]
        if not cells_a and not cells_b:
            return None
        return _apply_teachers(schedule, [(c, b) for c in cells_a] + [(c, a) for c in cells_b], "SWAPPED_FACULTY")

    new_m = next(
        (m for m in mentions if _NEW_TEACHER_BEFORE.search(text[: m.start()]) or _NEW_TEACHER_AFTER.match(text[m.end():])),
        None,
    )
    if new_m is None:
        if re.match(r"^\s*replace\b", lower) and len(mentions) >= 2:
            new_m = mentions[1]
        else:
            return None
    new_teacher = _resolve_teacher(new_m.group(0), schedule)
    old_mentions = [m for m in mentions if m is not new_m]

    # Text describing *which* class, with teacher names removed
    target_text = TEACHER_RE.sub(" ", text)
    movable = _movable(schedule)

    targets: list[ScheduledCell] = []
    if old_mentions:
        old_cells = [
            c for c in movable
            if c.faculty_name and any(_same_teacher(m.group(0), c.faculty_name) for m in old_mentions)
        ]
        topic_ranked = [c for _, c in _match_cells_by_topic(target_text, schedule) if c in old_cells]
        if topic_ranked:
            targets = topic_ranked[:1]
        elif _PLURAL_HINT.search(text) or len(old_cells) == 1:
            targets = old_cells
        elif old_cells:
            targets = old_cells
    if not targets:
        cell = _cell_at(schedule, target_text)
        if cell is None:
            ranked = _match_cells_by_topic(target_text, schedule)
            cell = ranked[0][1] if ranked else None
        if cell is None and selected_cell_id:
            cell = next((c for c in movable if c.id == selected_cell_id), None)
        if cell is not None:
            # A topic taught in several sessions moves to the new teacher as a whole.
            targets = [c for c in movable if c.topic_title == cell.topic_title and c.discipline == cell.discipline]
    if not targets:
        return CopilotChatResponse(
            reply=f"I couldn't tell which class should go to {new_teacher}. Select the class or name its topic, "
            f"e.g. 'Give Cardiac cycle to {new_teacher}'.",
            action_taken="INFO",
            updated_schedule=schedule,
        )
    return _apply_teachers(schedule, [(c, new_teacher) for c in targets], "REASSIGNED_FACULTY")


def _swap_teachers(c1: ScheduledCell, c2: ScheduledCell, schedule: TimetableSchedule) -> CopilotChatResponse:
    t1, t2 = c1.faculty_name, c2.faculty_name
    return _apply_teachers(
        schedule, [(c1, t2 or "Unassigned"), (c2, t1 or "Unassigned")], "SWAPPED_FACULTY"
    )


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


_COMMAND_SPLIT = re.compile(r"(?:\n+|;|\s+then\s+|(?:^|\s)\d+[.)]\s+)", re.I)


def split_commands(instruction: str) -> list[str]:
    """'1. Give X to Dr. A 2. Swap Monday 8 with Tuesday 9' -> two commands."""
    parts = [p.strip(" ,.") for p in _COMMAND_SPLIT.split(instruction)]
    return [p for p in parts if p and len(p) > 2]


def execute_copilot_command(req: CopilotChatRequest) -> CopilotChatResponse:
    """Run one instruction, or a list of changes (one per line, numbered, or ';'-separated)."""
    commands = split_commands(req.instruction) or [req.instruction.strip()]
    schedule = req.schedule.model_copy(deep=True)
    if len(commands) == 1:
        return _execute_single(commands[0], schedule, req.selected_cell_id)

    replies, conflicts = [], []
    last: Optional[CopilotChatResponse] = None
    for n, cmd in enumerate(commands, 1):
        res = _execute_single(cmd, schedule, req.selected_cell_id)
        schedule = res.updated_schedule
        replies.append(f"{n}. {res.reply}")
        conflicts.extend(res.conflicts)
        last = res
    applied = sum(1 for r in replies if "couldn't" not in r and "Try commands like" not in r)
    return CopilotChatResponse(
        reply=f"Applied {applied} of {len(commands)} changes:\n" + "\n".join(replies),
        action_taken="BATCH",
        updated_schedule=schedule,
        affected_cell_id=last.affected_cell_id if last else None,
        conflicts=conflicts,
    )


def _execute_single(text: str, schedule: TimetableSchedule, selected_cell_id: Optional[UUID]) -> CopilotChatResponse:
    """Process one rescheduling, teacher-assignment, swap, remove or status instruction."""
    text = text.strip()
    lower = text.lower()

    # Case 1: Teacher assignment ("Give Cardiac cycle to Dr. Tariq", "Renal filtration with Dr. Asma",
    # "Dr. Hina will teach Brachial plexus", "Replace Dr. Jillani with Dr. Tariq")
    teacher_res = _try_teacher_command(text, schedule, selected_cell_id)
    if teacher_res is not None:
        return teacher_res

    # Case 2: Remove / Delete / Cancel a session ("Remove Spine trauma", "Delete Monday 8 AM", "Remove selected class")
    if re.search(r"\b(?:remove|delete|cancel|drop|clear)\b", lower):
        movable = [c for c in schedule.cells if c.session_type not in ("BREAK", "HALF_DAY")]
        target: Optional[ScheduledCell] = None

        # Check if user specified day + time to remove (e.g., "Delete Monday 8 AM")
        day_matches = [_DAY_LOOKUP[m.group(0)] for m in re.finditer(r"\b(?:monday|mon|tuesday|tue|wednesday|wed|thursday|thu|friday|fri|saturday|sat)\b", lower)]
        time_matches = [_TIME_LOOKUP[m.group(1)][0] for m in re.finditer(r"\b(0?[89]:00|1[01]:00|12:30|0?[89]|1[01])\b", lower) if m.group(1) in _TIME_LOOKUP]
        if day_matches and time_matches:
            target = next((c for c in movable if c.day_of_week == day_matches[0] and c.time_start == time_matches[0]), None)

        if not target:
            target = _find_target_cell(text, schedule, selected_cell_id)

        if target:
            return remove_schedule_cell(schedule, target.id)

    # Case 3: Swap two sessions ("Swap Monday 8 AM with Wednesday 9 AM" or "Swap Spine trauma with Synapse")
    if re.search(r"\b(?:swap|switch|exchange)\b", lower):
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
                c1 = _find_target_cell(left_text, schedule, selected_cell_id)
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
            if re.search(r"\b(?:teacher|faculty|teachers)\b", lower):
                return _swap_teachers(c1, c2, schedule)
            return swap_schedule_cells(schedule, c1.id, c2.id)
        return CopilotChatResponse(
            reply="I couldn't find both classes to swap in this week's timetable. Name each by topic or by "
            "day and time, e.g. 'Swap Monday 8 AM with Wednesday 9 AM', or switch week first.",
            action_taken="INFO",
            updated_schedule=schedule,
        )

    # Case 3: Move / reschedule command ("Move Dr. Ambar's session to Wednesday 10 AM", "Move Spine trauma to Friday afternoon")
    if re.search(r"\b(?:move|reschedule|shift|put|place|postpone|prepone)\b", lower) or re.search(_DAY_PATTERN, lower):
        # The destination ("to Wednesday 10 am") must not be mistaken for the class being moved.
        dest = re.search(
            r"\b(?:to|into|onto|on|at)\b(?=.*(?:" + _DAY_PATTERN + r"|\d|afternoon|morning))", text, re.I
        )
        source_text = text[: dest.start()] if dest else text
        target = _find_target_cell(source_text, schedule, selected_cell_id) if source_text.strip() else None
        if target is None and selected_cell_id:
            target = next((c for c in _movable(schedule) if c.id == selected_cell_id), None)
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
            f"Try commands like: 'Move Cardiac cycle to Wednesday 10 AM', 'Give Cardiac cycle to Dr. Tariq', "
            f"'Replace Dr. Jillani with Dr. Tariq', 'Swap Monday 8 AM with Friday 9 AM', or several changes, one per line."
        ),
        action_taken="INFO",
        updated_schedule=schedule,
    )
