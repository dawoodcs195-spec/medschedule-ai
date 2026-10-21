# **BDS / MBBS Integrated Modular Curriculum & Timetable Management Engine**

# **System Architecture & Implementation Specification**

---

## **1\. Executive Technical Overview**

The Integrated Modular Curriculum & Timetable Management Engine is an enterprise-grade platform designed for medical and dental faculties (MBBS/BDS). It automates the ingestion, semantic alignment, mathematical scheduling, and publication of complex medical education timetables.

Medical curricula require tight horizontal integration (e.g., aligning Anatomy, Physiology, and Biochemistry within a "Cardiovascular Module") and vertical integration (e.g., embedding clinical cardiology cases into basic science weeks). Traditional manual scheduling fails to balance these requirements while managing resource limitations such as physical lab capacities, small group discussion (SGD) venue limits, Friday half-day schedules, and faculty availability.+-----------------------------------------------------------------------------------+

|                                 SYSTEM LANDSCAPE                                  |

|---|+-----------------------------------------------------------------------------------+

|                                                                                   |

|  \+------------------+     JSON/REST      \+-------------------------------------+  |

|  | Next.js Frontend | \<===============\> |  FastAPI Microservice Engine        |  |

|  | App Router \+ React|                   |  \- Parsing Pipeline                 |  |

|  | Data Grid \+ Chat |                   |  \- Solver Orchestration             |  |

|  \+------------------+                   |  \- Document Exporter                |  |

|                                         \+-------------------------------------+  |

|                                            //               ||             \\\\     |

|                                           //                ||              \\\\    |

|                                          //                 ||               \\\\   |

|  \+----------------------------------+   //       \+-------------------+        \\\\  |

|  | PostgreSQL \+ pgvector            |  //        | Google OR-Tools   |         \\\\ |

|  | \- Relational Schema              | \<=         | Constraint Solver |          \=\>|

|  | \- Semantic Embeddings (1536-dim) |            | (CP-SAT Engine)   |            |

|  \+----------------------------------+            \+-------------------+            |

|                                                                                   |

|  \+-----------------------------------------------------------------------------+  |

|  | LLM Services (OpenAI API / Local vLLM Embeddings)                           |  |

|  \+-----------------------------------------------------------------------------+  |

\+-----------------------------------------------------------------------------------+

### **Core Capabilities**

* **AI Ingestion & Structuring:** Converts unstructured course outlines and Word documents into structured relational objects using Large Language Models (LLMs).  
* **Semantic Vector Integration:** Uses `pgvector` to identify and align horizontal and vertical learning objectives across academic departments.  
* **Deterministic Constraint Solving:** Uses Google OR-Tools (CP-SAT) to generate conflict-free schedules that respect physical and pedagogical constraints.  
* **Interactive UI & AI Copilot:** Provides a matrix view for schedule review, manual drag-and-drop overrides, and natural language schedule modifications.  
* **Document Generation:** Produces single-page, landscape, publication-ready `.docx` schedules with pixel-perfect column alignment, nested batch structures, and custom OpenXML styling.

---

## **2\. Selected Technology Stack & Justification**

| Layer | Technology | Architectural Justification |
| :---- | :---- | :---- |
| **Frontend UI & Hosting** | Next.js 14+ (TypeScript), Tailwind CSS, React Query; Deployed on Vercel | Vercel provides seamless Edge deployment, server-side rendering for initial load speed, and fast client-side reactive rendering for high-density matrix components. |
| **Backend Framework & Hosting** | Python 3.11+, FastAPI, Pydantic v2; Deployed on Container Platform (Render / Railway / Fly.io) | Dedicated container hosting provides persistent execution environment for long-running constraint solver tasks, native Python data science/OR-Tools integration, and asynchronous FastAPI performance. |
| **Database & Vector Store** | Supabase Managed PostgreSQL 16+ with `pgvector` extension | Managed Supabase platform ensures instant vector search capability via pgvector alongside standard relational tables, ACID compliance, built-in Auth, and real-time backend capabilities. |
| **LLM & AI Services** | Gemini 1.5 Pro / Flash APIs (Google AI Studio / Vertex AI) | Gemini 1.5 Pro/Flash provides extreme context windows for heavy syllabus processing, cost-effective structure extraction, and reliable conversational tool calling for the AI Copilot. |
| **Document Generation** | `python-docx` \+ Native `lxml` Element Manipulation | Enables precise control over Word processing files, allowing hardcoded XML column widths, custom shading, and border properties required for standardized institutional exports. |

