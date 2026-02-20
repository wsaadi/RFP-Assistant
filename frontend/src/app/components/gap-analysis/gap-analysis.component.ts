import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatChipsModule } from '@angular/material/chips';
import { MatExpansionModule } from '@angular/material/expansion';
import { ApiService } from '../../services/api.service';
import { GapAnalysis } from '../../models/report.model';

@Component({
  selector: 'app-gap-analysis',
  standalone: true,
  imports: [CommonModule, RouterLink, MatCardModule, MatButtonModule, MatIconModule, MatProgressSpinnerModule, MatChipsModule, MatExpansionModule],
  template: `
    <div class="page-container">
      <div class="page-header">
        <button mat-icon-button [routerLink]="['/project', projectId]"><mat-icon>arrow_back</mat-icon></button>
        <h1>Analyse des écarts</h1>
        <button mat-raised-button color="primary" (click)="runAnalysis()" [disabled]="analyzing">
          <mat-spinner *ngIf="analyzing" diameter="18"></mat-spinner>
          <mat-icon *ngIf="!analyzing">compare_arrows</mat-icon>
          {{ analysis ? 'Relancer' : 'Lancer l\'analyse' }}
        </button>
      </div>

      <div *ngIf="analyzing" class="loading-container">
        <mat-spinner diameter="40"></mat-spinner>
        <p>Analyse en cours... Comparaison de l'ancien et du nouvel AO</p>
      </div>

      <div *ngIf="analysis" class="analysis-results">
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
  `],
})
export class GapAnalysisComponent implements OnInit {
  projectId = '';
  analysis: GapAnalysis | null = null;
  analyzing = false;
  error = '';

  constructor(private route: ActivatedRoute, private api: ApiService) {}

  ngOnInit(): void {
    this.projectId = this.route.snapshot.paramMap.get('projectId') || '';
  }

  runAnalysis(): void {
    this.analyzing = true;
    this.error = '';
    this.api.analyzeGap(this.projectId).subscribe({
      next: (res) => { this.analysis = res.analysis; this.analyzing = false; },
      error: (err) => { this.error = err.error?.detail || 'Erreur d\'analyse'; this.analyzing = false; },
    });
  }
}
