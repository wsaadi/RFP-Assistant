import { Injectable } from '@angular/core';
import { HttpClient, HttpEventType, HttpRequest } from '@angular/common/http';
import { Observable, Subject } from 'rxjs';
import {
  Workspace, WorkspaceMember,
  RFPProject, ProjectCreate,
  DocumentInfo, DocumentImage, DocumentProgress,
  Chapter,
  GapAnalysis, ComplianceAnalysis,
  ProjectStatistics, AnonymizationMapping, AnonymizationReport,
  GenerationStatus, PrefillStatus, DetectDeliverablesStatus, FillDeliverablesStatus, ResponseDocument,
  SearchResult, DocumentPreview,
  AIConfig, AIConfigUpdate,
  UserInfo, UserCreate, UserUpdate,
  FieldsToComplete,
  ImageAnalysisStatus,
} from '../models/report.model';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private baseUrl = '/api';

  constructor(private http: HttpClient) {}

  // ── Health ──
  healthCheck(): Observable<{ status: string; service: string }> {
    return this.http.get<any>(`${this.baseUrl}/health`);
  }

  // ── Workspaces ──
  getWorkspaces(): Observable<Workspace[]> {
    return this.http.get<Workspace[]>(`${this.baseUrl}/workspaces`);
  }

  getWorkspace(id: string): Observable<Workspace> {
    return this.http.get<Workspace>(`${this.baseUrl}/workspaces/${id}`);
  }

  createWorkspace(data: { name: string; description: string }): Observable<Workspace> {
    return this.http.post<Workspace>(`${this.baseUrl}/workspaces`, data);
  }

  updateWorkspace(id: string, data: any): Observable<Workspace> {
    return this.http.put<Workspace>(`${this.baseUrl}/workspaces/${id}`, data);
  }

  deleteWorkspace(id: string): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/workspaces/${id}`);
  }

  getWorkspaceMembers(workspaceId: string): Observable<WorkspaceMember[]> {
    return this.http.get<WorkspaceMember[]>(`${this.baseUrl}/workspaces/${workspaceId}/members`);
  }

  addWorkspaceMember(workspaceId: string, userId: string, role: string): Observable<any> {
    return this.http.post(`${this.baseUrl}/workspaces/${workspaceId}/members`, { user_id: userId, role });
  }

  updateWorkspaceMemberRole(workspaceId: string, userId: string, role: string): Observable<WorkspaceMember> {
    return this.http.put<WorkspaceMember>(`${this.baseUrl}/workspaces/${workspaceId}/members/${userId}`, { role });
  }

  removeWorkspaceMember(workspaceId: string, userId: string): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/workspaces/${workspaceId}/members/${userId}`);
  }

  // ── Projects ──
  getProjects(workspaceId: string): Observable<RFPProject[]> {
    return this.http.get<RFPProject[]>(`${this.baseUrl}/projects/workspace/${workspaceId}`);
  }

  getProject(id: string): Observable<RFPProject> {
    return this.http.get<RFPProject>(`${this.baseUrl}/projects/${id}`);
  }

  createProject(workspaceId: string, data: ProjectCreate): Observable<RFPProject> {
    return this.http.post<RFPProject>(`${this.baseUrl}/projects/workspace/${workspaceId}`, data);
  }

  updateProject(id: string, data: any): Observable<RFPProject> {
    return this.http.put<RFPProject>(`${this.baseUrl}/projects/${id}`, data);
  }

  deleteProject(id: string): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/projects/${id}`);
  }

  // ── Project Members ──
  getProjectMembers(projectId: string): Observable<any[]> {
    return this.http.get<any[]>(`${this.baseUrl}/projects/${projectId}/members`);
  }

  addProjectMember(projectId: string, userId: string, role: string): Observable<any> {
    return this.http.post(`${this.baseUrl}/projects/${projectId}/members`, { user_id: userId, role });
  }

  updateProjectMemberRole(projectId: string, userId: string, role: string): Observable<any> {
    return this.http.put(`${this.baseUrl}/projects/${projectId}/members/${userId}`, { role });
  }

  removeProjectMember(projectId: string, userId: string): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/projects/${projectId}/members/${userId}`);
  }

  // ── Documents ──
  getDocuments(projectId: string): Observable<DocumentInfo[]> {
    return this.http.get<DocumentInfo[]>(`${this.baseUrl}/documents/project/${projectId}`);
  }

  uploadDocument(projectId: string, file: File, category: string): Observable<DocumentInfo> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('category', category);
    return this.http.post<DocumentInfo>(`${this.baseUrl}/documents/upload/${projectId}`, formData);
  }

  /** Upload with HTTP progress events. Emits 0-100 for upload progress, then the server response. */
  uploadDocumentWithProgress(projectId: string, file: File, category: string): {
    progress$: Observable<number>;
    response$: Observable<DocumentInfo>;
  } {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('category', category);

    const progress$ = new Subject<number>();
    const response$ = new Subject<DocumentInfo>();

    const req = new HttpRequest('POST', `${this.baseUrl}/documents/upload/${projectId}`, formData, {
      reportProgress: true,
    });

    this.http.request(req).subscribe({
      next: (event) => {
        if (event.type === HttpEventType.UploadProgress && event.total) {
          progress$.next(Math.round(100 * event.loaded / event.total));
        } else if (event.type === HttpEventType.Response) {
          progress$.next(100);
          progress$.complete();
          response$.next(event.body as DocumentInfo);
          response$.complete();
        }
      },
      error: (err) => {
        progress$.error(err);
        response$.error(err);
      },
    });

    return { progress$, response$ };
  }

  deleteDocument(documentId: string): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/documents/${documentId}`);
  }

  getDocumentImages(documentId: string): Observable<DocumentImage[]> {
    return this.http.get<DocumentImage[]>(`${this.baseUrl}/documents/${documentId}/images`);
  }

  getProjectImages(projectId: string): Observable<DocumentImage[]> {
    return this.http.get<DocumentImage[]>(`${this.baseUrl}/documents/images/${projectId}`);
  }

  getImageUrl(imageId: string): string {
    return `${this.baseUrl}/documents/image-file/${imageId}`;
  }

  updateImage(imageId: string, data: { image_category?: string; selected?: boolean }): Observable<DocumentImage> {
    return this.http.put<DocumentImage>(`${this.baseUrl}/documents/image/${imageId}`, data);
  }

  batchUpdateImages(projectId: string, imageIds: string[], data: { image_category?: string; selected?: boolean }): Observable<{ updated: number }> {
    return this.http.put<{ updated: number }>(
      `${this.baseUrl}/documents/images-batch/${projectId}`,
      { image_ids: imageIds, ...data }
    );
  }

  analyzeImages(projectId: string, imageIds: string[]): Observable<{ status: string; count: number }> {
    return this.http.post<{ status: string; count: number }>(
      `${this.baseUrl}/documents/images-analyze/${projectId}`,
      { image_ids: imageIds }
    );
  }

  getImageAnalysisStatus(projectId: string): Observable<ImageAnalysisStatus> {
    return this.http.get<ImageAnalysisStatus>(`${this.baseUrl}/documents/images-analysis-status/${projectId}`);
  }

  searchDocuments(projectId: string, query: string, category?: string, topK: number = 10): Observable<{ results: SearchResult[] }> {
    return this.http.post<{ results: SearchResult[] }>(
      `${this.baseUrl}/documents/search/${projectId}`,
      { query, category, top_k: topK }
    );
  }

  getProcessingProgress(projectId: string): Observable<{ progress: DocumentProgress[] }> {
    return this.http.get<{ progress: DocumentProgress[] }>(`${this.baseUrl}/documents/progress/${projectId}`);
  }

  // ── Chapters ──
  getChapters(projectId: string): Observable<Chapter[]> {
    return this.http.get<Chapter[]>(`${this.baseUrl}/chapters/project/${projectId}`);
  }

  getChapter(chapterId: string): Observable<Chapter> {
    return this.http.get<Chapter>(`${this.baseUrl}/chapters/${chapterId}`);
  }

  createChapter(projectId: string, data: any): Observable<Chapter> {
    return this.http.post<Chapter>(`${this.baseUrl}/chapters/project/${projectId}`, data);
  }

  updateChapter(chapterId: string, data: any): Observable<Chapter> {
    return this.http.put<Chapter>(`${this.baseUrl}/chapters/${chapterId}`, data);
  }

  deleteChapter(chapterId: string): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/chapters/${chapterId}`);
  }

  bulkDeleteChapters(chapterIds: string[]): Observable<{ deleted: number }> {
    return this.http.post<{ deleted: number }>(`${this.baseUrl}/chapters/bulk-delete`, { chapter_ids: chapterIds });
  }

  addChapterNote(chapterId: string, content: string): Observable<any> {
    return this.http.post(`${this.baseUrl}/chapters/${chapterId}/note`, { content });
  }

  generateChapterContent(chapterId: string, action: string, customPrompt: string = '', useOldResponse: boolean = true, includeImprovementAxes: boolean = true): Observable<any> {
    return this.http.post<any>(
      `${this.baseUrl}/chapters/${chapterId}/generate-content`,
      { action, custom_prompt: customPrompt, use_old_response: useOldResponse, include_improvement_axes: includeImprovementAxes }
    );
  }

  getChapterGenStatus(chapterId: string): Observable<{ status: string; step: string; progress: number; message: string }> {
    return this.http.get<any>(`${this.baseUrl}/chapters/${chapterId}/generate-status`);
  }

  reorderChapters(chapterOrders: { id: string; order: number }[]): Observable<any> {
    return this.http.post(`${this.baseUrl}/chapters/reorder`, { chapter_orders: chapterOrders });
  }

  // ── AI Operations ──
  getGapAnalysis(projectId: string): Observable<{ analysis: GapAnalysis | null }> {
    return this.http.get<{ analysis: GapAnalysis | null }>(`${this.baseUrl}/projects/${projectId}/gap-analysis`);
  }

  analyzeGap(projectId: string): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/projects/${projectId}/gap-analysis`, {});
  }

  getGapAnalysisStatus(projectId: string): Observable<{ status: string; step: string; progress: number; message: string }> {
    return this.http.get<any>(`${this.baseUrl}/projects/${projectId}/gap-analysis-status`);
  }

  generateStructure(projectId: string): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/projects/${projectId}/generate-structure`, {});
  }

  getGenerationStatus(projectId: string): Observable<GenerationStatus> {
    return this.http.get<GenerationStatus>(`${this.baseUrl}/projects/${projectId}/generation-status`);
  }

  prefillChapters(projectId: string, chapterIds: string[] = []): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/projects/${projectId}/prefill`, { chapter_ids: chapterIds });
  }

  getPrefillStatus(projectId: string): Observable<PrefillStatus> {
    return this.http.get<PrefillStatus>(`${this.baseUrl}/projects/${projectId}/prefill-status`);
  }

  // ── Response Documents (Deliverables) ──
  detectDeliverables(projectId: string): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/projects/${projectId}/detect-deliverables`, {});
  }

  getDetectDeliverablesStatus(projectId: string): Observable<DetectDeliverablesStatus> {
    return this.http.get<DetectDeliverablesStatus>(`${this.baseUrl}/projects/${projectId}/detect-deliverables-status`);
  }

  getResponseDocuments(projectId: string): Observable<ResponseDocument[]> {
    return this.http.get<ResponseDocument[]>(`${this.baseUrl}/projects/${projectId}/response-documents`);
  }

  updateResponseDocument(projectId: string, docId: string, data: any): Observable<ResponseDocument> {
    return this.http.put<ResponseDocument>(`${this.baseUrl}/projects/${projectId}/response-documents/${docId}`, data);
  }

  confirmDocumentSelection(projectId: string, selections: { id: string; is_selected: boolean }[]): Observable<any> {
    return this.http.post(`${this.baseUrl}/projects/${projectId}/response-documents/confirm-selection`, { selections });
  }

  // ── Fill Deliverables (Excel/PDF completion) ──
  fillDeliverables(projectId: string): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/projects/${projectId}/fill-deliverables`, {});
  }

  getFillDeliverablesStatus(projectId: string): Observable<FillDeliverablesStatus> {
    return this.http.get<FillDeliverablesStatus>(`${this.baseUrl}/projects/${projectId}/fill-deliverables-status`);
  }

  resetFillContent(projectId: string, docId: string): Observable<ResponseDocument> {
    return this.http.post<ResponseDocument>(
      `${this.baseUrl}/projects/${projectId}/response-documents/${docId}/reset-fill`, {}
    );
  }

  fillExcelDocument(projectId: string, docId: string): Observable<Blob> {
    return this.http.post(
      `${this.baseUrl}/projects/${projectId}/fill-excel/${docId}`, {},
      { responseType: 'blob' }
    );
  }

  fillPdfDocument(projectId: string, docId: string): Observable<Blob> {
    return this.http.post(
      `${this.baseUrl}/projects/${projectId}/fill-pdf/${docId}`, {},
      { responseType: 'blob' }
    );
  }

  getComplianceAnalysis(projectId: string): Observable<{ analysis: ComplianceAnalysis | null }> {
    return this.http.get<{ analysis: ComplianceAnalysis | null }>(`${this.baseUrl}/projects/${projectId}/compliance-analysis`);
  }

  analyzeCompliance(projectId: string): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/projects/${projectId}/compliance-analysis`, {});
  }

  getComplianceAnalysisStatus(projectId: string): Observable<{ status: string; step: string; progress: number; message: string }> {
    return this.http.get<any>(`${this.baseUrl}/projects/${projectId}/compliance-analysis-status`);
  }

  launchRecommendationGeneration(
    projectId: string,
    recommendation: string,
    taskId: string,
    options?: { chapterId?: string; missingDescription?: string; inject?: boolean },
  ): Observable<{ task_id: string }> {
    return this.http.post<{ task_id: string }>(
      `${this.baseUrl}/projects/${projectId}/compliance-analysis/generate-recommendation`,
      {
        recommendation,
        task_id: taskId,
        chapter_id: options?.chapterId,
        missing_description: options?.missingDescription,
        inject: options?.inject ?? true,
      }
    );
  }

  getRecommendationGenStatus(
    projectId: string,
    taskId: string,
  ): Observable<{ status: string; step: string; progress: number; message: string; chapter_id?: string; chapter_title?: string; content?: string }> {
    return this.http.get<any>(
      `${this.baseUrl}/projects/${projectId}/compliance-analysis/generate-recommendation-status/${taskId}`
    );
  }

  exportCompliancePdf(projectId: string): Observable<Blob> {
    return this.http.get(`${this.baseUrl}/projects/${projectId}/compliance-analysis/export-pdf`, { responseType: 'blob' });
  }

  exportGapAnalysisPdf(projectId: string): Observable<Blob> {
    return this.http.get(`${this.baseUrl}/projects/${projectId}/gap-analysis/export-pdf`, { responseType: 'blob' });
  }

  addImprovementAxis(projectId: string, content: string, source: string = ''): Observable<any> {
    return this.http.post(`${this.baseUrl}/projects/${projectId}/improvement-axes`, { content, source });
  }

  getStatistics(projectId: string): Observable<ProjectStatistics> {
    return this.http.get<ProjectStatistics>(`${this.baseUrl}/projects/${projectId}/statistics`);
  }

  getAnonymizationMappings(projectId: string): Observable<AnonymizationMapping[]> {
    return this.http.get<AnonymizationMapping[]>(`${this.baseUrl}/projects/${projectId}/anonymization-mappings`);
  }

  getAnonymizationReport(projectId: string): Observable<AnonymizationReport> {
    return this.http.get<AnonymizationReport>(`${this.baseUrl}/projects/${projectId}/anonymization-report`);
  }

  createAnonymizationMapping(projectId: string, data: { entity_type: string; original_value: string; anonymized_value?: string }): Observable<AnonymizationMapping> {
    return this.http.post<AnonymizationMapping>(`${this.baseUrl}/projects/${projectId}/anonymization-mappings`, data);
  }

  updateAnonymizationMapping(projectId: string, mappingId: string, data: { original_value?: string; anonymized_value?: string; entity_type?: string; is_active?: boolean }): Observable<AnonymizationMapping> {
    return this.http.put<AnonymizationMapping>(`${this.baseUrl}/projects/${projectId}/anonymization-mappings/${mappingId}`, data);
  }

  deleteAnonymizationMapping(projectId: string, mappingId: string): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/projects/${projectId}/anonymization-mappings/${mappingId}`);
  }

  reAnonymizeProject(projectId: string): Observable<{ task_id: string; already_running?: boolean }> {
    return this.http.post<{ task_id: string; already_running?: boolean }>(`${this.baseUrl}/projects/${projectId}/re-anonymize`, {});
  }

  getReAnonymizeStatus(projectId: string): Observable<any> {
    return this.http.get<any>(`${this.baseUrl}/projects/${projectId}/re-anonymize-status`);
  }

  getNerDiagnostic(projectId: string): Observable<any> {
    return this.http.get<any>(`${this.baseUrl}/projects/${projectId}/ner-diagnostic`);
  }

  resolveOrphansWithAI(projectId: string): Observable<{ resolved: number; suggestions: any[] }> {
    return this.http.post<{ resolved: number; suggestions: any[] }>(`${this.baseUrl}/projects/${projectId}/resolve-orphans-ai`, {});
  }

  consolidateMappings(projectId: string): Observable<{ merged: number; groups: any[] }> {
    return this.http.post<{ merged: number; groups: any[] }>(`${this.baseUrl}/projects/${projectId}/consolidate-mappings`, {});
  }

  getChapterAnonymizedContent(projectId: string, chapterId: string): Observable<{ anonymized_content: string }> {
    return this.http.get<{ anonymized_content: string }>(`${this.baseUrl}/projects/${projectId}/chapters/${chapterId}/anonymized-content`);
  }

  purgeAnonymization(projectId: string): Observable<{ restored_chapters: number; cleared_chunks: number; deleted_mappings: number }> {
    return this.http.post<{ restored_chapters: number; cleared_chunks: number; deleted_mappings: number }>(`${this.baseUrl}/projects/${projectId}/purge-anonymization`, {});
  }

  // ── Fields to Complete ──
  getFieldsToComplete(projectId: string): Observable<FieldsToComplete> {
    return this.http.get<FieldsToComplete>(`${this.baseUrl}/projects/${projectId}/fields-to-complete`);
  }

  replaceFieldToComplete(projectId: string, placeholder: string, value: string): Observable<{ updated_chapters: number; total_replacements: number }> {
    return this.http.post<{ updated_chapters: number; total_replacements: number }>(`${this.baseUrl}/projects/${projectId}/fields-to-complete/replace`, { placeholder, value });
  }

  // ── Export/Import ──
  exportWord(projectId: string): Observable<any> {
    return this.http.post(`${this.baseUrl}/export/${projectId}/word`, {});
  }

  getWordStatus(projectId: string): Observable<{ status: string; step: string; progress: number; message: string }> {
    return this.http.get<any>(`${this.baseUrl}/export/${projectId}/word-status`);
  }

  downloadWord(projectId: string): Observable<Blob> {
    return this.http.get(`${this.baseUrl}/export/${projectId}/word-download`, { responseType: 'blob' });
  }

  exportBackup(projectId: string): Observable<any> {
    return this.http.post(`${this.baseUrl}/export/${projectId}/backup`, {});
  }

  getBackupStatus(projectId: string): Observable<{ status: string; step: string; progress: number; message: string }> {
    return this.http.get<any>(`${this.baseUrl}/export/${projectId}/backup-status`);
  }

  downloadBackup(projectId: string): Observable<Blob> {
    return this.http.get(`${this.baseUrl}/export/${projectId}/backup-download`, { responseType: 'blob' });
  }

  clearBackupProgress(projectId: string): Observable<any> {
    return this.http.delete(`${this.baseUrl}/export/${projectId}/backup-progress`);
  }

  cancelWordExport(projectId: string): Observable<any> {
    return this.http.post(`${this.baseUrl}/export/${projectId}/word-cancel`, {});
  }

  clearWordProgress(projectId: string): Observable<any> {
    return this.http.delete(`${this.baseUrl}/export/${projectId}/word-progress`);
  }

  importBackup(workspaceId: string, file: File): Observable<any> {
    const formData = new FormData();
    formData.append('file', file);
    return this.http.post(`${this.baseUrl}/export/import/${workspaceId}`, formData);
  }

  getPreview(projectId: string, anonymized = false): Observable<DocumentPreview> {
    const params = anonymized ? '?anonymized=true' : '';
    return this.http.get<DocumentPreview>(`${this.baseUrl}/export/${projectId}/preview${params}`);
  }

  sendPreviewChat(projectId: string, message: string): Observable<any> {
    return this.http.post(`${this.baseUrl}/export/${projectId}/preview-chat`, { message });
  }

  getPreviewChatStatus(projectId: string): Observable<{ status: string; step: string; progress: number; message: string; changed_chapters?: string[] }> {
    return this.http.get<any>(`${this.baseUrl}/export/${projectId}/preview-chat-status`);
  }

  cancelPreviewChat(projectId: string): Observable<any> {
    return this.http.post(`${this.baseUrl}/export/${projectId}/preview-chat-cancel`, {});
  }

  // ── Admin ──
  getUsers(): Observable<UserInfo[]> {
    return this.http.get<UserInfo[]>(`${this.baseUrl}/admin/users`);
  }

  createUser(data: UserCreate): Observable<UserInfo> {
    return this.http.post<UserInfo>(`${this.baseUrl}/admin/users`, data);
  }

  updateUser(userId: string, data: UserUpdate): Observable<UserInfo> {
    return this.http.put<UserInfo>(`${this.baseUrl}/admin/users/${userId}`, data);
  }

  deleteUser(userId: string): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/admin/users/${userId}`);
  }

  getAIConfig(workspaceId: string): Observable<AIConfig> {
    return this.http.get<AIConfig>(`${this.baseUrl}/admin/ai-config/${workspaceId}`);
  }

  updateAIConfig(workspaceId: string, data: AIConfigUpdate): Observable<AIConfig> {
    return this.http.put<AIConfig>(`${this.baseUrl}/admin/ai-config/${workspaceId}`, data);
  }
}
