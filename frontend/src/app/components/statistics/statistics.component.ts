import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
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
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { ApiService } from '../../services/api.service';
import { ProjectStatistics, AnonymizationReport, AnonymizationMapping } from '../../models/report.model';

@Component({
  selector: 'app-statistics',
  standalone: true,
  imports: [
    CommonModule, FormsModule, RouterLink,
    MatCardModule, MatButtonModule, MatIconModule, MatProgressSpinnerModule, MatProgressBarModule,
    MatListModule, MatExpansionModule, MatChipsModule, MatTableModule, MatInputModule,
    MatSelectModule, MatTooltipModule, MatSnackBarModule, MatSlideToggleModule,
  ],
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
        <div class="section-actions">
          <button mat-raised-button color="accent" (click)="reAnonymize()" [disabled]="reAnonymizing"
            matTooltip="Re-appliquer tous les mappings actifs sur les documents et chapitres">
            <mat-spinner *ngIf="reAnonymizing" diameter="18"></mat-spinner>
            <mat-icon *ngIf="!reAnonymizing">sync</mat-icon> Re-anonymiser tout
          </button>
        </div>
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

        <!-- Add new mapping form -->
        <mat-card class="full-width-card add-mapping-card">
          <h3><mat-icon>add_circle</mat-icon> Ajouter un mapping manuellement</h3>
          <p class="add-mapping-hint">Ajoutez les entites que le NER automatique n'a pas detectees (noms de clients, numeros d'AO, codes marche...)</p>
          <div class="add-mapping-form">
            <mat-form-field appearance="outline" class="form-field-type">
              <mat-label>Type</mat-label>
              <mat-select [(value)]="newMapping.entity_type">
                <mat-option *ngFor="let t of entityTypes" [value]="t.value">{{ t.label }}</mat-option>
              </mat-select>
            </mat-form-field>
            <mat-form-field appearance="outline" class="form-field-original">
              <mat-label>Valeur originale (secret)</mat-label>
              <input matInput [(ngModel)]="newMapping.original_value" placeholder="Ex: UGAP, AO 24U027...">
            </mat-form-field>
            <mat-form-field appearance="outline" class="form-field-anon">
              <mat-label>Placeholder (optionnel)</mat-label>
              <input matInput [(ngModel)]="newMapping.anonymized_value" placeholder="Auto-genere si vide">
            </mat-form-field>
            <button mat-raised-button color="primary" (click)="addMapping()" [disabled]="!newMapping.original_value || addingMapping">
              <mat-icon>add</mat-icon> Ajouter
            </button>
          </div>
        </mat-card>

        <!-- Entity groups with editable table -->
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
                <th mat-header-cell *matHeaderCellDef>Valeur originale (secret)</th>
                <td mat-cell *matCellDef="let m">
                  <span class="original-value" *ngIf="editingId !== m.id">{{ m.original_value }}</span>
                  <mat-form-field *ngIf="editingId === m.id" appearance="outline" class="inline-edit">
                    <input matInput [(ngModel)]="editForm.original_value">
                  </mat-form-field>
                </td>
              </ng-container>
              <ng-container matColumnDef="anonymized">
                <th mat-header-cell *matHeaderCellDef>Remplace par (visible par l'IA)</th>
                <td mat-cell *matCellDef="let m">
                  <span class="anon-value" *ngIf="editingId !== m.id">{{ m.anonymized_value }}</span>
                  <mat-form-field *ngIf="editingId === m.id" appearance="outline" class="inline-edit">
                    <input matInput [(ngModel)]="editForm.anonymized_value">
                  </mat-form-field>
                </td>
              </ng-container>
              <ng-container matColumnDef="active">
                <th mat-header-cell *matHeaderCellDef>Actif</th>
                <td mat-cell *matCellDef="let m">
                  <mat-slide-toggle [checked]="m.is_active" (change)="toggleMapping(m)"
                    matTooltip="Activer/desactiver ce mapping">
                  </mat-slide-toggle>
                </td>
              </ng-container>
              <ng-container matColumnDef="actions">
                <th mat-header-cell *matHeaderCellDef>Actions</th>
                <td mat-cell *matCellDef="let m">
                  <div class="action-buttons" *ngIf="editingId !== m.id">
                    <button mat-icon-button (click)="startEdit(m)" matTooltip="Modifier">
                      <mat-icon>edit</mat-icon>
                    </button>
                    <button mat-icon-button color="warn" (click)="deleteMapping(m)" matTooltip="Supprimer">
                      <mat-icon>delete</mat-icon>
                    </button>
                  </div>
                  <div class="action-buttons" *ngIf="editingId === m.id">
                    <button mat-icon-button color="primary" (click)="saveEdit(m)" matTooltip="Sauvegarder">
                      <mat-icon>check</mat-icon>
                    </button>
                    <button mat-icon-button (click)="cancelEdit()" matTooltip="Annuler">
                      <mat-icon>close</mat-icon>
                    </button>
                  </div>
                </td>
              </ng-container>
              <tr mat-header-row *matHeaderRowDef="mappingColumns"></tr>
              <tr mat-row *matRowDef="let row; columns: mappingColumns"></tr>
            </table>
          </mat-expansion-panel>
        </mat-accordion>

        <mat-card *ngIf="anonReport.total_entities === 0" class="full-width-card empty-card">
          <mat-icon>info</mat-icon>
          <p>Aucune entite anonymisee pour le moment. Ajoutez des mappings manuellement ou attendez le traitement des documents.</p>
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
    .section-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin: 32px 0 16px 0; }
    .section-header h2 { display: flex; align-items: center; gap: 8px; color: #1B3A5C; font-size: 18px; margin: 0; }
    .section-actions { display: flex; gap: 8px; }
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

    /* Add mapping form */
    .add-mapping-card { margin-bottom: 20px; }
    .add-mapping-hint { color: #666; font-size: 13px; margin: 0 0 16px 0; }
    .add-mapping-form { display: flex; gap: 12px; align-items: flex-start; flex-wrap: wrap; }
    .form-field-type { width: 180px; }
    .form-field-original { flex: 1; min-width: 200px; }
    .form-field-anon { width: 220px; }

    .group-icon { margin-right: 8px; color: #2C5F8A; }
    .mappings-table { width: 100%; }
    .original-value { color: #e65100; font-weight: 500; }
    .anon-value { color: #2e7d32; font-family: monospace; font-weight: 500; background: #f1f8e9; padding: 2px 6px; border-radius: 4px; }
    .inline-edit { width: 100%; font-size: 13px; }
    .action-buttons { display: flex; gap: 2px; }
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
  reAnonymizing = false;
  addingMapping = false;
  mappingColumns = ['original', 'anonymized', 'active', 'actions'];

  // New mapping form
  newMapping = { entity_type: 'company', original_value: '', anonymized_value: '' };

  // Inline edit state
  editingId: string | null = null;
  editForm = { original_value: '', anonymized_value: '' };

  entityTypes = [
    { value: 'company', label: 'Entreprise / Organisation' },
    { value: 'person', label: 'Personne' },
    { value: 'email', label: 'Adresse email' },
    { value: 'phone', label: 'Telephone' },
    { value: 'address', label: 'Adresse postale' },
    { value: 'project_code', label: 'Code projet / marche' },
    { value: 'rfp_code', label: 'Code AO' },
    { value: 'solution_name', label: 'Nom de solution' },
    { value: 'date', label: 'Date' },
    { value: 'amount', label: 'Montant' },
    { value: 'other', label: 'Autre' },
  ];

  constructor(
    private route: ActivatedRoute,
    private api: ApiService,
    private snackBar: MatSnackBar,
  ) {}

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

  // ── CRUD operations ──

  addMapping(): void {
    if (!this.newMapping.original_value) return;
    this.addingMapping = true;
    const data: any = {
      entity_type: this.newMapping.entity_type,
      original_value: this.newMapping.original_value,
    };
    if (this.newMapping.anonymized_value) {
      data.anonymized_value = this.newMapping.anonymized_value;
    }
    this.api.createAnonymizationMapping(this.projectId, data).subscribe({
      next: () => {
        this.snackBar.open('Mapping ajoute', 'OK', { duration: 2000 });
        this.newMapping = { entity_type: 'company', original_value: '', anonymized_value: '' };
        this.addingMapping = false;
        this.loadAnonReport();
      },
      error: (err) => {
        this.snackBar.open(err.error?.detail || 'Erreur', 'OK', { duration: 4000 });
        this.addingMapping = false;
      },
    });
  }

  toggleMapping(mapping: AnonymizationMapping): void {
    this.api.updateAnonymizationMapping(this.projectId, mapping.id, { is_active: !mapping.is_active }).subscribe({
      next: () => {
        mapping.is_active = !mapping.is_active;
        this.snackBar.open(mapping.is_active ? 'Mapping active' : 'Mapping desactive', 'OK', { duration: 1500 });
      },
      error: () => this.snackBar.open('Erreur', 'OK', { duration: 3000 }),
    });
  }

  startEdit(mapping: AnonymizationMapping): void {
    this.editingId = mapping.id;
    this.editForm = { original_value: mapping.original_value, anonymized_value: mapping.anonymized_value };
  }

  cancelEdit(): void {
    this.editingId = null;
  }

  saveEdit(mapping: AnonymizationMapping): void {
    this.api.updateAnonymizationMapping(this.projectId, mapping.id, {
      original_value: this.editForm.original_value,
      anonymized_value: this.editForm.anonymized_value,
    }).subscribe({
      next: (updated) => {
        mapping.original_value = updated.original_value;
        mapping.anonymized_value = updated.anonymized_value;
        this.editingId = null;
        this.snackBar.open('Mapping mis a jour', 'OK', { duration: 2000 });
      },
      error: () => this.snackBar.open('Erreur', 'OK', { duration: 3000 }),
    });
  }

  deleteMapping(mapping: AnonymizationMapping): void {
    if (!confirm(`Supprimer le mapping "${mapping.original_value}" -> "${mapping.anonymized_value}" ?`)) return;
    this.api.deleteAnonymizationMapping(this.projectId, mapping.id).subscribe({
      next: () => {
        this.snackBar.open('Mapping supprime', 'OK', { duration: 2000 });
        this.loadAnonReport();
      },
      error: () => this.snackBar.open('Erreur', 'OK', { duration: 3000 }),
    });
  }

  reAnonymize(): void {
    if (!confirm('Re-anonymiser tous les documents et chapitres avec les mappings actuels ? Cette operation peut prendre quelques secondes.')) return;
    this.reAnonymizing = true;
    this.api.reAnonymizeProject(this.projectId).subscribe({
      next: (res) => {
        this.snackBar.open(`Re-anonymisation terminee : ${res.updated_chunks} chunks et ${res.updated_chapters} chapitres mis a jour`, 'OK', { duration: 5000 });
        this.reAnonymizing = false;
        this.loadAnonReport();
      },
      error: (err) => {
        this.snackBar.open(err.error?.detail || 'Erreur', 'OK', { duration: 5000 });
        this.reAnonymizing = false;
      },
    });
  }

  // ── Helpers ──

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
