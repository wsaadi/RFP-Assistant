import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTabsModule } from '@angular/material/tabs';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatListModule } from '@angular/material/list';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatExpansionModule } from '@angular/material/expansion';
import { Subscription, interval } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { ApiService } from '../../services/api.service';
import { RFPProject, Chapter, DocumentInfo, DocumentProgress, ProjectStatistics } from '../../models/report.model';

@Component({
  selector: 'app-project-dashboard',
  standalone: true,
  imports: [
    CommonModule, FormsModule, RouterLink,
    MatCardModule, MatButtonModule, MatIconModule, MatTabsModule, MatChipsModule,
    MatProgressSpinnerModule, MatProgressBarModule, MatListModule,
    MatInputModule, MatSelectModule, MatSnackBarModule, MatTooltipModule, MatExpansionModule,
  ],
  template: `
    <div class="page-container" *ngIf="project">
      <div class="page-header">
        <div class="header-left">
          <button mat-icon-button [routerLink]="['/workspace', project.workspace_id]"><mat-icon>arrow_back</mat-icon></button>
          <div>
            <h1>{{ project.name }}</h1>
            <span class="subtitle">{{ project.client_name }} - {{ project.rfp_reference }}</span>
          </div>
        </div>
        <div class="header-actions">
          <button mat-raised-button (click)="exportWord()" matTooltip="Exporter en Word">
            <mat-icon>file_download</mat-icon> DOCX
          </button>
          <button mat-raised-button (click)="exportBackup()" matTooltip="Sauvegarder le projet">
            <mat-icon>save</mat-icon> Backup
          </button>
          <button mat-raised-button color="accent" [routerLink]="['/project', projectId, 'preview']">
            <mat-icon>visibility</mat-icon> Aperçu
          </button>
        </div>
      </div>

      <!-- Quick stats -->
      <div class="stats-row" *ngIf="stats">
        <mat-card class="stat-card">
          <mat-icon>insert_drive_file</mat-icon>
          <div><strong>{{ stats.documents_count }}</strong><span>Documents</span></div>
        </mat-card>
        <mat-card class="stat-card">
          <mat-icon>menu_book</mat-icon>
          <div><strong>{{ stats.chapters_total }}</strong><span>Chapitres</span></div>
        </mat-card>
        <mat-card class="stat-card">
          <mat-icon>check_circle</mat-icon>
          <div><strong>{{ stats.completion_percentage }}%</strong><span>Complétion</span></div>
        </mat-card>
        <mat-card class="stat-card">
          <mat-icon>text_fields</mat-icon>
          <div><strong>{{ stats.total_words }}</strong><span>Mots</span></div>
        </mat-card>
      </div>

      <mat-tab-group>
        <!-- Documents tab -->
        <mat-tab label="Documents">
          <div class="tab-content">
            <div class="upload-section">
              <h3>Charger des documents</h3>
              <div class="upload-categories">
                <mat-card class="upload-card" *ngFor="let cat of categories"
                  (dragover)="onDragOver($event)" (drop)="onDrop($event, cat.value)"
                  (click)="triggerUpload(cat.value)">
                  <mat-icon [style.color]="cat.color">{{ cat.icon }}</mat-icon>
                  <strong>{{ cat.label }}</strong>
                  <span>{{ cat.desc }}</span>
                  <input type="file" [id]="'upload-' + cat.value" (change)="onFileSelected($event, cat.value)"
                    accept=".pdf,.docx,.doc,.xlsx,.xls" multiple style="display:none">
                </mat-card>
              </div>
            </div>

            <div *ngFor="let cat of categories" class="doc-category">
              <h4>{{ cat.label }}</h4>
              <mat-list>
                <div *ngFor="let doc of getDocsByCategory(cat.value)" class="doc-item-wrap">
                  <mat-list-item>
                    <mat-icon matListItemIcon>{{ fileIcon(doc.file_type) }}</mat-icon>
                    <span matListItemTitle>{{ doc.original_filename }}</span>
                    <span matListItemLine>
                      {{ formatSize(doc.file_size) }}
                      <ng-container *ngIf="doc.processing_status === 'completed'">
                        - {{ doc.page_count }} pages - {{ doc.chunk_count }} chunks
                      </ng-container>
                      <mat-chip [class]="'proc-' + doc.processing_status" size="small">
                        {{ statusLabel(doc.processing_status) }}
                      </mat-chip>
                    </span>
                    <button mat-icon-button matListItemMeta (click)="deleteDoc(doc.id)"><mat-icon>delete</mat-icon></button>
                  </mat-list-item>
                  <div *ngIf="getProgress(doc.id) as prog" class="doc-progress">
                    <div class="progress-info">
                      <mat-spinner *ngIf="prog.progress > 0" diameter="16"></mat-spinner>
                      <span class="progress-label">{{ prog.step_label }}</span>
                      <span class="progress-pct" *ngIf="prog.progress > 0">{{ prog.progress }}%</span>
                    </div>
                    <mat-progress-bar
                      [mode]="prog.progress > 0 ? 'determinate' : 'indeterminate'"
                      [value]="prog.progress"
                      [color]="prog.progress < 0 ? 'warn' : 'primary'">
                    </mat-progress-bar>
                  </div>
                </div>
              </mat-list>
            </div>
          </div>
        </mat-tab>

        <!-- Chapters tab -->
        <mat-tab label="Structure">
          <div class="tab-content">
            <div class="chapter-actions">
              <button mat-raised-button color="primary" (click)="generateStructure()" [disabled]="generatingStructure">
                <mat-spinner *ngIf="generatingStructure" diameter="18"></mat-spinner>
                <mat-icon *ngIf="!generatingStructure">auto_fix_high</mat-icon>
                Générer la structure depuis l'AO
              </button>
              <button mat-raised-button color="accent" (click)="prefillAll()" [disabled]="prefilling">
                <mat-spinner *ngIf="prefilling" diameter="18"></mat-spinner>
                <mat-icon *ngIf="!prefilling">auto_awesome</mat-icon>
                Pré-remplir depuis ancienne réponse
              </button>
            </div>

            <div class="chapter-tree">
              <mat-accordion multi>
                <mat-expansion-panel *ngFor="let ch of chapters; let i = index">
                  <mat-expansion-panel-header>
                    <mat-panel-title>
                      <mat-chip [class]="'status-' + ch.status" size="small">{{ statusIcon(ch.status) }}</mat-chip>
                      <span class="ch-numbering">{{ i + 1 }}.</span> {{ ch.title }}
                    </mat-panel-title>
                    <mat-panel-description>
                      {{ ch.chapter_type }} - {{ ch.content ? (ch.content.split(' ').length + ' mots') : 'Vide' }}
                    </mat-panel-description>
                  </mat-expansion-panel-header>

                  <p class="ch-desc" *ngIf="ch.description">{{ ch.description }}</p>
                  <p class="ch-req" *ngIf="ch.rfp_requirement"><strong>Exigence AO:</strong> {{ ch.rfp_requirement }}</p>

                  <div class="ch-actions">
                    <button mat-raised-button color="primary" [routerLink]="['/project', projectId, 'chapter', ch.id]">
                      <mat-icon>edit</mat-icon> Éditer
                    </button>
                  </div>

                  <!-- Sub-chapters -->
                  <div *ngIf="ch.children?.length" class="sub-chapters">
                    <div *ngFor="let sub of ch.children; let j = index" class="sub-chapter-item">
                      <mat-chip [class]="'status-' + sub.status" size="small">{{ statusIcon(sub.status) }}</mat-chip>
                      <span class="ch-numbering">{{ i + 1 }}.{{ j + 1 }}</span>
                      <span>{{ sub.title }}</span>
                      <span class="sub-meta">{{ sub.content ? (sub.content.split(' ').length + ' mots') : 'Vide' }}</span>
                      <button mat-icon-button [routerLink]="['/project', projectId, 'chapter', sub.id]">
                        <mat-icon>edit</mat-icon>
                      </button>
                    </div>
                  </div>
                </mat-expansion-panel>
              </mat-accordion>
            </div>
          </div>
        </mat-tab>

        <!-- AI Tools tab -->
        <mat-tab label="Outils IA">
          <div class="tab-content">
            <div class="tools-grid">
              <mat-card class="tool-card" [routerLink]="['/project', projectId, 'gap-analysis']">
                <mat-icon>compare_arrows</mat-icon>
                <h3>Analyse des écarts</h3>
                <p>Comparer l'ancien et le nouvel AO pour identifier les différences</p>
              </mat-card>

              <mat-card class="tool-card" [routerLink]="['/project', projectId, 'compliance']">
                <mat-icon>fact_check</mat-icon>
                <h3>Conformité</h3>
                <p>Vérifier l'exhaustivité et la conformité de la réponse</p>
              </mat-card>

              <mat-card class="tool-card" [routerLink]="['/project', projectId, 'statistics']">
                <mat-icon>analytics</mat-icon>
                <h3>Statistiques</h3>
                <p>Voir les statistiques détaillées du document</p>
              </mat-card>

              <mat-card class="tool-card" (click)="showImprovementForm = true">
                <mat-icon>trending_up</mat-icon>
                <h3>Axes d'amélioration</h3>
                <p>Ajouter des retours client pour améliorer la réponse</p>
              </mat-card>
            </div>

            <mat-card *ngIf="showImprovementForm" class="improvement-form">
              <h3>Ajouter un axe d'amélioration</h3>
              <mat-form-field appearance="outline" class="full-width">
                <mat-label>Contenu du retour client</mat-label>
                <textarea matInput [(ngModel)]="improvementContent" rows="4"
                  placeholder="Ex: Le client souhaite plus de détails sur la méthodologie de test..."></textarea>
              </mat-form-field>
              <mat-form-field appearance="outline" class="full-width">
                <mat-label>Source</mat-label>
                <input matInput [(ngModel)]="improvementSource" placeholder="Ex: Réunion du 15/01, Appel téléphonique">
              </mat-form-field>
              <div class="form-actions">
                <button mat-button (click)="showImprovementForm = false">Annuler</button>
                <button mat-raised-button color="primary" (click)="addImprovement()">Ajouter</button>
              </div>
            </mat-card>

            <mat-card *ngIf="project.improvement_axes" class="axes-display">
              <h3>Axes d'amélioration enregistrés</h3>
              <pre class="axes-content">{{ project.improvement_axes }}</pre>
            </mat-card>
          </div>
        </mat-tab>
      </mat-tab-group>
    </div>

    <div *ngIf="loading" class="loading-container">
      <mat-spinner diameter="40"></mat-spinner>
    </div>
  `,
  styles: [`
    .page-container { max-width: 1400px; margin: 0 auto; }
    .page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
    .header-left { display: flex; align-items: center; gap: 8px; }
    .header-left h1 { margin: 0; color: #1B3A5C; }
    .subtitle { color: #666; font-size: 14px; }
    .header-actions { display: flex; gap: 8px; flex-wrap: wrap; }
    .stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 16px; }
    .stat-card { display: flex; align-items: center; gap: 12px; padding: 16px; }
    .stat-card mat-icon { font-size: 32px; width: 32px; height: 32px; color: #2C5F8A; }
    .stat-card div { display: flex; flex-direction: column; }
    .stat-card strong { font-size: 24px; color: #1B3A5C; }
    .stat-card span { font-size: 12px; color: #888; }
    .tab-content { padding: 16px 0; }
    .upload-categories { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 24px; }
    .upload-card { cursor: pointer; text-align: center; padding: 24px; border: 2px dashed #ccc; transition: border-color 0.2s; }
    .upload-card:hover { border-color: #2C5F8A; }
    .upload-card mat-icon { font-size: 36px; width: 36px; height: 36px; }
    .upload-card strong { display: block; margin: 8px 0 4px; }
    .upload-card span { font-size: 12px; color: #888; }
    .doc-category { margin-bottom: 16px; }
    .doc-category h4 { color: #1B3A5C; }
    .proc-completed { background: #c8e6c9 !important; }
    .proc-processing { background: #fff3e0 !important; }
    .proc-pending { background: #e0e0e0 !important; }
    .proc-failed { background: #ffcdd2 !important; }
    .chapter-actions { display: flex; gap: 8px; margin-bottom: 16px; }
    .ch-numbering { font-weight: bold; color: #2C5F8A; margin-right: 4px; }
    .ch-desc { color: #666; font-size: 13px; }
    .ch-req { font-size: 13px; background: #f5f5f5; padding: 8px; border-radius: 4px; }
    .ch-actions { display: flex; gap: 8px; margin-top: 8px; }
    .sub-chapters { margin-top: 12px; padding-left: 24px; }
    .sub-chapter-item { display: flex; align-items: center; gap: 8px; padding: 8px 0; border-bottom: 1px solid #eee; }
    .sub-meta { color: #888; font-size: 12px; margin-left: auto; }
    .status-not_started { background: #e0e0e0 !important; }
    .status-in_progress { background: #bbdefb !important; }
    .status-completed { background: #c8e6c9 !important; }
    .status-needs_review { background: #fff3e0 !important; }
    .tools-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
    .tool-card { cursor: pointer; padding: 24px; text-align: center; transition: transform 0.2s; }
    .tool-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
    .tool-card mat-icon { font-size: 48px; width: 48px; height: 48px; color: #2C5F8A; }
    .tool-card h3 { color: #1B3A5C; }
    .tool-card p { color: #666; font-size: 13px; }
    .improvement-form { padding: 24px; margin-top: 16px; }
    .axes-display { padding: 24px; margin-top: 16px; }
    .axes-content { white-space: pre-wrap; font-size: 14px; background: #f5f5f5; padding: 12px; border-radius: 4px; }
    .full-width { width: 100%; }
    .form-actions { display: flex; gap: 8px; justify-content: flex-end; }
    .loading-container { display: flex; justify-content: center; padding: 48px; }
    .doc-item-wrap { border-bottom: 1px solid #eee; }
    .doc-progress { padding: 0 16px 12px 56px; }
    .progress-info { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
    .progress-label { font-size: 12px; color: #555; }
    .progress-pct { font-size: 12px; color: #888; margin-left: auto; }
  `],
})
export class ProjectDashboardComponent implements OnInit, OnDestroy {
  projectId = '';
  project: RFPProject | null = null;
  chapters: Chapter[] = [];
  documents: DocumentInfo[] = [];
  stats: ProjectStatistics | null = null;
  progressMap: Record<string, DocumentProgress> = {};
  loading = true;
  generatingStructure = false;
  prefilling = false;
  showImprovementForm = false;
  improvementContent = '';
  improvementSource = '';
  private pollSub: Subscription | null = null;

