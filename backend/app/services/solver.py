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
6. Curriculum integration (see :func:`plan_integrated_weeks`):
   - Approved links inside a class are grouped (union-find) and each group is packed into the
     same teaching week, ordered structure -> function -> disease -> management
     (Anatomy, Histology, Physiology, Biochemistry, Pathology, ... Medicine, Surgery, specialties).
   - Within a week, CP-SAT minimises the day gap between linked lectures and penalises any
     linked pair taught out of logical order. Vertical links to other years are annotated.
7. Multi-class runs (:func:`solve_all_cohorts`) avoid double-booking a teacher across classes.
"""
from __future__ import annotations

import logging
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID, uuid4

from ortools.sat.python import cp_model
from pydantic import BaseModel, Field

from app.core.constants import (
    BASIC_SCIENCES, BATCHES, DAYS, FRIDAY, LECTURE_HALL_COUNT, PRACTICAL_VENUES, SGD_STATIONS,
    cohort_key, cohort_label, sequence_rank,
)
from app.models.schemas import ParsedTopic
from app.services.integrator import ProposedLink, topic_cohort
from app.services.semantic import BROAD_CONCEPTS

logger = logging.getLogger(__name__)

WHOLE_CLASS_TYPES = {"LGIS", "LECTURE", "DSL", "PAL", "MENTOR_MENTEE", "RIPPLE", "ISL", "SDL"}
ROTATION_TYPES = {"PRACTICAL", "SGD", "SKILL_LAB"}

SLOT_TIMES = {
    0: ("08:00", "09:00"),
    1: ("09:00", "10:00"),
    2: ("10:00", "11:00"),
    3: ("11:00", "12:00"),
    4: ("12:30", "14:00"),
}
# Lecture positions (day, slot) left free by the practical/SGD rotation blocks (basic-science years).
ROTATION_WEEK_LECTURE_POSITIONS = [
    (1, 0), (1, 1), (1, 2), (1, 3),
    (2, 0), (2, 1),
    (3, 0), (3, 1),
    (4, 0), (4, 1),
    (5, 0), (5, 1), (5, 2), (5, 3),
    (6, 0), (6, 1),
]
# Clinical years without lab rotations: every morning slot; afternoons stay free for wards.
CLINICAL_WEEK_LECTURE_POSITIONS = [(d, s) for d in range(1, 7) for s in range(4)]

PRACTICAL_BLOCKS = [
    (1, "12:30", "14:00"),  # Monday afternoon
    (2, "10:00", "12:00"),  # Tuesday morning (2-hr block)
    (4, "10:00", "12:00"),  # Thursday morning (2-hr block)
    (6, "10:00", "12:00"),  # Saturday morning (2-hr block)
]
SGD_BLOCKS = [
    (2, "12:30", "14:00"),
    (3, "10:00", "12:00"),
    (3, "12:30", "14:00"),
    (4, "12:30", "14:00"),
    (6, "12:30", "14:00"),
]
SGD_PERMUTATIONS = [[0, 1, 2, 3], [3, 0, 1, 2], [1, 2, 3, 0], [2, 3, 0, 1], [1, 2, 3, 0]]

# Objective weights for integrated sequencing
W_DAY_GAP = 10      # per day between two linked lectures
W_OUT_OF_ORDER = 25  # linked pair taught in the wrong logical order
W_TEACHER_BUSY = 1000  # teacher already teaching another class at that time


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
    topic_id: Optional[UUID] = None
    integration_group: Optional[str] = Field(
        default=None, description="Linked-topic group taught together, e.g. 'G2 · heart'"
    )
    integration_tags: list[str] = Field(
        default_factory=list, description="Human-readable horizontal (↔) and vertical (↕) links"
    )
    date: Optional[str] = Field(default=None, description="ISO date of the session (real timetables)")
    kind: Optional[str] = Field(default=None, description="TEACHING, ROTATION or EVENT (real timetables)")
    session_id: Optional[UUID] = Field(default=None, description="Uploaded session this cell comes from")
    moved_from: Optional[str] = Field(
        default=None, description="Where the integrator moved this lecture from, e.g. 'Week 3 · Wed 29/10 09:00'"
    )


DEFAULT_SESSION = "2026-2027"


def clean_session(value: Optional[str]) -> str:
    """Any non-empty label is accepted (e.g. '2026-2027'); blank falls back to the default."""
    text = (value or "").strip()
    return text or DEFAULT_SESSION


class TimetableSchedule(BaseModel):
    module_code: str
    module_title: str
    academic_year: int
    week_number: int = 1
    total_weeks: int = 1
    session: str = DEFAULT_SESSION
    cells: list[ScheduledCell]
    solver_status: str
    total_contact_hours: float
    analytics: dict[str, Any] = {}
    program: str = "MBBS"
    cohort: Optional[str] = None
    cohort_label: Optional[str] = None
    # Real-timetable (template) runs only
    template: bool = Field(default=False, description="Built from the uploaded timetable's exact sessions")
    week_dates: dict[int, str] = Field(default_factory=dict, description="day_of_week -> ISO date for this week")
    moves: list[dict[str, Any]] = Field(default_factory=list, description="Every lecture the integrator moved (whole module)")
    integration_metrics: dict[str, Any] = Field(
        default_factory=dict, description="Linked-pair distances before and after integration (whole module)"
    )


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


def _cell_hours(c: ScheduledCell) -> float:
    h1, m1 = map(int, c.time_start.split(":"))
    h2, m2 = map(int, c.time_end.split(":"))
    return max(0.0, round(((h2 * 60 + m2) - (h1 * 60 + m1)) / 60, 2))


def _integration_metrics(cells: list[ScheduledCell]) -> dict[str, Any]:
    """How well linked topics are co-located this week (recomputed after every edit)."""
    groups: dict[str, list[ScheduledCell]] = defaultdict(list)
    for c in cells:
        if c.integration_group:
            groups[c.integration_group].append(c)
    multi = {g: cs for g, cs in groups.items() if len(cs) > 1}
    spans, in_order = [], 0
    for cs in multi.values():
        cs_sorted = sorted(cs, key=lambda c: (c.day_of_week, c.time_start))
        spans.append(cs_sorted[-1].day_of_week - cs_sorted[0].day_of_week)
        ranks = [sequence_rank(c.discipline) for c in cs_sorted]
        in_order += int(ranks == sorted(ranks))
    return {
        "linked_groups": len(multi),
        "linked_sessions": sum(len(cs) for cs in multi.values()),
        "groups_within_2_days": sum(1 for s in spans if s <= 2),
        "groups_in_logical_order": in_order,
        "average_day_span": round(sum(spans) / len(spans), 2) if spans else 0.0,
    }


def recompute_schedule_analytics(schedule: TimetableSchedule) -> TimetableSchedule:
    """Recalculate contact hours, class counts per subject/teacher, coverage and integration."""
    contact_hours_by_discipline: dict[str, float] = {}
    faculty_hours: dict[str, float] = {}
    time_bracket_counts: dict[str, int] = {}
    classes_by_discipline: Counter[str] = Counter()
    classes_by_faculty: Counter[str] = Counter()
    classes_by_session_type: Counter[str] = Counter()
    topic_counts: Counter[tuple[str, str]] = Counter()

    for c in schedule.cells:
        if c.session_type in ("BREAK", "HALF_DAY"):
            continue
        dur = _cell_hours(c)
        contact_hours_by_discipline[c.discipline] = round(contact_hours_by_discipline.get(c.discipline, 0.0) + dur, 1)
        classes_by_discipline[c.discipline] += 1
        classes_by_session_type[c.session_type] += 1
        # Co-teachers ('Dr. A / Dr. B') and rotation station teachers each carry the session.
        names = [n.strip() for n in (c.faculty_name or "").split(" / ") if n.strip()]
        for b in c.batch_assignments:
            names.extend(n.strip() for n in (b.faculty or "").split(" / ") if n.strip() and n.strip() not in names)
        for name in names:
            faculty_hours[name] = round(faculty_hours.get(name, 0.0) + dur, 1)
            classes_by_faculty[name] += 1
        if not c.batch_assignments:
            topic_counts[(c.discipline, c.topic_title)] += 1
        bracket = f"{c.time_start} - {c.time_end}"
        time_bracket_counts[bracket] = time_bracket_counts.get(bracket, 0) + 1

    schedule.total_contact_hours = round(sum(contact_hours_by_discipline.values()), 1)
    schedule.analytics = {
        "contact_hours_by_discipline": contact_hours_by_discipline,
        "faculty_hours": faculty_hours,
        "time_bracket_distribution": time_bracket_counts,
        "classes_by_discipline": dict(classes_by_discipline.most_common()),
        "classes_by_faculty": dict(classes_by_faculty.most_common()),
        "classes_by_session_type": dict(classes_by_session_type.most_common()),
        "topic_coverage": [
            {"discipline": d, "topic": t, "classes": n}
            for (d, t), n in sorted(topic_counts.items(), key=lambda kv: (kv[0][0], kv[0][1]))
        ],
        "integration": _integration_metrics(schedule.cells),
    }
    return schedule


# ---------------------------------------------------------------------------
# Integration planning (which lectures share a week, and in what order)
# ---------------------------------------------------------------------------


@dataclass
class _Lecture:
    topic: ParsedTopic
    order: tuple  # original position, used to keep upload order as a tie-breaker
    group: int = -1


@dataclass
class IntegrationPlan:
    cohort: Optional[str]
    lectures: list[_Lecture]
    weeks: list[list[int]]
    pairs: list[tuple[int, int]]  # (earlier, later) lecture indices that should sit together
    group_labels: dict[int, str] = field(default_factory=dict)


def _link_endpoints(
    link: ProposedLink, lectures: list[_Lecture], cohort: Optional[str] = None
) -> tuple[list[int], list[int]]:
    """Lecture indices of a link's source and target inside this class (empty if elsewhere)."""

    def find(obj_id: Optional[UUID], title: str, discipline: str, link_cohort: Optional[str]) -> list[int]:
        if cohort is not None and link_cohort is not None and link_cohort != cohort:
            return []
        if obj_id is not None:
            hits = [i for i, l in enumerate(lectures) if l.topic.id == obj_id]
            if hits:
                return hits
        key = (title.strip().lower(), discipline)
        return [i for i, l in enumerate(lectures) if (l.topic.topic_title.strip().lower(), l.topic.discipline) == key]

    return (
        find(link.source_objective_id, link.source_topic, link.source_discipline, link.source_cohort),
        find(link.target_objective_id, link.target_topic, link.target_discipline, link.target_cohort),
    )


