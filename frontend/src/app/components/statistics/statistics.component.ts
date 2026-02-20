import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatListModule } from '@angular/material/list';
import { ApiService } from '../../services/api.service';
import { ProjectStatistics, AnonymizationMapping } from '../../models/report.model';

@Component({
  selector: 'app-statistics',
  standalone: true,
  imports: [CommonModule, RouterLink, MatCardModule, MatButtonModule, MatIconModule, MatProgressSpinnerModule, MatProgressBarModule, MatListModule],
  template: `
    <div class="page-container">
      <div class="page-header">
        <button mat-icon-button [routerLink]="['/project', projectId]"><mat-icon>arrow_back</mat-icon></button>
        <h1>Statistiques du projet</h1>
        <button mat-raised-button color="primary" (click)="loadStats()" [disabled]="loading">
          <mat-icon>refresh</mat-icon> Actualiser
        </button>
      </div>

      <div *ngIf="loading" class="loading-container">
        <mat-spinner diameter="40"></mat-spinner>
      </div>

      <div *ngIf="stats" class="stats-grid">
        <!-- Content stats -->
        <mat-card class="stat-card">
          <mat-icon class="stat-icon blue">description</mat-icon>
          <div class="stat-info">
            <span class="stat-value">{{ stats.total_words | number }}</span>
            <span class="stat-label">Mots</span>
          </div>
        </mat-card>

        <mat-card class="stat-card">
          <mat-icon class="stat-icon blue">text_fields</mat-icon>
          <div class="stat-info">
            <span class="stat-value">{{ stats.total_characters | number }}</span>
            <span class="stat-label">Caractères</span>
          </div>
        </mat-card>

        <mat-card class="stat-card">
          <mat-icon class="stat-icon blue">menu_book</mat-icon>
          <div class="stat-info">
            <span class="stat-value">{{ stats.total_pages }}</span>
            <span class="stat-label">Pages estimées</span>
          </div>
        </mat-card>

        <mat-card class="stat-card">
          <mat-icon class="stat-icon green">check_circle</mat-icon>
          <div class="stat-info">
            <span class="stat-value">{{ stats.completion_percentage }}%</span>
            <span class="stat-label">Complétion</span>
          </div>
        </mat-card>

        <!-- Completion bar -->
        <mat-card class="full-width-card">
          <h3>Avancement global</h3>
          <mat-progress-bar mode="determinate" [value]="stats.completion_percentage"
            [color]="stats.completion_percentage >= 80 ? 'primary' : stats.completion_percentage >= 50 ? 'accent' : 'warn'">
          </mat-progress-bar>
          <div class="completion-details">
            <span>{{ stats.chapters_completed }} / {{ stats.chapters_total }} chapitres complétés</span>
          </div>
        </mat-card>

        <!-- Chapters breakdown -->
        <mat-card class="full-width-card">
          <h3><mat-icon>assignment</mat-icon> Chapitres par statut</h3>
          <div class="status-grid">
            <div class="status-item">
              <div class="status-bar draft" [style.width.%]="statusPercent('draft')"></div>
              <span>Brouillon: {{ stats.chapters_by_status?.draft || 0 }}</span>
            </div>
            <div class="status-item">
              <div class="status-bar in-progress" [style.width.%]="statusPercent('in_progress')"></div>
              <span>En cours: {{ stats.chapters_by_status?.in_progress || 0 }}</span>
            </div>
            <div class="status-item">
              <div class="status-bar review" [style.width.%]="statusPercent('review')"></div>
              <span>En revue: {{ stats.chapters_by_status?.review || 0 }}</span>
            </div>
            <div class="status-item">
              <div class="status-bar completed" [style.width.%]="statusPercent('completed')"></div>
              <span>Complétés: {{ stats.chapters_by_status?.completed || 0 }}</span>
            </div>
          </div>
        </mat-card>
      </div>

      <!-- Anonymization mappings -->
      <mat-card *ngIf="mappings.length > 0" class="full-width-card mappings-card">
        <h3><mat-icon>security</mat-icon> Entités anonymisées ({{ mappings.length }})</h3>
        <mat-list>
          <mat-list-item *ngFor="let m of mappings">
            <mat-icon matListItemIcon>label</mat-icon>
            <span matListItemTitle>{{ m.anonymized_value }}</span>
            <span matListItemLine>{{ m.entity_type }} → {{ m.original_value }}</span>
          </mat-list-item>
        </mat-list>
      </mat-card>

      <mat-card *ngIf="error" class="error-card"><mat-icon>error</mat-icon><p>{{ error }}</p></mat-card>
    </div>
  `,
  styles: [`
    .page-container { max-width: 1000px; margin: 0 auto; }
    .page-header { display: flex; align-items: center; gap: 12px; margin-bottom: 24px; }
    .page-header h1 { flex: 1; margin: 0; color: #1B3A5C; font-size: 20px; }
    .loading-container { text-align: center; padding: 48px; }
    .stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; }
    .stat-card { display: flex; align-items: center; gap: 16px; padding: 24px; }
    .stat-icon { font-size: 40px; width: 40px; height: 40px; }
    .stat-icon.blue { color: #2C5F8A; }
    .stat-icon.green { color: #4caf50; }
    .stat-value { font-size: 28px; font-weight: bold; color: #1B3A5C; display: block; }
    .stat-label { font-size: 13px; color: #888; }
    .full-width-card { grid-column: 1 / -1; padding: 24px; }
    .full-width-card h3 { display: flex; align-items: center; gap: 8px; color: #1B3A5C; margin-top: 0; }
    .completion-details { margin-top: 12px; color: #666; font-size: 14px; }
    .status-grid { display: flex; flex-direction: column; gap: 12px; margin-top: 16px; }
    .status-item { display: flex; align-items: center; gap: 12px; }
    .status-item span { min-width: 160px; font-size: 14px; }
    .status-bar { height: 24px; border-radius: 4px; min-width: 4px; transition: width 0.3s; }
    .status-bar.draft { background: #e0e0e0; }
    .status-bar.in-progress { background: #bbdefb; }
    .status-bar.review { background: #fff3e0; }
    .status-bar.completed { background: #c8e6c9; }
    .mappings-card { margin-top: 16px; }
    .error-card { padding: 24px; display: flex; align-items: center; gap: 12px; color: #c62828; margin-top: 16px; }
  `],
})
export class StatisticsComponent implements OnInit {
  projectId = '';
  stats: ProjectStatistics | null = null;
  mappings: AnonymizationMapping[] = [];
  loading = false;
  error = '';

  constructor(private route: ActivatedRoute, private api: ApiService) {}

  ngOnInit(): void {
    this.projectId = this.route.snapshot.paramMap.get('projectId') || '';
    this.loadStats();
    this.loadMappings();
  }

  loadStats(): void {
    this.loading = true;
    this.error = '';
    this.api.getStatistics(this.projectId).subscribe({
      next: (res: ProjectStatistics) => { this.stats = res; this.loading = false; },
      error: (err: any) => { this.error = err.error?.detail || 'Erreur'; this.loading = false; },
    });
  }

  loadMappings(): void {
    this.api.getAnonymizationMappings(this.projectId).subscribe({
      next: (res) => this.mappings = res,
    });
  }

  statusPercent(status: string): number {
    if (!this.stats || !this.stats.chapters_total) return 0;
    const count = this.stats.chapters_by_status?.[status] || 0;
    return (count / this.stats.chapters_total) * 100;
  }
}
