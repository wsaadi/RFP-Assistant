export enum SectionStatus {
  NOT_STARTED = 'not_started',
  IN_PROGRESS = 'in_progress',
  COMPLETED = 'completed',
  NEEDS_REVIEW = 'needs_review',
}

export interface SectionNote {
  id: string;
  content: string;
  created_at?: string;
  updated_at?: string;
}

export interface ReportSection {
  id: string;
  title: string;
  description: string;
  required: boolean;
  order: number;
  parent_id?: string;
  min_pages?: number;
  max_pages?: number;
  status: SectionStatus;
  notes: SectionNote[];
  content: string;
  generated_questions: string[];
  recommendations: string[];
  subsections: ReportSection[];
}

export interface ReportPlan {
  sections: ReportSection[];
  total_min_pages: number;
  total_max_pages: number;
}

export interface ReportData {
  id: string;
  student_name: string;
  student_firstname: string;
  semester: string;
  company_name: string;
  company_location: string;
  internship_start_date: string;
  internship_end_date: string;
  tutor_name: string;
  plan: ReportPlan;
  created_at?: string;
  updated_at?: string;
}

export interface AIProviderConfig {
  provider: 'openai' | 'mistral';
  api_key: string;
}

export interface ReportProgress {
  total_sections: number;
  completed: number;
  in_progress: number;
  not_started: number;
  progress_percentage: number;
}

export interface CreateReportRequest {
  student_name: string;
  student_firstname: string;
  semester: string;
  company_name: string;
  company_location: string;
  internship_start_date: string;
  internship_end_date: string;
  tutor_name: string;
}
