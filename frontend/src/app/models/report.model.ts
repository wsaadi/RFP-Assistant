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
  company_name: string;
  rfp_reference: string;
  deadline: string;
  status: string;
  improvement_axes: string;
  ai_context: string;
  enabled_categories: string[];
  context_mode: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  document_count: number;
  chapter_count: number;
  current_user_role: string | null;
}

export interface ProjectCreate {
  name: string;
  description: string;
  client_name: string;
  company_name: string;
  rfp_reference: string;
  deadline: string;
  ai_context: string;
  enabled_categories: string[];
  context_mode: string;
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

export interface DocumentProgress {
  document_id: string;
  filename: string;
  step: string;
  step_label: string;
  progress: number;
  /** Authoritative status from the database (pending/processing/completed/failed) */
  db_status?: string;
}

export interface ImageOccurrence {
  page_number: number;
  document_id: string;
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
  image_category: string;
  selected: boolean;
  analysis_status: string;
  image_type: string;
  // Analysis results
  key_information: string[];
  pii_detected: { type: string; value: string }[];
  ocr_text: string;
  suggested_usage: string;
  anonymized_description: string;
  // Deduplication
  occurrence_count: number;
  occurrences: ImageOccurrence[];
  duplicate_ids: string[];
}

export interface ImageAnalysisStatus {
  status: 'idle' | 'running' | 'completed' | 'error';
  step: string;
  progress: number;
  message: string;
}

// ── Chapter ──
export interface Chapter {
  id: string;
  project_id: string;
  parent_id: string | null;
  response_document_id: string | null;
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
  word_limit: number;
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
  id?: string;
  new_requirements: { title: string; description: string; priority: string; source_new?: string }[];
  removed_requirements: { title: string; description: string; source_old?: string }[];
  modified_requirements: { title: string; old_description: string; new_description: string; impact: string; source_old?: string; source_new?: string }[];
  unchanged_requirements: { title: string; description: string; source_old?: string; source_new?: string }[];
  summary: string;
  created_at?: string;
}

export interface ComplianceAnalysis {
  id?: string;
  score: number;
  covered_requirements: { requirement: string; coverage: string; comment: string; source_rfp?: string; source_response?: string }[];
  missing_elements: { requirement: string; description: string; source_rfp?: string }[];
  recommendations: string[];
  summary: string;
  created_at?: string;
}

// ── Generation Progress ──
export interface GenerationStatus {
  status: 'idle' | 'running' | 'completed' | 'error';
  step: string;
  progress: number;
  message: string;
  chapters_created?: number;
  completion_docs_count?: number;
  delta_stats?: { new: number; modified: number; unchanged: number };
  has_gap_analysis?: boolean;
}

// ── Response Documents (Deliverables) ──
export interface ResponseDocument {
  id: string;
  project_id: string;
  title: string;
  description: string;
  expected_format: string;
  content_type: 'redaction' | 'completion';
  is_selected: boolean;
  order: number;
  rfp_source: string;
  fill_content: string;
  fill_status: 'pending' | 'generating' | 'completed' | 'error';
  source_document_ids: string[];
  source_categories: string[];
  include_generated_content: boolean;
  custom_notes: string;
  created_at: string;
  updated_at: string;
  chapter_count: number;
  _fillingExcel?: boolean;
  _fillingPdf?: boolean;
  _fillProgress?: { status: string; step: string; progress: number; message: string };
  _fillPollSub?: any;
  _showConfig?: boolean;
}

export interface DetectDeliverablesStatus {
  status: 'idle' | 'running' | 'completed' | 'error';
  step: string;
  progress: number;
  message: string;
  deliverables_count?: number;
}

export interface FillDeliverablesStatus {
  status: 'idle' | 'running' | 'completed' | 'error';
  step: string;
  progress: number;
  message: string;
  filled_count?: number;
}

// ── Prefill Progress ──
export interface PrefillStatus {
  status: 'idle' | 'running' | 'completed' | 'error';
  step: string;
  progress: number;
  message: string;
  prefilled_count?: number;
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
  chapters_by_status: Record<string, number>;
}

// ── AI Config ──
export interface AIConfig {
  provider: string;
  mistral_api_key?: string;
  model_name: string;
  temperature: number;
  max_tokens: number;
  has_api_key?: boolean;
  ollama_base_url: string;
  ollama_model: string;
  ner_provider: string;
  ner_model: string;
  vision_provider: string;
  vision_model: string;
  has_scaleway_key?: boolean;
  scaleway_project_id?: string;
}

export interface AIConfigUpdate {
  provider: string;
  mistral_api_key: string;
  model_name: string;
  temperature: number;
  max_tokens: number;
  ollama_base_url: string;
  ollama_model: string;
  ner_provider: string;
  ner_model: string;
  vision_provider: string;
  vision_model: string;
  scaleway_api_key: string;
  scaleway_project_id: string;
}

// ── Anonymization ──
export interface AnonymizationMapping {
  id: string;
  entity_type: string;
  original_value: string;
  anonymized_value: string;
  is_active: boolean;
}

export interface AnonymizationEntityGroup {
  entity_type: string;
  label: string;
  count: number;
  mappings: AnonymizationMapping[];
}

export interface AnonymizationReport {
  total_entities: number;
  active_entities: number;
  entity_groups: AnonymizationEntityGroup[];
  sample_before: string;
  sample_after: string;
}

// ── Fields to Complete (AI-invented placeholders) ──
export interface FieldChapterDetail {
  chapter_id: string;
  title: string;
  numbering: string;
}

export interface FieldToComplete {
  placeholder: string;
  readable_label: string;
  occurrences: number;
  chapters: string[];
  chapter_details: FieldChapterDetail[];
}

export interface FieldsToComplete {
  total: number;
  fields: FieldToComplete[];
}

// ── Content Reuse Statistics ──
export interface ContentReuseChapter {
  chapter_id: string;
  title: string;
  numbering: string;
  word_count: number;
  reuse_percentage: number;
  ngram_match: number;
  sequence_match: number;
}

export interface ContentReuseStats {
  has_old_response: boolean;
  overall_reuse_percentage: number;
  chapters: ContentReuseChapter[];
  summary: {
    total_chapters: number;
    chapters_with_reuse: number;
    avg_reuse_percentage: number;
    old_response_word_count: number;
    new_content_word_count: number;
  };
}

// ── AI Cost Tracking ──
export interface AICostDaily {
  date: string;
  input_tokens: number;
  output_tokens: number;
  cost: number;
  requests: number;
}

export interface AICostByModel {
  provider: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cost: number;
  requests: number;
}

export interface AIModelPricing {
  id: string;
  provider: string;
  model_name: string;
  price_per_1k_input: number;
  price_per_1k_output: number;
  currency: string;
}

export interface AICostTracking {
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost: number;
  total_requests: number;
  daily: AICostDaily[];
  by_model: AICostByModel[];
  pricing: AIModelPricing[];
  recent_logs: {
    id: string;
    operation: string;
    provider: string;
    model_name: string;
    input_tokens: number;
    output_tokens: number;
    created_at: string;
  }[];
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

// ── Soutenance ──
export interface SoutenanceQuestion {
  question: string;
  answer: string;
  tips: string;
}

export interface SoutenanceDifficultTopic {
  topic: string;
  strategy: string;
}

export interface SoutenanceScriptSection {
  title: string;
  duration: string;
  presenter_guide: string;
  key_messages: string[];
  anticipated_questions: string[];
  suggested_answers: string[];
}

export interface SoutenanceScript {
  project_name: string;
  client_name: string;
  company_name: string;
  rfp_reference: string;
  total_duration: string;
  introduction: string;
  sections: SoutenanceScriptSection[];
  closing: string;
  qa_preparation: {
    expected_questions: SoutenanceQuestion[];
    difficult_topics: SoutenanceDifficultTopic[];
  };
  general_tips: string[];
  sections_overview: { title: string; duration: string }[];
  key_figures: { value: string; label: string }[];
  strengths: string[];
}

// ── Preview ──
export interface PreviewDocumentGroup {
  id: string | null;
  title: string;
  description: string;
  chapters: PreviewChapter[];
}

export interface DocumentPreview {
  project_name: string;
  client_name: string;
  rfp_reference: string;
  chapters: PreviewChapter[];
  documents?: PreviewDocumentGroup[];
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