  categories = [
    { value: 'old_rfp', label: 'Ancien AO', desc: 'Documents de l\'ancien appel d\'offres', icon: 'history', color: '#1976d2' },
    { value: 'old_response', label: 'Ancienne Réponse', desc: 'Réponse à l\'ancien AO', icon: 'reply', color: '#388e3c' },
    { value: 'new_rfp', label: 'Nouvel AO', desc: 'Documents du nouvel appel d\'offres', icon: 'fiber_new', color: '#d32f2f' },
  ];

  constructor(
    private route: ActivatedRoute,
    private api: ApiService,
    private snackBar: MatSnackBar,
    private router: Router,
  ) {}

  ngOnInit(): void {
    this.projectId = this.route.snapshot.paramMap.get('projectId') || '';
    this.loadAll();
  }

  ngOnDestroy(): void {
    this.stopPolling();
  }

  loadAll(): void {
    this.loading = true;
    this.api.getProject(this.projectId).subscribe({
      next: (p) => { this.project = p; this.loading = false; },
    });
    this.api.getChapters(this.projectId).subscribe({
      next: (ch) => this.chapters = ch,
    });
    this.api.getDocuments(this.projectId).subscribe({
      next: (d) => {
        this.documents = d;
        const hasProcessing = d.some(doc => doc.processing_status === 'pending' || doc.processing_status === 'processing');
        if (hasProcessing) {
          this.startPolling();
        } else {
          this.stopPolling();
          this.progressMap = {};
        }
      },
    });
    this.api.getStatistics(this.projectId).subscribe({
      next: (s) => this.stats = s,
    });
  }

