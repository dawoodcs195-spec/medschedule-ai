# AGENTS.md — Master Instructions & System Context

## 1. Project Overview
You are building the **BDS / MBBS Integrated Modular Curriculum & Timetable Management Engine**.
This platform ingests unstructured medical/dental syllabi or legacy schedules, uses AI vector embeddings to perform **Horizontal Integration** (aligning basic sciences like Anatomy, Physiology, Histology, and Biochemistry within the same week/organ system) and **Vertical Integration** (linking basic sciences to clinical departments like Surgery, Medicine, ENT, Ophthalmology, Pediatrics, and Radiology), solves conflict-free schedules via **Google OR-Tools**, provides an interactive **Matrix Grid UI + Conversational AI Copilot**, and exports publication-ready **single-page landscape Microsoft Word (.docx)** timetables.

**Before executing any task, always consult:**
- `docs/PRD_Requirements.md` (Functional & Institutional Specifications)
- `docs/Architecture_Plan.md` (System Design, Schema, CSP Model, & Exporter Rules)
- `docs/sample_timetable.docx` (Reference 2nd Year MBBS Neurosciences Block-IV Module-07 Timetable)
- `docs/screenshots/` (Current UI in light and dark mode: landing, workspace, solver, analytics)

---

## 2. Monorepo Directory Structure
Maintain a clean monorepo architecture:

/
├── AGENTS.md
├── docs/
│   ├── PRD_Requirements.md
│   ├── Architecture_Plan.md
│   ├── sample_timetable.docx
│   └── screenshots/          # README / portfolio screenshots
├── frontend/                 # Next.js 16 App Router (React 19, TypeScript, Tailwind CSS v4, shadcn/ui)
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   │   ├── landing/      # Animated marketing landing page
│   │   │   ├── tour/         # 9-step first-run product tour
│   │   │   ├── workspace/    # Upload step, workspace header, solver overlay
│   │   │   ├── analytics/    # Contact-hour, time-slot & faculty workload dashboard
│   │   │   ├── grid/         # Timetable Matrix Grid & Drag-and-Drop
│   │   │   ├── copilot/      # Right-hand AI Chat Drawer
│   │   │   └── integration/  # Pre-Solver Curriculum Linkage Review & Approval Screen
│   │   ├── lib/
│   │   └── types/
├── backend/                  # FastAPI (Python 3.12, Pydantic v2)
│   ├── app/
│   │   ├── api/              # REST & SSE Streaming Endpoints
│   │   ├── core/             # Config, Supabase DB Connection, Gemini Client
│   │   ├── models/           # SQLAlchemy / SQLModel & Pydantic Schemas
│   │   ├── services/
│   │   │   ├── parser.py     # LLM Syllabus & .docx Ingestion
│   │   │   ├── integrator.py # pgvector Cosine Similarity Clustering
│   │   │   ├── solver.py     # Google OR-Tools CP-SAT Engine
│   │   │   ├── copilot.py    # Natural Language Rescheduling Tool Calls
│   │   │   └── exporter.py   # python-docx + lxml Landscape Exporter
└── supabase/
    └── migrations/           # PostgreSQL 16 + pgvector SQL migrations

---

## 3. Technology Stack & Infrastructure Rules
- **Frontend:** Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS v4, `shadcn/ui`, `motion`, `@dnd-kit/core` (for drag-and-drop slots), TanStack Query. Deployed on **Vercel** (`https://medschedule-ai.vercel.app`).
- **Backend:** Python 3.11/3.12, FastAPI, Pydantic v2, `google-genai` (Gemini, default model `gemini-2.5-flash`, configurable via `GEMINI_MODEL`), `ortools` (CP-SAT solver), `python-docx`, `lxml`. Deployed as a Vercel Python function (`backend/vercel.json`); a Render Blueprint (`render.yaml`) and `Dockerfile` are included for container hosts.
- **Database:** Supabase Managed PostgreSQL 16 with `pgvector` and `uuid-ossp` extensions enabled.
- **User Access Model:** Single-role **Admin / Academic Coordinator** platform for Phase 1.

---

## 4. Non-Negotiable Domain & Scheduling Constraints (OR-Tools CP-SAT)
Whenever modifying `solver.py` or validating schedule edits, strictly enforce these institutional rules:

1. **Operating Window & Days:**
   - **6-Day Academic Week:** Monday through Saturday.
   - **Standard Hours (Mon–Thu & Sat):** `08:00` to `14:00` (08:00 AM – 02:00 PM).
   - **Daily Break:** `12:00` to `12:30` (Strictly blocked on Mon–Thu & Sat).
   - **Friday Half-Day Rule:** `08:00` to `12:00` only (Strictly no classes after 12:00 PM on Fridays).

2. **Cohort & Batching Math:**
   - **Total Cohort Size:** 100 students per year/class.
   - **LGIS (Large Group Interactive Sessions):** 1-hour lectures hosting all 100 students together in 1 Lecture Hall.
   - **Practicals & SGDs (Small Group Discussions):** 1.5 to 2-hour sessions (`08:00–10:00`, `10:00–12:00`, or `12:30–14:00`). The 100 students split strictly into **4 Equal Batches (Batch A, Batch B, Batch C, Batch D)** of 25 students each.