---

## **3\. End-to-End System Pipeline & Data Flow**

\+---------------------------------------------------------------------------------------------------+

|                                 END-TO-END DATA PROCESSING PIPELINE                               |

\+---------------------------------------------------------------------------------------------------+

 \[STEP 1: INGESTION\]          \[STEP 2: VECTOR CLUSTERING\]        \[STEP 3: CONSTRAINT SOLVING\]

 Unstructured Syllabus/Docx   Unstructured Curriculum Tokens     Hard/Soft Operational Constraints

            |                             |                                    |

            v                             v                                    v

\+-----------------------+     \+-----------------------+        \+-------------------------------+

| OpenXML Document      |     | Embedding Engine      |        | Google OR-Tools CP-SAT Model  |

| Parsing & Parsing LLM | \==\> | text-embedding-3-large|  \===\>  | \- Batch Rotations             |

| Structured JSON Schema|     | Vector Storage        |        | \- Faculty / Room Constraints  |

\+-----------------------+     \+-----------------------+        \+-------------------------------+

                                          |                                    |

                                          v                                    v

                               \+----------------------+        \+-------------------------------+

                               | pgvector HNSW Index  |        | Validated Matrix Schedule     |

                               | Integration Links    |        | Candidate (Database persisted)|

                               \+----------------------+        \+-------------------------------+

                                                                               |

                                                                               v

 \[STEP 5: PUBLICATION\]        \[STEP 4: INTERACTIVE UI\]              \+------------------+

 Landscape .docx Export       Matrix Editor & NL Copilot            | Human Validation |

 Native XML Formatting  \<===  Drag-and-Drop Override Engine  \<======= | & Interactive UI |

 Strict Single-Page Fit       Real-time Constraint Validation       \+------------------+

\+-----------------------+     \+----------------------------------------------------------------+

### **Step 1: Text/Docx Ingestion & Parsing**

Unstructured syllabus documents, PDF files, and Word forms are ingested via `python-docx` or `pypdf`. Extracted text blocks are passed to Gemini 1.5 Pro / Flash using JSON Schema enforcing structured output. The parser converts free text into validated Pydantic models containing topics, requested contact hours, session types (Lecture, SGD, Lab), explicit faculty extraction, and prerequisites.

### **Step 2: Semantic Clustering via pgvector**

Extracted learning objectives are processed through an embedding engine to generate 1536-dimensional vector representations stored in Supabase PostgreSQL via `pgvector`. Spatial cosine similarity queries (`<=>`) aggregate related concepts, proposing candidate horizontal and vertical curriculum alignments. An interactive Curriculum Review & Approval screen then allows academic admins to review, edit, or approve suggested linkages prior to solver scheduling.

### **Step 3: Deterministic Constraint Solver**

The approved syllabus models, physical room constraints, pre-seeded clinical faculty rosters (with dynamic admin upload capabilities), and time-block definitions are loaded into the Google OR-Tools CP-SAT solver. The solver dynamically handles flexible morning vs. afternoon practical slot allocations, treats SGD venues as room-unconstrained (group assignment only), and enforces hard operational rules while optimizing soft constraints.

### **Step 4: Interactive Matrix UI & Natural Language Copilot**

The generated schedule is rendered in a custom Next.js data grid featuring semantic color-coding by discipline (e.g., Anatomy, Physiology, Biochemistry, Clinical specialties). Manual drag-and-drop actions use "Soft Warning" handling (Option B): conflicts are highlighted in red while the AI Copilot presents detailed conflicting slot information and suggests available alternative open slots.

