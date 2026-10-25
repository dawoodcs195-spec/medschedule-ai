"""Acceptance tests for the client's requirements (offline: no database, no API key).

R1 multi-class upload · R2 horizontal/vertical topic matching · R3 integrated sequencing ·
R4 Copilot teacher/slot edits · R5 per-subject / per-teacher / per-topic counts · R6 exports.

Run from backend/:  python tests/test_client_requirements.py
"""
from __future__ import annotations

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)
FIXTURES = ROOT / "tests" / "fixtures"
FILES = ["MBBS_Year2_CardioRenal.docx", "MBBS_Year4_SpecialSenses.xlsx", "BDS_Year1_HeadNeck.txt"]
SLOT = {"08:00": 0, "09:00": 1, "10:00": 2, "11:00": 3}


def ok(cond: bool, msg: str) -> None:
    assert cond, msg
    print(f"  ✓ {msg}")


def has_link(links, a: str, b: str, kind: str | None = None) -> bool:
    for l in links:
        pair = {l["source_topic"], l["target_topic"]}
        if a in pair and b in pair and (kind is None or l["integration_type"] == kind):
            return True
    return False


def lectures(schedule):
    return [c for c in schedule["cells"] if not c["batch_assignments"] and c["session_type"] not in ("BREAK", "HALF_DAY")]


def find(schedule, title):
    return [c for c in lectures(schedule) if c["topic_title"] == title]


