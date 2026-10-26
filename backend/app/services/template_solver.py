"""Integrate a real (uploaded) timetable without breaking its structure.

When an upload is a real college timetable (``ParseResponse.sessions`` is filled), the college has
already fixed the skeleton of the module: practical and SGD rotation blocks, whole-class SGD / LGD
sessions, SDL, mentor-mentee meetings, PAL, Islamiat, RIPPLE, breaks and half days. The client's
rule is that only **1-hour subject lectures (LGIS / DSL)** are re-sequenced, and only into the
lecture slots the module already has (same total capacity). Lectures may move between weeks
wherever that buys integration (``max_week_shift=None``).

Model (OR-Tools CP-SAT, assignment of lectures to the existing lecture slots):

* hard: every lecture gets exactly one slot and every slot one lecture;
* hard: each subject keeps its own topic order (Cranial nerves 1-3 before 4-6, Bioenergetics I -> II -> III);
* hard: a lecture keeps its teacher, and that teacher is never booked twice at the same time
  (rotation stations, whole-class SGDs, events and other classes' lectures included);
* hard: a teacher does not get more lectures in one day than the original timetable gave them (min 2);
* soft: linked topics (approved integration links) land on the same or adjacent teaching days,
  in the logical order anatomy / embryology / histology -> physiology -> biochemistry -> pathology ->
  community / behavioural -> clinical;
* soft: a light penalty per week (and per day) moved, so nothing moves without an integration gain.

If CP-SAT finds nothing better in its budget, a greedy swap search is used; the original timetable
is always a valid answer, so the result is never worse than the upload.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional
from uuid import UUID

from ortools.sat.python import cp_model

from app.core.constants import DAYS, FRIDAY, cohort_label, discipline_category
from app.models.schemas import ParsedSession, ParsedTopic
from app.services.integrator import ProposedLink, topic_cohort

logger = logging.getLogger(__name__)

MOVABLE_TYPES = {"LGIS", "DSL"}

# Logical teaching order for linked topics (client's wording). Lower tier is taught first.
_TIERS: list[tuple[int, set[str]]] = [
    (0, {"Anatomy", "Gross Anatomy", "Neuroanatomy", "Embryology", "Histology", "Oral Biology"}),
    (1, {"Physiology"}),
    (2, {"Biochemistry", "Dental Materials"}),
    (3, {"Pathology", "Pharmacology", "Oral Pathology", "Forensic Medicine"}),
    (4, {"Community Medicine", "Behavioural Sciences"}),
    (5, {"Medicine", "Surgery", "Pediatrics", "ENT", "Ophthalmology", "Radiology", "Skill Lab",
         "Oral & Maxillofacial Surgery", "Obstetrics & Gynaecology", "Oral Medicine"}),
]
TIER_LABEL = ["anatomy/embryology/histology", "physiology", "biochemistry", "pathology",
              "community/behavioural", "clinical"]


def integration_tier(discipline: str) -> int:
    for tier, names in _TIERS:
        if discipline in names:
            return tier
    return 4


# Objective weights
W_PAIR_DAY = 10   # per teaching day between two linked lectures
W_PAIR_ORDER = 30  # linked pair taught out of logical order
W_WEEK = 6        # per week a lecture moves
W_DAY = 2         # per teaching day a lecture moves
W_SLOT = 1        # any change of slot (keeps pointless same-day reshuffles out)
PAIR_DAY_CAP = 12  # a pair further apart than this counts as this far (keeps the objective focused)

_DAY_ABBR = {d: n[:3].title() for d, n in DAYS.items()}


def _min(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _teacher_key(name: str) -> str:
    return " ".join(name.lower().replace("dr.", "dr ").replace("prof.", "prof ").split())


def _fmt_date(iso: Optional[str]) -> str:
    if not iso:
        return ""
    try:
        return dt.date.fromisoformat(iso).strftime("%d/%m")
    except ValueError:
        return iso


@dataclass
class Slot:
    idx: int
    week: int
    day: int
    date: Optional[str]
    start: str
    end: str
    dayord: int

    def label(self) -> str:
        date = f" {_fmt_date(self.date)}" if self.date else ""
        return f"Week {self.week} · {_DAY_ABBR.get(self.day, self.day)}{date} {self.start}"


@dataclass
class _Endpoint:
    """Where one side of a link is taught: movable lectures and/or fixed (day, minute) points."""

    lectures: list[int] = field(default_factory=list)
    fixed: list[tuple[int, int, int]] = field(default_factory=list)  # (dayord, start minute, week)
    label: str = ""
    discipline: str = ""

    @property
    def found(self) -> bool:
        return bool(self.lectures or self.fixed)


@dataclass
class TemplateResult:
    cohort: Optional[str]
    sessions: list[ParsedSession]          # this class's sessions, original positions
    slots: list[Slot]
    lectures: list[ParsedSession]          # movable lectures, index == original slot index
    assignment: list[int]                  # lecture index -> slot index
    moves: list[dict[str, Any]]
    metrics: dict[str, Any]
    status: str
    dayords: dict[tuple[int, int], int]
    week_dates: dict[int, dict[int, str]]
    warnings: list[str] = field(default_factory=list)
    link_labels: list[tuple[str, str]] = field(default_factory=list)  # ('Discipline: title', ...)

    @property
    def total_weeks(self) -> int:
        return max((s.week for s in self.sessions), default=1)


# ---------------------------------------------------------------------------
# Building the problem
# ---------------------------------------------------------------------------


def sessions_for(sessions: list[ParsedSession], cohort: Optional[str]) -> list[ParsedSession]:
    if cohort is None:
        return list(sessions)
    own = [s for s in sessions if s.cohort == cohort]
    if own:
        return own
    # Single-class upload whose sessions carry no class key.
    return [s for s in sessions if s.cohort is None]


def list_session_cohorts(sessions: list[ParsedSession]) -> list[Optional[str]]:
    return list(dict.fromkeys(s.cohort for s in sessions)) or [None]


def _is_movable(s: ParsedSession) -> bool:
    if s.kind != "TEACHING" or s.session_type.value not in MOVABLE_TYPES:
        return False
    if s.movable:
        return True
    return _min(s.time_end) - _min(s.time_start) == 60 and s.discipline not in {
        "Research (RIPPLE)", "Islamiat & Pak Studies", "Institutional", "General"}


def _sort_key(s: ParsedSession) -> tuple:
    return (s.week, s.day_of_week, _min(s.time_start), _min(s.time_end))


def _teachers_of(s: ParsedSession) -> list[str]:
    names = list(s.faculty_names)
    for b in s.batches:
        names.extend(n for n in b.faculty_names if n not in names)
    return names


def _norm(text: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in text).split())


def _build_endpoints(
    link: ProposedLink,
    sessions: list[ParsedSession],
    lecture_index: dict[UUID, int],
    dayords: dict[tuple[int, int], int],
    topics_by_id: dict[UUID, ParsedTopic],
    cohort: Optional[str],
) -> tuple[_Endpoint, _Endpoint]:
    def build(obj_id: Optional[UUID], title: str, disc: str, link_cohort: Optional[str]) -> _Endpoint:
        ep = _Endpoint(label=f"{disc}: {title}", discipline=disc)
        if cohort is not None and link_cohort is not None and link_cohort != cohort:
            return ep
        tnorm = _norm(title)
        for s in sessions:
            d = dayords[(s.week, s.day_of_week)]
            if s.kind == "TEACHING":
                hit = (obj_id is not None and s.topic_id == obj_id) or (
                    _norm(s.topic_title) == tnorm and s.discipline == disc)
                if not hit:
                    continue
                if s.id in lecture_index:
                    ep.lectures.append(lecture_index[s.id])
                else:
                    ep.fixed.append((d, _min(s.time_start), s.week))
            elif s.kind == "ROTATION":
                for b in s.batches:
                    if b.topic_title and _norm(b.topic_title) == tnorm and b.discipline == disc:
                        ep.fixed.append((d, _min(s.time_start), s.week))
                        break
        return ep

    return (
        build(link.source_objective_id, link.source_topic, link.source_discipline, link.source_cohort),
        build(link.target_objective_id, link.target_topic, link.target_discipline, link.target_cohort),
    )


@dataclass
class _Problem:
    slots: list[Slot]
    lectures: list[ParsedSession]
    allowed: list[list[int]]               # lecture -> allowed slot indices
    chains: list[list[int]]                # per subject, lectures in original order
    teacher_lectures: dict[str, list[int]]
    teacher_day_cap: dict[str, int]
    pairs: list[tuple[int, int, int, int]]  # (lo, hi, weight, link idx): lo should come first (tier)
    unary: list[list[int]]                 # lecture -> cost per slot (fixed-endpoint links + move penalty)
    links: list[tuple[ProposedLink, _Endpoint, _Endpoint]]


def _build_problem(
    sessions: list[ParsedSession],
    links: list[ProposedLink],
    topics: list[ParsedTopic],
    cohort: Optional[str],
    max_week_shift: Optional[int],
    busy: Optional[dict[str, list[tuple[str, int, int]]]],
) -> tuple[_Problem, dict[tuple[int, int], int], list[str]]:
    warnings: list[str] = []
    ordered = sorted(sessions, key=_sort_key)
    days = sorted({(s.week, s.day_of_week) for s in ordered})
    dayords = {wd: i for i, wd in enumerate(days)}
    date_of = {}
    for s in ordered:
        if s.date:
            date_of.setdefault((s.week, s.day_of_week), s.date)

    lectures = [s for s in ordered if _is_movable(s)]
    slots = [
        Slot(idx=i, week=s.week, day=s.day_of_week, date=date_of.get((s.week, s.day_of_week)),
             start=s.time_start, end=s.time_end, dayord=dayords[(s.week, s.day_of_week)])
        for i, s in enumerate(lectures)
    ]
    lecture_index = {s.id: i for i, s in enumerate(lectures) if s.id is not None}

    # Teachers busy in fixed sessions of this class, and in other classes' timetables.
    fixed_busy: dict[str, list[tuple[int, int, int]]] = defaultdict(list)
    for s in ordered:
        if s.id in lecture_index:
            continue
        for name in _teachers_of(s):
            fixed_busy[_teacher_key(name)].append((dayords[(s.week, s.day_of_week)], _min(s.time_start), _min(s.time_end)))
    ext_busy: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
    for k, v in (busy or {}).items():
        ext_busy[k].extend(v)

    def slot_key(sl: Slot) -> str:
        return sl.date or f"w{sl.week}d{sl.day}"

    allowed: list[list[int]] = []
    for i, lec in enumerate(lectures):
        keys = [_teacher_key(n) for n in lec.faculty_names]
        ok: list[int] = []
        for sl in slots:
            if max_week_shift is not None and abs(sl.week - lec.week) > max_week_shift:
                continue
            a, b = _min(sl.start), _min(sl.end)
            clash = any(
                d == sl.dayord and a < e and s0 < b for k in keys for d, s0, e in fixed_busy.get(k, ())
            ) or any(
                day == slot_key(sl) and a < e and s0 < b for k in keys for day, s0, e in ext_busy.get(k, ())
            )
            if not clash or sl.idx == i and not ext_busy:
                ok.append(sl.idx)
        if i not in ok:
            if any(k in ext_busy for k in keys):
                warnings.append(
                    f"{lec.discipline}: '{lec.topic_title}' ({', '.join(lec.faculty_names)}) clashed with another "
                    "class at its original time; it was moved to a free slot."
                )
            else:
                ok.append(i)
        allowed.append(sorted(set(ok)))

    chains_map: dict[str, list[int]] = defaultdict(list)
    for i, lec in enumerate(lectures):
        chains_map[lec.discipline].append(i)
    chains = [c for c in chains_map.values() if len(c) > 1]

    teacher_lectures: dict[str, list[int]] = defaultdict(list)
    for i, lec in enumerate(lectures):
        for n in lec.faculty_names:
            teacher_lectures[_teacher_key(n)].append(i)
    teacher_day_cap: dict[str, int] = {}
    for k, idxs in teacher_lectures.items():
        per_day = Counter(slots[i].dayord for i in idxs)
        teacher_day_cap[k] = max(2, max(per_day.values()))

    # Integration links -> pairwise and unary objective terms
    topics_by_id = {t.id: t for t in topics if t.id is not None}
    unary = [[W_WEEK * abs(sl.week - lec.week) + W_DAY * abs(sl.dayord - slots[i].dayord)
              + (W_SLOT if sl.idx != i else 0) for sl in slots]
             for i, lec in enumerate(lectures)]
    pairs: list[tuple[int, int, int, int]] = []
    link_eps: list[tuple[ProposedLink, _Endpoint, _Endpoint]] = []
    seen_pairs: set[tuple[int, int]] = set()
    for li, link in enumerate(l for l in links if l.is_approved):
        a, b = _build_endpoints(link, ordered, lecture_index, dayords, topics_by_id, cohort)
        if not (a.found and b.found):
            continue
        link_eps.append((link, a, b))
        ta, tb = integration_tier(a.discipline), integration_tier(b.discipline)
        for i in a.lectures[:3]:
            for j in b.lectures[:3]:
                if i == j:
                    continue
                lo, hi = (i, j) if ta <= tb else (j, i)
                if (lo, hi) in seen_pairs:
                    continue
                seen_pairs.add((lo, hi))
                pairs.append((lo, hi, 1 if ta != tb else 0, len(link_eps) - 1))
        # one side movable, other side fixed in the timetable (rotation station, whole-class SGD ...)
        for mov, fix, t_mov, t_fix in ((a, b, ta, tb), (b, a, tb, ta)):
            if not mov.lectures or not fix.fixed or fix.lectures:
                continue
            for i in mov.lectures[:3]:
                for sl in slots:
                    dist = min(min(abs(sl.dayord - d), PAIR_DAY_CAP) for d, _, _ in fix.fixed)
                    cost = W_PAIR_DAY * dist
                    if t_mov != t_fix:
                        first = min(fix.fixed)
                        before = (sl.dayord, _min(sl.start)) < (first[0], first[1])
                        if before != (t_mov < t_fix):
                            cost += W_PAIR_ORDER
                    unary[i][sl.idx] += cost
    prob = _Problem(slots=slots, lectures=lectures, allowed=allowed, chains=chains,
                    teacher_lectures=teacher_lectures, teacher_day_cap=teacher_day_cap,
                    pairs=pairs, unary=unary, links=link_eps)
    return prob, dayords, warnings


# ---------------------------------------------------------------------------
# Solving
# ---------------------------------------------------------------------------


def _objective(prob: _Problem, assign: list[int]) -> int:
    total = sum(prob.unary[i][k] for i, k in enumerate(assign))
    for lo, hi, ordered, _ in prob.pairs:
        a, b = prob.slots[assign[lo]], prob.slots[assign[hi]]
        total += W_PAIR_DAY * min(abs(a.dayord - b.dayord), PAIR_DAY_CAP)
        if ordered and assign[lo] > assign[hi]:
            total += W_PAIR_ORDER
    return total


def _feasible(prob: _Problem, assign: list[int]) -> bool:
    if len(set(assign)) != len(assign):
        return False
    if any(k not in prob.allowed[i] for i, k in enumerate(assign)):
        return False
    for chain in prob.chains:
        if any(assign[a] >= assign[b] for a, b in zip(chain, chain[1:])):
            return False
    for t, idxs in prob.teacher_lectures.items():
        per_day = Counter(prob.slots[assign[i]].dayord for i in idxs)
        if per_day and max(per_day.values()) > prob.teacher_day_cap[t]:
            return False
        times = [(prob.slots[assign[i]].dayord, prob.slots[assign[i]].start) for i in idxs]
        if len(times) != len(set(times)):
            return False
    return True


def _solve_cpsat(prob: _Problem, time_limit: float, deterministic: bool = True,
                 hint: Optional[list[int]] = None, free: Optional[set[int]] = None,
                 ) -> tuple[Optional[list[int]], str]:
    """Compact model: pos[i] = slot of lecture i (AllDifferent), day/cost read through Element.

    ``free`` limits the search to those lectures (the rest stay at ``hint``): used for the
    week-window neighbourhoods, which CP-SAT solves far better than the whole module at once.
    """
    n = len(prob.lectures)
    model = cp_model.CpModel()
    day_of = [sl.dayord for sl in prob.slots]
    max_day = max(day_of, default=0)
    pos = []
    for i in range(n):
        if free is not None and i not in free and hint is not None:
            pos.append(model.NewConstant(hint[i]))
            continue
        values = prob.allowed[i]
        if free is not None and hint is not None:
            window = {hint[j] for j in free}
            values = [k for k in values if k in window]
        dom = cp_model.Domain.FromValues(values)
        pos.append(model.NewIntVarFromDomain(dom, f"p{i}"))
    model.AddAllDifferent(pos)
    day = [model.NewIntVar(0, max_day, f"d{i}") for i in range(n)]
    for i in range(n):
        model.AddElement(pos[i], day_of, day[i])
    for chain in prob.chains:
        for a, b in zip(chain, chain[1:]):
            model.Add(pos[a] < pos[b])
    # teacher per-day cap (same-time clash is impossible: one lecture per slot, single class)
    on_vars: dict[tuple[int, int], cp_model.IntVar] = {}
    for t, idxs in prob.teacher_lectures.items():
        cap = prob.teacher_day_cap[t]
        if len(idxs) <= cap:
            continue
        days_used = sorted(set(day_of))
        on = on_vars
        for i in idxs:
            for d in days_used:
                b = model.NewBoolVar("")
                model.Add(day[i] == d).OnlyEnforceIf(b)
                model.Add(day[i] != d).OnlyEnforceIf(b.Not())
                on[i, d] = b
        for d in days_used:
            model.Add(sum(on[i, d] for i in idxs) <= cap)
    start = hint if hint is not None else list(range(n))
    hints: list[tuple[Any, int]] = []
    obj = []
    for i in range(n):
        if free is None or i in free:
            hints.append((pos[i], start[i]))
        hints.append((day[i], day_of[start[i]]))
        costs = prob.unary[i]
        if any(costs):
            c = model.NewIntVar(min(costs), max(costs), f"c{i}")
            model.AddElement(pos[i], costs, c)
            obj.append(c)
            hints.append((c, costs[start[i]]))
    for lo, hi, ordered, _ in prob.pairs:
        dl, dh = day_of[start[lo]], day_of[start[hi]]
        diff = model.NewIntVar(-max_day, max_day, "")
        model.Add(diff == day[lo] - day[hi])
        dist = model.NewIntVar(0, max_day, "")
        model.AddAbsEquality(dist, diff)
        capped = model.NewIntVar(0, PAIR_DAY_CAP, "")
        model.AddMinEquality(capped, [dist, model.NewConstant(PAIR_DAY_CAP)])
        obj.append(W_PAIR_DAY * capped)
        hints += [(diff, dl - dh), (dist, abs(dl - dh)), (capped, min(abs(dl - dh), PAIR_DAY_CAP))]
        if ordered:
            wrong = model.NewBoolVar("")
            model.Add(pos[lo] < pos[hi]).OnlyEnforceIf(wrong.Not())
            obj.append(W_PAIR_ORDER * wrong)
            hints.append((wrong, int(start[lo] > start[hi])))
    model.Minimize(sum(obj))
    # Start from the uploaded timetable (or a greedy improvement of it): always feasible.
    for var, val in hints:
        model.AddHint(var, val)
    for (i, d), b in on_vars.items():
        model.AddHint(b, int(day_of[start[i]] == d))

    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 4
    solver.parameters.random_seed = 7
    if deterministic:
        # Deterministic work budget + interleaved search: the same upload always gives the same plan,
        # so weeks requested one at a time (even from another server instance) come from one module
        # plan. The wall-clock cap is only a safety net on a very slow machine.
        solver.parameters.max_deterministic_time = time_limit
        solver.parameters.interleave_search = True
        solver.parameters.max_time_in_seconds = time_limit * 4
    else:
        solver.parameters.max_time_in_seconds = time_limit
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None, solver.StatusName(status)
    return [solver.Value(p) for p in pos], solver.StatusName(status)


def _solve_greedy(prob: _Problem, start: list[int], rounds: int = 3) -> list[int]:
    """Pairwise-swap descent from a feasible assignment (fallback when CP-SAT gives nothing)."""
    best = list(start)
    best_cost = _objective(prob, best)
    n = len(best)
    for _ in range(rounds):
        improved = False
        for i in range(n):
            for j in range(i + 1, n):
                cand = list(best)
                cand[i], cand[j] = cand[j], cand[i]
                if cand[i] not in prob.allowed[i] or cand[j] not in prob.allowed[j]:
                    continue
                c = _objective(prob, cand)
                if c < best_cost and _feasible(prob, cand):
                    best, best_cost, improved = cand, c, True
        if not improved:
            break
    return best


def _optimise(prob: _Problem, time_limit: float) -> tuple[list[int], str]:
    """Greedy swaps from the upload, then CP-SAT over sliding two-week windows (cross-week moves)."""
    t0 = time.monotonic()
    ident = list(range(len(prob.lectures)))
    base_ok = _feasible(prob, ident)
    current = _solve_greedy(prob, ident) if base_ok else ident
    status = "GREEDY"
    weeks = sorted({sl.week for sl in prob.slots})
    windows = [set(weeks[k:k + 2]) for k in range(max(1, len(weeks) - 1))]
    # deterministic work units per window; ~1 unit is ~1 s on a 4-core machine
    per_window = max(0.3, (time_limit - (time.monotonic() - t0)) / max(1, len(windows)) * 0.8)
    solved_any = False
    for win in windows:
        if time.monotonic() - t0 > time_limit * 1.5:
            break
        free = {i for i, k in enumerate(current) if prob.slots[k].week in win}
        if len(free) < 2:
            continue
        cand, st = _solve_cpsat(prob, per_window, hint=current, free=free)
        if cand is not None and _feasible(prob, cand) and _objective(prob, cand) <= _objective(prob, current):
            current, solved_any = cand, True
            status = st
    if solved_any:
        status = f"CP-SAT {status} (week windows)"
    if base_ok and _objective(prob, current) > _objective(prob, ident):
        current, status = ident, "UPLOADED_ORIGINAL"  # never worse than the upload
    return current, status


# ---------------------------------------------------------------------------
# Metrics, moves
# ---------------------------------------------------------------------------


def _endpoint_points(ep: _Endpoint, prob: _Problem, assign: list[int]) -> list[tuple[int, int, int]]:
    pts = list(ep.fixed)
    for i in ep.lectures:
        sl = prob.slots[assign[i]]
        pts.append((sl.dayord, _min(sl.start), sl.week))
    return pts


def _link_metrics(prob: _Problem, assign: list[int]) -> dict[str, Any]:
    dists, same_week, within2, same_day, in_order = [], 0, 0, 0, 0
    for link, a, b in prob.links:
        pa, pb = _endpoint_points(a, prob, assign), _endpoint_points(b, prob, assign)
        best = min(((abs(x[0] - y[0]), x, y) for x in pa for y in pb), key=lambda t: t[0])
        d, x, y = best
        dists.append(d)
        same_week += int(x[2] == y[2])
        within2 += int(d <= 2)
        same_day += int(d == 0)
        ta, tb = integration_tier(a.discipline), integration_tier(b.discipline)
        if ta == tb:
            in_order += 1
        else:
            first_a, first_b = min(pa), min(pb)
            in_order += int((first_a < first_b) == (ta < tb))
    n = len(dists) or 1
    return {
        "linked_pairs": len(dists),
        "avg_day_distance": round(sum(dists) / n, 2),
        "same_week_pct": round(100 * same_week / n, 1),
        "within_2_days_pct": round(100 * within2 / n, 1),
        "same_day_pct": round(100 * same_day / n, 1),
        "logical_order_pct": round(100 * in_order / n, 1),
    }


def _moves(prob: _Problem, assign: list[int]) -> list[dict[str, Any]]:
    ident = list(range(len(prob.lectures)))
    partners: dict[int, list[tuple[_Endpoint, _Endpoint]]] = defaultdict(list)
    for _, a, b in prob.links:
        for i in a.lectures:
            partners[i].append((a, b))
        for i in b.lectures:
            partners[i].append((b, a))
    moves: list[dict[str, Any]] = []
    for i, k in enumerate(assign):
        if k == i:
            continue
        lec, src, dst = prob.lectures[i], prob.slots[i], prob.slots[k]
        near: list[tuple[int, str]] = []
        for own, other in partners.get(i, []):
            new_pts = _endpoint_points(other, prob, assign)
            old_pts = _endpoint_points(other, prob, ident)
            d_new = min(abs(dst.dayord - p[0]) for p in new_pts)
            d_old = min(abs(src.dayord - p[0]) for p in old_pts)
            if d_new <= 2 and d_new < d_old:
                near.append((d_new, other.label))
        uniq: dict[str, tuple[int, str]] = {}
        for d, lab in sorted(near):
            uniq.setdefault(lab.lower(), (d, lab))
        near = sorted(uniq.values())[:3]
        if near:
            when = {0: "same day", 1: "next/previous day", 2: "two days apart"}
            reason = "Now sits with " + "; ".join(f"{lab} ({when[d]})" for d, lab in near)
        elif partners.get(i):
            reason = "Shifted to make room for linked topics; its subject's topic order is kept"
        else:
            reason = "Shifted to free its slot for a linked topic; its subject's topic order is kept"
        moves.append({
            "session_id": str(lec.id) if lec.id else None,
            "topic_title": lec.topic_title,
            "discipline": lec.discipline,
            "session_type": lec.session_type.value,
            "faculty_name": " / ".join(lec.faculty_names) or None,
            "from_week": src.week, "from_day": src.day, "from_date": src.date,
            "from_start": src.start, "from_end": src.end, "from_label": src.label(),
            "to_week": dst.week, "to_day": dst.day, "to_date": dst.date,
            "to_start": dst.start, "to_end": dst.end, "to_label": dst.label(),
            "week_shift": dst.week - src.week,
            "linked_with": [lab for _, lab in near],
            "reason": reason,
        })
    moves.sort(key=lambda m: (m["to_week"], m["to_day"], m["to_start"]))
    return moves


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_CACHE: dict[str, TemplateResult] = {}
_CACHE_MAX = 16


def _cache_key(*parts: Any) -> str:
    raw = json.dumps(parts, default=str, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def integrate_template(
    sessions: list[ParsedSession],
    links: list[ProposedLink],
    topics: Optional[list[ParsedTopic]] = None,
    cohort: Optional[str] = None,
    max_week_shift: Optional[int] = None,
    time_limit_seconds: float = 20.0,
    busy: Optional[dict[str, list[tuple[str, int, int]]]] = None,
    integrate: bool = True,
) -> TemplateResult:
    """Re-sequence one class's movable lectures inside its real timetable (see module docstring)."""
    own = sessions_for(sessions, cohort)
    topics = topics or []
    approved = [l for l in links if l.is_approved]
    key = _cache_key(
        [s.model_dump(mode="json", include={"id", "week", "day_of_week", "time_start", "time_end", "discipline",
                                            "topic_title", "faculty_names", "kind", "session_type", "topic_id"})
         for s in own],
        [l.model_dump(mode="json", include={"source_objective_id", "target_objective_id", "source_topic",
                                            "target_topic", "source_discipline", "target_discipline",
                                            "source_cohort", "target_cohort"}) for l in approved],
        cohort, max_week_shift, round(time_limit_seconds, 1), sorted((busy or {}).items()), integrate,
    )
    if key in _CACHE:
        return _CACHE[key]

    prob, dayords, warnings = _build_problem(own, approved, topics, cohort, max_week_shift, busy)
    ident = list(range(len(prob.lectures)))
    status = "UPLOADED_ORIGINAL"
    assign = ident
    if integrate and prob.lectures:
        assign, status = _optimise(prob, time_limit_seconds)
    week_dates: dict[int, dict[int, str]] = defaultdict(dict)
    for s in own:
        if s.date:
            week_dates[s.week].setdefault(s.day_of_week, s.date)
    res = TemplateResult(
        cohort=cohort, sessions=own, slots=prob.slots, lectures=prob.lectures, assignment=assign,
        moves=_moves(prob, assign) if integrate else [],
        metrics={"before": _link_metrics(prob, ident), "after": _link_metrics(prob, assign),
                 "moved_lectures": sum(1 for i, k in enumerate(assign) if i != k),
                 "cross_week_moves": sum(1 for i, k in enumerate(assign) if prob.slots[i].week != prob.slots[k].week),
                 "movable_lectures": len(prob.lectures),
                 "max_week_shift": max_week_shift},
        status=status, dayords=dayords, week_dates=dict(week_dates), warnings=warnings,
        link_labels=[(a.label, b.label) for _, a, b in prob.links],
    )
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = res
    return res