### **Step 5: .docx Landscape Single-Page Exporter**

The final schedule is compiled into a publication-ready `.docx` landscape document. The export engine automatically builds standardized module headers reverse-engineered from institutional templates and generates dynamic footer keys for SGD and Practical session abbreviations.

---

## **4\. PostgreSQL Database Schema with pgvector**

The database structure relies on PostgreSQL with the `pgvector` extension enabled.-- Enable vector extension

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE EXTENSION IF NOT EXISTS "vector";

\-- Academic Program Definition

CREATE TABLE academic\_programs (

    id UUID PRIMARY KEY DEFAULT uuid\_generate\_v4(),

    code VARCHAR(20) NOT NULL UNIQUE, \-- e.g., 'MBBS', 'BDS'

    title VARCHAR(250) NOT NULL,

    created\_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT\_TIMESTAMP

);

\-- Modules / Courses

CREATE TABLE modules (

    id UUID PRIMARY KEY DEFAULT uuid\_generate\_v4(),

    program\_id UUID NOT NULL REFERENCES academic\_programs(id) ON DELETE CASCADE,

    code VARCHAR(50) NOT NULL,

    title VARCHAR(250) NOT NULL,

    academic\_year INT NOT NULL, \-- e.g., 1, 2, 3

    created\_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT\_TIMESTAMP

);

\-- Curriculum Topics & Learning Objectives (Vector Enabled)

CREATE TABLE learning\_objectives (

    id UUID PRIMARY KEY DEFAULT uuid\_generate\_v4(),

    module\_id UUID NOT NULL REFERENCES modules(id) ON DELETE CASCADE,

    topic\_title VARCHAR(250) NOT NULL,

    description TEXT NOT NULL,

    session\_type VARCHAR(50) NOT NULL, \-- 'LECTURE', 'SGD', 'LAB', 'SKILL\_LAB'

    duration\_minutes INT NOT NULL DEFAULT 60,

    embedding vector(1536), \-- Vector representation for semantic alignment

    created\_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT\_TIMESTAMP

);

\-- Index for HNSW Cosine Similarity Search

CREATE INDEX ON learning\_objectives 

USING hnsw (embedding vector\_cosine\_ops);

\-- Vertical/Horizontal Curriculum Linkages

CREATE TABLE curriculum\_integrations (

    id UUID PRIMARY KEY DEFAULT uuid\_generate\_v4(),

    source\_objective\_id UUID NOT NULL REFERENCES learning\_objectives(id) ON DELETE CASCADE,

    target\_objective\_id UUID NOT NULL REFERENCES learning\_objectives(id) ON DELETE CASCADE,

    integration\_type VARCHAR(20) NOT NULL, \-- 'HORIZONTAL', 'VERTICAL'

    similarity\_score FLOAT NOT NULL,

    created\_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT\_TIMESTAMP

);

\-- Physical Locations / Resources

CREATE TABLE rooms (

    id UUID PRIMARY KEY DEFAULT uuid\_generate\_v4(),

    name VARCHAR(100) NOT NULL,

    room\_type VARCHAR(50) NOT NULL, \-- 'LECTURE\_HALL', 'LAB', 'SKILL\_LAB', 'SGD\_ROOM'

    capacity INT NOT NULL,

    is\_active BOOLEAN DEFAULT TRUE

);

\-- Timetable Schedule Master

CREATE TABLE schedule\_slots (

    id UUID PRIMARY KEY DEFAULT uuid\_generate\_v4(),

    objective\_id UUID NOT NULL REFERENCES learning\_objectives(id) ON DELETE CASCADE,

    room\_id UUID REFERENCES rooms(id) ON DELETE SET NULL,

    day\_of\_week INT NOT NULL, \-- 1 \= Monday ... 5 \= Friday

    start\_time TIME NOT NULL,

    end\_time TIME NOT NULL,

    student\_batch\_mask VARCHAR(20) NOT NULL, \-- e.g., 'ALL', 'BATCH\_A', 'BATCH\_B', 'BATCH\_C', 'BATCH\_D'

    created\_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT\_TIMESTAMP

);

