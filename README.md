# MedSchedule AI

**AI-Powered MBBS & BDS Modular Curriculum & Timetable Management Engine**

MedSchedule AI ingests unstructured medical/dental syllabi or legacy schedules (`.docx`, `.xlsx`, `.txt`), uses **Google Gemini + pgvector** semantic embeddings to perform **Horizontal Integration** (aligning Basic Sciences: Anatomy, Physiology, Histology, Biochemistry) and **Vertical Integration** (linking Basic Sciences with Clinical Specialties: Surgery, Medicine, ENT, Ophthalmology, Pediatrics, Radiology), solves conflict-free 6-day schedules with 4-batch practical lab rotations via **Google OR-Tools (CP-SAT)**, provides an interactive **Drag-and-Drop Matrix UI + Conversational AI Copilot**, and exports publication-ready **single-page landscape Microsoft Word (`.docx`)** timetables.

---

## Key Features

- **Multi-Format Curriculum Ingestion:** Upload `.docx`, `.xlsx`, or `.txt` files or paste topics in `Subject | Format | Topic | Faculty` format.
- **Horizontal & Vertical Integration Review:** Inspect, filter, customize, or auto-generate clinical linkages before running the solver.
- **Google OR-Tools CP-SAT Solver:** Enforces 6-day operating hours (`08:00–14:00`, daily break `12:00–12:30`, Friday half-day `08:00–12:00`) and simultaneous 4-batch (`A, B, C, D`) practical lab rotations across Histology, Physiology, Biochemistry, and Skill Labs.
- **Interactive Matrix Grid + AI Copilot:** Drag-and-drop rescheduling with soft conflict warnings, undo/redo history, side-by-side comparison with uploaded legacy timetables, and natural-language rescheduling via AI Copilot.
- **Academic Workload Analytics & 1-Page `.docx` Exporter:** Audit subject contact hours, morning slot distributions, and faculty workload, and export a single-page A4 landscape Word document with automatic practical/SGD legends.

---

## Monorepo Structure

```text
├── frontend/             # Next.js 16 + React 19 + TypeScript + Tailwind CSS + shadcn/ui
├── backend/              # FastAPI + Google OR-Tools + google-genai + python-docx + SQLAlchemy
├── supabase/migrations/  # PostgreSQL 16 + pgvector schema migrations
├── docs/                 # PRD, Architecture Plan, and Reference Sample Timetable
└── render.yaml           # One-click Render Blueprint configuration for FastAPI backend
```

---

## Local Development

### 1. Backend (`FastAPI` on port `8000`)

```bash
cd backend
cp .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend (`Next.js` on port `3000`)

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

---

## Production Deployment

1. **Backend (Render / Railway):**
   - Root Directory: `backend`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Environment Variables: `GEMINI_API_KEY`, `SUPABASE_URL`, `CORS_ORIGINS`
2. **Frontend (Vercel):**
   - Root Directory: `frontend`
   - Framework Preset: `Next.js`
   - Environment Variable: `NEXT_PUBLIC_API_URL=https://<your-backend-domain>/api`