def plan_integrated_weeks(
    topics: list[ParsedTopic], links: list[ProposedLink], slots_per_week: int, cohort: Optional[str] = None
) -> IntegrationPlan:
    """Group linked lectures and pack each group into one week in logical teaching order."""
    lectures: list[_Lecture] = []
    for idx, t in enumerate(topics):
        base = (t.original_week or 99, t.original_day or 9, t.original_start or "99", idx)
        for k in range(max(1, t.occurrences)):
            lectures.append(_Lecture(topic=t, order=(*base, k)))

    parent = list(range(len(lectures)))

    def root(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    pairs: set[tuple[int, int]] = set()
    concept_votes: dict[int, Counter[str]] = defaultdict(Counter)
    for link in links:
        if not link.is_approved:
            continue
        srcs, tgts = _link_endpoints(link, lectures, cohort)
        for a in srcs:
            for b in tgts:
                if a == b:
                    continue
                parent[root(a)] = root(b)
                first, second = sorted((a, b), key=lambda i: (sequence_rank(lectures[i].topic.discipline), lectures[i].order))
                pairs.add((first, second))
                for c in link.shared_concepts:
                    concept_votes[a][c] += 1
                    concept_votes[b][c] += 1

    # Repeated sessions of the same topic stay in one group too (taught as a series).
    by_topic: dict[int, list[int]] = defaultdict(list)
    for i, l in enumerate(lectures):
        by_topic[id(l.topic)].append(i)
    for idxs in by_topic.values():
        for a, b in zip(idxs, idxs[1:]):
            parent[root(a)] = root(b)

    members: dict[int, list[int]] = defaultdict(list)
    for i in range(len(lectures)):
        members[root(i)].append(i)

    groups: list[list[int]] = []
    for idxs in members.values():
        idxs.sort(key=lambda i: (sequence_rank(lectures[i].topic.discipline), lectures[i].order))
        for start in range(0, len(idxs), slots_per_week):  # a group larger than a week is split
            groups.append(idxs[start : start + slots_per_week])
    groups.sort(key=lambda g: min(lectures[i].order for i in g))

    group_labels: dict[int, str] = {}
    g_num = 0
    for g_idx, g in enumerate(groups):
        if len(g) < 2:
            continue
        g_num += 1
        votes: Counter[str] = Counter()
        for i in g:
            votes.update(concept_votes.get(i, Counter()))
            lectures[i].group = g_idx
        ranked = sorted(votes.items(), key=lambda kv: (kv[0] in BROAD_CONCEPTS, -kv[1]))
        theme = ranked[0][0].replace("_", " ") if ranked else "linked topics"
        group_labels[g_idx] = f"G{g_num} · {theme}"

    # First-fit packing keeps every group inside a single week.
    weeks: list[list[int]] = []
    for g in groups:
        target = next((w for w in weeks if len(w) + len(g) <= slots_per_week), None)
        if target is None:
            weeks.append([])
            target = weeks[-1]
        target.extend(g)

    # Chain consecutive members of each group so transitively-linked topics also sit together.
    for g in groups:
        for a, b in zip(g, g[1:]):
            pairs.add((a, b))

    return IntegrationPlan(cohort=cohort, lectures=lectures, weeks=weeks or [[]], pairs=sorted(pairs), group_labels=group_labels)


# ---------------------------------------------------------------------------
# Week solver
# ---------------------------------------------------------------------------


def _fixed_institutional_cells() -> list[ScheduledCell]:
    cells = []
    for d, day_name in DAYS.items():
        if d == FRIDAY:
            cells.append(ScheduledCell(
                day_of_week=d, day_name=day_name, time_start="12:00", time_end="14:00",
                session_type="HALF_DAY", discipline="Institutional", category="INSTITUTIONAL",
                topic_title="HALF DAY",
            ))
        else:
            cells.append(ScheduledCell(
                day_of_week=d, day_name=day_name, time_start="12:00", time_end="12:30",
                session_type="BREAK", discipline="Institutional", category="INSTITUTIONAL",
                topic_title="BREAK",
            ))
    return cells


def _faculty_key(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    return " ".join(name.lower().replace("dr.", "dr ").replace("prof.", "prof ").split())


def _needs_rotations(topics: list[ParsedTopic]) -> bool:
    return any(t.session_type.value in ROTATION_TYPES or t.discipline in BASIC_SCIENCES for t in topics)


def solve_schedule(
    topics: list[ParsedTopic],
    approved_links: list[ProposedLink] = [],
    module_code: str = "MODULE-07",
    module_title: str = "NEUROSCIENCES BLOCK-IV",
    academic_year: int = 2,
    week_number: int = 1,
    time_limit_seconds: float = 8.0,
    cohort: Optional[str] = None,
    program: Optional[str] = None,
    busy_faculty: Optional[dict[str, set[tuple[int, int]]]] = None,
    lecture_hall: Optional[str] = None,
    session: Optional[str] = None,
) -> TimetableSchedule:
    """Schedule one teaching week for one class with CP-SAT, honouring integration links.

    ``cohort`` (e.g. 'MBBS-2') restricts the run to that class's topics; ``busy_faculty`` maps a
    teacher to (day, slot) positions already taken in other classes; those placements are
    penalised so heavily that they only happen when a teacher's load leaves no alternative.
    """
    if cohort is not None:
        topics = [t for t in topics if topic_cohort(t) == cohort]
        sample = topics[0] if topics else None
        if sample is not None:
            academic_year = sample.academic_year or academic_year
            program = program or sample.program
    program = (program or "MBBS").upper()

    with_rotations = _needs_rotations(topics)
    positions = ROTATION_WEEK_LECTURE_POSITIONS if with_rotations else CLINICAL_WEEK_LECTURE_POSITIONS
    num_slots = len(positions)

    lecture_topics = [t for t in topics if t.session_type.value in WHOLE_CLASS_TYPES] or (
        [t for t in topics if t.session_type.value not in ROTATION_TYPES] or list(topics)
    )
    links_here = [l for l in approved_links if l.is_approved]
    key = cohort or cohort_key(program, academic_year)
    plan = plan_integrated_weeks(lecture_topics, links_here, num_slots, key)
    total_weeks = max(1, len(plan.weeks))
    clamped_week = max(1, min(week_number, total_weeks))
    week_idx = plan.weeks[clamped_week - 1] if plan.weeks else []

    model = cp_model.CpModel()
    scheduled_cells: list[ScheduledCell] = _fixed_institutional_cells()

    # -----------------------------------------------------------------------
    # CP-SAT 4-Batch Simultaneous Lab Rotation Model (x[b, v, p])
    # -----------------------------------------------------------------------
    num_p_blocks, num_batches, num_venues = len(PRACTICAL_BLOCKS), len(BATCHES), len(PRACTICAL_VENUES)
    x_lab: dict[tuple[int, int, int], cp_model.IntVar] = {}
    if with_rotations:
        for b in range(num_batches):
            for v in range(num_venues):
                for p in range(num_p_blocks):
                    x_lab[b, v, p] = model.NewBoolVar(f"x_lab_b{b}_v{v}_p{p}")
        # Each venue hosts exactly one batch per block (zero room collisions)
        for p in range(num_p_blocks):
            for v in range(num_venues):
                model.AddExactlyOne(x_lab[b, v, p] for b in range(num_batches))
        # Each batch is in exactly one venue per block
        for p in range(num_p_blocks):
            for b in range(num_batches):
                model.AddExactlyOne(x_lab[b, v, p] for v in range(num_venues))
        # Latin square: every batch visits every station once a week
        for b in range(num_batches):
            for v in range(num_venues):
                model.AddExactlyOne(x_lab[b, v, p] for p in range(num_p_blocks))
        for b in range(num_batches):  # symmetry breaking on Monday's block
            model.Add(x_lab[b, b, 0] == 1)

    # -----------------------------------------------------------------------
    # Lecture placement with integration objective
    # -----------------------------------------------------------------------
    local = {lec: n for n, lec in enumerate(week_idx)}
    assign: dict[tuple[int, int], cp_model.IntVar] = {}
    for n in range(len(week_idx)):
        for p in range(num_slots):
            assign[n, p] = model.NewBoolVar(f"assign_{n}_{p}")
        model.AddExactlyOne(assign[n, p] for p in range(num_slots))
    for p in range(num_slots):
        model.AddAtMostOne(assign[n, p] for n in range(len(week_idx)))

    pos_var, day_var = {}, {}
    for n in range(len(week_idx)):
        pos_var[n] = model.NewIntVar(0, num_slots - 1, f"pos_{n}")
        day_var[n] = model.NewIntVar(1, 6, f"day_{n}")
        model.Add(pos_var[n] == sum(p * assign[n, p] for p in range(num_slots)))
        model.Add(day_var[n] == sum(positions[p][0] * assign[n, p] for p in range(num_slots)))

    penalties = []
    week_pairs = [(local[a], local[b]) for a, b in plan.pairs if a in local and b in local]
    for a, b in week_pairs:
        gap = model.NewIntVar(0, 5, f"gap_{a}_{b}")
        model.AddAbsEquality(gap, day_var[a] - day_var[b])
        penalties.append(W_DAY_GAP * gap)
        lec_a, lec_b = plan.lectures[week_idx[a]], plan.lectures[week_idx[b]]
        same_topic_series = lec_a.topic is lec_b.topic
        if sequence_rank(lec_a.topic.discipline) < sequence_rank(lec_b.topic.discipline) or same_topic_series:
            in_order = model.NewBoolVar(f"order_{a}_{b}")
            model.Add(pos_var[a] < pos_var[b]).OnlyEnforceIf(in_order)
            penalties.append(W_OUT_OF_ORDER * (1 - in_order))

    # Teachers already booked in another class at that time: a near-hard penalty, so the solver
    # always finds a timetable and only double-books when a teacher's load makes it unavoidable.
    if busy_faculty:
        for n, lec in enumerate(week_idx):
            taken = busy_faculty.get(_faculty_key(plan.lectures[lec].topic.faculty_name) or "", set())
            penalties += [W_TEACHER_BUSY * assign[n, p] for p, pos in enumerate(positions) if pos in taken]
    if penalties:
        model.Minimize(sum(penalties))

    # Warm start: the plan already lists each group contiguously in teaching order, so laying it
    # out slot by slot is a strong first solution that CP-SAT then improves.
    for n in range(len(week_idx)):
        for p in range(num_slots):
            model.AddHint(assign[n, p], int(p == n))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = min(time_limit_seconds, 5.0)
    solver.parameters.num_search_workers = 1
    status = solver.Solve(model)
    status_name = solver.StatusName(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise ValueError(f"CP-SAT solver could not find a feasible schedule: {status_name}")

    # Practical rotations
    if with_rotations:
        for p_idx, (d, t_start, t_end) in enumerate(PRACTICAL_BLOCKS):
            batch_assignments: list[BatchStationAssignment] = []
            for b_idx, batch_code in enumerate(BATCHES):
                v_idx = next(v for v in range(num_venues) if solver.Value(x_lab[b_idx, v, p_idx]) == 1)
                venue = PRACTICAL_VENUES[v_idx]
                batch_assignments.append(BatchStationAssignment(
                    batch=f"Batch {batch_code}",
                    station=_resolve_practical_station_label(venue, clamped_week, topics),
                    venue=venue,
                ))
            scheduled_cells.append(ScheduledCell(
                day_of_week=d, day_name=DAYS[d], time_start=t_start, time_end=t_end,
                session_type="PRACTICAL", discipline="Multi-Disciplinary", category="INSTITUTIONAL",
                topic_title=f"Practical Rotation (Week-{clamped_week:02d})",
                venue_name="Histo / Physio / Biochem / Skill Labs",
                batch_assignments=batch_assignments,
            ))

        # Room-unconstrained SGD rotations (Anatomy, Physiology, Biochem, SDL)
        for s_idx, (d, t_start, t_end) in enumerate(SGD_BLOCKS):
            perm = SGD_PERMUTATIONS[s_idx % len(SGD_PERMUTATIONS)]
            scheduled_cells.append(ScheduledCell(
                day_of_week=d, day_name=DAYS[d], time_start=t_start, time_end=t_end,
                session_type="SGD", discipline="Multi-Disciplinary", category="INSTITUTIONAL",
                topic_title=f"SGD & SDL Rotation (Week-{clamped_week:02d})",
                venue_name="Departmental SGD (Room-Unconstrained)",
                batch_assignments=[
                    BatchStationAssignment(
                        batch=f"Batch {batch_code}",
                        station=_resolve_sgd_station_label(SGD_STATIONS[perm[b_idx]], clamped_week, topics),
                        venue=None,  # Room-unconstrained per AGENTS.md §4.3
                    )
                    for b_idx, batch_code in enumerate(BATCHES)
                ],
            ))

    # Lectures
    hall = lecture_hall or f"Lecture Hall {((academic_year - 1) % LECTURE_HALL_COUNT) + 1}"
    placed: dict[int, tuple[int, int]] = {}
    lecture_cells: dict[int, ScheduledCell] = {}
    for n, lec in enumerate(week_idx):
        p = next(p for p in range(num_slots) if solver.Value(assign[n, p]) == 1)
        d, s_num = positions[p]
        placed[lec] = (d, s_num)
        t = plan.lectures[lec].topic
        t_start, t_end = SLOT_TIMES[s_num]
        lecture_cells[lec] = ScheduledCell(
            day_of_week=d, day_name=DAYS[d], time_start=t_start, time_end=t_end,
            session_type=t.session_type.value, discipline=t.discipline, category=t.category,
            topic_title=t.topic_title, faculty_name=t.faculty_name, venue_name=hall,
            topic_id=t.id, integration_group=plan.group_labels.get(plan.lectures[lec].group),
        )
    _annotate_links(plan, placed, lecture_cells, links_here, week_idx)
    scheduled_cells.extend(lecture_cells.values())
    scheduled_cells.sort(key=lambda c: (c.day_of_week, c.time_start))

    sched = TimetableSchedule(
        module_code=module_code,
        module_title=module_title,
        academic_year=academic_year,
        week_number=clamped_week,
        total_weeks=total_weeks,
        session=clean_session(session),
        cells=scheduled_cells,
        solver_status=status_name,
        total_contact_hours=0.0,
        program=program,
        cohort=key,
        cohort_label=cohort_label(key),
    )
    return recompute_schedule_analytics(sched)


def _annotate_links(
    plan: IntegrationPlan,
    placed: dict[int, tuple[int, int]],
    cells: dict[int, ScheduledCell],
    links: list[ProposedLink],
    week_idx: list[int],
) -> None:
    """Attach readable '↔ same-class' and '↕ other-year' link notes to each lecture cell."""
    week_of = {lec: w + 1 for w, idxs in enumerate(plan.weeks) for lec in idxs}
    in_week = set(week_idx)
    for link in links:
        srcs, tgts = _link_endpoints(link, plan.lectures, plan.cohort)
        for here, other_title, other_disc, other_cohort, partners in (
            (srcs, link.target_topic, link.target_discipline, link.target_cohort, tgts),
            (tgts, link.source_topic, link.source_discipline, link.source_cohort, srcs),
        ):
            for lec in here:
                if lec not in in_week:
                    continue
                cell = cells[lec]
                if partners:  # partner is in this class's timetable
                    partner = partners[0]
                    if partner in placed:
                        d, s = placed[partner]
                        when = f"{DAYS[d][:3].title()} {SLOT_TIMES[s][0]}"
                    else:
                        when = f"Week {week_of.get(partner, '?')}"
                    tag = f"↔ {other_disc}: {other_title} ({when})"
                else:
                    who = cohort_label(other_cohort) if other_cohort else "another year"
                    tag = f"↕ {who} {other_disc}: {other_title}"
                if tag not in cell.integration_tags:
                    cell.integration_tags.append(tag)


# ---------------------------------------------------------------------------
# Multi-class runs
# ---------------------------------------------------------------------------


class MultiCohortSchedule(BaseModel):
    schedules: list[TimetableSchedule]
    shared_teacher_sessions: int = Field(
        default=0, description="Lectures whose teacher also teaches another class (kept clash-free)"
    )
    warnings: list[str] = []


def list_cohorts(topics: list[ParsedTopic]) -> list[str]:
    keys = {topic_cohort(t) for t in topics if topic_cohort(t)}
    return sorted(keys, key=lambda k: (k.split("-")[0], int(k.split("-")[1]) if k.split("-")[1].isdigit() else 0))


class CohortModule(BaseModel):
    module_title: Optional[str] = None
    module_code: Optional[str] = None
    session: Optional[str] = None


def solve_all_cohorts(
    topics: list[ParsedTopic],
    approved_links: list[ProposedLink],
    module_code: str,
    module_title: str,
    week_number: int = 1,
    cohorts: Optional[list[str]] = None,
    time_limit_seconds: float = 8.0,
    cohort_modules: Optional[dict[str, CohortModule]] = None,
    session: Optional[str] = None,
) -> MultiCohortSchedule:
    """Solve the same week for every class, booking shared teachers only once per slot.

    ``time_limit_seconds`` is the budget for the whole run, shared between the classes.
    """
    keys = cohorts or list_cohorts(topics) or [None]
    per_class_limit = max(0.5, time_limit_seconds / len(keys))
    busy: dict[str, set[tuple[int, int]]] = defaultdict(set)
    warnings: list[str] = []
    shared = 0
    if len(keys) > LECTURE_HALL_COUNT:
        warnings.append(
            f"{len(keys)} classes share {LECTURE_HALL_COUNT} lecture halls; halls are reused, so stagger "
            "lecture times for the extra classes or assign clinical classes to ward teaching."
        )
    # Busiest classes are solved first so they get first pick of shared teachers' time.
    load = Counter(topic_cohort(t) for t in topics if t.session_type.value in WHOLE_CLASS_TYPES)
    solve_order = sorted(range(len(keys)), key=lambda i: -load.get(keys[i], 0))
    solved: dict[int, TimetableSchedule] = {}
    for idx in solve_order:
        key = keys[idx]
        mod = (cohort_modules or {}).get(key or "") or CohortModule()
        sched = solve_schedule(
            topics=topics,
            approved_links=approved_links,
            module_code=mod.module_code or module_code,
            module_title=mod.module_title or module_title,
            week_number=week_number,
            time_limit_seconds=per_class_limit,
            cohort=key,
            busy_faculty=busy,
            lecture_hall=f"Lecture Hall {(idx % LECTURE_HALL_COUNT) + 1}",
            session=mod.session or session,
        )
        slot_index = {start: k for k, (start, _end) in SLOT_TIMES.items()}
        for c in sched.cells:
            fk = _faculty_key(c.faculty_name)
            if fk and c.time_start in slot_index:
                pos = (c.day_of_week, slot_index[c.time_start])
                if pos in busy[fk]:
                    warnings.append(f"{c.faculty_name} is double-booked on {c.day_name.title()} {c.time_start}.")
                busy[fk].add(pos)
        solved[idx] = sched
    schedules = [solved[i] for i in range(len(keys))]

    teacher_classes: dict[str, set[str]] = defaultdict(set)
    for sched in schedules:
        for c in sched.cells:
            if (fk := _faculty_key(c.faculty_name)) and sched.cohort:
                teacher_classes[fk].add(sched.cohort)
    shared = sum(
        1 for sched in schedules for c in sched.cells
        if (fk := _faculty_key(c.faculty_name)) and len(teacher_classes[fk]) > 1
    )
    return MultiCohortSchedule(schedules=schedules, shared_teacher_sessions=shared, warnings=warnings)


def build_original_schedule(
    topics: list[ParsedTopic],
    module_code: str = "MODULE-07",
    module_title: str = "NEUROSCIENCES BLOCK-IV",
    academic_year: int = 2,
    week_number: int = 1,
    cohort: Optional[str] = None,
    session: Optional[str] = None,
) -> TimetableSchedule:
    """Reconstruct the original uploaded ('Old') timetable for the given week without AI reordering.

    - If topics came from a .docx/.xlsx table with explicit `original_day` and `original_start`,
      places them in their exact original uploaded slots for `week_number`.
    - If topics came from a pasted list without grid coordinates, places them in their exact
      uploaded sequential order across the week.
    """
    if cohort is not None:
        topics = [t for t in topics if topic_cohort(t) == cohort]
        if topics and topics[0].academic_year:
            academic_year = topics[0].academic_year
    program = (topics[0].program if topics and topics[0].program else "MBBS").upper()
    key = cohort or cohort_key(program, academic_year)
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
    lecture_hall_name = f"Lecture Hall {((academic_year - 1) % LECTURE_HALL_COUNT) + 1}"

    # 1. Fixed Institutional Blocks: Daily Break (Mon-Thu & Sat 12:00-12:30) & Friday Half-Day
    scheduled_cells.extend(_fixed_institutional_cells())

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

    # 3. Fill standard Practical & SGD rotation blocks on unoccupied slots (basic-science years only)
    with_rotations = _needs_rotations(topics)
    latin_square = [
        [0, 1, 2, 3],
        [3, 0, 1, 2],
        [2, 3, 0, 1],
        [1, 2, 3, 0],
    ]
    for p_idx, (d, t_start, t_end) in enumerate(PRACTICAL_BLOCKS):
        if not with_rotations or (d, t_start) in occupied_slots:
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

    for s_idx, (d, t_start, t_end) in enumerate(SGD_BLOCKS):
        if not with_rotations or (d, t_start) in occupied_slots:
            continue
        perm = SGD_PERMUTATIONS[s_idx % len(SGD_PERMUTATIONS)]
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
        session=clean_session(session),
        cells=scheduled_cells,
        solver_status="UPLOADED_ORIGINAL",
        total_contact_hours=0.0,
        program=program,
        cohort=key,
        cohort_label=cohort_label(key),
    )
    return recompute_schedule_analytics(sched)