---

## **5\. Constraint Satisfaction Problem (CSP) Formulation**

The scheduling engine uses Google OR-Tools CP-SAT solver to arrange academic events.

### **Problem Space Parameters**

* **Cohort Size (\$N\$):** 100 Students.  
* **Large Group Interactive Sessions (LGIS / Lectures):** Entire cohort (\$N=100\$) in a single venue.  
* **Small Group Discussions (SGD) / Rotations:** Cohort split into 4 equal batches: \$A, B, C, D\$ (\$n=25\$ per batch).  
* **Facilities (\$R\$):**  
  * 3 \$\\times\$ Specialized Science Labs (\$L\_1, L\_2, L\_3\$)  
  * 1 \$\\times\$ Clinical Skills Lab (\$S\_1\$)  
  * Lecture Halls (\$H\_1\$) and SGD Breakout Rooms.  
* **Time Grid (\$T\$):** Monday through Thursday (8 Slots: \$08:00 \- 16:00\$), Friday (4 Slots: \$08:00 \- 12:00\$, Half-Day Constraint).

### **Mathematical CSP Formalization**

import collections

from ortools.sat.python import cp\_model

def solve\_academic\_schedule():

    model \= cp\_model.CpModel()

    \# \--- SETS & INDEXES \---

    days \= range(1, 6\) \# 1=Mon, 2=Tue, 3=Wed, 4=Thu, 5=Fri

    slots\_per\_day \= {1: range(8), 2: range(8), 3: range(8), 4: range(8), 5: range(4)} \# Fri capped at 4

    batches \= \['Batch\_A', 'Batch\_B', 'Batch\_C', 'Batch\_D'\]

    labs \= \['Lab\_1', 'Lab\_2', 'Lab\_3', 'Skill\_Lab'\]

    \# \--- DECISION VARIABLES \---

    \# Assignment matrix: x\[b, l, d, t\] \= 1 if Batch 'b' is in Lab 'l' on Day 'd' at Slot 't'

    x \= {}

    for b in batches:

        for l in labs:

            for d in days:

                for t in slots\_per\_day\[d\]:

                    x\[b, l, d, t\] \= model.NewBooleanField(f'x\_{b}\_{l}\_{d}\_{t}')

    \# \--- HARD CONSTRAINTS \---

    \# 1\. Friday Capacity Constraint (No events after slot 3 on Friday)

    \# Automatically enforced by slot array definitions for Day 5 (range(4) \-\> 0,1,2,3).

    \# 2\. Room Single-Occupancy Constraint

    \# At most one batch can occupy a specific lab during any single slot.

    for l in labs:

        for d in days:

            for t in slots\_per\_day\[d\]:

                model.AddAtMostOne(x\[b, l, d, t\] for b in batches)

    \# 3\. Student Batch Non-Overlap Constraint

    \# A single batch can be in at most one lab during any single time slot.

    for b in batches:

        for d in days:

            for t in slots\_per\_day\[d\]:

                model.AddAtMostOne(x\[b, l, d, t\] for l in labs)

    \# 4\. Perfect Rotation Requirement

    \# During a scheduled 2-hour rotation block (e.g., Slots 0 & 1), all 4 batches must

    \# simultaneously occupy all 4 distinct lab resources.

    rotation\_block\_starts \= \[0, 2, 4, 6\] \# Every 2-hour block

    for d in range(1, 5): \# Mon-Thu

        for t\_start in rotation\_block\_starts:

            \# Active indicator for rotation block

            block\_active \= model.NewBooleanField(f'rot\_active\_{d}\_{t\_start}')

            

            \# If active, every lab must be filled

            for l in labs:

                model.Add(

                    sum(x\[b, l, d, t\_start\] for b in batches) \== 1

                ).OnlyEnforceIf(block\_active)

                

            \# Session continuity: slot t and slot t+1 must match assignment

            for b in batches:

                for l in labs:

                    model.Add(

                        x\[b, l, d, t\_start\] \== x\[b, l, d, t\_start \+ 1\]

                    ).OnlyEnforceIf(block\_active)

    \# \--- SOFT CONSTRAINTS / OPTIMIZATION GOALS \---

    \# Minimize faculty movement and balance distribution across the week

    penalty\_terms \= \[\]

    

    \# Target: Avoid placing intensive Skill Lab sessions in slot 0 on Mondays

    for b in batches:

        penalty\_terms.append(x\[b, 'Skill\_Lab', 1, 0\] \* 10\)

    model.Minimize(sum(penalty\_terms))

    \# \--- SOLVER EXECUTION \---

    solver \= cp\_model.CpSolver()

    solver.parameters.max\_time\_in\_seconds \= 30.0

    solver.parameters.num\_search\_workers \= 8

    

    status \= solver.Solve(model)

    if status in (cp\_model.OPTIMAL, cp\_model.FEASIBLE):

        return solver, x

    else:

        raise ValueError("No feasible schedule found satisfying constraints.")

