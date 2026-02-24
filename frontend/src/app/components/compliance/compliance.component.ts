import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatChipsModule } from '@angular/material/chips';
import { MatListModule } from '@angular/material/list';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatDividerModule } from '@angular/material/divider';
import { Subscription, timer } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { ApiService } from '../../services/api.service';
import { ComplianceAnalysis, Chapter } from '../../models/report.model';
import { renderMarkdown } from '../../services/markdown.service';

@Component({
  selector: 'app-compliance',
  standalone: true,
  imports: [
    CommonModule, RouterLink,
    MatCardModule, MatButtonModule, MatIconModule, MatProgressSpinnerModule,
    MatProgressBarModule, MatChipsModule, MatListModule, MatSnackBarModule,
    MatTooltipModule, MatDividerModule,
  ],
  template: `
    <div class="page-container">
      <div class="page-header">
        <button mat-icon-button [routerLink]="['/project', projectId]"><mat-icon>arrow_back</mat-icon></button>
        <h1>Analyse de conformite et exhaustivite</h1>
        <button mat-raised-button color="primary" (click)="runAnalysis()" [disabled]="analyzing">
          <mat-spinner *ngIf="analyzing" diameter="18"></mat-spinner>
          <mat-icon *ngIf="!analyzing">fact_check</mat-icon>
          {{ analysis ? 'Relancer' : 'Analyser' }}
        </button>
      </div>

      <!-- Loading existing analysis -->
      <div *ngIf="loadingExisting" class="loading-container">
        <mat-spinner diameter="30"></mat-spinner>
        <span>Chargement de l'analyse precedente...</span>
      </div>

      <!-- Progress bar -->
      <mat-card *ngIf="analyzing && analysisProgress" class="progress-card">
        <div class="progress-header">
          <mat-spinner diameter="20"></mat-spinner>
          <h3>Analyse de conformite en cours...</h3>
        </div>
        <mat-progress-bar mode="determinate" [value]="analysisProgress.progress"></mat-progress-bar>
        <div class="progress-details">
          <span class="progress-step">{{ analysisProgress.step }}</span>
          <span class="progress-pct">{{ analysisProgress.progress }}%</span>
        </div>
        <p class="progress-message">{{ analysisProgress.message }}</p>
      </mat-card>

      <div *ngIf="analysis && !analyzing" class="analysis-results">
        <!-- Timestamp -->
        <div *ngIf="analysis.created_at" class="analysis-timestamp">
          <mat-icon>schedule</mat-icon>
          Derniere analyse : {{ analysis.created_at | date:'medium' }}
        </div>

        <!-- Score -->
        <mat-card class="score-card">
          <div class="score-circle" [class]="scoreClass">
            <span class="score-value">{{ analysis.score }}</span>
            <span class="score-label">/ 100</span>
          </div>
          <div class="score-details">
            <h2>Score de conformite</h2>
            <mat-progress-bar [value]="analysis.score" [color]="analysis.score >= 80 ? 'primary' : analysis.score >= 50 ? 'accent' : 'warn'"></mat-progress-bar>
            <p>{{ analysis.summary }}</p>
          </div>
        </mat-card>

        <!-- Covered requirements -->
        <mat-card class="section-card">
          <h3><mat-icon>check_circle</mat-icon> Exigences couvertes</h3>
          <mat-list>
            <mat-list-item *ngFor="let req of analysis.covered_requirements">
              <mat-icon matListItemIcon [class]="'coverage-' + req.coverage">
                {{ req.coverage === 'complete' ? 'check_circle' : req.coverage === 'partial' ? 'remove_circle' : 'cancel' }}
              </mat-icon>
              <span matListItemTitle>{{ req.requirement }}</span>
              <span matListItemLine>
                <mat-chip [class]="'cov-chip-' + req.coverage" size="small">{{ coverageLabel(req.coverage) }}</mat-chip>
                {{ req.comment }}
              </span>
            </mat-list-item>
          </mat-list>
        </mat-card>

        <!-- Missing elements -->
        <mat-card *ngIf="analysis.missing_elements?.length" class="section-card missing">
          <h3><mat-icon>warning</mat-icon> Elements manquants</h3>
          <mat-list>
            <mat-list-item *ngFor="let item of analysis.missing_elements">
              <mat-icon matListItemIcon color="warn">error_outline</mat-icon>
              <span matListItemTitle>{{ item.requirement }}</span>
              <span matListItemLine>{{ item.description }}</span>
            </mat-list-item>
          </mat-list>
        </mat-card>

        <!-- Recommendations with generate buttons -->
        <mat-card *ngIf="analysis.recommendations?.length" class="section-card recommendations-card">
          <h3><mat-icon>lightbulb</mat-icon> Recommandations</h3>
          <div *ngFor="let rec of analysis.recommendations; let i = index" class="recommendation-item">
            <div class="rec-header">
              <mat-icon class="rec-icon">arrow_forward</mat-icon>
              <span class="rec-text">{{ rec }}</span>
              <button mat-raised-button color="accent" (click)="generateRecommendation(i, rec)"
                [disabled]="generatingRec === i"
                matTooltip="Generer du contenu repondant a cette recommandation">
                <mat-spinner *ngIf="generatingRec === i" diameter="16"></mat-spinner>
                <mat-icon *ngIf="generatingRec !== i">auto_fix_high</mat-icon>
                Generer
              </button>
            </div>
            <!-- Generated content preview -->
            <div *ngIf="generatedContents[i]" class="generated-content">
              <div class="generated-header">
                <mat-icon>description</mat-icon>
                <span>Contenu genere</span>
                <button mat-icon-button (click)="copyToClipboard(generatedContents[i])" matTooltip="Copier">
                  <mat-icon>content_copy</mat-icon>
                </button>
              </div>
              <div class="generated-body" [innerHTML]="renderMarkdown(generatedContents[i])"></div>
            </div>
            <mat-divider *ngIf="i < analysis.recommendations.length - 1"></mat-divider>
          </div>
        </mat-card>
      </div>

      <!-- Empty state -->
      <mat-card *ngIf="!analysis && !analyzing && !loadingExisting && !error" class="empty-card">
        <mat-icon>fact_check</mat-icon>
        <div>
          <h3>Aucune analyse disponible</h3>
          <p>Lancez une analyse pour evaluer la conformite de votre reponse par rapport au cahier des charges. Fonctionne avec les documents "Notre reponse" charges ou les chapitres rediges.</p>
        </div>
      </mat-card>

      <mat-card *ngIf="error" class="error-card"><mat-icon>error</mat-icon><p>{{ error }}</p></mat-card>
    </div>
  `,
  styles: [`
    .page-container { max-width: 1000px; margin: 0 auto; }
    .page-header { display: flex; align-items: center; gap: 12px; margin-bottom: 24px; }
    .page-header h1 { flex: 1; margin: 0; color: #1B3A5C; font-size: 20px; }
    .loading-container { display: flex; align-items: center; gap: 12px; padding: 24px; color: #666; }
    .analysis-timestamp { display: flex; align-items: center; gap: 6px; font-size: 13px; color: #888; margin-bottom: 16px; }
    .analysis-timestamp mat-icon { font-size: 18px; width: 18px; height: 18px; }
    .progress-card { padding: 24px; margin-bottom: 16px; border-left: 4px solid #1976d2; }
    .progress-header { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
    .progress-header h3 { margin: 0; color: #1976d2; font-size: 15px; }
    .progress-details { display: flex; justify-content: space-between; margin-top: 8px; font-size: 13px; }
    .progress-step { color: #1976d2; }
    .progress-pct { font-weight: bold; }
    .progress-message { margin: 8px 0 0 0; font-size: 13px; color: #666; }
    .score-card { display: flex; align-items: center; gap: 24px; padding: 32px; margin-bottom: 16px; }
    .score-circle { width: 100px; height: 100px; border-radius: 50%; display: flex; flex-direction: column; justify-content: center; align-items: center; }
    .score-circle.high { background: #e8f5e9; border: 4px solid #4caf50; }
    .score-circle.medium { background: #fff3e0; border: 4px solid #ff9800; }
    .score-circle.low { background: #ffebee; border: 4px solid #f44336; }
    .score-value { font-size: 32px; font-weight: bold; }
    .score-label { font-size: 14px; color: #888; }
    .score-details { flex: 1; }
    .score-details h2 { margin: 0 0 8px; }
    .section-card { padding: 16px; margin-bottom: 16px; }
    .section-card h3 { display: flex; align-items: center; gap: 8px; color: #1B3A5C; }
    .missing h3 { color: #c62828; }
    .coverage-complete { color: #4caf50; }
    .coverage-partial { color: #ff9800; }
    .coverage-missing { color: #f44336; }
    .cov-chip-complete { background: #e8f5e9 !important; }
    .cov-chip-partial { background: #fff3e0 !important; }
    .cov-chip-missing { background: #ffebee !important; }
    .recommendations-card { padding: 20px; }
    .recommendation-item { padding: 12px 0; }
    .rec-header { display: flex; align-items: flex-start; gap: 10px; }
    .rec-icon { color: #1976d2; margin-top: 2px; flex-shrink: 0; }
    .rec-text { flex: 1; font-size: 14px; line-height: 1.5; }
    .rec-header button { flex-shrink: 0; }
    .generated-content { margin: 12px 0 12px 34px; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden; }
    .generated-header { display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: #e3f2fd; font-size: 13px; font-weight: 500; color: #1565c0; }
    .generated-header span { flex: 1; }
    .generated-body { padding: 16px; font-size: 14px; line-height: 1.6; }
    .generated-body h2, .generated-body h3 { font-size: 16px; color: #1B3A5C; margin: 16px 0 8px 0; }
    .generated-body h2:first-child, .generated-body h3:first-child { margin-top: 0; }
    .generated-body p { margin: 0 0 10px 0; }
    .generated-body ul, .generated-body ol { margin: 4px 0 10px 0; padding-left: 24px; }
    .generated-body li { margin-bottom: 4px; }
    .generated-body strong { color: #1B3A5C; }
    .empty-card { padding: 32px; display: flex; align-items: center; gap: 16px; }
    .empty-card mat-icon { font-size: 40px; width: 40px; height: 40px; color: #bdbdbd; }
    .empty-card h3 { margin: 0 0 4px; color: #1B3A5C; }
    .empty-card p { margin: 0; color: #888; font-size: 14px; }
    .error-card { padding: 24px; display: flex; align-items: center; gap: 12px; color: #c62828; }
  `],
})
export class ComplianceComponent implements OnInit, OnDestroy {
  projectId = '';
  analysis: ComplianceAnalysis | null = null;
  analyzing = false;
  loadingExisting = false;
  error = '';
  generatingRec: number | null = null;
  generatedContents: Record<number, string> = {};
  renderMarkdown = renderMarkdown;
  analysisProgress: { status: string; step: string; progress: number; message: string } | null = null;
  private pollSub: Subscription | null = null;