def teacher_busy_from(result: TemplateResult) -> dict[str, list[tuple[str, int, int]]]:
    """Every (date, start, end) each teacher teaches in this class's integrated timetable."""
    out: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
    for s, (week, day, date, start, end) in placed_sessions(result):
        key_day = date or f"w{week}d{day}"
        for n in _teachers_of(s):
            out[_teacher_key(n)].append((key_day, _min(start), _min(end)))
    return out


def placed_sessions(result: TemplateResult) -> Iterable[tuple[ParsedSession, tuple[int, int, Optional[str], str, str]]]:
    """Every session of the class with its (week, day, date, start, end) after integration."""
    moved_to = {id(lec): result.slots[k] for lec, k in zip(result.lectures, result.assignment)}
    for s in result.sessions:
        sl = moved_to.get(id(s))
        if sl is not None:
            yield s, (sl.week, sl.day, sl.date, sl.start, sl.end)
        else:
            date = result.week_dates.get(s.week, {}).get(s.day_of_week) or s.date
            yield s, (s.week, s.day_of_week, date, s.time_start, s.time_end)


def _cell_from_session(s: ParsedSession, week: int, day: int, date: Optional[str], start: str, end: str,
                       moved_from: Optional[str]) -> dict[str, Any]:
    from app.services.solver import BatchStationAssignment, ScheduledCell  # local: avoid import cycle

    batches = []
    for b in s.batches:
        label = b.station + (f" ({b.topic_title})" if b.topic_title and s.kind == "ROTATION" else "")
        batches.append(BatchStationAssignment(
            batch="Batch " + ", ".join(b.batches) if len(b.batches) == 1 else "Batches " + ", ".join(b.batches),
            station=label, faculty=" / ".join(b.faculty_names) or None,
        ))
    if s.kind == "ROTATION":
        faculty = None
        venue = "Labs (batch rotation)" if s.session_type.value == "PRACTICAL" else "SGD rooms (batch rotation)"
    else:
        faculty = " / ".join(s.faculty_names) or None
        venue = None
    return ScheduledCell(
        day_of_week=day, day_name=DAYS.get(day, "MONDAY"), time_start=start, time_end=end,
        session_type=s.session_type.value, discipline=s.discipline,
        category=s.category if s.kind != "EVENT" else "INSTITUTIONAL",
        topic_title=s.topic_title, faculty_name=faculty, venue_name=venue,
        batch_assignments=batches, topic_id=s.topic_id, date=date, kind=s.kind, session_id=s.id,
        moved_from=moved_from,
    )


