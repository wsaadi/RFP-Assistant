import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import {
  ReportData,
  ReportPlan,
  ReportProgress,
  AIProviderConfig,
  CreateReportRequest,
  SectionStatus,
} from '../models/report.model';

@Injectable({
  providedIn: 'root',
})
export class ApiService {
  private baseUrl = '/api';

  constructor(private http: HttpClient) {}

  // Health check
  healthCheck(): Observable<{ status: string; service: string }> {
    return this.http.get<{ status: string; service: string }>(
      `${this.baseUrl}/health`
    );
  }

  // Get guidelines
  getGuidelines(): Observable<{ guidelines: string }> {
    return this.http.get<{ guidelines: string }>(`${this.baseUrl}/guidelines`);
  }

  // Get default plan
  getDefaultPlan(): Observable<ReportPlan> {
    return this.http.get<ReportPlan>(`${this.baseUrl}/plan/default`);
  }

  // Create report
  createReport(request: CreateReportRequest): Observable<ReportData> {
    return this.http.post<ReportData>(`${this.baseUrl}/reports`, request);
  }

  // Get report progress
  getReportProgress(report: ReportData): Observable<ReportProgress> {
    return this.http.post<ReportProgress>(
      `${this.baseUrl}/reports/progress`,
      report
    );
  }

  // Test AI connection
  testAIConnection(
    aiConfig: AIProviderConfig
  ): Observable<{ success: boolean; message: string }> {
    return this.http.post<{ success: boolean; message: string }>(
      `${this.baseUrl}/ai/test`,
      { ai_config: aiConfig }
    );
  }

  // Generate questions for a section
  generateQuestions(
    sectionId: string,
    sectionTitle: string,
    sectionDescription: string,
    currentNotes: string,
    currentContent: string,
    schoolInstructions: string,
    aiConfig: AIProviderConfig
  ): Observable<{ success: boolean; questions: string[] }> {
    return this.http.post<{ success: boolean; questions: string[] }>(
      `${this.baseUrl}/ai/questions`,
      {
        section_id: sectionId,
        section_title: sectionTitle,
        section_description: sectionDescription,
        current_notes: currentNotes,
        current_content: currentContent,
        school_instructions: schoolInstructions,
        ai_config: aiConfig,
      }
    );
  }

  // Generate recommendations
  generateRecommendations(
    sectionId: string,
    sectionTitle: string,
    sectionDescription: string,
    status: SectionStatus,
    currentNotes: string,
    currentContent: string,
    schoolInstructions: string,
    aiConfig: AIProviderConfig
  ): Observable<{ success: boolean; recommendations: string[] }> {
    return this.http.post<{ success: boolean; recommendations: string[] }>(
      `${this.baseUrl}/ai/recommendations`,
      {
        section_id: sectionId,
        section_title: sectionTitle,
        section_description: sectionDescription,
        status: status,
        current_notes: currentNotes,
        current_content: currentContent,
        school_instructions: schoolInstructions,
        ai_config: aiConfig,
      }
    );
  }

  // Generate content for a section
  generateContent(
    sectionTitle: string,
    sectionDescription: string,
    notes: string,
    companyContext: string,
    aiConfig: AIProviderConfig
  ): Observable<{ success: boolean; content: string }> {
    return this.http.post<{ success: boolean; content: string }>(
      `${this.baseUrl}/ai/generate-content`,
      {
        section_title: sectionTitle,
        section_description: sectionDescription,
        notes: notes,
        company_context: companyContext,
        ai_config: aiConfig,
      }
    );
  }

  // Improve text
  improveText(
    text: string,
    sectionContext: string,
    notes: string,
    aiConfig: AIProviderConfig
  ): Observable<{ success: boolean; improved_text: string }> {
    return this.http.post<{ success: boolean; improved_text: string }>(
      `${this.baseUrl}/ai/improve-text`,
      {
        text: text,
        section_context: sectionContext,
        notes: notes,
        ai_config: aiConfig,
      }
    );
  }

  // Generate Word document with AI
  generateWordDocument(
    reportData: ReportData,
    aiConfig: AIProviderConfig
  ): Observable<Blob> {
    return this.http.post(
      `${this.baseUrl}/generate-word`,
      {
        report_data: reportData,
        ai_config: aiConfig,
      },
      {
        responseType: 'blob',
      }
    );
  }