  get scoreClass(): string {
    if (!this.analysis) return '';
    if (this.analysis.score >= 80) return 'high';
    if (this.analysis.score >= 50) return 'medium';
    return 'low';
  }

  constructor(
    private route: ActivatedRoute,
    private api: ApiService,
    private snackBar: MatSnackBar,
  ) {}

  ngOnInit(): void {
    this.projectId = this.route.snapshot.paramMap.get('projectId') || '';
    this.loadExisting();
    // Resume polling if analysis was already running
    this.api.getComplianceAnalysisStatus(this.projectId).subscribe({
      next: (status) => {
        if (status.status === 'running') {
          this.analyzing = true;
          this.analysisProgress = status;
          this.startPolling();
        }
      },
    });
  }

  ngOnDestroy(): void {
    this.stopPolling();
  }

  loadExisting(): void {
    this.loadingExisting = true;
    this.api.getComplianceAnalysis(this.projectId).subscribe({
      next: (res) => {
        this.analysis = res.analysis;
        this.loadingExisting = false;
      },
      error: () => { this.loadingExisting = false; },
    });
  }

  runAnalysis(): void {
    this.analyzing = true;
    this.error = '';
    this.generatedContents = {};
    this.analysisProgress = { status: 'running', step: 'starting', progress: 0, message: 'Lancement...' };
    this.api.analyzeCompliance(this.projectId).subscribe({
      next: () => {
        this.startPolling();
      },
      error: (err) => {
        this.error = err.error?.detail || 'Erreur';
        this.analyzing = false;
        this.analysisProgress = null;
      },
    });
  }