  private startPolling(): void {
    if (this.pollSub) return;
    this.pollSub = interval(2000).pipe(
      switchMap(() => this.api.getProcessingProgress(this.projectId))
    ).subscribe({
      next: (res) => {
        const map: Record<string, DocumentProgress> = {};
        for (const p of res.progress) {
          map[p.document_id] = p;
        }
        this.progressMap = map;
        if (res.progress.length === 0 || res.progress.every(p => p.step === 'completed' || p.step === 'failed')) {
          this.stopPolling();
          this.loadAll();
        }
      },
    });
  }

  private stopPolling(): void {
    this.pollSub?.unsubscribe();
    this.pollSub = null;
  }

  getProgress(docId: string): DocumentProgress | null {
    return this.progressMap[docId] || null;
  }

  statusLabel(status: string): string {
    const labels: Record<string, string> = {
      pending: 'En attente', processing: 'Traitement...', completed: 'Traité', failed: 'Échec',
    };
    return labels[status] || status;
  }

  getDocsByCategory(category: string): DocumentInfo[] {
    return this.documents.filter((d) => d.category === category);
  }

  triggerUpload(category: string): void {
    document.getElementById('upload-' + category)?.click();
  }

  onFileSelected(event: Event, category: string): void {
    const files = (event.target as HTMLInputElement).files;
    if (!files) return;
    for (let i = 0; i < files.length; i++) {
      this.api.uploadDocument(this.projectId, files[i], category).subscribe({
        next: () => {
          this.snackBar.open(`${files[i].name} chargé`, 'OK', { duration: 2000 });
          this.loadAll();
        },
        error: (err) => this.snackBar.open(err.error?.detail || 'Erreur upload', 'OK', { duration: 3000 }),
      });
    }
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
  }

