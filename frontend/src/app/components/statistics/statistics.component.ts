import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatListModule } from '@angular/material/list';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatChipsModule } from '@angular/material/chips';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../../services/api.service';
import { ProjectStatistics, AnonymizationReport, AnonymizationEntityGroup } from '../../models/report.model';

@Component({
  selector: 'app-statistics',
  standalone: true,
  imports: [CommonModule, RouterLink, MatCardModule, MatButtonModule, MatIconModule, MatProgressSpinnerModule, MatProgressBarModule, MatListModule, MatExpansionModule, MatChipsModule, MatTableModule],
  template: `
    <div class="page-container">
      <div class="page-header">
        <button mat-icon-button [routerLink]="['/project', projectId]"><mat-icon>arrow_back</mat-icon></button>
        <h1>Statistiques du projet</h1>
        <button mat-raised-button color="primary" (click)="loadAll()" [disabled]="loading">
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
            <span class="stat-label">Caracteres</span>
          </div>
        </mat-card>

        <mat-card class="stat-card">
          <mat-icon class="stat-icon blue">menu_book</mat-icon>
          <div class="stat-info">
            <span class="stat-value">{{ stats.total_pages }}</span>
            <span class="stat-label">Pages estimees</span>
          </div>
        </mat-card>

        <mat-card class="stat-card">
          <mat-icon class="stat-icon green">check_circle</mat-icon>
          <div class="stat-info">
            <span class="stat-value">{{ stats.completion_percentage }}%</span>
            <span class="stat-label">Completion</span>
          </div>
        </mat-card>

        <!-- Completion bar -->
        <mat-card class="full-width-card">
          <h3>Avancement global</h3>
          <mat-progress-bar mode="determinate" [value]="stats.completion_percentage"
            [color]="stats.completion_percentage >= 80 ? 'primary' : stats.completion_percentage >= 50 ? 'accent' : 'warn'">
          </mat-progress-bar>
          <div class="completion-details">
            <span>{{ stats.chapters_completed }} / {{ stats.chapters_total }} chapitres completes</span>
          </div>
        </mat-card>

        <!-- Chapters breakdown -->
        <mat-card class="full-width-card">
          <h3><mat-icon>assignment</mat-icon> Chapitres par statut</h3>
          <div class="status-grid">
            <div class="status-item">
              <div class="status-bar draft" [style.width.%]="statusPercent('draft')"></div>
              <span>Brouillon: {{ statusCount('draft') }}</span>
            </div>
            <div class="status-item">
              <div class="status-bar in-progress" [style.width.%]="statusPercent('in_progress')"></div>
              <span>En cours: {{ statusCount('in_progress') }}</span>
            </div>
            <div class="status-item">
              <div class="status-bar review" [style.width.%]="statusPercent('review')"></div>
              <span>En revue: {{ statusCount('review') }}</span>
            </div>
            <div class="status-item">
              <div class="status-bar completed" [style.width.%]="statusPercent('completed')"></div>
              <span>Completes: {{ statusCount('completed') }}</span>
            </div>
          </div>
        </mat-card>
      </div>

      <!-- Anonymization report -->
      <div class="section-header" *ngIf="anonReport">
        <h2><mat-icon>security</mat-icon> Rapport d'anonymisation</h2>
      </div>

      <div *ngIf="anonReport" class="anon-section">
        <!-- Summary cards -->
        <div class="anon-summary">
          <mat-card class="anon-stat-card">
            <div class="anon-stat-value">{{ anonReport.total_entities }}</div>
            <div class="anon-stat-label">Entites detectees</div>
          </mat-card>
          <mat-card class="anon-stat-card active">
            <div class="anon-stat-value">{{ anonReport.active_entities }}</div>
            <div class="anon-stat-label">Actives</div>
          </mat-card>
          <mat-card class="anon-stat-card" *ngFor="let g of anonReport.entity_groups">
            <div class="anon-stat-value">{{ g.count }}</div>
            <div class="anon-stat-label">{{ g.label }}</div>
          </mat-card>
        </div>

        <!-- Before/After sample -->
        <mat-card *ngIf="anonReport.sample_before" class="full-width-card sample-card">
          <h3><mat-icon>compare_arrows</mat-icon> Exemple avant / apres anonymisation</h3>
          <div class="sample-grid">
            <div class="sample-box">
              <div class="sample-label original">ORIGINAL</div>
              <div class="sample-content">{{ anonReport.sample_before }}</div>
            </div>
            <div class="sample-box">
              <div class="sample-label anonymized">ANONYMISE</div>
              <div class="sample-content">{{ anonReport.sample_after }}</div>
            </div>
          </div>
        </mat-card>

        <!-- Entity groups -->
        <mat-accordion multi>
          <mat-expansion-panel *ngFor="let group of anonReport.entity_groups">
            <mat-expansion-panel-header>
              <mat-panel-title>
                <mat-icon class="group-icon">{{ getEntityIcon(group.entity_type) }}</mat-icon>
                {{ group.label }}
              </mat-panel-title>
              <mat-panel-description>
                {{ group.count }} entite(s)
              </mat-panel-description>
            </mat-expansion-panel-header>

            <table mat-table [dataSource]="group.mappings" class="mappings-table">
              <ng-container matColumnDef="original">
                <th mat-header-cell *matHeaderCellDef>Valeur originale</th>
                <td mat-cell *matCellDef="let m">
                  <span class="original-value">{{ m.original_value }}</span>
                </td>
              </ng-container>
              <ng-container matColumnDef="anonymized">
                <th mat-header-cell *matHeaderCellDef>Remplace par</th>
                <td mat-cell *matCellDef="let m">
                  <span class="anon-value">{{ m.anonymized_value }}</span>
                </td>
              </ng-container>
              <ng-container matColumnDef="active">
                <th mat-header-cell *matHeaderCellDef>Actif</th>
                <td mat-cell *matCellDef="let m">
                  <mat-icon [class.active-icon]="m.is_active" [class.inactive-icon]="!m.is_active">
                    {{ m.is_active ? 'check_circle' : 'cancel' }}
                  </mat-icon>
                </td>
              </ng-container>
              <tr mat-header-row *matHeaderRowDef="['original', 'anonymized', 'active']"></tr>
              <tr mat-row *matRowDef="let row; columns: ['original', 'anonymized', 'active']"></tr>
            </table>
          </mat-expansion-panel>
        </mat-accordion>

        <mat-card *ngIf="anonReport.total_entities === 0" class="full-width-card empty-card">
          <mat-icon>info</mat-icon>
          <p>Aucune entite anonymisee pour le moment. Les entites seront detectees lors du traitement des documents et des appels IA.</p>
        </mat-card>
      </div>

      <mat-card *ngIf="error" class="error-card"><mat-icon>error</mat-icon><p>{{ error }}</p></mat-card>
    </div>
  `,
  styles: [`
    .page-container { max-width: 1100px; margin: 0 auto; }
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
    .error-card { padding: 24px; display: flex; align-items: center; gap: 12px; color: #c62828; margin-top: 16px; }

    /* Anonymization section */
    .section-header { display: flex; align-items: center; gap: 8px; margin: 32px 0 16px 0; }
    .section-header h2 { display: flex; align-items: center; gap: 8px; color: #1B3A5C; font-size: 18px; margin: 0; }
    .anon-section { margin-bottom: 32px; }
    .anon-summary { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px; margin-bottom: 20px; }
    .anon-stat-card { padding: 16px; text-align: center; }
    .anon-stat-card.active { border-left: 4px solid #4caf50; }
    .anon-stat-value { font-size: 24px; font-weight: bold; color: #1B3A5C; }
    .anon-stat-label { font-size: 12px; color: #888; margin-top: 4px; }

    .sample-card { margin-bottom: 20px; }
    .sample-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .sample-box { border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden; }
    .sample-label { padding: 6px 12px; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
    .sample-label.original { background: #fff3e0; color: #e65100; }
    .sample-label.anonymized { background: #e8f5e9; color: #2e7d32; }
    .sample-content { padding: 12px; font-size: 13px; line-height: 1.5; color: #333; white-space: pre-wrap; word-break: break-word; max-height: 200px; overflow-y: auto; }

    .group-icon { margin-right: 8px; color: #2C5F8A; }
    .mappings-table { width: 100%; }
    .original-value { color: #e65100; font-weight: 500; }
    .anon-value { color: #2e7d32; font-family: monospace; font-weight: 500; background: #f1f8e9; padding: 2px 6px; border-radius: 4px; }
    .active-icon { color: #4caf50; font-size: 20px; }
    .inactive-icon { color: #bdbdbd; font-size: 20px; }
    .empty-card { display: flex; align-items: center; gap: 12px; color: #666; }
    .empty-card mat-icon { color: #2C5F8A; }

    mat-expansion-panel { margin-bottom: 8px; }
  `],
})
export class StatisticsComponent implements OnInit {
  projectId = '';
  stats: ProjectStatistics | null = null;
  anonReport: AnonymizationReport | null = null;
  loading = false;
  error = '';

