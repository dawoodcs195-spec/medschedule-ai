"""Real-timetable scheduling on the client's (anonymised) 2nd Year MBBS Neurosciences module.

Fixture: tests/fixtures/real_neuro_module07.docx — the client's real 7-week timetable with every
teacher name replaced by a code ('Dr. T01' ...); built by tests/fixtures/make_real_fixture.py.

Checks: exact parse counts, key integration links, and the template scheduler's guarantees:
practical/SGD rotations and events never move, only 1-hour lectures are re-sequenced inside the
module's existing lecture slots, each lecture keeps its teacher, no teacher is in two places at
once, every subject keeps its own topic order, and linked topics end up closer than in the upload.

Runs under pytest or directly:  python tests/test_real_timetable.py   (from backend/)
"""
from __future__ import annotations

import io
import pathlib
import re
import sys
from collections import defaultdict
from functools import lru_cache

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import docx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.models.schemas import ParsedSession, ParsedTopic  # noqa: E402
from app.services import integrator, template_solver  # noqa: E402
from app.services.integrator import ProposedLink  # noqa: E402

client = TestClient(app)
FIXTURE = ROOT / "tests" / "fixtures" / "real_neuro_module07.docx"
TIME_LIMIT = template_solver.DEFAULT_TEMPLATE_TIME_LIMIT


def _m(t: str) -> int:
    h, mm = t.split(":")
    return int(h) * 60 + int(mm)


@lru_cache(maxsize=1)
def parsed() -> dict:
    res = client.post(
        "/api/ingest/file",
        files={"file": ("real_neuro_module07.docx", FIXTURE.read_bytes())},
        data={"use_llm": "false"},
    )
    assert res.status_code == 200, res.text
    return res.json()


@lru_cache(maxsize=1)
def links() -> list[dict]:
    res = client.post("/api/integrate/cluster", json={"topics": parsed()["topics"]})
    assert res.status_code == 200, res.text
    return res.json()["links"]


def _models():
    p = parsed()
    return ([ParsedSession.model_validate(s) for s in p["sessions"]],
            [ParsedTopic.model_validate(t) for t in p["topics"]],
            [ProposedLink.model_validate(l) for l in links()])


@lru_cache(maxsize=2)
def solved(max_week_shift: int | None = None) -> template_solver.TemplateResult:
    sessions, topics, lks = _models()
    cohort = template_solver.resolve_cohort(sessions, parsed()["cohorts"][0]["cohort"])
    return template_solver.integrate_template(sessions, lks, topics, cohort=cohort,
                                              max_week_shift=max_week_shift, time_limit_seconds=TIME_LIMIT)


def placed(result: template_solver.TemplateResult):
    return list(template_solver.placed_sessions(result))


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------

def test_parse_counts():
    p = parsed()
    s = p["sessions"]
    weeks = sorted({x["week"] for x in s})
    assert weeks == list(range(1, 8))
    dates = sorted(x["date"] for x in s if x["date"])
    assert dates[0] == "2026-10-26" and dates[-1] == "2026-12-12"
    lgis = [x for x in s if x["kind"] == "TEACHING" and x["session_type"] == "LGIS"]
    assert len(lgis) == 98
    assert sum(1 for x in s if x["kind"] == "ROTATION" and x["session_type"] == "PRACTICAL") == 28
    assert sum(1 for x in s if x["kind"] == "ROTATION" and x["session_type"] == "SGD") == 28
    assert {x["session_type"] for x in s if x["kind"] == "EVENT"} >= {"SDL", "MENTOR_MENTEE", "PAL"}
    assert len(p["faculty"]) == 43
    assert all(re.fullmatch(r"Dr\. T\d\d", f) for f in p["faculty"])
    assert sum(1 for x in s if x["movable"]) == 105  # 98 LGIS + 7 DSL, all 1 hour
    # split afternoon and 2-hour morning blocks are read with their real times
    spans = {(x["time_start"], x["time_end"]) for x in s}
    assert {("12:30", "13:30"), ("13:30", "14:00"), ("08:00", "10:00"), ("09:00", "11:00")} <= spans


def _linked(a: str, b: str) -> bool:
    for l in links():
        A = f"{l['source_discipline']}: {l['source_topic']}"
        B = f"{l['target_discipline']}: {l['target_topic']}"
        if (re.search(a, A) and re.search(b, B)) or (re.search(a, B) and re.search(b, A)):
            return True
    return False


def test_key_links():
    assert _linked(r"Neuroanatomy: Spinal cord \(External", r"Histology: Spinal Cord$")
    assert _linked(r"Neuroanatomy: Cerebellum", r"Physiology: Cerebellum")
    assert _linked(r"Neuroanatomy: Blood supply of the brain", r"Medicine: Stroke|Surgery: Stroke")
    assert _linked(r"Community Medicine: Meningitis", r"Medicine: Acute bacterial meningitis")
    assert _linked(r"Neuroanatomy: Ascending Tracts", r"Physiology: Ascending pathway")
    assert not _linked(r"Biochemistry: Bioenergetics", r".*")
    assert not _linked(r"Research \(RIPPLE\)", r".*")


# ---------------------------------------------------------------------------
# Template scheduler
# ---------------------------------------------------------------------------

def test_fixed_sessions_never_move():
    r = solved()
    for s, (week, day, _date, start, end) in placed(r):
        if not template_solver._is_movable(s):
            assert (week, day, start, end) == (s.week, s.day_of_week, s.time_start, s.time_end), s.topic_title