  onDrop(event: DragEvent, category: string): void {
    event.preventDefault();
    const files = event.dataTransfer?.files;
    if (!files) return;
    for (let i = 0; i < files.length; i++) {
      this.api.uploadDocument(this.projectId, files[i], category).subscribe({
        next: () => { this.snackBar.open(`${files[i].name} chargé`, 'OK', { duration: 2000 }); this.loadAll(); },
      });
    }
  }

  deleteDoc(docId: string): void {
    this.api.deleteDocument(docId).subscribe({ next: () => this.loadAll() });
  }

  generateStructure(): void {
    this.generatingStructure = true;
    this.api.generateStructure(this.projectId).subscribe({
      next: (res) => {
        this.snackBar.open(`${res.chapters_created} chapitres créés`, 'OK', { duration: 3000 });
        this.generatingStructure = false;
        this.loadAll();
      },
      error: (err) => {
        this.snackBar.open(err.error?.detail || 'Erreur', 'OK', { duration: 5000 });
        this.generatingStructure = false;
      },
    });
  }

  prefillAll(): void {
    this.prefilling = true;
    this.api.prefillChapters(this.projectId).subscribe({
      next: (res) => {
        this.snackBar.open(`${res.prefilled_count} chapitres pré-remplis`, 'OK', { duration: 3000 });
        this.prefilling = false;
        this.loadAll();
      },
      error: (err) => {
        this.snackBar.open(err.error?.detail || 'Erreur', 'OK', { duration: 5000 });
        this.prefilling = false;
      },
    });
  }