---

## **6\. `.docx` Exporter Technical Specification**

The document exporter builds single-page, landscape timetable grids. It uses custom XML manipulation via `lxml` inside `python-docx` to enforce strict formatting standards.+---------------------------------------------------------------------------------------+

| SYSTEM TIMETABLE GRID FORMAT                                                         |

\+------------+-------------------+-------------------+------------------+---------------+

| TIME       | BATCH A           | BATCH B           | BATCH C          | BATCH D       |

\+------------+-------------------+-------------------+------------------+---------------+

| 08:00-09:00| LGIS: General Anatomy \- Main Lecture Hall (All Batches)                  |

\+------------+-------------------+-------------------+------------------+---------------+

| 09:00-11:00| Lab 1: Histology  | Lab 2: Physiology | Lab 3: Biochem   | Skill Lab     |

\+------------+-------------------+-------------------+------------------+---------------+

| 11:00-12:00| SGD: Pathology    | SGD: Pharmacology | SGD: Anatomy     | SGD: Physiol  |

\+------------+-------------------+-------------------+------------------+---------------+

### **OpenXML Engineering Rules**

1. **Explicit Column Widths (`w:gridCol` & `w:tcW`):** Table rendering engines recalculated flexible widths unless absolute dxa (twips) values are explicitly assigned to all grid columns and individual cell instances.  
2. **Cell Margins (`w:tcMar`):** Padding must be set directly at the cell level to maximize visible text area on standard paper sizes.  
3. **Table Borders (`w:tblBorders`):** Internal gridlines use subtle colors (e.g., `#CBD5E1`), while outer edges are unbordered or styled with clean lines.  
4. **Cell Shading (`w:shd`):** Headers and special status blocks use muted hex values (e.g., `#F8FAFC`, `#F1F5F9`).

### **Python Generator Engine Implementation**

import docx

from docx.shared import Inches, Pt, RGBColor

from docx.enum.text import WD\_ALIGN\_PARAGRAPH

from docx.enum.table import WD\_TABLE\_ALIGNMENT, WD\_ALIGN\_VERTICAL

from docx.oxml import parse\_xml, OxmlElement

from docx.oxml.ns import nsdecls, qn

