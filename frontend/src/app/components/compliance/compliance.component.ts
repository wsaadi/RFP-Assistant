import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatChipsModule } from '@angular/material/chips';
import { MatListModule } from '@angular/material/list';
import { ApiService } from '../../services/api.service';
import { ComplianceAnalysis } from '../../models/report.model';

@Component({
  selector: 'app-compliance',
  standalone: true,
  imports: [CommonModule, RouterLink, MatCardModule, MatButtonModule, MatIconModule, MatProgressSpinnerModule, MatProgressBarModule, MatChipsModule, MatListModule],
  template: `
    <div class="page-container">
      <div class="page-header">
        <button mat-icon-button [routerLink]="['/project', projectId]"><mat-icon>arrow_back</mat-icon></button>
        <h1>Analyse de conformité et exhaustivité</h1>
        <button mat-raised-button color="primary" (click)="runAnalysis()" [disabled]="analyzing">
          <mat-spinner *ngIf="analyzing" diameter="18"></mat-spinner>
          <mat-icon *ngIf="!analyzing">fact_check</mat-icon>
          {{ analysis ? 'Relancer' : 'Analyser' }}
        </button>
      </div>

      <div *ngIf="analyzing" class="loading-container">
        <mat-spinner diameter="40"></mat-spinner>
        <p>Analyse de conformité en cours...</p>
      </div>

      <div *ngIf="analysis" class="analysis-results">
        <!-- Score -->
        <mat-card class="score-card">
          <div class="score-circle" [class]="scoreClass">
            <span class="score-value">{{ analysis.score }}</span>
            <span class="score-label">/ 100</span>
          </div>
          <div class="score-details">
            <h2>Score de conformité</h2>
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
          <h3><mat-icon>warning</mat-icon> Éléments manquants</h3>
          <mat-list>
            <mat-list-item *ngFor="let item of analysis.missing_elements">
              <mat-icon matListItemIcon color="warn">error_outline</mat-icon>
              <span matListItemTitle>{{ item.requirement }}</span>
              <span matListItemLine>{{ item.description }}</span>
            </mat-list-item>
          </mat-list>
        </mat-card>

        <!-- Recommendations -->
        <mat-card *ngIf="analysis.recommendations?.length" class="section-card">
          <h3><mat-icon>lightbulb</mat-icon> Recommandations</h3>
          <mat-list>
            <mat-list-item *ngFor="let rec of analysis.recommendations">
              <mat-icon matListItemIcon>arrow_forward</mat-icon>
              <span matListItemTitle>{{ rec }}</span>
            </mat-list-item>
          </mat-list>
        </mat-card>
      </div>

      <mat-card *ngIf="error" class="error-card"><mat-icon>error</mat-icon><p>{{ error }}</p></mat-card>
    </div>
  `,
  styles: [`
    .page-container { max-width: 1000px; margin: 0 auto; }
    .page-header { display: flex; align-items: center; gap: 12px; margin-bottom: 24px; }
    .page-header h1 { flex: 1; margin: 0; color: #1B3A5C; font-size: 20px; }
    .loading-container { text-align: center; padding: 48px; }
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
    .error-card { padding: 24px; display: flex; align-items: center; gap: 12px; color: #c62828; }
  `],
})
export class ComplianceComponent implements OnInit {
  projectId = '';
  analysis: ComplianceAnalysis | null = null;
  analyzing = false;
  error = '';

  get scoreClass(): string {
    if (!this.analysis) return '';
    if (this.analysis.score >= 80) return 'high';
    if (this.analysis.score >= 50) return 'medium';
    return 'low';
  }

  constructor(private route: ActivatedRoute, private api: ApiService) {}

  ngOnInit(): void {
    this.projectId = this.route.snapshot.paramMap.get('projectId') || '';
  }

  runAnalysis(): void {
    this.analyzing = true;
    this.error = '';
    this.api.analyzeCompliance(this.projectId).subscribe({
      next: (res) => { this.analysis = res.analysis; this.analyzing = false; },
      error: (err) => { this.error = err.error?.detail || 'Erreur'; this.analyzing = false; },
    });
  }

  coverageLabel(coverage: string): string {
    const labels: Record<string, string> = { complete: 'Complet', partial: 'Partiel', missing: 'Manquant' };
    return labels[coverage] || coverage;
  }
}
