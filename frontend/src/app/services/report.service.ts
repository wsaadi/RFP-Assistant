import { Injectable, signal, computed } from '@angular/core';
import {
  ReportData,
  ReportSection,
  SectionStatus,
  SectionNote,
  AIProviderConfig,
  ReportProgress,
} from '../models/report.model';

export interface SchoolInstructions {
  filename: string;
  text: string;
  uploadedAt: string;
}

@Injectable({
  providedIn: 'root',
})
export class ReportService {
  private readonly STORAGE_KEY = 'utc_report_data';
  private readonly AI_CONFIG_KEY = 'utc_ai_config';
  private readonly SCHOOL_INSTRUCTIONS_KEY = 'utc_school_instructions';

  // Signals for reactive state
  report = signal<ReportData | null>(null);
  aiConfig = signal<AIProviderConfig | null>(null);
  selectedSection = signal<ReportSection | null>(null);
  schoolInstructions = signal<SchoolInstructions | null>(null);

  // Computed values
  progress = computed(() => {
    const reportData = this.report();
    if (!reportData) {
      return {
        total_sections: 0,
        completed: 0,
        in_progress: 0,
        not_started: 0,
        progress_percentage: 0,
      };
    }
    return this.calculateProgress(reportData.plan.sections);
  });

  constructor() {
    this.loadFromStorage();
  }

  // Load data from localStorage
  loadFromStorage(): void {
    const savedReport = localStorage.getItem(this.STORAGE_KEY);
    if (savedReport) {
      try {
        this.report.set(JSON.parse(savedReport));
      } catch (e) {
        console.error('Error loading report from storage', e);
      }
    }

    const savedConfig = localStorage.getItem(this.AI_CONFIG_KEY);
    if (savedConfig) {
      try {
        this.aiConfig.set(JSON.parse(savedConfig));
      } catch (e) {
        console.error('Error loading AI config from storage', e);
      }
    }

    const savedInstructions = localStorage.getItem(this.SCHOOL_INSTRUCTIONS_KEY);
    if (savedInstructions) {
      try {
        this.schoolInstructions.set(JSON.parse(savedInstructions));
      } catch (e) {
        console.error('Error loading school instructions from storage', e);
      }
    }
  }

  // Save data to localStorage
  saveToStorage(): void {
    const reportData = this.report();
    if (reportData) {
      localStorage.setItem(this.STORAGE_KEY, JSON.stringify(reportData));
    }
  }

  // Save AI config
  saveAIConfig(config: AIProviderConfig): void {
    this.aiConfig.set(config);
    localStorage.setItem(this.AI_CONFIG_KEY, JSON.stringify(config));
  }

  // Save school instructions
  saveSchoolInstructions(filename: string, text: string): void {
    const instructions: SchoolInstructions = {
      filename,
      text,
      uploadedAt: new Date().toISOString(),
    };
    this.schoolInstructions.set(instructions);
    localStorage.setItem(this.SCHOOL_INSTRUCTIONS_KEY, JSON.stringify(instructions));
  }

  // Remove school instructions
  removeSchoolInstructions(): void {
    this.schoolInstructions.set(null);
    localStorage.removeItem(this.SCHOOL_INSTRUCTIONS_KEY);
  }

  // Get school instructions text
  getSchoolInstructionsText(): string {
    return this.schoolInstructions()?.text || '';
  }

  // Set report data
  setReport(data: ReportData): void {
    this.report.set(data);
    this.saveToStorage();
  }

  // Find section by ID
  findSection(
    sections: ReportSection[],
    sectionId: string
  ): ReportSection | null {
    for (const section of sections) {
      if (section.id === sectionId) {
        return section;
      }
      if (section.subsections?.length) {
        const found = this.findSection(section.subsections, sectionId);
        if (found) return found;
      }
    }
    return null;
  }

  // Update section status
  updateSectionStatus(sectionId: string, status: SectionStatus): void {
    const reportData = this.report();
    if (!reportData) return;

    const section = this.findSection(reportData.plan.sections, sectionId);
    if (section) {
      section.status = status;
      // Force signal update by creating a deep copy
      const updatedReport = JSON.parse(JSON.stringify(reportData)) as ReportData;
      this.report.set(updatedReport);
      this.saveToStorage();

      // Update selected section reference if needed
      const currentSelected = this.selectedSection();
      if (currentSelected?.id === sectionId) {
        const updatedSection = this.findSection(updatedReport.plan.sections, sectionId);
        if (updatedSection) {
          this.selectedSection.set(updatedSection);
        }
      }
    }
  }

  // Update section content
  updateSectionContent(sectionId: string, content: string): void {
    const reportData = this.report();
    if (!reportData) return;

    const section = this.findSection(reportData.plan.sections, sectionId);
    if (section) {
      section.content = content;
      this.report.set({ ...reportData });
      this.saveToStorage();
    }
  }

  // Add note to section
  addNoteToSection(sectionId: string, noteContent: string): void {
    const reportData = this.report();
    if (!reportData) return;

    const section = this.findSection(reportData.plan.sections, sectionId);
    if (section) {
      const note: SectionNote = {
        id: this.generateId(),
        content: noteContent,
        created_at: new Date().toISOString(),
      };
      section.notes.push(note);
      this.report.set({ ...reportData });
      this.saveToStorage();
    }
  }

