export type SessionType =
  | "LGIS"
  | "PRACTICAL"
  | "SGD"
  | "DSL"
  | "SDL"
  | "RIPPLE"
  | "ISL"
  | "MENTOR_MENTEE"
  | "PAL"
  | "SKILL_LAB"
  | "BREAK"
  | "HALF_DAY";

export type DisciplineCategory =
  | "ANATOMY"
  | "PHYSIOLOGY"
  | "BIOCHEMISTRY"
  | "CLINICAL"
  | "INSTITUTIONAL";

export interface ParsedTopic {
  topic_title: string;
  description: string;
  discipline: string;
  raw_discipline: string;
  category: DisciplineCategory;
  session_type: SessionType;
  organ_system?: string | null;
  faculty_name?: string | null;
  duration_minutes: number;
  practical_code?: string | null;
  id?: string | null;
  original_week?: number | null;
  original_day?: number | null;
  original_start?: string | null;
  original_end?: string | null;
  program?: string | null;
  academic_year?: number | null;
  /** Class key, e.g. "MBBS-2". */
  cohort?: string | null;
  /** Times the topic appears in the uploaded timetable. */
  occurrences?: number;
}

export interface LegendEntry {
  code: string;
  title: string;
  cohort?: string | null;
}

/** One class (e.g. 2nd Year MBBS) found in an upload. */
export interface CohortSummary {
  cohort: string;
  label: string;
  program: string;
  academic_year: number;
  module_title?: string | null;
  module_code?: string | null;
  /** Academic session read from the header, e.g. "2026-2027". */
  session?: string | null;
  /** True when program/year came from the file (header or file name) rather than the form. */
  class_detected?: boolean;
  source?: string | null;
  topic_count: number;
}

export interface ExtractedModuleMeta {
  program?: string | null;
  academic_year?: number | null;
  module_title?: string | null;
  module_code?: string | null;
  session?: string | null;
}

/** One batch (or group of batches) inside a practical / SGD rotation block. */
export interface SessionBatch {
  batches: string[];
  station: string;
  discipline: string;
  code?: string | null;
  topic_title?: string | null;
  faculty_names: string[];
}

/** One session exactly where the uploaded timetable puts it (real timetable uploads). */
export interface ParsedSession {
  id?: string | null;
  cohort?: string | null;
  week: number;
  day_of_week: number;
  date?: string | null;
  time_start: string;
  time_end: string;
  kind: "TEACHING" | "ROTATION" | "EVENT" | string;
  session_type: SessionType;
  raw_session?: string;
  discipline: string;
  raw_discipline?: string;
  category?: DisciplineCategory;
  topic_title: string;
  faculty_names: string[];
  batches: SessionBatch[];
  topic_id?: string | null;
  movable: boolean;
}

export interface ParseResponse {
  meta: ExtractedModuleMeta;
  topics: ParsedTopic[];
  legend: LegendEntry[];
  faculty: string[];
  engine: "gemini" | "heuristic";
  warnings: string[];
  module_id?: string | null;
  persisted: boolean;
  cohorts?: CohortSummary[];
  /** Every session in its original slot (real timetable uploads only). */
  sessions?: ParsedSession[];
  /** Teacher spelling variants merged into one name, variant -> canonical. */
  teacher_aliases?: Record<string, string>;
}

export interface ProposedLink {
  id: string;
  source_objective_id?: string | null;
  target_objective_id?: string | null;
  source_index: number;
  target_index: number;
  source_topic: string;
  target_topic: string;
  source_discipline: string;
  target_discipline: string;
  integration_type: "HORIZONTAL" | "VERTICAL";
  similarity_score: number;
  is_approved: boolean;
  rationale: string;
  source_cohort?: string | null;
  target_cohort?: string | null;
  shared_concepts?: string[];
}

export interface IntegrationClusterResult {
  links: ProposedLink[];
  horizontal_count: number;
  vertical_count: number;
  embedding_engine: string;
}

export interface BatchStationAssignment {
  batch: string;
  station: string;
  faculty?: string | null;
  venue?: string | null;
}

export interface ScheduledCell {
  id: string;
  day_of_week: number;
  day_name: string;
  time_start: string;
  time_end: string;
  session_type: string;
  discipline: string;
  category: DisciplineCategory;
  topic_title: string;
  faculty_name?: string | null;
  venue_name?: string | null;
  student_batch_mask: string;
  batch_assignments: BatchStationAssignment[];
  is_conflicted: boolean;
  conflict_notes?: string | null;
  topic_id?: string | null;
  /** Linked topics taught together, e.g. "G2 · heart". */
  integration_group?: string | null;
  /** "↔ Physiology: Cardiac cycle (Tue 09:00)" or "↕ 4th Year MBBS Medicine: …" */
  integration_tags?: string[];
  /** ISO date of the session (real timetables). */
  date?: string | null;
  /** TEACHING, ROTATION or EVENT (real timetables). */
  kind?: string | null;
  session_id?: string | null;
  /** Where the integrator moved this lecture from, e.g. "Week 3 · Wed 29/10 09:00". */
  moved_from?: string | null;
}

