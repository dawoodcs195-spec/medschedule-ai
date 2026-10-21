# **BDS / MBBS Integrated Modular Curriculum & Timetable Management Engine**

# **Project Documentation & Discovery Specification**

October 2026

# **1\. Executive Summary**

The client—a BDS doctor and medical/dental academic professor—requires an intelligent, AI-assisted curriculum alignment and timetable scheduling platform. In contemporary medical and dental education aligned with WFME and PMDC standards, institutions are rapidly transitioning from legacy, subject-based syllabi to **Modular Integrated Curricula**.

The primary goal of this platform is to ingest fragmented or raw syllabi and timetables across 5-year MBBS and 4-year BDS programs, intelligently identify thematic overlaps, integrate related topics both horizontally and vertically, generate harmonized schedules, and provide conversational AI rescheduling alongside comprehensive academic workload analytics.

# **2\. Core Functional Requirements**

# **2.1 AI-Driven Curriculum Integration**

## **Horizontal Integration (Intra-Year Synchronization)**

When a specific bodily or organ system is taught within a single academic year, all corresponding basic science disciplines must run synchronously.

* **Example:** When teaching the "Eye" module, the schedule must seamlessly co-locate Anatomy of the Eye, Physiology of Vision, and Histology/Pathology together rather than dispersing them across separate months.

## **Vertical Integration (Inter-Year / Pre-Clinical to Clinical Progression)**

Linking foundational topics taught in earlier years (1st and 2nd year) directly to clinical, medical, and surgical specialties in subsequent senior years (3rd, 4th, and 5th year).

* **Example:** Basic eye anatomy and physiology from early years must link forward to Ophthalmology, Ophthalmic Surgery, and Systemic Medicine during clinical ward rotations.

## **Semantic De-duplication & Topic Clustering**

Ingest unstructured topic lists or legacy schedules and automatically cluster them by theme or organ system to eliminate haphazard, fragmented schedules and resolve curriculum redundancies.

# **2.2 Timetable Generation & Natural Language Editing**

## **Automated Modular Scheduling**

Automatically allocate lectures, practicals, small group discussions (SGDs), and clinical ward postings into conflict-free weekly and monthly grids.

## **Interactive AI Copilot (Natural Language Rescheduling)**

Enable the professor or academic coordinator to perform direct schedule modifications using conversational instructions via an integrated chat panel.

* **Capability:** Accept commands such as *"Reassign Dr. Khan's Friday 9 AM session to Dr. Tariq"* or *"Move the Ophthalmic Surgery practical to next Tuesday morning."*  
* **Validation:** The AI automatically validates instructor availability, room clashes, and prerequisite timing to update the schedule without breaking cross-discipline horizontal alignment.

# **2.3 Workload Tracking & Academic Analytics**

## **Contact Hours Tracking**

Track and aggregate the total number of instructional classes, practicals, and credit hours delivered per subject and discipline against target curriculum requirements.

## **Slot Distribution Analytics**

Count and report session allocations across specific daily slots (e.g., total 8:00 AM – 9:00 AM lecture allocations per subject) to ensure fair distribution and avoid subject bias.

## **Faculty Workload & Quota Metrics**

Calculate total teaching, laboratory supervision, and clinical supervisory hours completed by each faculty member to support institutional compliance, regulatory reporting, and performance audits

# **3\. Real-World Timetable Breakdown & System Architecture (Reverse-Engineered from Client Sample)**

## **3.1 Program & Cohort Context**

The operational specifications reverse-engineered from the client sample timetable (2026 Neurosciences Block-IV, Module-07) define the target curriculum framework for 2nd Year MBBS:

* **Target Cohort:** 2nd Year MBBS, Neurosciences Block-IV (Module-07).  
* **Academic Week Structure:** 6-day academic week (Monday to Saturday), with Friday operating as a Half-Day.

## **3.2 Operating Hours & Time Brackets**

* **Standard Operating Window:** 08:00 AM to 02:00 PM (14:00).  
* **Break Slot:** Daily break from 12:00 PM to 12:30 PM.  
* **Friday Schedule:** Concludes early at 12:00 PM.

## **3.3 Instructional Formats & Session Types**

* **LGIS (Large Group Interactive Sessions):** Didactic lectures (1-hour slots), delivered by single faculty to the entire cohort.  
* **Practicals:** 1.5 to 2-hour multi-batch practical sessions where student batches (Batches A, B, C, D) rotate simultaneously across Histology, Physiology, Biochemistry, and Skill Lab environments.  
* **SGD (Small Group Discussions):** 1.5-hour interactive learning sessions, with batches rotating through Anatomy, Physiology, Biochemistry, and Self-Directed Learning (SDL).  
* **DSL / SDL:** Directed Self-Learning / Self-Directed Learning sessions held in the Digital Library.  
* **PAL / MMT:** Peer-Assisted Learning and Mentor-Mentee Meetings integrated into periodic review slots.

## **3.4 Observed Curriculum Integration In Action**

* **Horizontal Integration:** When teaching the "Spinal Cord" topic, Anatomy covers external features and grey matter, Histology examines spinal cord tissue sections, Physiology delivers motor organization lectures, and Biochemistry addresses relevant metabolic markers within the exact same week.  
* **Vertical Integration:** Clinical faculty (Surgery, Medicine, ENT, Pediatrics, Radiology) are scheduled directly alongside basic science modules (e.g., Spine Trauma & Spine Tumors taught by Surgery, Paraplegia by Medicine, Head Trauma and Neck Triangles by ENT, Hydrocephalus by Pediatrics/Surgery, and CT/MRI of Skull by Radiology).

# **4\. Concrete Constraints & Specifications**

* **Campus Infrastructure Constraints:** Exactly 8 Lecture Halls and 3 Practical Laboratories (supplemented by Skill Lab and Digital Library facilities).  
* **Faculty Scheduling Constraints:** No rigid external time/day restrictions on faculty availability, granting administrative scheduling flexibility for academic coordinators.  
* **User Access Model:** Single-role Admin / Academic Coordinator platform in Phase 1 (no independent student or faculty portals).  
* **Output & Deliverable Format:** Native Microsoft Word (.docx) document containing the complete timetable matrix export, preserving multi-batch cell splitting and multi-span layout grid formatting matching institutional standards.

# **5\. System Implementation Strategy for .docx Export & Auto-Scheduler**

* **Solver Engine:** A deterministic batch rotation matrix algorithm that distributes Batches A–D seamlessly across Histology, Physiology, Biochemistry, and Skill Lab environments without laboratory collisions, accounting for the 3 physical labs plus skill lab constraint.  
* **Word Exporter:** Backend document generation engine built on *python-docx* or *docx* (Node.js). Implements precise cell merging (*gridSpan* and *rowSpan*), custom table header shading, and landscape page orientation for clear printability.  
* **Final Confirmed User Workflow & Operational Rules:**  
  * **Input Workflow:** The admin will paste raw lists of topics or upload existing unintegrated timetables for the AI engine to parse, match, and integrate horizontally and vertically.  
  * **Cohort Sizing & Batching:** Exactly 100 students per cohort. LGIS lectures host all 100 students together in a single lecture hall. SGDs and Practicals strictly split the 100 students into 4 Batches (A, B, C, D) of \~25 students each, rotating across the 3 physical labs and the skill lab.  
  * **Word (.docx) Export Layout:** Every module/week timetable must export on a single landscape-oriented page table, matching institutional multi-span cell formatting.