import { Component, Output, EventEmitter, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ReportService } from '../../services/report.service';
import { ApiService } from '../../services/api.service';
import { ReportSection } from '../../models/report.model';

interface ComplianceAnalysis {
  score: number;
  conformes: string[];
  non_conformes: string[];
  recommandations: string[];
}

@Component({
  selector: 'app-compliance-check',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatProgressBarModule,
    MatSnackBarModule,
  ],
  template: `
    <div class="compliance-check">
      <div class="check-header">
        <div class="header-info">
          <h1>
            <mat-icon>fact_check</mat-icon>
            Vérification de conformité
          </h1>
          <p>Comparez votre rapport avec les instructions du stage</p>
        </div>
        <button class="btn-secondary" (click)="close.emit()">
          <mat-icon>close</mat-icon>
          Fermer
        </button>
      </div>

      <div class="check-content">
        @if (!analysis()) {
          <div class="upload-section">
            @if (hasInstructions()) {
              <!-- Instructions déjà chargées -->
              <div class="instructions-ready">
                <div class="instructions-info">
                  <mat-icon class="ready-icon">task_alt</mat-icon>
                  <div class="info-content">
                    <h3>Instructions chargées</h3>
                    <p class="filename">{{ reportService.schoolInstructions()?.filename }}</p>
                    <p class="date">Importées le {{ formatDate(reportService.schoolInstructions()?.uploadedAt) }}</p>
                  </div>
                </div>

                <div class="report-summary">
                  <h4>
                    <mat-icon>description</mat-icon>
                    Votre rapport
                  </h4>
                  <div class="summary-stats">
                    <div class="stat">
                      <span class="stat-value">{{ reportService.progress().progress_percentage }}%</span>
                      <span class="stat-label">Progression</span>
                    </div>
                    <div class="stat">
                      <span class="stat-value">{{ reportService.progress().completed }}</span>
                      <span class="stat-label">Sections complètes</span>
                    </div>
                    <div class="stat">
                      <span class="stat-value">{{ reportService.progress().in_progress }}</span>
                      <span class="stat-label">En cours</span>
                    </div>
                  </div>
                </div>

                @if (analyzing()) {
                  <div class="analyzing-overlay">
                    <mat-spinner diameter="48"></mat-spinner>
                    <p class="analyzing-text">Analyse en cours...</p>
                    <span>Comparaison de votre rapport avec les exigences de l'école</span>
                  </div>
                }

                <button
                  class="btn-primary analyze-btn"
                  (click)="analyzeWithLoadedInstructions()"
                  [disabled]="analyzing()"
                >
                  @if (analyzing()) {
                    <mat-spinner diameter="18"></mat-spinner>
                  } @else {
                    <mat-icon>analytics</mat-icon>
                  }
                  Lancer l'analyse de conformité
                </button>

                <p class="info-text">
                  <mat-icon>info</mat-icon>
                  L'analyse comparera le contenu réel de votre rapport (notes de recherche et textes rédigés dans chaque section) avec les exigences du document d'instructions. Assurez-vous d'avoir ajouté du contenu dans vos sections avant de lancer l'analyse.
                </p>
              </div>
            } @else {
              <!-- Pas d'instructions - afficher l'upload -->
              <div class="no-instructions">
                <mat-icon class="warning-icon">warning</mat-icon>
                <h3>Instructions non chargées</h3>
                <p>Pour vérifier la conformité, vous devez d'abord importer le document d'instructions de votre école.</p>
                <p class="hint">Utilisez la zone "Instructions de l'école" dans la barre latérale pour importer le PDF.</p>
                <button class="btn-secondary" (click)="close.emit()">
                  <mat-icon>arrow_back</mat-icon>
                  Retour à l'éditeur
                </button>
              </div>
            }
          </div>
        } @else {
          <div class="results-section">
            <div class="score-card" [ngClass]="getScoreClass()">
              <div class="score-circle">
                <span class="score-value">{{ analysis()?.score }}%</span>
                <span class="score-label">Conformité</span>
              </div>
              <mat-progress-bar
                mode="determinate"
                [value]="analysis()?.score || 0"
                [color]="getScoreColor()"
              ></mat-progress-bar>
            </div>

            <div class="results-grid">
              <div class="result-card conformes">
                <div class="card-header">
                  <mat-icon>check_circle</mat-icon>
                  <h3>Points conformes</h3>
                  <span class="count">{{ analysis()?.conformes?.length || 0 }}</span>
                </div>
                <ul class="result-list">
                  @for (item of analysis()?.conformes; track $index) {
                    <li>
                      <mat-icon>done</mat-icon>
                      <span [innerHTML]="formatMarkdown(item)"></span>
                    </li>
                  }
                  @if (!analysis()?.conformes?.length) {
                    <li class="empty">Aucun point conforme identifié</li>
                  }
                </ul>
              </div>

              <div class="result-card non-conformes">
                <div class="card-header">
                  <mat-icon>warning</mat-icon>
                  <h3>Points non conformes</h3>
                  <span class="count">{{ analysis()?.non_conformes?.length || 0 }}</span>
                </div>
                <ul class="result-list">
                  @for (item of analysis()?.non_conformes; track $index) {
                    <li>
                      <mat-icon>close</mat-icon>
                      <span [innerHTML]="formatMarkdown(item)"></span>
                    </li>
                  }
                  @if (!analysis()?.non_conformes?.length) {
                    <li class="empty">Tous les points sont conformes</li>
                  }
                </ul>
              </div>

              <div class="result-card recommandations full-width">
                <div class="card-header">
                  <mat-icon>lightbulb</mat-icon>
                  <h3>Recommandations</h3>
                  <span class="count">{{ analysis()?.recommandations?.length || 0 }}</span>
                </div>
                <ul class="result-list">
                  @for (item of analysis()?.recommandations; track $index) {
                    <li>
                      <mat-icon>arrow_right</mat-icon>
                      <span [innerHTML]="formatMarkdown(item)"></span>
                    </li>
                  }
                  @if (!analysis()?.recommandations?.length) {
                    <li class="empty">Aucune recommandation particulière</li>
                  }
                </ul>
              </div>
            </div>

            <div class="results-actions">
              <button class="btn-secondary" (click)="resetAnalysis()">
                <mat-icon>refresh</mat-icon>
                Nouvelle analyse
              </button>
            </div>
          </div>
        }
      </div>
    </div>
  `,
  styles: [`
    .compliance-check {
      height: 100%;
      display: flex;
      flex-direction: column;
      background: #f5f7fa;
    }

    .check-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 20px 24px;
      background: white;
      border-bottom: 1px solid #e0e0e0;

      .header-info {
        h1 {
          display: flex;
          align-items: center;
          gap: 10px;
          font-size: 22px;
          color: #1a237e;
          margin-bottom: 4px;

          mat-icon {
            color: #43a047;
          }
        }

        p {
          color: #78909c;
          font-size: 14px;
        }
      }
    }

    .check-content {
      flex: 1;
      overflow-y: auto;
      padding: 24px;
    }

    .upload-section {
      max-width: 700px;
      margin: 0 auto;
    }

    .instructions-ready {
      background: white;
      border-radius: 16px;
      padding: 32px;
      box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
    }

    .instructions-info {
      display: flex;
      align-items: flex-start;
      gap: 16px;
      padding-bottom: 24px;
      border-bottom: 1px solid #e0e0e0;
      margin-bottom: 24px;

      .ready-icon {
        font-size: 48px;
        width: 48px;
        height: 48px;
        color: #43a047;
      }

      .info-content {
        h3 {
          color: #37474f;
          margin-bottom: 8px;
          font-size: 18px;
        }

        .filename {
          color: #43a047;
          font-weight: 500;
          margin-bottom: 4px;
        }

        .date {
          font-size: 13px;
          color: #78909c;
        }
      }
    }

    .report-summary {
      background: #f5f7fa;
      border-radius: 12px;
      padding: 20px;
      margin-bottom: 24px;

      h4 {
        display: flex;
        align-items: center;
        gap: 8px;
        color: #37474f;
        margin-bottom: 16px;

        mat-icon {
          color: #1976d2;
        }
      }

      .summary-stats {
        display: flex;
        gap: 24px;

        .stat {
          flex: 1;
          text-align: center;
          padding: 12px;
          background: white;
          border-radius: 8px;

          .stat-value {
            display: block;
            font-size: 24px;
            font-weight: 700;
            color: #1976d2;
          }

          .stat-label {
            font-size: 12px;
            color: #78909c;
          }
        }
      }
    }

    .analyzing-overlay {
      text-align: center;
      padding: 32px;
      background: #e3f2fd;
      border-radius: 12px;
      margin-bottom: 24px;

      .analyzing-text {
        color: #1976d2;
        font-weight: 500;
        margin-top: 16px;
        margin-bottom: 8px;
      }

      span {
        color: #78909c;
        font-size: 14px;
      }
    }

    .info-text {
      display: flex;
      align-items: flex-start;
      gap: 8px;
      margin-top: 20px;
      padding: 12px 16px;
      background: #fff8e1;
      border-radius: 8px;
      font-size: 13px;
      color: #6d5d00;

      mat-icon {
        color: #f9a825;
        font-size: 18px;
        width: 18px;
        height: 18px;
        flex-shrink: 0;
      }
    }

    .no-instructions {
      background: white;
      border-radius: 16px;
      padding: 48px;
      text-align: center;
      box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);

      .warning-icon {
        font-size: 64px;
        width: 64px;
        height: 64px;
        color: #ff9800;
        margin-bottom: 16px;
      }

      h3 {
        color: #37474f;
        margin-bottom: 12px;
      }

      p {
        color: #78909c;
        margin-bottom: 8px;
      }

      .hint {
        font-size: 13px;
        color: #9e9e9e;
        margin-bottom: 24px;
      }
    }

    .analyze-btn {
      width: 100%;
      padding: 16px 24px;
      font-size: 16px;
    }

    .results-section {
      max-width: 900px;
      margin: 0 auto;
    }

    .score-card {
      background: white;
      border-radius: 16px;
      padding: 32px;
      text-align: center;
      margin-bottom: 24px;
      box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);

      .score-circle {
        margin-bottom: 24px;

        .score-value {
          display: block;
          font-size: 56px;
          font-weight: 700;
        }

        .score-label {
          font-size: 16px;
          color: #78909c;
        }
      }

      &.excellent .score-value { color: #43a047; }
      &.good .score-value { color: #8bc34a; }
      &.average .score-value { color: #ff9800; }
      &.poor .score-value { color: #f44336; }

      ::ng-deep .mat-mdc-progress-bar {
        height: 8px;
        border-radius: 4px;
      }
    }

    .results-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;

      .full-width {
        grid-column: span 2;
      }

      @media (max-width: 768px) {
        grid-template-columns: 1fr;

        .full-width {
          grid-column: span 1;
        }
      }
    }

    .result-card {
      background: white;
      border-radius: 12px;
      padding: 20px;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);

      .card-header {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 16px;
        padding-bottom: 12px;
        border-bottom: 1px solid #e0e0e0;

        h3 {
          flex: 1;
          font-size: 16px;
          color: #37474f;
        }

        .count {
          background: #f5f5f5;
          padding: 4px 10px;
          border-radius: 12px;
          font-size: 13px;
          font-weight: 500;
        }
      }

      &.conformes {
        mat-icon { color: #43a047; }
        .count { background: #e8f5e9; color: #43a047; }
      }

      &.non-conformes {
        mat-icon { color: #f44336; }
        .count { background: #ffebee; color: #f44336; }
      }

      &.recommandations {
        mat-icon { color: #ff9800; }
        .count { background: #fff3e0; color: #ff9800; }
      }
    }

    .result-list {
      list-style: none;
      padding: 0;
      margin: 0;
      max-height: 500px;
      overflow-y: auto;

      /* Style de la scrollbar */
      &::-webkit-scrollbar {
        width: 6px;
      }

      &::-webkit-scrollbar-track {
        background: #f1f1f1;
        border-radius: 3px;
      }

      &::-webkit-scrollbar-thumb {
        background: #bdbdbd;
        border-radius: 3px;

        &:hover {
          background: #9e9e9e;
        }
      }

      li {
        display: flex;
        align-items: flex-start;
        gap: 10px;
        padding: 12px 8px;
        border-bottom: 1px solid #f5f5f5;

        &:last-child {
          border-bottom: none;
        }

        mat-icon {
          font-size: 18px;
          width: 18px;
          height: 18px;
          flex-shrink: 0;
          margin-top: 3px;
        }

        span {
          color: #37474f;
          line-height: 1.6;
          flex: 1;
          font-size: 14px;

          ::ng-deep strong {
            color: #1a237e;
            font-weight: 600;
          }

          ::ng-deep em {
            font-style: italic;
            color: #546e7a;
          }
        }

        &.empty {
          color: #9e9e9e;
          font-style: italic;
          justify-content: center;
          padding: 20px;
        }

        &:hover {
          background: #fafafa;
        }
      }
    }

    .results-actions {
      margin-top: 24px;
      text-align: center;
    }

    .btn-primary {
      background: #43a047;
      color: white;
      border: none;
      padding: 12px 24px;
      border-radius: 8px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-size: 14px;

      &:hover {
        background: #388e3c;
      }

      &:disabled {
        background: #c8e6c9;
        cursor: not-allowed;
      }
    }

    .btn-secondary {
      background: #f5f5f5;
      color: #37474f;
      border: none;
      padding: 12px 24px;
      border-radius: 8px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-size: 14px;

      &:hover {
        background: #e0e0e0;
      }
    }
  `],
})
export class ComplianceCheckComponent {
  @Output() close = new EventEmitter<void>();