/** One lecture the integrator moved (real timetables). */
export interface LectureMove {
  session_id?: string | null;
  topic_title: string;
  discipline: string;
  session_type: string;
  faculty_name?: string | null;
  from_week: number;
  from_day: number;
  from_date?: string | null;
  from_start: string;
  from_end: string;
  from_label: string;
  to_week: number;
  to_day: number;
  to_date?: string | null;
  to_start: string;
  to_end: string;
  to_label: string;
  week_shift: number;
  linked_with: string[];
  reason: string;
}

export interface LinkDistanceMetrics {
  linked_pairs: number;
  avg_day_distance: number;
  same_week_pct: number;
  within_2_days_pct: number;
  same_day_pct: number;
  logical_order_pct: number;
}

export interface TemplateIntegrationMetrics {
  before?: LinkDistanceMetrics;
  after?: LinkDistanceMetrics;
  moved_lectures?: number;
  cross_week_moves?: number;
  movable_lectures?: number;
  max_week_shift?: number | null;
}

export interface TopicCoverageRow {
  discipline: string;
  topic: string;
  classes: number;
}

export interface IntegrationMetrics {
  linked_groups: number;
  linked_sessions: number;
  groups_within_2_days: number;
  groups_in_logical_order: number;
  average_day_span: number;
}

export interface TimetableSchedule {
  module_code: string;
  module_title: string;
  academic_year: number;
  week_number: number;
  total_weeks?: number;
  session: string;
  cells: ScheduledCell[];
  solver_status: string;
  total_contact_hours: number;
  analytics: {
    contact_hours_by_discipline?: Record<string, number>;
    faculty_hours?: Record<string, number>;
    time_bracket_distribution?: Record<string, number>;
    classes_by_discipline?: Record<string, number>;
    classes_by_faculty?: Record<string, number>;
    classes_by_session_type?: Record<string, number>;
    topic_coverage?: TopicCoverageRow[];
    integration?: IntegrationMetrics;
  };
  program?: string;
  cohort?: string | null;
  cohort_label?: string | null;
  /** Built from the uploaded timetable's exact sessions (structure kept). */
  template?: boolean;
  /** day_of_week -> ISO date for this week. */
  week_dates?: Record<string, string>;
  /** Every lecture the integrator moved across the whole module. */
  moves?: LectureMove[];
  integration_metrics?: TemplateIntegrationMetrics;
}

export interface MultiCohortSchedule {
  schedules: TimetableSchedule[];
  shared_teacher_sessions: number;
  warnings: string[];
}

export interface SubjectStat {
  cohort?: string | null;
  cohort_label?: string | null;
  discipline: string;
  classes: number;
  topics: number;
  contact_hours: number;
  teachers: string[];
  integrated_topics: number;
}

export interface TeacherStat {
  faculty: string;
  classes: number;
  contact_hours: number;
  subjects: string[];
  cohorts: string[];
}

export interface TopicCoverage {
  cohort?: string | null;
  discipline: string;
  topic: string;
  session_type: string;
  times_covered: number;
  faculty: string[];
  horizontal_links: number;
  vertical_links: number;
}

export interface CurriculumReport {
  totals: {
    cohorts: number;
    classes: number;
    contact_hours: number;
    subjects: number;
    teachers: number;
    topics: number;
    horizontal_links: number;
    vertical_links: number;
  };
  subjects: SubjectStat[];
  teachers: TeacherStat[];
  topics: TopicCoverage[];
}

export interface ConflictDetail {
  severity: "ERROR" | "WARNING";
  message: string;
  conflicting_cell_ids: string[];
  suggested_alternative_slots: string[];
}

export interface ValidationResult {
  is_valid: boolean;
  conflicts: ConflictDetail[];
  updated_cell: ScheduledCell;
}

export interface CopilotChatResponse {
  reply: string;
  action_taken: string;
  updated_schedule: TimetableSchedule;
  affected_cell_id?: string | null;
  conflicts: ConflictDetail[];
}

export interface Department {
  id?: string | null;
  name: string;
  code?: string | null;
  is_active: boolean;
}