  // Generate Word document without AI
  generateWordDocumentSimple(reportData: ReportData): Observable<Blob> {
    return this.http.post(`${this.baseUrl}/generate-word-simple`, reportData, {
      responseType: 'blob',
    });
  }

  // Generate notes from user prompt
  generateNotes(
    sectionTitle: string,
    sectionDescription: string,
    userPrompt: string,
    existingNotes: string,
    aiConfig: AIProviderConfig
  ): Observable<{ success: boolean; notes: string[] }> {
    return this.http.post<{ success: boolean; notes: string[] }>(
      `${this.baseUrl}/ai/generate-notes`,
      {
        section_title: sectionTitle,
        section_description: sectionDescription,
        user_prompt: userPrompt,
        existing_notes: existingNotes,
        ai_config: aiConfig,
      }
    );
  }

  // Analyze compliance with instructions
  analyzeCompliance(
    reportContent: string,
    instructionsContent: string,
    aiConfig: AIProviderConfig
  ): Observable<{
    success: boolean;
    analysis: {
      score: number;
      conformes: string[];
      non_conformes: string[];
      recommandations: string[];
    };
  }> {
    return this.http.post<{
      success: boolean;
      analysis: {
        score: number;
        conformes: string[];
        non_conformes: string[];
        recommandations: string[];
      };
    }>(`${this.baseUrl}/ai/analyze-compliance`, {
      report_content: reportContent,
      instructions_content: instructionsContent,
      ai_config: aiConfig,
    });
  }

  // Analyze compliance with PDF instructions
  analyzePdfCompliance(
    pdfFile: File,
    reportData: ReportData,
    aiConfig: AIProviderConfig
  ): Observable<{
    success: boolean;
    analysis: {
      score: number;
      conformes: string[];
      non_conformes: string[];
      recommandations: string[];
    };
    instructions_filename: string;
  }> {
    const formData = new FormData();
    formData.append('file', pdfFile);
    formData.append('report_data', JSON.stringify(reportData));
    formData.append('ai_config', JSON.stringify(aiConfig));

    return this.http.post<{
      success: boolean;
      analysis: {
        score: number;
        conformes: string[];
        non_conformes: string[];
        recommandations: string[];
      };
      instructions_filename: string;
    }>(`${this.baseUrl}/pdf/analyze-compliance`, formData);
  }

  // Extract text from PDF
  extractPdfText(pdfFile: File): Observable<{
    success: boolean;
    text: string;
    page_count: number;
    filename: string;
  }> {
    const formData = new FormData();
    formData.append('file', pdfFile);

    return this.http.post<{
      success: boolean;
      text: string;
      page_count: number;
      filename: string;
    }>(`${this.baseUrl}/pdf/extract-text`, formData);
  }

  // Review grammar and spelling
  reviewGrammar(
    reportContent: string,
    aiConfig: AIProviderConfig
  ): Observable<{
    success: boolean;
    review: {
      nombre_erreurs: number;
      erreurs: Array<{
        texte_errone: string;
        correction: string;
        explication: string;
      }>;
      message: string;
    };
  }> {
    return this.http.post<{
      success: boolean;
      review: {
        nombre_erreurs: number;
        erreurs: Array<{
          texte_errone: string;
          correction: string;
          explication: string;
        }>;
        message: string;
      };
    }>(`${this.baseUrl}/ai/review-grammar`, {
      report_content: reportContent,
      ai_config: aiConfig,
    });
  }

  // Execute custom prompt on content
  executeCustomPrompt(
    content: string,
    userPrompt: string,
    sectionTitle: string,
    aiConfig: AIProviderConfig
  ): Observable<{ success: boolean; content: string }> {
    return this.http.post<{ success: boolean; content: string }>(
      `${this.baseUrl}/ai/custom-prompt`,
      {
        content: content,
        user_prompt: userPrompt,
        section_title: sectionTitle,
        ai_config: aiConfig,
      }
    );
  }

  // Adjust content length to target pages
  adjustContentLength(
    content: string,
    sectionTitle: string,
    targetPages: number,
    targetWords: number,
    aiConfig: AIProviderConfig
  ): Observable<{ success: boolean; content: string }> {
    return this.http.post<{ success: boolean; content: string }>(
      `${this.baseUrl}/ai/adjust-length`,
      {
        content: content,
        section_title: sectionTitle,
        target_pages: targetPages,
        target_words: targetWords,
        ai_config: aiConfig,
      }
    );
  }
}
