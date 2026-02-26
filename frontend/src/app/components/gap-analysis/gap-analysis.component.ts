import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatChipsModule } from '@angular/material/chips';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { Subscription, timer } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { ApiService } from '../../services/api.service';
import { GapAnalysis } from '../../models/report.model';

@Component({
  selector: 'app-gap-analysis',
  standalone: true,
  imports: [CommonModule, RouterLink, MatCardModule, MatButtonModule, MatIconModule, MatProgressSpinnerModule, MatProgressBarModule, MatChipsModule, MatExpansionModule, MatSnackBarModule],
  template: `
    <div class="page-container">
      <div class="page-header">
        <button mat-icon-button [routerLink]="['/project', projectId]"><mat-icon>arrow_back</mat-icon></button>
        <h1>Analyse des écarts</h1>
        <button mat-stroked-button (click)="exportPdf()" [disabled]="!analysis || analyzing || exportingPdf">
          <mat-spinner *ngIf="exportingPdf" diameter="18"></mat-spinner>
          <mat-icon *ngIf="!exportingPdf">picture_as_pdf</mat-icon>
          Export PDF
        </button>
        <button mat-raised-button color="primary" (click)="runAnalysis()" [disabled]="analyzing">
          <mat-spinner *ngIf="analyzing" diameter="18"></mat-spinner>
          <mat-icon *ngIf="!analyzing">compare_arrows</mat-icon>
          {{ analysis ? 'Relancer' : 'Lancer analyse' }}
        </button>
      </div>

      <div *ngIf="loadingExisting" class="loading-container">
        <mat-spinner diameter="30"></mat-spinner>
        <p>Chargement de l'analyse precedente...</p>
      </div>

      <mat-card *ngIf="analyzing && analysisProgress" class="progress-card">
        <div class="progress-header">
          <mat-spinner diameter="20"></mat-spinner>
          <h3>Analyse des ecarts en cours...</h3>
        </div>
        <mat-progress-bar mode="determinate" [value]="analysisProgress.progress"></mat-progress-bar>
        <div class="progress-details">
          <span class="progress-step">{{ analysisProgress.step }}</span>
          <span class="progress-pct">{{ analysisProgress.progress }}%</span>
        </div>
        <p class="progress-message">{{ analysisProgress.message }}</p>
      </mat-card>

      <div *ngIf="analysis && !analyzing" class="analysis-results">
        <div *ngIf="analysis.created_at" class="analysis-timestamp">
          <mat-icon>schedule</mat-icon>
          Derniere analyse : {{ analysis.created_at | date:'medium' }}
        </div>
        <mat-card class="summary-card">
          <h3>Résumé</h3>
          <p>{{ analysis.summary }}</p>
        </mat-card>

        <div class="results-grid">
          <mat-card class="result-section new">
            <h3><mat-icon>fiber_new</mat-icon> Nouvelles exigences ({{ analysis.new_requirements?.length || 0 }})</h3>
            <mat-accordion>
              <mat-expansion-panel *ngFor="let req of analysis.new_requirements">
                <mat-expansion-panel-header>
                  <mat-panel-title>{{ req.title }}</mat-panel-title>
                  <mat-chip [class]="'priority-' + req.priority">{{ req.priority }}</mat-chip>
                </mat-expansion-panel-header>
                <p>{{ req.description }}</p>
              </mat-expansion-panel>
            </mat-accordion>
          </mat-card>

          <mat-card class="result-section removed">
            <h3><mat-icon>remove_circle</mat-icon> Exigences supprimées ({{ analysis.removed_requirements?.length || 0 }})</h3>
            <div *ngFor="let req of analysis.removed_requirements" class="req-item">
              <strong>{{ req.title }}</strong>
              <p>{{ req.description }}</p>
            </div>
          </mat-card>

          <mat-card class="result-section modified">
            <h3><mat-icon>edit</mat-icon> Exigences modifiées ({{ analysis.modified_requirements?.length || 0 }})</h3>
            <mat-accordion>
              <mat-expansion-panel *ngFor="let req of analysis.modified_requirements">
                <mat-expansion-panel-header>
                  <mat-panel-title>{{ req.title }}</mat-panel-title>
                </mat-expansion-panel-header>
                <p><strong>Avant:</strong> {{ req.old_description }}</p>
                <p><strong>Après:</strong> {{ req.new_description }}</p>
                <p><strong>Impact:</strong> {{ req.impact }}</p>
              </mat-expansion-panel>
            </mat-accordion>
          </mat-card>

          <mat-card class="result-section unchanged">
            <h3><mat-icon>check</mat-icon> Inchangées ({{ analysis.unchanged_requirements?.length || 0 }})</h3>
            <div *ngFor="let req of analysis.unchanged_requirements" class="req-item">
              <strong>{{ req.title }}</strong>
            </div>
          </mat-card>
        </div>
      </div>

      <mat-card *ngIf="error" class="error-card">
        <mat-icon>error</mat-icon>
        <p>{{ error }}</p>
      </mat-card>
    </div>
  `,
  styles: [`
    .page-container { max-width: 1200px; margin: 0 auto; }
    .page-header { display: flex; align-items: center; gap: 12px; margin-bottom: 24px; }
    .page-header h1 { flex: 1; margin: 0; color: #1B3A5C; }
    .loading-container { text-align: center; padding: 48px; }
    .loading-container p { color: #666; margin-top: 16px; }
    .progress-card { padding: 24px; margin-bottom: 16px; border-left: 4px solid #1976d2; }
    .progress-header { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
    .progress-header h3 { margin: 0; color: #1976d2; font-size: 15px; }
    .progress-details { display: flex; justify-content: space-between; margin-top: 8px; font-size: 13px; }
    .progress-step { color: #1976d2; }
    .progress-pct { font-weight: bold; }
    .progress-message { margin: 8px 0 0 0; font-size: 13px; color: #666; }
    .summary-card { padding: 24px; margin-bottom: 16px; background: #e3f2fd; }
    .results-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .result-section { padding: 16px; }
    .result-section h3 { display: flex; align-items: center; gap: 8px; }
    .new h3 { color: #1565c0; }
    .removed h3 { color: #c62828; }
    .modified h3 { color: #ef6c00; }
    .unchanged h3 { color: #2e7d32; }
    .req-item { padding: 8px; border-bottom: 1px solid #eee; }
    .req-item p { font-size: 13px; color: #666; }
    .priority-high { background: #ffcdd2 !important; }
    .priority-medium { background: #fff3e0 !important; }
    .priority-low { background: #e8f5e9 !important; }
    .error-card { padding: 24px; display: flex; align-items: center; gap: 12px; color: #c62828; }
    .analysis-timestamp { display: flex; align-items: center; gap: 6px; font-size: 13px; color: #888; margin-bottom: 16px; }
    .analysis-timestamp mat-icon { font-size: 18px; width: 18px; height: 18px; }
  `],
})
export class GapAnalysisComponent implements OnInit, OnDestroy {
  projectId = '';
  analysis: GapAnalysis | null = null;
  analyzing = false;
  loadingExisting = false;
  exportingPdf = false;
  error = '';
  analysisProgress: { status: string; step: string; progress: number; message: string } | null = null;
  private pollSub: Subscription | null = null;