def main() -> None:
    print("R1 · upload several classes at once")
    res = client.post(
        "/api/ingest/batch",
        files=[("files", (f, (FIXTURES / f).read_bytes())) for f in FILES],
        data={"use_llm": "false"},
    )
    assert res.status_code == 200, res.text
    parse = res.json()
    cohorts = {c["cohort"]: c for c in parse["cohorts"]}
    ok(set(cohorts) == {"MBBS-2", "MBBS-4", "BDS-1"}, "classes read from headers: MBBS-2, MBBS-4 (xlsx), BDS-1 (txt)")
    ok(all(t["cohort"] in cohorts for t in parse["topics"]), "every topic is tagged with its class")
    cc = next(t for t in parse["topics"] if t["topic_title"] == "Cardiac cycle")
    ok(cc["occurrences"] == 2, "a topic taught twice is counted twice (Cardiac cycle × 2)")

    two_in_one = client.post("/api/ingest/text", json={
        "text": (FIXTURES / "BDS_Year1_HeadNeck.txt").read_text()
        + "\nTIMETABLE FOR 3RD YEAR BDS\nOral Pathology | LGIS | Dental caries | Dr. Imran\n",
        "use_llm": False,
    }).json()
    ok({c["cohort"] for c in two_in_one["cohorts"]} == {"BDS-1", "BDS-3"}, "two classes pasted together are split by header")

    print("R2 · horizontal (same class) and vertical (across years) links")
    t0 = time.time()
    cl = client.post("/api/integrate/cluster", json={"topics": parse["topics"]}).json()
    links = cl["links"]
    ok(time.time() - t0 < 3, f"{len(links)} links proposed offline in {time.time() - t0:.2f}s ({cl['embedding_engine']})")
    for a, b in [
        ("Heart chambers and valves", "Cardiac cycle"),
        ("Kidney gross structure and relations", "Renal filtration and GFR"),
        ("Histology of peripheral nerve", "Nerve conduction and action potential"),
        ("Bronchopulmonary segments of lung", "Gas exchange in lungs"),
        ("Diabetes mellitus: diagnosis and management", "Diabetic retinopathy"),
        ("Diabetes mellitus: diagnosis and management", "Diabetic foot"),
        ("Hypertension: diagnosis and management", "Hypertensive retinopathy"),
        ("Thyroid disorders: hyper and hypothyroidism", "Thyroid swelling and goitre: surgical management"),
        ("Parotid and submandibular salivary glands", "Saliva composition and secretion"),
    ]:
        ok(has_link(links, a, b, "HORIZONTAL"), f"horizontal: {a} ↔ {b}")
    for a, b in [
        ("Glucose metabolism and glycolysis", "Diabetes mellitus: diagnosis and management"),
        ("Regulation of blood pressure", "Hypertension: diagnosis and management"),
        ("Coronary arteries", "Ischaemic heart disease and angina"),
    ]:
        ok(has_link(links, a, b, "VERTICAL"), f"vertical: {a} (MBBS-2) → {b} (MBBS-4)")
    for a, b in [
        ("Muscles of mastication", "Histology of cardiac muscle"),
        ("Regulation of blood pressure", "Glucose metabolism and glycolysis"),
        ("Acute appendicitis", "Diabetic foot"),
        ("Cataract", "Diabetes mellitus: diagnosis and management"),
    ]:
        ok(not has_link(links, a, b), f"no false link: {a} / {b}")
    ok(all(l["source_cohort"] == l["target_cohort"] for l in links if l["integration_type"] == "HORIZONTAL"),
       "horizontal links never cross classes")

    print("R3 · integrated timetables for every class")
    ga = client.post("/api/schedule/generate-all", json={
        "topics": parse["topics"], "approved_links": links, "week_number": 1,
    })
    assert ga.status_code == 200, ga.text
    by_cohort = {s["cohort"]: s for s in ga.json()["schedules"]}
    ok(set(by_cohort) == set(cohorts), "one timetable per class")

    m4 = by_cohort["MBBS-4"]
    diab = [find(m4, t)[0] for t in ("Diabetes mellitus: diagnosis and management", "Type 1 diabetes in children",
                                     "Diabetic foot", "Diabetic retinopathy")]
    ok(max(c["day_of_week"] for c in diab) - min(c["day_of_week"] for c in diab) <= 1,
       "4th Year: diabetes in Medicine, Paediatrics, Surgery and Eye taught on the same/adjacent days")
    order = sorted(diab, key=lambda c: (c["day_of_week"], c["time_start"]))
    ok(order[0]["discipline"] == "Medicine", "4th Year: Medicine (the disease) comes before its complications")

    week_of = {}
    for wk in (1, 2):
        s = client.post("/api/schedule/generate", json={
            "topics": parse["topics"], "approved_links": links, "week_number": wk, "cohort": "MBBS-2",
        }).json()
        for c in lectures(s):
            week_of.setdefault(c["topic_title"], (wk, c["day_of_week"], c["time_start"], c["discipline"]))
    kidney = ["Kidney gross structure and relations", "Histology of kidney and nephron", "Renal filtration and GFR",
              "Renal function tests"]
    ok(len({week_of[t][0] for t in kidney}) == 1, "2nd Year: renal anatomy, histology, physiology, biochem in one week")
    ok(week_of[kidney[0]][1:3] < week_of[kidney[2]][1:3], "2nd Year: kidney anatomy is taught before renal physiology")
    heart = ["Heart chambers and valves", "Histology of cardiac muscle", "Cardiac cycle"]
    ok(len({week_of[t][0] for t in heart}) == 1, "2nd Year: heart anatomy, histology and cardiac cycle in one week")
    ok(week_of[heart[0]][1:3] < week_of[heart[2]][1:3], "2nd Year: heart anatomy before cardiac cycle")

    booked: set[tuple] = set()
    clashes = []
    for s in by_cohort.values():
        for c in lectures(s):
            if c["faculty_name"]:
                key = (c["faculty_name"], c["day_of_week"], c["time_start"])
                if key in booked:
                    clashes.append(key)
                booked.add(key)
    ok(not clashes, f"no teacher is double-booked across classes {clashes or ''}")
    ok(any(c["integration_tags"] for c in lectures(by_cohort["MBBS-2"])), "lecture cells carry ↔/↕ link notes")

    print("R4 · Copilot edits")
    m2 = by_cohort["MBBS-2"]
    r = client.post("/api/copilot/chat", json={"instruction": "Give Cardiac cycle to Dr. Tariq", "schedule": m2}).json()
    ok(r["action_taken"] == "REASSIGNED_FACULTY" and all(c["faculty_name"] == "Dr. Tariq" for c in find(r["updated_schedule"], "Cardiac cycle")),
       "'Give Cardiac cycle to Dr. Tariq' reassigns every Cardiac cycle session")
    r = client.post("/api/copilot/chat", json={"instruction": "Renal filtration with Dr. Asma Khan", "schedule": m2}).json()
    ok(find(r["updated_schedule"], "Renal filtration and GFR")[0]["faculty_name"] == "Dr. Asma Khan", "'<class> with <teacher>' works")
    r = client.post("/api/copilot/chat", json={"instruction": "Dr. Hina Shah will teach Coronary arteries", "schedule": m2}).json()
    ok(find(r["updated_schedule"], "Coronary arteries")[0]["faculty_name"] == "Dr. Hina Shah", "'<teacher> will teach <class>' works")
    selected = find(m2, "Histology of lymph node")[0]
    r = client.post("/api/copilot/chat", json={"instruction": "Assign this class to Dr. Fareed", "schedule": m2,
                                               "selected_cell_id": selected["id"]}).json()
    ok(find(r["updated_schedule"], "Histology of lymph node")[0]["faculty_name"] == "Dr. Fareed", "'this class' uses the selected cell")
    r = client.post("/api/copilot/chat", json={"instruction": "Replace Dr. Gul Rukh with Dr. Fareed", "schedule": m2}).json()
    ok(not any(c["faculty_name"] == "Dr. Gul Rukh" for c in lectures(r["updated_schedule"])), "'Replace Dr. A with Dr. B' moves all of A's classes")
    r = client.post("/api/copilot/chat", json={"instruction": "Move Histology of lymph node to Saturday 9", "schedule": m2}).json()
    moved = find(r["updated_schedule"], "Histology of lymph node")[0]
    ok((moved["day_of_week"], moved["time_start"]) == (6, "09:00"), "'Move <class> to Saturday 9' moves the class, not the destination")
    batch = "1. Give Development of kidney to Dr. Bushra\n2. Swap the teachers of Cardiac cycle and Renal function tests"
    r = client.post("/api/copilot/chat", json={"instruction": batch, "schedule": m2}).json()
    ok(r["action_taken"] == "BATCH" and r["reply"].startswith("Applied 2 of 2"), "a numbered list of changes is applied in one go")

    print("R5 · report: classes per subject, coverage per topic, classes per teacher")
    rep = client.post("/api/analytics/report", json={"topics": parse["topics"], "links": links,
                                                     "schedules": list(by_cohort.values())}).json()
    phys2 = next(s for s in rep["subjects"] if s["cohort"] == "MBBS-2" and s["discipline"] == "Physiology")
    ok(phys2["classes"] == 11, f"2nd Year Physiology: {phys2['classes']} classes over {phys2['topics']} topics")
    jillani = next(t for t in rep["teachers"] if t["faculty"] == "Dr. Jillani")
    ok(set(jillani["cohorts"]) == {"MBBS-2", "BDS-1"}, f"Dr. Jillani: {jillani['classes']} classes across MBBS-2 and BDS-1")
    cov = next(t for t in rep["topics"] if t["topic"] == "Cardiac cycle")
    ok(cov["times_covered"] == 2, "Cardiac cycle covered 2×")
    edited = client.post("/api/analytics/report", json={"topics": parse["topics"], "links": links,
                                                        "schedules": [r["updated_schedule"]]}).json()
    ok(any(t["faculty"] == "Dr. Bushra" for t in edited["teachers"]), "Copilot teacher changes flow into the teacher load")

    print("R6 · exports")
    d = client.post("/api/export/docx", json={"schedule": m4, "legend_entries": parse["legend"]})
    ok(d.status_code == 200 and b"word/document.xml" in d.content, "weekly timetable .docx for 4th Year MBBS")
    import io
    import docx
    header = docx.Document(io.BytesIO(d.content)).paragraphs[0].text
    ok(header == "TIMETABLE FOR 4TH YEAR MBBS", f"header reads '{header}'")
    rd = client.post("/api/export/report-docx", json={"topics": parse["topics"], "links": links})
    ok(rd.status_code == 200 and len(rd.content) > 10_000, "curriculum report .docx")

    print("\n>>> ALL CLIENT REQUIREMENT TESTS PASSED <<<")


if __name__ == "__main__":
    main()