3. **Facility & Lab Rotation Rules:**
   - **Lecture Halls:** 8 physical Lecture Halls available.
   - **Practical Venues:** Exactly 3 Specialized Practical Labs (**Histology Lab**, **Physiology Lab**, **Biochemistry Lab**) + **1 Skill Lab**.
   - **Simultaneous 4-Batch Permutation:** During any Practical block, Batches A, B, C, and D must simultaneously occupy the 4 distinct venues (`Histo`, `Physio`, `Biochem`, `Skill Lab`) with zero room collisions. Across the week, every batch must rotate through all 4 practical stations.
   - **SGD Venues:** Rotations across `Anatomy`, `Physiology`, `Biochemistry`, and `SDL (Self-Directed Learning)`. Do not apply hard room constraints to SGDs (teachers decide locally).
   - **Other Session Types:** Support `DSL` (Directed Self-Learning), `SDL / Digital Library`, `RIPPLE` (Research), `ISL / P.STD`, `MENTOR MENTEE MEETING`, and `PEER ASSISTED LEARNING`.

4. **Faculty & Clinical Specialty Rules:**
   - Parse explicit faculty names directly from the input text/file (e.g., `Dr. Ambar Saba`, `Dr. Ayyaz Afridi`).
   - Maintain a pre-seeded dictionary of Clinical Departments (`CLINICAL FACULTY SURGERY`, `CLINICAL FACULTY MEDICINE`, `CLINICAL FACULTY ENT`, `CLINICAL FACULTY EYE`, `CLINICAL FACULTY PEADS`, `CLINICAL FACULTY RADIOLOGY`, `ORAL & MAXILLOFACIAL SURGERY`, etc.) with an Admin UI option to add custom departments.

---

## 5. End-to-End Application Workflow
1. **Step 1 — Ingestion:** Admin pastes raw topic lists or uploads a `.docx`/`.xlsx` syllabus. FastAPI uses Gemini structured outputs (with a deterministic heuristic parser as fallback when no API key is configured) to extract topics, disciplines, session formats (`LGIS`, `PRACTICAL`, `SGD`, `DSL`), organ systems, and faculty names.
2. **Step 2 — Semantic Vector Integration & Review Screen:** Compute 1536-dim embeddings stored in `pgvector`. Calculate cosine similarity (`<=>`) to propose Horizontal and Vertical integration pairs. **Crucial UI Step:** Present an **Interactive Integration Review & Edit Screen** where the admin can inspect, modify, or approve topic linkages before generating the schedule.
3. **Step 3 — Auto-Scheduling:** Run Google OR-Tools CP-SAT solver to generate the weekly schedule matrix.
4. **Step 4 — Interactive Matrix Grid & Option B Conflict Handling:**
   - Render the 6-day timetable grid in Next.js.
   - **Discipline Color Palette (Tailwind):**
     - Anatomy / Neuro Anat / Gross Anat / Embryo / Histo: `bg-sky-50/80 border-sky-500 text-sky-950`
     - Physiology: `bg-emerald-50/80 border-emerald-500 text-emerald-950`
     - Biochemistry: `bg-amber-50/80 border-amber-500 text-amber-950`
     - Clinical Specialties (Surgery, Medicine, ENT, Eye, Peads, Radiology): `bg-purple-50/80 border-purple-500 text-purple-950`
     - Institutional / SDL / RIPPLE / Break: `bg-slate-100/80 border-slate-400 text-slate-900`
   - **Option B Conflict Handling (Soft Warning):** When an admin drags a slot or uses the AI Copilot to make a move that causes a clash, **do not hard-block**. Highlight the conflicting cell in pulsing red (`bg-rose-100 border-rose-600 text-rose-900`) and have the AI Copilot display the exact clash details along with suggested open alternative slots.
5. **Step 5 — Analytics Dashboard:** Track total contact hours per subject, time-bracket distribution (e.g., count of `08:00–09:00` slots per subject), and individual faculty teaching hours.

---

## 6. Native Microsoft Word (.docx) Exporter Rules
When building `exporter.py` with `python-docx` and `lxml`:
- **Single-Page Landscape Fit:** Each week of a module MUST fit cleanly onto **1 single Landscape A4 page** (`11.69" x 8.27"`, margins `0.4"` all around).
- **Header Format:** Standardized plain module header matching the sample:
  `TIMETABLE FOR 2ND YEAR MBBS`
  `NEUROSCIENCES BLOCK-IV (MODULE-07) (WEEK-01) (SESSION 2026-2027)`
- **Grid Structure:** Columns for `DAYS`, `08:00 – 09:00`, `09:00 – 10:00`, `10:00 – 11:00`, `11:00 – 12:00`, `12:00 – 12:30` (BREAK), and `12:30 – 02:00`.
- **Merged Cells:** Use explicit `gridSpan` (horizontal merge for 2-hour Practicals or Friday `HALF DAY`) and `vMerge` where needed, plus explicit DXA column widths (`w:gridCol` and `w:tcW`).
- **Footer Legend Keys:** Automatically append the Practical and SGD legend keys at the bottom of each weekly page (e.g., `HISTO P1 = Neurons`, `PHYSIO P1 = Temperature regulation`, `SKILL LAB = History taking of neurological patient`).

---

## 7. Execution Sprints
- **Sprint 1:** Monorepo scaffolding (`/frontend`, `/backend`), Supabase `pgvector` SQL schema migration, and FastAPI `.docx`/text ingestion + Gemini structured parser.
- **Sprint 2:** `pgvector` cosine similarity integration service, Frontend Integration Review/Approval UI, and Google OR-Tools CP-SAT scheduling engine.
- **Sprint 3:** Next.js Interactive Timetable Matrix Grid, discipline color coding, Drag-and-Drop with Option B soft conflict warnings, and Gemini Copilot drawer.
- **Sprint 4:** `python-docx` single-page landscape exporter + Academic Workload Analytics dashboard.