  constructor(private route: ActivatedRoute, private api: ApiService, private snackBar: MatSnackBar) {}

  ngOnInit(): void {
    this.projectId = this.route.snapshot.paramMap.get('projectId') || '';
    this.loadExisting();
    // Resume polling if analysis was already running
    this.api.getGapAnalysisStatus(this.projectId).subscribe({
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
    this.api.getGapAnalysis(this.projectId).subscribe({
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
    this.analysisProgress = { status: 'running', step: 'starting', progress: 0, message: 'Lancement...' };
    this.api.analyzeGap(this.projectId).subscribe({
      next: () => {
        this.startPolling();
      },
      error: (err) => {
        this.error = err.error?.detail || 'Erreur d\'analyse';
        this.analyzing = false;
        this.analysisProgress = null;
      },
    });
  }

  exportPdf(): void {
    this.exportingPdf = true;
    this.api.exportGapAnalysisPdf(this.projectId).subscribe({
      next: (blob) => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'analyse_ecarts.pdf';
        a.click();
        window.URL.revokeObjectURL(url);
        this.exportingPdf = false;
        this.snackBar.open('PDF exporte avec succes', 'OK', { duration: 3000 });
      },
      error: () => {
        this.exportingPdf = false;
        this.snackBar.open('Erreur lors de l\'export PDF', 'OK', { duration: 3000 });
      },
    });
  }

  private startPolling(): void {
    this.stopPolling();
    this.pollSub = timer(1000, 1500).pipe(
      switchMap(() => this.api.getGapAnalysisStatus(this.projectId))
    ).subscribe({
      next: (status) => {
        this.analysisProgress = status;
        if (status.status === 'completed') {
          this.stopPolling();
          this.analyzing = false;
          this.analysisProgress = null;
          this.snackBar.open('Analyse des ecarts terminee', 'OK', { duration: 3000 });
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
}
