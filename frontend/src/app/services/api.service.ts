import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import {
  Workspace, WorkspaceMember,
  RFPProject, ProjectCreate,
  DocumentInfo, DocumentImage, DocumentProgress,
  Chapter,
  GapAnalysis, ComplianceAnalysis,
  ProjectStatistics, AnonymizationMapping, AnonymizationReport, GenerationStatus,
  SearchResult, DocumentPreview,
  AIConfig, AIConfigUpdate,
  UserInfo, UserCreate, UserUpdate,
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

  getWorkspaceMembers(workspaceId: string): Observable<WorkspaceMember[]> {
    return this.http.get<WorkspaceMember[]>(`${this.baseUrl}/workspaces/${workspaceId}/members`);
  }

  addWorkspaceMember(workspaceId: string, userId: string, role: string): Observable<any> {
    return this.http.post(`${this.baseUrl}/workspaces/${workspaceId}/members`, { user_id: userId, role });
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

  addChapterNote(chapterId: string, content: string): Observable<any> {
    return this.http.post(`${this.baseUrl}/chapters/${chapterId}/note`, { content });
  }

  generateChapterContent(chapterId: string, action: string, customPrompt: string = '', useOldResponse: boolean = true, includeImprovementAxes: boolean = true): Observable<{ content: string }> {
    return this.http.post<{ content: string }>(
      `${this.baseUrl}/chapters/${chapterId}/generate-content`,
      { action, custom_prompt: customPrompt, use_old_response: useOldResponse, include_improvement_axes: includeImprovementAxes }
    );
  }

  reorderChapters(chapterOrders: { id: string; order: number }[]): Observable<any> {
    return this.http.post(`${this.baseUrl}/chapters/reorder`, { chapter_orders: chapterOrders });
  }

  // ── AI Operations ──
  analyzeGap(projectId: string): Observable<{ analysis: GapAnalysis }> {
    return this.http.post<{ analysis: GapAnalysis }>(`${this.baseUrl}/projects/${projectId}/gap-analysis`, {});
  }

  generateStructure(projectId: string): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/projects/${projectId}/generate-structure`, {});
  }

  getGenerationStatus(projectId: string): Observable<GenerationStatus> {
    return this.http.get<GenerationStatus>(`${this.baseUrl}/projects/${projectId}/generation-status`);
  }

  prefillChapters(projectId: string, chapterIds: string[] = []): Observable<{ prefilled_count: number }> {
    return this.http.post<{ prefilled_count: number }>(`${this.baseUrl}/projects/${projectId}/prefill`, { chapter_ids: chapterIds });
  }

  analyzeCompliance(projectId: string): Observable<{ analysis: ComplianceAnalysis }> {
    return this.http.post<{ analysis: ComplianceAnalysis }>(`${this.baseUrl}/projects/${projectId}/compliance-analysis`, {});
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

  // ── Export/Import ──
  exportWord(projectId: string): Observable<Blob> {
    return this.http.post(`${this.baseUrl}/export/${projectId}/word`, {}, { responseType: 'blob' });
  }

  exportBackup(projectId: string): Observable<Blob> {
    return this.http.post(`${this.baseUrl}/export/${projectId}/backup`, {}, { responseType: 'blob' });
  }

  importBackup(workspaceId: string, file: File): Observable<any> {
    const formData = new FormData();
    formData.append('file', file);
    return this.http.post(`${this.baseUrl}/export/import/${workspaceId}`, formData);
  }

  getPreview(projectId: string): Observable<DocumentPreview> {
    return this.http.get<DocumentPreview>(`${this.baseUrl}/export/${projectId}/preview`);
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