  constructor(private route: ActivatedRoute, private api: ApiService) {}

  ngOnInit(): void {
    this.projectId = this.route.snapshot.paramMap.get('projectId') || '';
    this.loadAll();
  }

  loadAll(): void {
    this.loadStats();
    this.loadAnonReport();
  }

  loadStats(): void {
    this.loading = true;
    this.error = '';
    this.api.getStatistics(this.projectId).subscribe({
      next: (res: ProjectStatistics) => { this.stats = res; this.loading = false; },
      error: (err: any) => { this.error = err.error?.detail || 'Erreur'; this.loading = false; },
    });
  }

  loadAnonReport(): void {
    this.api.getAnonymizationReport(this.projectId).subscribe({
      next: (res) => this.anonReport = res,
    });
  }

  statusCount(status: string): number {
    return (this.stats as any)?.chapters_by_status?.[status] || 0;
  }

  statusPercent(status: string): number {
    if (!this.stats || !this.stats.chapters_total) return 0;
    return (this.statusCount(status) / this.stats.chapters_total) * 100;
  }

  getEntityIcon(entityType: string): string {
    const icons: Record<string, string> = {
      'company': 'business',
      'person': 'person',
      'email': 'email',
      'phone': 'phone',
      'address': 'place',
      'project_code': 'tag',
      'rfp_code': 'label',
      'solution_name': 'devices',
      'date': 'calendar_today',
      'amount': 'euro',
      'other': 'help_outline',
    };
    return icons[entityType] || 'label';
  }
}