def _institutional_cells(day_sessions: dict[int, list[tuple[str, str]]], week_dates: dict[int, str]) -> list[Any]:
    """BREAK (12:00-12:30) each teaching day, HALF DAY on a Friday with nothing after 12:00."""
    from app.services.solver import ScheduledCell

    cells = []
    for day, spans in day_sessions.items():
        afternoon = any(_min(s) >= 12 * 60 for s, _ in spans)
        if day == FRIDAY and not afternoon:
            cells.append(ScheduledCell(day_of_week=day, day_name=DAYS[day], time_start="12:00", time_end="14:00",
                                       session_type="HALF_DAY", discipline="Institutional",
                                       category="INSTITUTIONAL", topic_title="HALF DAY", date=week_dates.get(day),
                                       kind="EVENT"))
        elif not any(_min(s) < 12 * 60 + 30 and _min(e) > 12 * 60 for s, e in spans):
            cells.append(ScheduledCell(day_of_week=day, day_name=DAYS[day], time_start="12:00", time_end="12:30",
                                       session_type="BREAK", discipline="Institutional",
                                       category="INSTITUTIONAL", topic_title="BREAK", date=week_dates.get(day),
                                       kind="EVENT"))
    return cells


def week_schedule(
    result: TemplateResult,
    week_number: int,
    module_code: str,
    module_title: str,
    academic_year: int,
    program: str,
    session: Optional[str],
    original: bool = False,
):
    """One week of the class's timetable in the client's structure (dates, real times, rotations)."""
    from app.services.solver import TimetableSchedule, clean_session, recompute_schedule_analytics

    total = result.total_weeks
    week = max(1, min(week_number, total))
    moved_to = {id(lec): result.slots[k] for lec, k in zip(result.lectures, result.assignment)}
    orig_slot = {id(lec): result.slots[i] for i, lec in enumerate(result.lectures)}
    week_dates = result.week_dates.get(week, {})
    cells = []
    spans: dict[int, list[tuple[str, str]]] = defaultdict(list)
    if original:
        placed = ((s, (s.week, s.day_of_week, result.week_dates.get(s.week, {}).get(s.day_of_week) or s.date,
                       s.time_start, s.time_end)) for s in result.sessions)
    else:
        placed = placed_sessions(result)
    for s, (w, d, date, start, end) in placed:
        if w != week:
            continue
        moved_from = None
        if not original and id(s) in moved_to and moved_to[id(s)].idx != orig_slot[id(s)].idx:
            moved_from = orig_slot[id(s)].label()
        cells.append(_cell_from_session(s, w, d, date, start, end, moved_from))
        spans[d].append((start, end))
    cells.extend(_institutional_cells(spans, week_dates))
    cells.sort(key=lambda c: (c.day_of_week, _min(c.time_start)))

    if not original:
        _tag_links(result, week, cells)
    cohort = result.cohort
    sched = TimetableSchedule(
        module_code=module_code, module_title=module_title, academic_year=academic_year,
        week_number=week, total_weeks=total, session=clean_session(session), cells=cells,
        solver_status="UPLOADED_ORIGINAL" if original else result.status, total_contact_hours=0.0,
        program=program, cohort=cohort, cohort_label=cohort_label(cohort) if cohort else None,
        template=True, week_dates={d: v for d, v in week_dates.items()},
        moves=[] if original else result.moves,
        integration_metrics=result.metrics,
    )
    return recompute_schedule_analytics(sched)


