"""Upload-form fields: program/year fallback, module override and academic session.

Runs under pytest or directly:  python tests/test_upload_fields.py   (from backend/)
"""
from __future__ import annotations

import io
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import docx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import parser  # noqa: E402

client = TestClient(app)
SAMPLE = ROOT.parent / "docs" / "sample_timetable.docx"
FIXTURES = ROOT / "tests" / "fixtures"

PASTED = """TIMETABLE FOR 3RD YEAR MBBS
CARDIOVASCULAR BLOCK-II (MODULE-04) (WEEK-01)
SESSION: 2025 – 2026

Anatomy | LGIS | Heart chambers and valves | Dr. Ali
Physiology | LGIS | Cardiac cycle | Dr. Sara
"""

NO_HEADER = """Anatomy | LGIS | Heart chambers and valves | Dr. Ali
Physiology | LGIS | Cardiac cycle | Dr. Sara
"""


def _ingest_text(text: str, **extra) -> dict:
    res = client.post("/api/ingest/text", json={"text": text, "use_llm": False, **extra})
    assert res.status_code == 200, res.text
    return res.json()


def _header_lines(content: bytes) -> list[str]:
    return [p.text for p in docx.Document(io.BytesIO(content)).paragraphs[:2]]


def test_session_parsed_from_module_header_of_sample_docx() -> None:
    res = client.post(
        "/api/ingest/file",
        files={"file": ("sample_timetable.docx", SAMPLE.read_bytes())},
        data={"use_llm": "false"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["meta"]["session"] == "2026-2027"
    assert body["meta"]["module_title"] == "NEUROSCIENCES BLOCK-IV"
    assert body["meta"]["module_code"] == "MODULE-07"
    cohort = body["cohorts"][0]
    assert cohort["session"] == "2026-2027"
    assert cohort["class_detected"] is True


def test_session_parsed_from_standalone_line_and_normalized() -> None:
    meta = parser.parse_header(["TIMETABLE FOR 3RD YEAR MBBS", "SESSION: 2025 – 2026"])
    assert meta.session == "2025-2026"
    body = _ingest_text(PASTED)
    assert body["meta"]["session"] == "2025-2026"
    assert body["meta"]["module_code"] == "MODULE-04"


def test_text_without_header_uses_form_defaults_and_is_not_detected() -> None:
    body = _ingest_text(NO_HEADER, program="BDS", academic_year=1)
    assert body["meta"]["session"] is None
    cohort = body["cohorts"][0]
    assert (cohort["program"], cohort["academic_year"]) == ("BDS", 1)
    assert cohort["class_detected"] is False


def test_generate_and_export_use_provided_session_and_module() -> None:
    topics = _ingest_text(PASTED)["topics"]
    payload = {
        "topics": topics,
        "module_code": "MODULE-09",
        "module_title": "Custom Block-X",
        "academic_year": 3,
        "session": "2030-2031",
    }
    sched = client.post("/api/schedule/generate", json=payload).json()
    assert sched["session"] == "2030-2031"
    assert sched["module_title"] == "Custom Block-X"
    original = client.post("/api/schedule/original", json=payload).json()
    assert original["session"] == "2030-2031"

    d = client.post("/api/export/docx", json={"schedule": sched, "legend_entries": []})
    assert d.status_code == 200
    lines = _header_lines(d.content)
    assert lines[0] == "TIMETABLE FOR 3RD YEAR MBBS"
    assert lines[1] == "CUSTOM BLOCK-X (MODULE-09) (WEEK-01) (SESSION 2030-2031)"


def test_blank_session_falls_back_to_default() -> None:
    topics = _ingest_text(NO_HEADER)["topics"]
    sched = client.post(
        "/api/schedule/generate", json={"topics": topics, "module_code": "MODULE-01",
                                        "module_title": "Integrated Module", "session": "   "}
    ).json()
    assert sched["session"] == "2026-2027"
    d = client.post("/api/export/docx", json={"schedule": sched, "legend_entries": []})
    assert _header_lines(d.content)[1].endswith("(SESSION 2026-2027)")


def test_generate_all_keeps_per_class_module_and_session() -> None:
    files = ["MBBS_Year2_CardioRenal.docx", "BDS_Year1_HeadNeck.txt"]
    parse = client.post(
        "/api/ingest/batch",
        files=[("files", (f, (FIXTURES / f).read_bytes())) for f in files],
        data={"use_llm": "false"},
    ).json()
    cohorts = parse["cohorts"]
    assert len(cohorts) == 2
    modules = {c["cohort"]: {"module_title": c["module_title"], "module_code": c["module_code"]} for c in cohorts}
    modules[cohorts[0]["cohort"]]["session"] = "2031-2032"
    res = client.post("/api/schedule/generate-all", json={
        "topics": parse["topics"], "module_code": "MODULE-01", "module_title": "INTEGRATED MODULE",
        "session": "2029-2030", "cohort_modules": modules,
    }).json()
    by = {s["cohort"]: s for s in res["schedules"]}
    for c in cohorts:
        expected_title = c["module_title"] or "INTEGRATED MODULE"
        assert by[c["cohort"]]["module_title"] == expected_title
    assert by[cohorts[0]["cohort"]]["session"] == "2031-2032"
    assert by[cohorts[1]["cohort"]]["session"] == "2029-2030"


def main() -> None:
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n>>> {len(tests)} UPLOAD FIELD TESTS PASSED <<<")


if __name__ == "__main__":
    main()
