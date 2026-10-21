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
}

export interface LegendEntry {
  code: string;
  title: string;
}

export interface ExtractedModuleMeta {
  program?: string | null;
  academic_year?: number | null;
  module_title?: string | null;
  module_code?: string | null;
  session?: string | null;
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
}

export interface ProposedLink {
  id: string;
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
  };
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