def _tag_links(result: TemplateResult, week: int, cells: list[Any]) -> None:
    """Attach '↔ Physiology: Cerebellum (Tue 09:00)' notes to lectures whose linked topic is taught
    the same week (lecture, whole-class SGD or practical/SGD station)."""
    def key(label: str) -> str:
        disc, _, title = label.partition(": ")
        return f"{disc}|{_norm(title)}"

    points: dict[str, list[tuple[int, int, str]]] = defaultdict(list)
    for s, (w, d, _date, start, _end) in placed_sessions(result):
        if s.kind == "TEACHING":
            points[key(f"{s.discipline}: {s.topic_title}")].append((w, d, start))
        elif s.kind == "ROTATION":
            for b in s.batches:
                if b.topic_title:
                    points[key(f"{b.discipline}: {b.topic_title}")].append((w, d, start))
    partners: dict[str, list[str]] = defaultdict(list)
    for a, b in result.link_labels:
        partners[key(a)].append(b)
        partners[key(b)].append(a)
    for c in cells:
        if c.kind != "TEACHING":
            continue
        tags: list[str] = []
        for lab in partners.get(key(f"{c.discipline}: {c.topic_title}"), []):
            here = sorted(p for p in points.get(key(lab), []) if p[0] == week)
            if not here:
                continue
            _, d, start = here[0]
            tag = f"↔ {lab} ({_DAY_ABBR.get(d, d)} {start})"
            if tag.lower() not in {t.lower() for t in tags}:
                tags.append(tag)
        c.integration_tags = tags[:6]