def test_same_lecture_slots_and_teachers():
    r = solved()
    orig = sorted((s.week, s.day_of_week, s.time_start, s.time_end) for s in r.lectures)
    new = sorted((w, d, st, en) for s, (w, d, _x, st, en) in placed(r) if template_solver._is_movable(s))
    assert orig == new  # same slot set, same capacity
    assert len(set(r.assignment)) == len(r.assignment) == len(r.lectures)


def test_no_teacher_clash():
    r = solved()
    busy: dict[str, list[tuple[str, int, int, str]]] = defaultdict(list)
    for s, (w, d, date, start, end) in placed(r):
        names = set(s.faculty_names) | {n for b in s.batches for n in b.faculty_names}
        for n in names:
            busy[n].append((date or f"{w}-{d}", _m(start), _m(end), s.topic_title))
    for teacher, slots in busy.items():
        slots.sort()
        for a, b in zip(slots, slots[1:]):
            assert not (a[0] == b[0] and b[1] < a[2]), f"{teacher} double-booked: {a} / {b}"


def test_subject_topic_order_kept():
    r = solved()
    by_disc_orig: dict[str, list[str]] = defaultdict(list)
    for lec in r.lectures:  # already in original order
        by_disc_orig[lec.discipline].append(str(lec.id))
    new_pos = {str(lec.id): k for lec, k in zip(r.lectures, r.assignment)}
    for disc, ids in by_disc_orig.items():
        assert [new_pos[i] for i in ids] == sorted(new_pos[i] for i in ids), disc
    # spot checks from the client's wording
    titles = [lec.topic_title for lec, _ in sorted(zip(r.lectures, r.assignment), key=lambda x: x[1])]
    bio = [t for t in titles if t.startswith("Bioenergetics")]
    assert bio == sorted(bio, key=len)  # I -> II -> III


def test_metrics_improve_and_moves_explained():
    r = solved()
    before, after = r.metrics["before"], r.metrics["after"]
    assert before["linked_pairs"] == after["linked_pairs"] > 150
    assert after["avg_day_distance"] < before["avg_day_distance"]
    assert after["within_2_days_pct"] > before["within_2_days_pct"] + 5
    assert after["same_week_pct"] >= before["same_week_pct"]
    assert r.moves and all(m["reason"] for m in r.moves)
    assert any(m["week_shift"] != 0 for m in r.moves)  # cross-week moves are allowed
    assert any(m["linked_with"] for m in r.moves)


def test_max_week_shift_zero_keeps_weeks():
    r = solved(0)
    assert all(m["week_shift"] == 0 for m in r.moves)
    assert r.metrics["after"]["avg_day_distance"] <= r.metrics["before"]["avg_day_distance"]


def test_deterministic_plan():
    sessions, topics, lks = _models()
    cohort = template_solver.resolve_cohort(sessions, parsed()["cohorts"][0]["cohort"])
    template_solver._CACHE.clear()
    again = template_solver.integrate_template(sessions, lks, topics, cohort=cohort, time_limit_seconds=TIME_LIMIT)
    assert again.assignment == solved().assignment


# ---------------------------------------------------------------------------
# API, report, export
# ---------------------------------------------------------------------------

def _body(week: int) -> dict:
    p = parsed()
    return dict(topics=p["topics"], sessions=p["sessions"], approved_links=links(), week_number=week,
                cohort=p["cohorts"][0]["cohort"], module_code="MODULE-07", module_title="NEUROSCIENCES BLOCK-IV")


def test_api_generate_original_and_all():
    gen = client.post("/api/schedule/generate", json=_body(1))
    assert gen.status_code == 200, gen.text
    g = gen.json()
    assert g["template"] and g["total_weeks"] == 7 and g["moves"]
    assert g["integration_metrics"]["after"]["avg_day_distance"] < g["integration_metrics"]["before"]["avg_day_distance"]
    assert g["week_dates"]["1"] == "2026-10-26"
    assert any(c["moved_from"] for c in g["cells"])
    assert sum(1 for c in g["cells"] if c["kind"] == "ROTATION") == 8  # week 1: 4 practical + 4 SGD blocks
    o = client.post("/api/schedule/original", json=_body(1)).json()
    assert o["solver_status"] == "UPLOADED_ORIGINAL" and not o["moves"]
    assert not any(c["moved_from"] for c in o["cells"])
    a = client.post("/api/schedule/generate-all", json=_body(1))
    assert a.status_code == 200, a.text
    assert a.json()["schedules"][0]["template"]


def test_report_counts_rotation_teachers():
    p = parsed()
    rep = client.post("/api/analytics/report", json=dict(topics=p["topics"], links=links(), sessions=p["sessions"])).json()
    station_teachers = {n for s in p["sessions"] if s["kind"] == "ROTATION" for b in s["batches"] for n in b["faculty_names"]}
    reported = {t["faculty"] for t in rep["teachers"]}
    assert station_teachers <= reported
    assert rep["totals"]["teachers"] == 43
    assert any(s["discipline"] == "Histology" and s["classes"] > 20 for s in rep["subjects"])


def test_export_keeps_split_afternoon():
    g = client.post("/api/schedule/generate", json=_body(4)).json()  # week 4 has 12:30-01:30 + 01:30-02:00
    res = client.post("/api/export/docx", json={"schedule": g, "legend_entries": parsed()["legend"]})
    assert res.status_code == 200
    table = docx.Document(io.BytesIO(res.content)).tables[0]
    headers = [c.text for c in table.rows[0].cells]
    assert "12:30 – 01:30" in headers and "01:30 – 02:00" in headers
    text = " ".join(c.text for row in table.rows for c in row.cells)
    for cell in g["cells"]:
        assert cell["topic_title"] in text, cell["topic_title"]


def main() -> None:
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n>>> {len(tests)} REAL TIMETABLE TESTS PASSED <<<")


if __name__ == "__main__":
    main()