  private startPolling(): void {
    this.stopPolling();
    this.pollSub = timer(1000, 1500).pipe(
      switchMap(() => this.api.getComplianceAnalysisStatus(this.projectId))
    ).subscribe({
      next: (status) => {
        this.analysisProgress = status;
        if (status.status === 'completed') {
          this.stopPolling();
          this.analyzing = false;
          this.analysisProgress = null;
          this.snackBar.open('Analyse de conformite terminee', 'OK', { duration: 3000 });
          this.loadExisting();
        } else if (status.status === 'error') {
          this.stopPolling();
          this.analyzing = false;
          this.error = status.message;
          this.analysisProgress = null;
        }
      },
    });
  }

  private stopPolling(): void {
    this.pollSub?.unsubscribe();
    this.pollSub = null;
  }

  generateRecommendation(index: number, recommendation: string): void {
    this.generatingRec = index;
    this.api.generateRecommendationContent(this.projectId, recommendation).subscribe({
      next: (res) => {
        this.generatedContents[index] = res.content;
        this.generatingRec = null;
        this.snackBar.open('Contenu genere', 'OK', { duration: 2000 });
      },
      error: (err) => {
        this.snackBar.open(err.error?.detail || 'Erreur de generation', 'OK', { duration: 4000 });
        this.generatingRec = null;
      },
    });
  }

  copyToClipboard(text: string): void {
    navigator.clipboard.writeText(text).then(() => {
      this.snackBar.open('Copie dans le presse-papier', 'OK', { duration: 1500 });
    });
  }

  coverageLabel(coverage: string): string {
    const labels: Record<string, string> = { complete: 'Complet', partial: 'Partiel', missing: 'Manquant' };
    return labels[coverage] || coverage;
  }
}
