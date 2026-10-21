"""End-to-End Smoke Test across all 4 sprints:
Ingestion -> Semantic Clustering -> CP-SAT Schedule -> Option B Validation -> .docx Export.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

print("=== 1. Health Probe ===")
health = client.get("/api/health").json()
print("Health:", health)

print("\n=== 2. Parse Sample Docx File ===")
sample_path = ROOT / "docs" / "sample_timetable.docx"
with sample_path.open("rb") as f:
    ingest_res = client.post("/api/ingest/file", files={"file": ("sample.docx", f)}, data={"use_llm": "false"})
assert ingest_res.status_code == 200, ingest_res.text
parse_data = ingest_res.json()
topics = parse_data["topics"]
legend = parse_data["legend"]
print(f"Extracted {len(topics)} topics, {len(legend)} legend items")

print("\n=== 3. Semantic Vector Clustering (Horizontal & Vertical) ===")
cluster_res = client.post("/api/integrate/cluster", json={"topics": topics[:25]})
assert cluster_res.status_code == 200, cluster_res.text
cluster_data = cluster_res.json()
print(f"Engine: {cluster_data['embedding_engine']}")
print(f"Proposed Links: {len(cluster_data['links'])} (Horizontal: {cluster_data['horizontal_count']}, Vertical: {cluster_data['vertical_count']})")
for l in cluster_data["links"][:4]:
    print(f"  [{l['integration_type']:10}] {l['source_discipline']} ({l['source_topic'][:25]}) <-> {l['target_discipline']} ({l['target_topic'][:25]}) | score: {l['similarity_score']}")

print("\n=== 4. Google OR-Tools CP-SAT Timetable Generation ===")
sched_req = {
    "topics": topics,
    "approved_links": cluster_data["links"],
    "module_code": parse_data["meta"]["module_code"] or "MODULE-07",
    "module_title": parse_data["meta"]["module_title"] or "NEUROSCIENCES BLOCK-IV",
    "academic_year": 2,
    "week_number": 1,
}
sched_res = client.post("/api/schedule/generate", json=sched_req)
assert sched_res.status_code == 200, sched_res.text
schedule = sched_res.json()
print(f"Solver Status: {schedule['solver_status']} | Total Contact Hours: {schedule['total_contact_hours']}")
print(f"Scheduled Cells Count: {len(schedule['cells'])}")
# Show Friday cells
fri_cells = [c for c in schedule["cells"] if c["day_name"] == "FRIDAY"]
print("Friday schedule:")
for c in fri_cells:
    print(f"  {c['time_start']} - {c['time_end']}: [{c['session_type']}] {c['topic_title'][:40]}")

print("\n=== 5. Option B Soft-Validation (Conflict Checker) & AI Copilot Chat ===")
first_cell = schedule["cells"][0]
# Move to Friday 13:00 (which should trigger a soft warning for Friday half-day)
val_req = {
    "schedule": schedule,
    "cell_id": first_cell["id"],
    "new_day": 5, # Friday
    "new_start": "13:00",
    "new_end": "14:00",
}
val_res = client.post("/api/schedule/validate-move", json=val_req)
assert val_res.status_code == 200, val_res.text
val_data = val_res.json()
print("Is Valid:", val_data["is_valid"])
print("Conflicts detected:", len(val_data["conflicts"]))
for conf in val_data["conflicts"]:
    print(f"  [{conf['severity']}] {conf['message']}")
    print(f"  Suggestions: {conf['suggested_alternative_slots']}")

chat_res = client.post("/api/copilot/chat", json={
    "instruction": "Move Spine trauma to Friday afternoon",
    "schedule": schedule,
})
assert chat_res.status_code == 200, chat_res.text
chat_data = chat_res.json()
print("Copilot Action:", chat_data["action_taken"], "| Reply:", chat_data["reply"])

print("\n=== 6. Native Single-Page Landscape .docx Export ===")
export_req = {
    "schedule": schedule,
    "legend_entries": legend[:10],
}
docx_res = client.post("/api/export/docx", json=export_req)
assert docx_res.status_code == 200
docx_bytes = docx_res.content
print(f"Generated .docx Size: {len(docx_bytes):,} bytes")
out_test_docx = ROOT / "backend" / "tests" / "test_export_output.docx"
out_test_docx.write_bytes(docx_bytes)
print(f"Saved test export to: {out_test_docx.name}")

print("\n>>> ALL PIPELINE TESTS PASSED SUCCESSFULLY! <<<")
