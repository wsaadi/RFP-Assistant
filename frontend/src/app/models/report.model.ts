// ── Auth ──
export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user_id: string;
  role: string;
  username: string;
}

export interface UserInfo {
  id: string;
  email: string;
  username: string;
  full_name: string;
  role: string;
  is_active: boolean;
}

export interface UserCreate {
  email: string;
  username: string;
  password: string;
  full_name: string;
  role: string;
}

export interface UserUpdate {
  email?: string;
  username?: string;
  full_name?: string;
  is_active?: boolean;
  role?: string;
}

// ── Workspace ──
export interface Workspace {
  id: string;
  name: string;
  description: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  member_count: number;
  project_count: number;
}

export interface WorkspaceMember {
  id: string;
  user_id: string;
  username: string;
  email: string;
  full_name: string;
  role: string;
  joined_at: string;
}

// ── Project ──
export interface RFPProject {
  id: string;
  workspace_id: string;
  name: string;
  description: string;
  client_name: string;
  rfp_reference: string;
  deadline: string;
  status: string;
  improvement_axes: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  document_count: number;
  chapter_count: number;
}

export interface ProjectCreate {
  name: string;
  description: string;
  client_name: string;
  rfp_reference: string;
  deadline: string;
}

// ── Document ──
export interface DocumentInfo {
  id: string;
  project_id: string;
  category: string;
  original_filename: string;
  file_type: string;
  file_size: number;
  processing_status: string;
  page_count: number;
  chunk_count: number;
  uploaded_by: string;
  created_at: string;
}

export interface DocumentImage {
  id: string;
  document_id: string;
  stored_filename: string;
  description: string;
  page_number: number;
  context: string;
  tags: string[];
  width: number;
  height: number;
}

// ── Chapter ──
export interface Chapter {
  id: string;
  project_id: string;
  parent_id: string | null;
  title: string;
  description: string;
  order: number;
  chapter_type: string;
  content: string;
  status: string;
  notes: ChapterNote[];
  improvement_axes: any[];
  source_references: any[];
  image_references: any[];
  rfp_requirement: string;
  is_prefilled: boolean;
  numbering: string;
  created_at: string;
  updated_at: string;
  children: Chapter[];
}

export interface ChapterNote {
  id: string;
  content: string;
  author: string;
  created_at: string;
}

// ── Analysis ──
export interface GapAnalysis {
  new_requirements: { title: string; description: string; priority: string }[];
  removed_requirements: { title: string; description: string }[];
  modified_requirements: { title: string; old_description: string; new_description: string; impact: string }[];
  unchanged_requirements: { title: string; description: string }[];
  summary: string;
}

export interface ComplianceAnalysis {
  score: number;
  covered_requirements: { requirement: string; coverage: string; comment: string }[];
  missing_elements: { requirement: string; description: string }[];
  recommendations: string[];
  summary: string;
}

// ── Statistics ──
export interface ProjectStatistics {
  total_pages: number;
  total_words: number;
  total_characters: number;
  anonymized_entities: number;
  chapters_completed: number;
  chapters_total: number;
  chapters_in_progress: number;
  documents_count: number;
  images_count: number;
  completion_percentage: number;
}

// ── AI Config ──
export interface AIConfig {
  model_name: string;
  temperature: number;
  max_tokens: number;
  has_api_key: boolean;
}

export interface AIConfigUpdate {
  mistral_api_key: string;
  model_name: string;
  temperature: number;
  max_tokens: number;
}

// ── Anonymization ──
export interface AnonymizationMapping {
  id: string;
  entity_type: string;
  original_value: string;
  anonymized_value: string;
  is_active: boolean;
}

// ── Search ──
export interface SearchResult {
  chunk_id: string;
  content: string;
  document_name: string;
  category: string;
  page_number: number;
  score: number;
}

// ── Preview ──
export interface DocumentPreview {
  project_name: string;
  client_name: string;
  rfp_reference: string;
  chapters: PreviewChapter[];
}

export interface PreviewChapter {
  id: string;
  title: string;
  numbering: string;
  level: number;
  content: string;
  status: string;
  chapter_type: string;
  children: PreviewChapter[];
}