  addImprovement(): void {
    if (!this.improvementContent) return;
    this.api.addImprovementAxis(this.projectId, this.improvementContent, this.improvementSource).subscribe({
      next: () => {
        this.snackBar.open('Axe ajouté', 'OK', { duration: 2000 });
        this.showImprovementForm = false;
        this.improvementContent = '';
        this.improvementSource = '';
        this.loadAll();
      },
    });
  }

  exportWord(): void {
    this.api.exportWord(this.projectId).subscribe({
      next: (blob) => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `reponse_ao_${this.project?.rfp_reference || 'export'}.docx`;
        a.click();
        window.URL.revokeObjectURL(url);
      },
      error: (err) => this.snackBar.open('Erreur export', 'OK', { duration: 3000 }),
    });
  }

  exportBackup(): void {
    this.api.exportBackup(this.projectId).subscribe({
      next: (blob) => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `backup_${this.project?.name || 'export'}.zip`;
        a.click();
        window.URL.revokeObjectURL(url);
      },
    });
  }

  formatSize(bytes: number): string {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
  }

  fileIcon(type: string): string {
    const icons: Record<string, string> = { pdf: 'picture_as_pdf', docx: 'article', xlsx: 'table_chart' };
    return icons[type] || 'insert_drive_file';
  }

  statusIcon(status: string): string {
    const icons: Record<string, string> = {
      not_started: '○', in_progress: '◐', completed: '●', needs_review: '◑', validated: '✓',
    };
    return icons[status] || '○';
  }
}
