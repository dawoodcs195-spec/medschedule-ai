"""Sprint 2: Google OR-Tools CP-SAT Scheduling Engine.

Enforces all non-negotiable institutional constraints from AGENTS.md §4:
1. 6-Day Academic Week (Monday to Saturday).
2. Operating hours: 08:00 - 14:00 (Mon-Thu & Sat), Break 12:00 - 12:30.
3. Friday Half-Day: 08:00 - 12:00 only (strictly no classes after 12:00).
4. Cohort size: 100 students.
   - LGIS: 1-hour sessions with all 100 students in 1 Lecture Hall (8 Lecture Halls available).
   - Practicals & SGDs: 4 Batches (A, B, C, D) of 25 students each.
5. Venue & Lab rules (Solved via CP-SAT Boolean variables):
   - Practicals: During any scheduled 2-hour Practical block, Batches A, B, C, and D
     simultaneously occupy Histology Lab, Physiology Lab, Biochemistry Lab, and Skill Lab
     with zero collisions (`AddExactlyOne`), and each batch completes all 4 stations across the week.
   - SGDs: Room-unconstrained rotations across Anatomy, Physiology, Biochemistry, SDL.
6. Horizontal and Vertical alignment optimization across multi-week modules.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Optional
from uuid import UUID, uuid4

from ortools.sat.python import cp_model
from pydantic import BaseModel, Field

from app.core.constants import (
    BATCHES, CLINICAL_DISCIPLINES, DAYS, FRIDAY, PRACTICAL_VENUES, SGD_STATIONS,
)
from app.models.schemas import LegendEntry, ParsedTopic
from app.services.integrator import ProposedLink

logger = logging.getLogger(__name__)


class BatchStationAssignment(BaseModel):
    batch: str  # 'Batch A', 'Batch B', etc.
    station: str  # 'Histo-P1 (Neurons)', 'Physio-P1 (Temp Reg)', etc.
    faculty: Optional[str] = None
    venue: Optional[str] = None


class ScheduledCell(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    day_of_week: int  # 1 = Monday ... 6 = Saturday
    day_name: str
    time_start: str
    time_end: str
    session_type: str  # LGIS, PRACTICAL, SGD, DSL, SDL, BREAK, HALF_DAY
    discipline: str
    category: str  # ANATOMY, PHYSIOLOGY, BIOCHEMISTRY, CLINICAL, INSTITUTIONAL
    topic_title: str
    faculty_name: Optional[str] = None
    venue_name: Optional[str] = None
    student_batch_mask: str = "ALL"  # ALL or specific batch
    batch_assignments: list[BatchStationAssignment] = []
    is_conflicted: bool = False
    conflict_notes: Optional[str] = None


class TimetableSchedule(BaseModel):
    module_code: str
    module_title: str
    academic_year: int
    week_number: int = 1
    total_weeks: int = 1
    session: str = "2026-2027"
    cells: list[ScheduledCell]
    solver_status: str
    total_contact_hours: float
    analytics: dict[str, Any] = {}


def _resolve_practical_station_label(venue: str, week_number: int, topics: list[ParsedTopic]) -> str:
    prefix = venue.split()[0]  # Histology, Physiology, Biochemistry, Skill
    short_map = {
        "Histology": "Histo",
        "Physiology": "Physio",
        "Biochemistry": "Biochem",
        "Skill": "Skill Lab",
    }
    short = short_map.get(prefix, prefix)
    if short == "Skill Lab":
        matches = [t for t in topics if t.session_type.value == "SKILL_LAB" or "skill" in (t.practical_code or "").lower()]
        if matches:
            chosen = matches[(week_number - 1) % len(matches)]
            return f"Skill Lab ({chosen.topic_title[:28]})"
        return "Skill Lab"

    code_target = f"P{week_number}"
    disc_matches = [
        t for t in topics
        if t.session_type.value == "PRACTICAL" and t.discipline.lower().startswith(prefix[:4].lower())
    ]
    exact = next((t for t in disc_matches if code_target in (t.practical_code or "")), None)
    chosen = exact or (disc_matches[(week_number - 1) % len(disc_matches)] if disc_matches else None)
    if chosen:
        return f"{short}-P{week_number} ({chosen.topic_title[:24]})"
    return f"{short}-P{week_number}"


def _resolve_sgd_station_label(station: str, week_number: int, topics: list[ParsedTopic]) -> str:
    if station == "SDL":
        return "SDL (Digital Library)"
    sgd_matches = [
        t for t in topics
        if t.session_type.value == "SGD" and (
            t.discipline.lower().startswith(station[:4].lower())
            or (station == "Anatomy" and t.category == "ANATOMY")
        )
    ]
    if sgd_matches:
        chosen = sgd_matches[(week_number - 1) % len(sgd_matches)]
        return f"{station} SGD ({chosen.topic_title[:22]})"
    return f"{station} SGD"


def recompute_schedule_analytics(schedule: TimetableSchedule) -> TimetableSchedule:
    """Recalculate contact hours, faculty workload, and slot distribution."""
    contact_hours_by_discipline: dict[str, float] = {}
    faculty_hours: dict[str, float] = {}
    time_bracket_counts: dict[str, int] = {}

    for c in schedule.cells:
        if c.session_type in ("BREAK", "HALF_DAY"):
            continue
        dur = 1.0 if c.session_type == "LGIS" else 1.5 if c.time_start == "12:30" else 2.0
        contact_hours_by_discipline[c.discipline] = round(
            contact_hours_by_discipline.get(c.discipline, 0.0) + dur, 1
        )
        if c.faculty_name:
            faculty_hours[c.faculty_name] = round(
                faculty_hours.get(c.faculty_name, 0.0) + dur, 1
            )
        bracket = f"{c.time_start} - {c.time_end}"
        time_bracket_counts[bracket] = time_bracket_counts.get(bracket, 0) + 1

    total_hours = round(sum(contact_hours_by_discipline.values()), 1)
    schedule.total_contact_hours = total_hours
    schedule.analytics = {
        "contact_hours_by_discipline": contact_hours_by_discipline,
        "faculty_hours": faculty_hours,
        "time_bracket_distribution": time_bracket_counts,
    }
    return schedule


def solve_schedule(
    topics: list[ParsedTopic],
    approved_links: list[ProposedLink] = [],
    module_code: str = "MODULE-07",
    module_title: str = "NEUROSCIENCES BLOCK-IV",
    academic_year: int = 2,
    week_number: int = 1,
    time_limit_seconds: float = 8.0,
) -> TimetableSchedule:
    """Run Google OR-Tools CP-SAT solver to schedule a modular curriculum week."""
    model = cp_model.CpModel()

    # Days: 1=Mon, 2=Tue, 3=Wed, 4=Thu, 5=Fri, 6=Sat
    days = [1, 2, 3, 4, 5, 6]

    slot_times = {
        0: ("08:00", "09:00"),
        1: ("09:00", "10:00"),
        2: ("10:00", "11:00"),
        3: ("11:00", "12:00"),
        4: ("12:30", "14:00"),
    }

    # Separate lecture/whole-cohort topics from rotation topics
    lgis_all = [
        t for t in topics
        if t.session_type.value in ("LGIS", "LECTURE", "DSL", "PAL", "MENTOR_MENTEE", "RIPPLE", "ISL", "SDL")
    ]
    if not lgis_all:
        lgis_all = list(topics)

    available_lgis_positions = [
        (1, 0), (1, 1), (1, 2), (1, 3),
        (2, 0), (2, 1),
        (3, 0), (3, 1),
        (4, 0), (4, 1),
        (5, 0), (5, 1), (5, 2), (5, 3),
        (6, 0), (6, 1),
    ]
    num_slots = len(available_lgis_positions)  # 16 lecture slots per week
    total_weeks = max(1, min(8, math.ceil(len(lgis_all) / num_slots)))
    clamped_week = max(1, min(week_number, total_weeks))

    start_idx = (clamped_week - 1) * num_slots
    lgis_topics = lgis_all[start_idx : start_idx + num_slots]
    if not lgis_topics:
        lgis_topics = lgis_all[:num_slots]

    scheduled_cells: list[ScheduledCell] = []

    # -----------------------------------------------------------------------
    # 1. Fixed Breaks (Mon-Thu & Sat 12:00-12:30) & Friday Half-Day (12:00-14:00)
    # -----------------------------------------------------------------------
    for d in days:
        day_name = DAYS[d]
        if d == FRIDAY:
            scheduled_cells.append(
                ScheduledCell(
                    day_of_week=d,
                    day_name=day_name,
                    time_start="12:00",
                    time_end="14:00",
                    session_type="HALF_DAY",
                    discipline="Institutional",
                    category="INSTITUTIONAL",
                    topic_title="HALF DAY",
                )
            )
        else:
            scheduled_cells.append(
                ScheduledCell(
                    day_of_week=d,
                    day_name=day_name,
                    time_start="12:00",
                    time_end="12:30",
                    session_type="BREAK",
                    discipline="Institutional",
                    category="INSTITUTIONAL",
                    topic_title="BREAK",
                )
            )

    # -----------------------------------------------------------------------
    # 2. CP-SAT 4-Batch Simultaneous Lab Rotation Model (x[b, l, p])
    #    - 4 Practical blocks across the week (p in 0..3):
    #      Mon 12:30-14:00, Tue 10:00-12:00, Thu 10:00-12:00, Sat 10:00-12:00 (Zero Friday afternoons)
    #    - 4 Batches (Batch A, B, C, D) of 25 students
    #    - 4 Venues (Histology Lab, Physiology Lab, Biochemistry Lab, Skill Lab)
    # -----------------------------------------------------------------------
    practical_days_and_slots = [
        (1, "12:30", "14:00"),  # Monday afternoon
        (2, "10:00", "12:00"),  # Tuesday morning (2-hr block)
        (4, "10:00", "12:00"),  # Thursday morning (2-hr block)
        (6, "10:00", "12:00"),  # Saturday morning (2-hr block)
    ]
    num_p_blocks = len(practical_days_and_slots)
    num_batches = len(BATCHES)
    num_venues = len(PRACTICAL_VENUES)

    # Decision variable: x_lab[b, v, p] == 1 iff Batch b occupies Lab Venue v during Practical Block p
    x_lab: dict[tuple[int, int, int], cp_model.IntVar] = {}
    for b in range(num_batches):
        for v in range(num_venues):
            for p in range(num_p_blocks):
                x_lab[b, v, p] = model.NewBoolVar(f"x_lab_b{b}_v{v}_p{p}")

    # Hard Constraint 2a: Simultaneous 4-Batch Venue Occupancy (Zero Room Collisions)
    # During every Practical block p, each of the 4 venues hosts exactly 1 batch
    for p in range(num_p_blocks):
        for v in range(num_venues):
            model.AddExactlyOne(x_lab[b, v, p] for b in range(num_batches))

    # Hard Constraint 2b: Student Batch Non-Overlap
    # During every Practical block p, each batch is assigned to exactly 1 venue
    for p in range(num_p_blocks):
        for b in range(num_batches):
            model.AddExactlyOne(x_lab[b, v, p] for v in range(num_venues))

    # Hard Constraint 2c: Complete Weekly Station Rotation (Latin Square)
    # Across the 4 weekly practical sessions, every batch visits every station (Histo, Physio, Biochem, Skill Lab) exactly once
    for b in range(num_batches):
        for v in range(num_venues):
            model.AddExactlyOne(x_lab[b, v, p] for p in range(num_p_blocks))

    # Symmetry breaking on block 0 so Batch A->Histo, B->Physio, C->Biochem, D->Skill Lab on Monday
    for b in range(num_batches):
        model.Add(x_lab[b, b, 0] == 1)

    # -----------------------------------------------------------------------
    # 3. CP-SAT LGIS Lecture Slot Assignment & Horizontal/Vertical Affinity
    # -----------------------------------------------------------------------
    num_topics = min(len(lgis_topics), num_slots)

    assign: dict[tuple[int, int], cp_model.IntVar] = {}
    for t_idx in range(num_topics):
        for pos_idx in range(num_slots):
            assign[t_idx, pos_idx] = model.NewBoolVar(f"assign_{t_idx}_{pos_idx}")

    # Each scheduled topic assigned to exactly 1 position
    for t_idx in range(num_topics):
        model.AddExactlyOne(assign[t_idx, pos_idx] for pos_idx in range(num_slots))

    # Each position gets at most 1 topic
    for pos_idx in range(num_slots):
        model.AddAtMostOne(assign[t_idx, pos_idx] for t_idx in range(num_topics))

    # Soft Constraint / Objective: Maximize Horizontal & Vertical Integration Co-Scheduling on the same day
    affinity_bonus = []
    for link in approved_links:
        if not link.is_approved:
            continue
        src = next((i for i, t in enumerate(lgis_topics[:num_topics]) if t.topic_title == link.source_topic), None)
        tgt = next((i for i, t in enumerate(lgis_topics[:num_topics]) if t.topic_title == link.target_topic), None)
        if src is not None and tgt is not None and src != tgt:
            for p1, (d1, s1) in enumerate(available_lgis_positions):
                for p2, (d2, s2) in enumerate(available_lgis_positions):
                    if d1 == d2 and p1 < p2:
                        both = model.NewBoolVar(f"affinity_{src}_{tgt}_{p1}_{p2}")
                        model.AddBoolAnd([assign[src, p1], assign[tgt, p2]]).OnlyEnforceIf(both)
                        affinity_bonus.append(both * int(link.similarity_score * 25))

    if affinity_bonus:
        model.Maximize(sum(affinity_bonus))

    # -----------------------------------------------------------------------
    # 4. Execute CP-SAT Solver
    # -----------------------------------------------------------------------
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = 1
    status = solver.Solve(model)
    status_name = solver.StatusName(status)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise ValueError(f"CP-SAT solver could not find a feasible schedule: {status_name}")

    # Extract CP-SAT solved 4-Batch Practical Rotations
    for p_idx, (d, t_start, t_end) in enumerate(practical_days_and_slots):
        day_name = DAYS[d]
        batch_assignments: list[BatchStationAssignment] = []

        for b_idx, batch_code in enumerate(BATCHES):
            assigned_venue_idx = next(
                v for v in range(num_venues) if solver.Value(x_lab[b_idx, v, p_idx]) == 1
            )
            venue = PRACTICAL_VENUES[assigned_venue_idx]
            station_name = _resolve_practical_station_label(venue, clamped_week, topics)
            batch_assignments.append(
                BatchStationAssignment(
                    batch=f"Batch {batch_code}",
                    station=station_name,
                    venue=venue,
                )
            )

        scheduled_cells.append(
            ScheduledCell(
                day_of_week=d,
                day_name=day_name,
                time_start=t_start,
                time_end=t_end,
                session_type="PRACTICAL",
                discipline="Multi-Disciplinary",
                category="INSTITUTIONAL",
                topic_title=f"Practical Rotation (Week-{clamped_week:02d})",
                venue_name="Histo / Physio / Biochem / Skill Labs",
                student_batch_mask="ALL",
                batch_assignments=batch_assignments,
            )
        )

    # -----------------------------------------------------------------------
    # 5. Build Room-Unconstrained SGD Rotations (Anatomy, Physiology, Biochem, SDL)
    # -----------------------------------------------------------------------
    sgd_days_and_slots = [
        (2, "12:30", "14:00"),  # Tuesday afternoon
        (3, "10:00", "12:00"),  # Wednesday morning
        (3, "12:30", "14:00"),  # Wednesday afternoon
        (4, "12:30", "14:00"),  # Thursday afternoon
        (6, "12:30", "14:00"),  # Saturday afternoon
    ]

    sgd_permutations = [
        [0, 1, 2, 3],  # Anat, Physio, Bio, SDL
        [3, 0, 1, 2],  # SDL, Anat, Physio, Bio
        [1, 2, 3, 0],  # Physio, Bio, SDL, Anat
        [2, 3, 0, 1],  # Bio, SDL, Anat, Physio
        [1, 2, 3, 0],  # Physio, Bio, SDL, Anat
    ]

    for s_idx, (d, t_start, t_end) in enumerate(sgd_days_and_slots):
        day_name = DAYS[d]
        perm = sgd_permutations[s_idx % len(sgd_permutations)]
        batch_assignments = []
        for b_idx, batch_code in enumerate(BATCHES):
            station = SGD_STATIONS[perm[b_idx]]
            station_label = _resolve_sgd_station_label(station, clamped_week, topics)
            batch_assignments.append(
                BatchStationAssignment(
                    batch=f"Batch {batch_code}",
                    station=station_label,
                    venue=None,  # Room-unconstrained per AGENTS.md §4.3
                )
            )

        scheduled_cells.append(
            ScheduledCell(
                day_of_week=d,
                day_name=day_name,
                time_start=t_start,
                time_end=t_end,
                session_type="SGD",
                discipline="Multi-Disciplinary",
                category="INSTITUTIONAL",
                topic_title=f"SGD & SDL Rotation (Week-{clamped_week:02d})",
                venue_name="Departmental SGD (Room-Unconstrained)",
                student_batch_mask="ALL",
                batch_assignments=batch_assignments,
            )
        )

    # Extract CP-SAT solved LGIS Lecture Slots (100 students in 1 of 8 Lecture Halls)
    lecture_hall_name = f"Lecture Hall {((academic_year - 1) % 8) + 1}"
    for pos_idx, (d, s_num) in enumerate(available_lgis_positions):
        day_name = DAYS[d]
        t_start, t_end = slot_times[s_num]

        assigned_topic = None
        for t_idx in range(num_topics):
            if solver.Value(assign[t_idx, pos_idx]) == 1:
                assigned_topic = lgis_topics[t_idx]
                break

        if assigned_topic is not None:
            scheduled_cells.append(
                ScheduledCell(
                    day_of_week=d,
                    day_name=day_name,
                    time_start=t_start,
                    time_end=t_end,
                    session_type=assigned_topic.session_type.value,
                    discipline=assigned_topic.discipline,
                    category=assigned_topic.category,
                    topic_title=assigned_topic.topic_title,
                    faculty_name=assigned_topic.faculty_name,
                    venue_name=lecture_hall_name,
                    student_batch_mask="ALL",
                )
            )

    scheduled_cells.sort(key=lambda c: (c.day_of_week, c.time_start))

    sched = TimetableSchedule(
        module_code=module_code,
        module_title=module_title,
        academic_year=academic_year,
        week_number=clamped_week,
        total_weeks=total_weeks,
        session="2026-2027",
        cells=scheduled_cells,
        solver_status=status_name,
        total_contact_hours=0.0,
    )
    return recompute_schedule_analytics(sched)


def build_original_schedule(
    topics: list[ParsedTopic],
    module_code: str = "MODULE-07",
    module_title: str = "NEUROSCIENCES BLOCK-IV",
    academic_year: int = 2,
    week_number: int = 1,
) -> TimetableSchedule:
    """Reconstruct the original uploaded ('Old') timetable for the given week without AI reordering.

    - If topics came from a .docx/.xlsx table with explicit `original_day` and `original_start`,
      places them in their exact original uploaded slots for `week_number`.
    - If topics came from a pasted list without grid coordinates, places them in their exact
      uploaded sequential order across the week.
    """
    all_lgis = [
        t for t in topics if t.session_type.value not in ("PRACTICAL", "SKILL_LAB")
    ]
    max_lgis_per_week = 16
    total_weeks = max(1, math.ceil(len(all_lgis) / max_lgis_per_week)) if all_lgis else 1
    max_orig_week = max((t.original_week or 1 for t in topics), default=1)
    total_weeks = max(total_weeks, max_orig_week)
    clamped_week = max(1, min(week_number, total_weeks))

    scheduled_cells: list[ScheduledCell] = []
    occupied_slots: set[tuple[int, str]] = set()
    lecture_hall_name = f"Lecture Hall {((academic_year - 1) % 8) + 1}"

    # 1. Fixed Institutional Blocks: Daily Break (Mon-Thu & Sat 12:00-12:30) & Friday Half-Day
    for d, day_name in DAYS.items():
        if d == FRIDAY:
            scheduled_cells.append(
                ScheduledCell(
                    day_of_week=d,
                    day_name=day_name,
                    time_start="12:00",
                    time_end="14:00",
                    session_type="HALF_DAY",
                    discipline="Institutional",
                    category="INSTITUTIONAL",
                    topic_title="HALF DAY",
                    student_batch_mask="ALL",
                )
            )
        else:
            scheduled_cells.append(
                ScheduledCell(
                    day_of_week=d,
                    day_name=day_name,
                    time_start="12:00",
                    time_end="12:30",
                    session_type="BREAK",
                    discipline="Institutional",
                    category="INSTITUTIONAL",
                    topic_title="BREAK",
                    student_batch_mask="ALL",
                )
            )

    # 2. Check if topics have explicit table coordinates for this week
    week_coord_topics = [
        t
        for t in all_lgis
        if t.original_day is not None
        and t.original_start is not None
        and (t.original_week == clamped_week or (t.original_week is None and clamped_week == 1))
    ]

    if week_coord_topics:
        for t in week_coord_topics:
            d = t.original_day or 1
            s_time = t.original_start or "08:00"
            e_time = t.original_end or "09:00"
            occupied_slots.add((d, s_time))
            if s_time == "10:00" and e_time == "12:00":
                occupied_slots.add((d, "11:00"))
            scheduled_cells.append(
                ScheduledCell(
                    day_of_week=d,
                    day_name=DAYS.get(d, "MONDAY"),
                    time_start=s_time,
                    time_end=e_time,
                    session_type=t.session_type.value,
                    discipline=t.discipline,
                    category=t.category,
                    topic_title=t.topic_title,
                    faculty_name=t.faculty_name,
                    venue_name=lecture_hall_name,
                    student_batch_mask="ALL",
                )
            )
    else:
        # Sequential layout in exact uploaded order (un-integrated)
        start_idx = (clamped_week - 1) * max_lgis_per_week
        week_slice = all_lgis[start_idx : start_idx + max_lgis_per_week]
        if not week_slice and all_lgis:
            week_slice = all_lgis[:max_lgis_per_week]

        available_positions = [
            (1, "08:00", "09:00"), (1, "09:00", "10:00"), (1, "10:00", "11:00"), (1, "11:00", "12:00"),
            (2, "08:00", "09:00"), (2, "09:00", "10:00"),
            (3, "08:00", "09:00"), (3, "09:00", "10:00"),
            (4, "08:00", "09:00"), (4, "09:00", "10:00"),
            (5, "08:00", "09:00"), (5, "09:00", "10:00"), (5, "10:00", "11:00"), (5, "11:00", "12:00"),
            (6, "08:00", "09:00"), (6, "09:00", "10:00"),
        ]
        for idx, t in enumerate(week_slice):
            if idx >= len(available_positions):
                break
            d, s_time, e_time = available_positions[idx]
            occupied_slots.add((d, s_time))
            scheduled_cells.append(
                ScheduledCell(
                    day_of_week=d,
                    day_name=DAYS[d],
                    time_start=s_time,
                    time_end=e_time,
                    session_type=t.session_type.value,
                    discipline=t.discipline,
                    category=t.category,
                    topic_title=t.topic_title,
                    faculty_name=t.faculty_name,
                    venue_name=lecture_hall_name,
                    student_batch_mask="ALL",
                )
            )

    # 3. Fill standard Practical & SGD rotation blocks on unoccupied afternoon/late-morning slots
    practical_days_and_slots = [
        (1, "12:30", "14:00"),
        (2, "10:00", "12:00"),
        (4, "10:00", "12:00"),
        (6, "10:00", "12:00"),
    ]
    latin_square = [
        [0, 1, 2, 3],
        [3, 0, 1, 2],
        [2, 3, 0, 1],
        [1, 2, 3, 0],
    ]
    for p_idx, (d, t_start, t_end) in enumerate(practical_days_and_slots):
        if (d, t_start) in occupied_slots:
            continue
        batch_assignments = []
        for b_idx, batch_code in enumerate(BATCHES):
            venue = PRACTICAL_VENUES[latin_square[p_idx][b_idx]]
            station_label = _resolve_practical_station_label(venue, clamped_week, topics)
            batch_assignments.append(
                BatchStationAssignment(batch=f"Batch {batch_code}", station=station_label, venue=venue)
            )
        scheduled_cells.append(
            ScheduledCell(
                day_of_week=d,
                day_name=DAYS[d],
                time_start=t_start,
                time_end=t_end,
                session_type="PRACTICAL",
                discipline="Multi-Disciplinary",
                category="INSTITUTIONAL",
                topic_title=f"Practical Rotation (Week-{clamped_week:02d})",
                venue_name="Histo / Physio / Biochem / Skill Labs",
                student_batch_mask="ALL",
                batch_assignments=batch_assignments,
            )
        )

    sgd_days_and_slots = [
        (2, "12:30", "14:00"),
        (3, "10:00", "12:00"),
        (3, "12:30", "14:00"),
        (4, "12:30", "14:00"),
        (6, "12:30", "14:00"),
    ]
    sgd_permutations = [
        [0, 1, 2, 3],
        [3, 0, 1, 2],
        [1, 2, 3, 0],
        [2, 3, 0, 1],
        [1, 2, 3, 0],
    ]
    for s_idx, (d, t_start, t_end) in enumerate(sgd_days_and_slots):
        if (d, t_start) in occupied_slots:
            continue
        perm = sgd_permutations[s_idx % len(sgd_permutations)]
        batch_assignments = []
        for b_idx, batch_code in enumerate(BATCHES):
            station = SGD_STATIONS[perm[b_idx]]
            station_label = _resolve_sgd_station_label(station, clamped_week, topics)
            batch_assignments.append(
                BatchStationAssignment(batch=f"Batch {batch_code}", station=station_label, venue=None)
            )
        scheduled_cells.append(
            ScheduledCell(
                day_of_week=d,
                day_name=DAYS[d],
                time_start=t_start,
                time_end=t_end,
                session_type="SGD",
                discipline="Multi-Disciplinary",
                category="INSTITUTIONAL",
                topic_title=f"SGD & SDL Rotation (Week-{clamped_week:02d})",
                venue_name="Departmental SGD (Room-Unconstrained)",
                student_batch_mask="ALL",
                batch_assignments=batch_assignments,
            )
        )

    scheduled_cells.sort(key=lambda c: (c.day_of_week, c.time_start))
    sched = TimetableSchedule(
        module_code=module_code,
        module_title=module_title,
        academic_year=academic_year,
        week_number=clamped_week,
        total_weeks=total_weeks,
        session="2026-2027",
        cells=scheduled_cells,
        solver_status="UPLOADED_ORIGINAL",
        total_contact_hours=0.0,
    )
    return recompute_schedule_analytics(sched)