def create\_landscape\_timetable():

    doc \= docx.Document()

    

    \# \--- PAGE SETUP: LANDSCAPE A4 \---

    section \= doc.sections\[0\]

    section.orientation \= docx.enum.section.WD\_ORIENT.LANDSCAPE

    section.page\_width \= Inches(11.69)

    section.page\_height \= Inches(8.27)

    

    \# Narrow Margins (0.4 inch)

    section.top\_margin \= Inches(0.4)

    section.bottom\_margin \= Inches(0.4)

    section.left\_margin \= Inches(0.4)

    section.right\_margin \= Inches(0.4)

    \# Absolute Total Printable Width \= 10.89 inches \= 15681 DXA

    col\_widths\_dxa \= \[1681, 3500, 3500, 3500, 3500\] 

    table \= doc.add\_table(rows=3, cols=5)

    table.alignment \= WD\_TABLE\_ALIGNMENT.CENTER

    table.autofit \= False

    \# Force Table Level Grid Definition

    tblPr \= table.\_tbl.tblPr

    tblGrid \= OxmlElement('w:tblGrid')

    for width in col\_widths\_dxa:

        gridCol \= OxmlElement('w:gridCol')

        gridCol.set(qn('w:w'), str(width))

        tblGrid.append(gridCol)

    table.\_tbl.insert(1, tblGrid)

    \# Borders XML Injection

    borders\_xml \= parse\_xml(f'''

        \<w:tblBorders {nsdecls("w")}\>

            \<w:top w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/\>

            \<w:bottom w:val="single" w:sz="6" w:space="0" w:color="0F172A"/\>

            \<w:left w:val="none"/\>

            \<w:right w:val="none"/\>

            \<w:insideH w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/\>

            \<w:insideV w:val="none"/\>

        \</w:tblBorders\>

    ''')

    tblPr.append(borders\_xml)

    \# Build Header Row

    headers \= \["Time Slot", "Batch A (n=25)", "Batch B (n=25)", "Batch C (n=25)", "Batch D (n=25)"\]

    hdr\_row \= table.rows\[0\]

    

    \# Set header height

    trPr \= hdr\_row.\_tr.get\_or\_add\_trPr()

    trPr.append(parse\_xml(f'\<w:trHeight {nsdecls("w")} w:val="360" w:hRule="exact"/\>'))

    for i, text in enumerate(headers):

        cell \= hdr\_row.cells\[i\]

        set\_cell\_properties(cell, col\_widths\_dxa\[i\], "F8FAFC", top\_pad=120, bottom\_pad=120)

        p \= cell.paragraphs\[0\]

        p.alignment \= WD\_ALIGN\_PARAGRAPH.CENTER

        run \= p.add\_run(text)

        run.font.name \= 'Inter'

        run.font.size \= Pt(9)

        run.font.bold \= True

        run.font.color.rgb \= RGBColor(15, 23, 42\)

    \# Populate LGIS (Full Width Merge)

    row\_lgis \= table.rows\[1\]

    row\_lgis.cells\[0\].paragraphs\[0\].add\_run("08:00 \- 09:00")

    

    \# Merge cells 1 to 4 for full cohort

    a \= row\_lgis.cells\[1\]

    b \= row\_lgis.cells\[4\]

    merged\_cell \= a.merge(b)

    

    set\_cell\_properties(merged\_cell, sum(col\_widths\_dxa\[1:\]), "FFFFFF")

    p\_lgis \= merged\_cell.paragraphs\[0\]

    p\_lgis.alignment \= WD\_ALIGN\_PARAGRAPH.CENTER

    run\_lgis \= p\_lgis.add\_run("LGIS: Anatomy Core \- General Histology\\nVenue: Main Lecture Hall | All Batches")

    run\_lgis.font.name \= 'Inter'

    run\_lgis.font.size \= Pt(8.5)

    run\_lgis.font.bold \= True

    run\_lgis.font.color.rgb \= RGBColor(30, 41, 59\)

    doc.save("Academic\_Timetable\_Export.docx")