  // Delete note from section
  deleteNoteFromSection(sectionId: string, noteId: string): void {
    const reportData = this.report();
    if (!reportData) return;

    const section = this.findSection(reportData.plan.sections, sectionId);
    if (section) {
      section.notes = section.notes.filter((n) => n.id !== noteId);
      this.report.set({ ...reportData });
      this.saveToStorage();
    }
  }

  // Update note in section
  updateNoteInSection(
    sectionId: string,
    noteId: string,
    content: string
  ): void {
    const reportData = this.report();
    if (!reportData) return;

    const section = this.findSection(reportData.plan.sections, sectionId);
    if (section) {
      const note = section.notes.find((n) => n.id === noteId);
      if (note) {
        note.content = content;
        note.updated_at = new Date().toISOString();
        this.report.set({ ...reportData });
        this.saveToStorage();
      }
    }
  }

  // Update section questions
  updateSectionQuestions(sectionId: string, questions: string[]): void {
    const reportData = this.report();
    if (!reportData) return;

    const section = this.findSection(reportData.plan.sections, sectionId);
    if (section) {
      section.generated_questions = questions;
      this.report.set({ ...reportData });
      this.saveToStorage();
    }
  }

  // Update section recommendations
  updateSectionRecommendations(
    sectionId: string,
    recommendations: string[]
  ): void {
    const reportData = this.report();
    if (!reportData) return;

    const section = this.findSection(reportData.plan.sections, sectionId);
    if (section) {
      section.recommendations = recommendations;
      this.report.set({ ...reportData });
      this.saveToStorage();
    }
  }

  // Select section
  selectSection(section: ReportSection | null): void {
    this.selectedSection.set(section);
  }

  // Calculate progress
  calculateProgress(sections: ReportSection[]): ReportProgress {
    let total = 0;
    let completed = 0;
    let inProgress = 0;

    const countSections = (secs: ReportSection[]): void => {
      for (const section of secs) {
        if (section.required) {
          total++;
          if (section.status === SectionStatus.COMPLETED) {
            completed++;
          } else if (section.status === SectionStatus.IN_PROGRESS) {
            inProgress++;
          }
        }
        if (section.subsections?.length) {
          countSections(section.subsections);
        }
      }
    };

    countSections(sections);

    return {
      total_sections: total,
      completed,
      in_progress: inProgress,
      not_started: total - completed - inProgress,
      progress_percentage: total > 0 ? Math.round((completed / total) * 100) : 0,
    };
  }

  // Reset report
  resetReport(): void {
    this.report.set(null);
    this.selectedSection.set(null);
    localStorage.removeItem(this.STORAGE_KEY);
  }

  // Generate unique ID
  private generateId(): string {
    return Math.random().toString(36).substring(2, 15);
  }

  // Get company context string
  getCompanyContext(): string {
    const reportData = this.report();
    if (!reportData) return '';

    return `Entreprise : ${reportData.company_name}
Lieu : ${reportData.company_location}
Période : du ${reportData.internship_start_date} au ${reportData.internship_end_date}
Tuteur : ${reportData.tutor_name}`;
  }

  // Export all data as JSON
  exportAllData(): string {
    const exportData = {
      version: '1.0',
      exportDate: new Date().toISOString(),
      report: this.report(),
      aiConfig: this.aiConfig(),
      schoolInstructions: this.schoolInstructions(),
    };
    return JSON.stringify(exportData, null, 2);
  }

  // Import all data from JSON
  importAllData(jsonString: string): { success: boolean; error?: string } {
    try {
      const importData = JSON.parse(jsonString);

      // Validate the data structure
      if (!importData.version || !importData.report) {
        return {
          success: false,
          error: 'Format de fichier invalide. Assurez-vous d\'importer un fichier exporté par l\'application.',
        };
      }

      // Import report data
      if (importData.report) {
        this.report.set(importData.report);
        localStorage.setItem(this.STORAGE_KEY, JSON.stringify(importData.report));
      }

      // Import AI config
      if (importData.aiConfig) {
        this.aiConfig.set(importData.aiConfig);
        localStorage.setItem(this.AI_CONFIG_KEY, JSON.stringify(importData.aiConfig));
      }

      // Import school instructions
      if (importData.schoolInstructions) {
        this.schoolInstructions.set(importData.schoolInstructions);
        localStorage.setItem(this.SCHOOL_INSTRUCTIONS_KEY, JSON.stringify(importData.schoolInstructions));
      }

      return { success: true };
    } catch (error) {
      return {
        success: false,
        error: `Erreur lors de l'importation: ${error instanceof Error ? error.message : 'Erreur inconnue'}`,
      };
    }
  }

  // Download export as file
  downloadExport(): void {
    const jsonData = this.exportAllData();
    const blob = new Blob([jsonData], { type: 'application/json' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;

    const reportData = this.report();
    const filename = reportData
      ? `utc_rapport_${reportData.student_name}_${reportData.student_firstname}_${new Date().toISOString().split('T')[0]}.json`
      : `utc_rapport_export_${new Date().toISOString().split('T')[0]}.json`;

    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  }
}