  reportService = inject(ReportService);
  private apiService = inject(ApiService);
  private snackBar = inject(MatSnackBar);

  analyzing = signal(false);
  analysis = signal<ComplianceAnalysis | null>(null);

  // Computed pour vérifier si les instructions sont chargées
  hasInstructions = computed(() => !!this.reportService.schoolInstructions());

  // Formater la date
  formatDate(dateString: string | undefined): string {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleDateString('fr-FR', {
      day: 'numeric',
      month: 'long',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  // Vérifier si le rapport contient du contenu réel (notes ou texte rédigé)
  private hasRealContent(): boolean {
    const report = this.reportService.report();
    if (!report) return false;

    const checkSections = (sections: ReportSection[]): boolean => {
      for (const section of sections) {
        // Vérifier si la section a du contenu rédigé
        if (section.content && section.content.trim().length > 0) {
          return true;
        }
        // Vérifier si la section a des notes
        if (section.notes && section.notes.length > 0) {
          return true;
        }
        // Vérifier les sous-sections récursivement
        if (section.subsections && section.subsections.length > 0) {
          if (checkSections(section.subsections)) {
            return true;
          }
        }
      }
      return false;
    };

    return checkSections(report.plan.sections);
  }

  // Construire le contenu du rapport pour l'analyse
  private buildReportContent(): string {
    const report = this.reportService.report();
    if (!report) return '';

    const getSectionContent = (sections: ReportSection[], level: number = 1): string => {
      const contentParts: string[] = [];
      for (const section of sections) {
        const prefix = '#'.repeat(level);
        contentParts.push(`${prefix} ${section.title}`);

        // Ajouter le statut de la section
        const statusLabels: Record<string, string> = {
          'not_started': 'Non commencée',
          'in_progress': 'En cours',
          'completed': 'Terminée',
          'needs_review': 'À réviser',
        };
        contentParts.push(`Statut: ${statusLabels[section.status] || section.status}`);

        // Ajouter le contenu s'il existe
        if (section.content && section.content.trim()) {
          contentParts.push(`Contenu:\n${section.content}`);
        }

        // Ajouter les notes s'il y en a
        if (section.notes && section.notes.length > 0) {
          const notesText = section.notes.map(n => `- ${n.content}`).join('\n');
          contentParts.push(`Notes de recherche:\n${notesText}`);
        }

        // Traiter les sous-sections
        if (section.subsections && section.subsections.length > 0) {
          contentParts.push(getSectionContent(section.subsections, level + 1));
        }
      }
      return contentParts.join('\n\n');
    };

    return `
Rapport de stage de ${report.student_firstname} ${report.student_name}
Semestre: ${report.semester}
Entreprise: ${report.company_name} (${report.company_location})
Période: ${report.internship_start_date} - ${report.internship_end_date}
Tuteur: ${report.tutor_name}

Progression globale: ${this.reportService.progress().progress_percentage}%
- Sections terminées: ${this.reportService.progress().completed}
- Sections en cours: ${this.reportService.progress().in_progress}
- Sections non commencées: ${this.reportService.progress().not_started}

${getSectionContent(report.plan.sections)}
`;
  }

  // Analyser avec les instructions déjà chargées
  analyzeWithLoadedInstructions(): void {
    const report = this.reportService.report();
    const aiConfig = this.reportService.aiConfig();
    const instructions = this.reportService.schoolInstructions();

    if (!instructions) {
      this.snackBar.open('Aucune instruction chargée', 'OK', { duration: 3000 });
      return;
    }

    if (!report) {
      this.snackBar.open('Aucun rapport en cours', 'OK', { duration: 3000 });
      return;
    }

    if (!aiConfig) {
      this.snackBar.open('Veuillez configurer l\'IA dans les paramètres', 'OK', { duration: 3000 });
      return;
    }

    // Vérifier que le rapport contient du contenu réel
    if (!this.hasRealContent()) {
      this.snackBar.open(
        'Votre rapport ne contient pas encore de contenu à analyser. Veuillez d\'abord ajouter des notes ou rédiger du contenu dans vos sections.',
        'OK',
        { duration: 6000 }
      );
      return;
    }

    this.analyzing.set(true);

    const reportContent = this.buildReportContent();

    // Log pour déboguer
    console.log('=== REPORT CONTENT SENT TO API ===');
    console.log(reportContent);
    console.log('=== END REPORT CONTENT ===');
    console.log('Instructions length:', instructions.text.length);

    this.apiService.analyzeCompliance(reportContent, instructions.text, aiConfig).subscribe({
      next: (response) => {
        console.log('=== API RESPONSE ===');
        console.log(response);
        console.log('=== END API RESPONSE ===');
        this.analysis.set(response.analysis);
        this.analyzing.set(false);
        this.snackBar.open('Analyse terminée', 'OK', { duration: 3000 });
      },
      error: (error) => {
        this.analyzing.set(false);
        this.snackBar.open('Erreur lors de l\'analyse', 'OK', { duration: 5000 });
        console.error('Compliance analysis error:', error);
      }
    });
  }

  resetAnalysis(): void {
    this.analysis.set(null);
  }

  getScoreClass(): string {
    const score = this.analysis()?.score || 0;
    if (score >= 80) return 'excellent';
    if (score >= 60) return 'good';
    if (score >= 40) return 'average';
    return 'poor';
  }

  getScoreColor(): 'primary' | 'accent' | 'warn' {
    const score = this.analysis()?.score || 0;
    if (score >= 60) return 'primary';
    if (score >= 40) return 'accent';
    return 'warn';
  }

  // Formater le markdown dans le texte (gras, italique, etc.)
  formatMarkdown(text: string): string {
    if (!text) return '';

    // Convertir **texte** en <strong>texte</strong>
    let formatted = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

    // Convertir *texte* en <em>texte</em>
    formatted = formatted.replace(/\*(.+?)\*/g, '<em>$1</em>');

    // Convertir les retours à la ligne en <br> si nécessaire
    formatted = formatted.replace(/\n/g, '<br>');

    return formatted;
  }
}