def set\_cell\_properties(cell, width\_dxa, bg\_hex, top\_pad=80, bottom\_pad=80, left\_pad=100, right\_pad=100):

    """Applies cell-level dimensions, margins, and background colors via XML."""

    tcPr \= cell.\_tc.get\_or\_add\_tcPr()

    

    \# Explicit Width

    tcW \= parse\_xml(f'\<w:tcW {nsdecls("w")} w:w="{width\_dxa}" w:type="dxa"/\>')

    tcPr.append(tcW)

    

    \# Background Shading

    shd \= parse\_xml(f'\<w:shd {nsdecls("w")} w:fill="{bg\_hex}"/\>')

    tcPr.append(shd)

    

    \# Cell Margins / Padding

    tcMar \= parse\_xml(f'''

        \<w:tcMar {nsdecls("w")}\>

            \<w:top w:w="{top\_pad}" w:type="dxa"/\>

            \<w:bottom w:w="{bottom\_pad}" w:type="dxa"/\>

            \<w:left w:w="{left\_pad}" w:type="dxa"/\>

            \<w:right w:w="{right\_pad}" w:type="dxa"/\>

        \</w:tcMar\>

    ''')

    tcPr.append(tcMar)

    

    cell.vertical\_alignment \= WD\_ALIGN\_VERTICAL.CENTER

---

## **7\. Implementation Roadmap**

\+-----------------------------------------------------------------------------------+

|                            4-SPRINT IMPLEMENTATION ROADMAP                        |

\+-----------------------------------------------------------------------------------+

  SPRINT 1: Core Foundation & Data Layer

  \[========================================\] 100%

  \- Database schema deployment & pgvector initialization

  \- Unstructured syllabus document parser (FastAPI \+ LLM pipeline)

  \- Raw JSON module definitions & API contracts

  SPRINT 2: Mathematical Engine & Solver Integration

  \[========================================\] 100%

  \- Google OR-Tools CP-SAT formulation & rotation logic

  \- Hard constraint enforcement (Rooms, Batches, Friday limits)

  \- Vector similarity integration for objective linkage

  SPRINT 3: Interactive UI & AI Copilot Workspace

  \[========================================\] 100%

  \- Next.js high-density timetable matrix rendering grid

  \- Drag-and-Drop conflict checking engine

  \- LLM Copilot interface for natural language schedule edits

  SPRINT 4: Native Document Exporter & Deployment

  \[========================================\] 100%

  \- \`python-docx\` XML rendering engine implementation

  \- Single landscape page layout validation

  \- End-to-end integration testing, QA, and deployment

\+-----------------------------------------------------------------------------------+

### **Sprint Breakdown**

* **Sprint 1: Core Data Infrastructure & Parsing Engine**  
  * Set up PostgreSQL with the `pgvector` extension and establish DB schema migrations.  
  * Build the FastAPI document ingestion module (`python-docx` / `pypdf`).  
  * Implement the LLM extraction pipeline using Pydantic JSON schemas.  
  * *Deliverable:* API endpoints that ingest raw syllabus documents and output structured JSON learning objectives.  
* **Sprint 2: Constraint Solver & Semantic Engine**  
  * Integrate Google OR-Tools CP-SAT engine for schedule optimization.  
  * Write mathematical rules for 4-batch lab rotations, SGDs, and Friday half-day caps.  
  * Create the embedding pipeline for cosine similarity clustering using `pgvector`.  
  * *Deliverable:* Functional solver module capable of generating optimal schedules within 30 seconds.  
* **Sprint 3: Matrix UI & Real-Time Copilot Interface**  
  * Construct the Next.js matrix grid UI for schedule visualization.  
  * Implement interactive drag-and-drop mechanics with real-time validation checks against the backend.  
  * Deploy the natural language Copilot chat interface for dynamic schedule adjustments.  
  * *Deliverable:* Web platform for reviewing, validating, and fine-tuning generated schedules.  
* **Sprint 4: Layout Exporter, Optimization & Handover**  
  * Build the `python-docx` XML generation pipeline for single-page landscape exports.  
  * Calibrate font styles, padding values, and explicit column widths (`dxa`) to match layout specifications.  
  * Conduct end-to-end user acceptance testing across edge-case schedule scenarios.  
  * *Deliverable:* Production-ready software pipeline for generating publication-quality `.docx` timetables.

