"""Module-wide curriculum report: classes per subject, topic coverage and teacher load.

The weekly ``schedule.analytics`` block only sees one week of one class. This report covers the
whole upload (every week, every class): each topic counts as many classes as it appears in the
uploaded timetable (``ParsedTopic.occurrences``). Edits made on the timetable grid or through the
Copilot (teacher reassignments, added classes) are applied when the edited schedules are passed in.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from pydantic import BaseModel, Field

from app.core.constants import cohort_label
from app.models.schemas import ParsedTopic
from app.services.integrator import ProposedLink, topic_cohort
from app.services.solver import ROTATION_TYPES, TimetableSchedule

UNASSIGNED = "Unassigned"


class SubjectStat(BaseModel):
    cohort: Optional[str] = None
    cohort_label: Optional[str] = None
    discipline: str
    classes: int = Field(description="Sessions taught, counting repeats")
    topics: int = Field(description="Distinct topics")
    contact_hours: float
    teachers: list[str] = []
    integrated_topics: int = Field(default=0, description="Topics with at least one approved link")


class TeacherStat(BaseModel):
    faculty: str
    classes: int
    contact_hours: float
    subjects: list[str] = []
    cohorts: list[str] = []


class TopicCoverage(BaseModel):
    cohort: Optional[str] = None
    discipline: str
    topic: str
    session_type: str
    times_covered: int
    faculty: list[str] = []
    horizontal_links: int = 0
    vertical_links: int = 0


class ReportTotals(BaseModel):
    cohorts: int
    classes: int
    contact_hours: float
    subjects: int
    teachers: int
    topics: int
    horizontal_links: int
    vertical_links: int


class CurriculumReport(BaseModel):
    totals: ReportTotals
    subjects: list[SubjectStat]
    teachers: list[TeacherStat]
    topics: list[TopicCoverage]


def _faculty_per_occurrence(
    topics: list[ParsedTopic], schedules: list[TimetableSchedule]
) -> dict[int, list[str]]:
    """Faculty for each taught occurrence of each topic, after grid/Copilot edits."""
    per_topic: dict[int, list[str]] = {
        i: [t.faculty_name or UNASSIGNED] * max(1, t.occurrences) for i, t in enumerate(topics)
    }
    index_by_id = {t.id: i for i, t in enumerate(topics) if t.id is not None}
    replaced: dict[int, int] = defaultdict(int)
    for sched in schedules:
        for cell in sched.cells:
            i = index_by_id.get(cell.topic_id) if cell.topic_id else None
            if i is None:
                continue
            slot = replaced[i] % len(per_topic[i])
            per_topic[i][slot] = cell.faculty_name or UNASSIGNED
            replaced[i] += 1
    return per_topic


def build_report(
    topics: list[ParsedTopic],
    links: list[ProposedLink] | None = None,
    schedules: list[TimetableSchedule] | None = None,
) -> CurriculumReport:
    links = [l for l in (links or []) if l.is_approved]
    schedules = schedules or []

    def link_key(title: str, discipline: str, cohort: Optional[str]) -> tuple[str, str, Optional[str]]:
        return (title.strip().lower(), discipline, cohort)

    h_count: dict[tuple, int] = defaultdict(int)
    v_count: dict[tuple, int] = defaultdict(int)
    for l in links:
        bucket = h_count if l.integration_type == "HORIZONTAL" else v_count
        bucket[link_key(l.source_topic, l.source_discipline, l.source_cohort)] += 1
        bucket[link_key(l.target_topic, l.target_discipline, l.target_cohort)] += 1

    def links_for(t: ParsedTopic) -> tuple[int, int]:
        c = topic_cohort(t)
        keys = [link_key(t.topic_title, t.discipline, c), link_key(t.topic_title, t.discipline, None)]
        return sum(h_count.get(k, 0) for k in set(keys)), sum(v_count.get(k, 0) for k in set(keys))

    faculty_occ = _faculty_per_occurrence(topics, schedules)

    coverage: list[TopicCoverage] = []
    subj: dict[tuple[Optional[str], str], dict] = {}
    teach: dict[str, dict] = {}

    def add_class(cohort: Optional[str], discipline: str, faculty: str, hours: float) -> None:
        s = subj.setdefault((cohort, discipline), {"classes": 0, "hours": 0.0, "teachers": set(), "topics": 0, "linked": 0})
        s["classes"] += 1
        s["hours"] += hours
        if faculty != UNASSIGNED:
            s["teachers"].add(faculty)
        tch = teach.setdefault(faculty, {"classes": 0, "hours": 0.0, "subjects": set(), "cohorts": set()})
        tch["classes"] += 1
        tch["hours"] += hours
        tch["subjects"].add(discipline)
        if cohort:
            tch["cohorts"].add(cohort)

    for i, t in enumerate(topics):
        cohort = topic_cohort(t)
        hours = (t.duration_minutes or 60) / 60
        for fac in faculty_occ[i]:
            add_class(cohort, t.discipline, fac, hours)
        h, v = links_for(t)
        s = subj[(cohort, t.discipline)]
        s["topics"] += 1
        s["linked"] += int(h + v > 0)
        coverage.append(TopicCoverage(
            cohort=cohort,
            discipline=t.discipline,
            topic=t.topic_title,
            session_type=t.session_type.value,
            times_covered=len(faculty_occ[i]),
            faculty=sorted({f for f in faculty_occ[i] if f != UNASSIGNED}),
            horizontal_links=h,
            vertical_links=v,
        ))

    # Classes added on the grid / via Copilot that were not in the upload
    for sched in schedules:
        for cell in sched.cells:
            if cell.topic_id or cell.batch_assignments or cell.session_type in ROTATION_TYPES | {"BREAK", "HALF_DAY"}:
                continue
            h1, m1 = map(int, cell.time_start.split(":"))
            h2, m2 = map(int, cell.time_end.split(":"))
            add_class(sched.cohort, cell.discipline, cell.faculty_name or UNASSIGNED, ((h2 * 60 + m2) - (h1 * 60 + m1)) / 60)

    subjects = [
        SubjectStat(
            cohort=c,
            cohort_label=cohort_label(c) if c else None,
            discipline=d,
            classes=v["classes"],
            topics=v["topics"],
            contact_hours=round(v["hours"], 1),
            teachers=sorted(v["teachers"]),
            integrated_topics=v["linked"],
        )
        for (c, d), v in subj.items()
    ]
    subjects.sort(key=lambda s: (s.cohort or "", -s.classes, s.discipline))
    teachers = [
        TeacherStat(
            faculty=f,
            classes=v["classes"],
            contact_hours=round(v["hours"], 1),
            subjects=sorted(v["subjects"]),
            cohorts=sorted(v["cohorts"]),
        )
        for f, v in teach.items()
    ]
    teachers.sort(key=lambda t: (t.faculty == UNASSIGNED, -t.classes, t.faculty))
    coverage.sort(key=lambda c: (c.cohort or "", c.discipline, -c.times_covered, c.topic))

    return CurriculumReport(
        totals=ReportTotals(
            cohorts=len({c.cohort for c in coverage if c.cohort}) or 1,
            classes=sum(s.classes for s in subjects),
            contact_hours=round(sum(s.contact_hours for s in subjects), 1),
            subjects=len({s.discipline for s in subjects}),
            teachers=sum(1 for t in teachers if t.faculty != UNASSIGNED),
            topics=len(coverage),
            horizontal_links=sum(1 for l in links if l.integration_type == "HORIZONTAL"),
            vertical_links=sum(1 for l in links if l.integration_type == "VERTICAL"),
        ),
        subjects=subjects,
        teachers=teachers,
        topics=coverage,
    )
