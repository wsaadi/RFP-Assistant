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
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatDialogModule } from '@angular/material/dialog';
import { Subscription, interval, timer, forkJoin } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { ApiService } from '../../services/api.service';
import { RFPProject, Chapter, DocumentInfo, DocumentProgress, ProjectStatistics, GenerationStatus, PrefillStatus, DetectDeliverablesStatus, ResponseDocument } from '../../models/report.model';

@Component({
  selector: 'app-project-dashboard',
  standalone: true,
  imports: [
    CommonModule, FormsModule, RouterLink,
    MatCardModule, MatButtonModule, MatIconModule, MatTabsModule, MatChipsModule,
    MatProgressSpinnerModule, MatProgressBarModule, MatListModule,
    MatInputModule, MatSelectModule, MatSnackBarModule, MatTooltipModule, MatExpansionModule,
    MatCheckboxModule, MatDialogModule,
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
                <div *ngFor="let doc of docsByCategory[cat.value]" class="doc-item-wrap">
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
            <!-- Step 1: Detect deliverables -->
            <div class="chapter-actions">
              <button mat-raised-button (click)="detectDeliverables()"
                [disabled]="detectingDeliverables || detectStatus?.status === 'running'"
                style="background: #7b1fa2; color: white;">
                <mat-spinner *ngIf="detectingDeliverables || detectStatus?.status === 'running'" diameter="18"></mat-spinner>
                <mat-icon *ngIf="!detectingDeliverables && detectStatus?.status !== 'running'">find_in_page</mat-icon>
                1. Detecter les livrables attendus
              </button>
              <button mat-raised-button color="primary" (click)="generateStructure()"
                [disabled]="generatingStructure || genStatus?.status === 'running'">
                <mat-spinner *ngIf="generatingStructure || genStatus?.status === 'running'" diameter="18"></mat-spinner>
                <mat-icon *ngIf="!generatingStructure && genStatus?.status !== 'running'">auto_fix_high</mat-icon>
                2. Generer la structure
              </button>
              <button mat-raised-button color="accent" (click)="prefillAll()"
                [disabled]="prefilling || prefillStatus?.status === 'running'">
                <mat-spinner *ngIf="prefilling || prefillStatus?.status === 'running'" diameter="18"></mat-spinner>
                <mat-icon *ngIf="!prefilling && prefillStatus?.status !== 'running'">auto_awesome</mat-icon>
                3. Pre-remplir
              </button>
              <span class="spacer"></span>
              <button mat-raised-button color="warn" (click)="deleteSelectedChapters()"
                *ngIf="selectedChapters.size > 0" [disabled]="deletingChapters">
                <mat-spinner *ngIf="deletingChapters" diameter="18"></mat-spinner>
                <mat-icon *ngIf="!deletingChapters">delete</mat-icon>
                Supprimer ({{ selectedChapters.size }})
              </button>
              <button mat-button color="warn" (click)="deleteAllChapters()"
                *ngIf="chapters.length > 0" [disabled]="deletingChapters">
                <mat-icon>delete_sweep</mat-icon>
                Tout supprimer
              </button>
            </div>

            <!-- Detection progress -->
            <mat-card *ngIf="detectStatus && detectStatus.status === 'running'" class="gen-progress-card detect-progress-card">
              <div class="gen-progress-header">
                <mat-icon class="spin-icon">find_in_page</mat-icon>
                <h3>Detection des livrables attendus...</h3>
              </div>
              <mat-progress-bar mode="determinate" [value]="detectStatus.progress"></mat-progress-bar>
              <div class="gen-progress-detail">
                <span class="gen-step detect-step">{{ detectStatus.step === 'analyzing' ? 'Analyse IA' : 'Chargement' }}</span>
                <span class="gen-pct">{{ detectStatus.progress }}%</span>
              </div>
              <p class="gen-message">{{ detectStatus.message }}</p>
            </mat-card>

            <mat-card *ngIf="detectStatus && detectStatus.status === 'error'" class="gen-error-card">
              <mat-icon>error_outline</mat-icon>
              <div>
                <strong>Echec de la detection</strong>
                <p>{{ detectStatus.message }}</p>
              </div>
            </mat-card>

            <mat-card *ngIf="detectStatus && detectStatus.status === 'completed' && detectStatus.deliverables_count" class="gen-success-card detect-success-card">
              <mat-icon>check_circle</mat-icon>
              <div>
                <strong>{{ detectStatus.deliverables_count }} livrables detectes</strong>
                <span class="detect-success-hint">Selectionnez les documents a produire puis generez la structure.</span>
              </div>
            </mat-card>

            <!-- Deliverables list -->
            <mat-card *ngIf="responseDocuments.length > 0" class="deliverables-card">
              <div class="deliverables-header">
                <mat-icon>description</mat-icon>
                <h3>Documents attendus par l'AO</h3>
                <span class="deliverables-count">{{ selectedDocCount() }}/{{ responseDocuments.length }} selectionnes</span>
              </div>
              <div class="deliverables-list">
                <div *ngFor="let rd of responseDocuments; let i = index" class="deliverable-item"
                  [class.deselected]="!rd.is_selected">
                  <mat-checkbox [checked]="rd.is_selected"
                    (change)="toggleDeliverable(rd, $event.checked)">
                  </mat-checkbox>
                  <div class="deliverable-format-icon" [class]="'format-' + rd.expected_format">
                    <mat-icon>{{ formatIcon(rd.expected_format) }}</mat-icon>
                    <span class="format-label">{{ rd.expected_format | uppercase }}</span>
                  </div>
                  <div class="deliverable-info">
                    <strong>{{ rd.title }}</strong>
                    <span class="deliverable-desc">{{ rd.description }}</span>
                    <div class="deliverable-meta">
                      <span class="deliverable-source" *ngIf="rd.rfp_source">
                        <mat-icon class="meta-icon">source</mat-icon> {{ rd.rfp_source }}
                      </span>
                      <span class="deliverable-chapters" *ngIf="rd.chapter_count > 0">
                        <mat-icon class="meta-icon">menu_book</mat-icon> {{ rd.chapter_count }} chapitres
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </mat-card>

            <!-- Generation progress panel -->
            <mat-card *ngIf="genStatus && genStatus.status === 'running'" class="gen-progress-card">
              <div class="gen-progress-header">
                <mat-icon class="spin-icon">autorenew</mat-icon>
                <h3>Generation de la structure en cours...</h3>
              </div>
              <mat-progress-bar mode="determinate" [value]="genStatus.progress"></mat-progress-bar>
              <div class="gen-progress-detail">
                <span class="gen-step">{{ genStepLabel(genStatus.step) }}</span>
                <span class="gen-pct">{{ genStatus.progress }}%</span>
              </div>
              <p class="gen-message">{{ genStatus.message }}</p>
            </mat-card>

            <mat-card *ngIf="genStatus && genStatus.status === 'error'" class="gen-error-card">
              <mat-icon>error_outline</mat-icon>
              <div>
                <strong>Echec de la generation</strong>
                <p>{{ genStatus.message }}</p>
              </div>
            </mat-card>

            <mat-card *ngIf="genStatus && genStatus.status === 'completed' && genStatus.chapters_created" class="gen-success-card">
              <mat-icon>check_circle</mat-icon>
              <div>
                <strong>{{ genStatus.message }}</strong>
              </div>
            </mat-card>

            <!-- Prefill progress panel -->
            <mat-card *ngIf="prefillStatus && prefillStatus.status === 'running'" class="gen-progress-card prefill-progress-card">
              <div class="gen-progress-header">
                <mat-icon class="spin-icon">auto_awesome</mat-icon>
                <h3>Pre-remplissage depuis l'ancienne reponse...</h3>
              </div>
              <mat-progress-bar mode="determinate" [value]="prefillStatus.progress"></mat-progress-bar>
              <div class="gen-progress-detail">
                <span class="gen-step prefill-step">{{ prefillStepLabel(prefillStatus.step) }}</span>
                <span class="gen-pct">{{ prefillStatus.progress }}%</span>
              </div>
              <p class="gen-message">{{ prefillStatus.message }}</p>
            </mat-card>

            <mat-card *ngIf="prefillStatus && prefillStatus.status === 'error'" class="gen-error-card">
              <mat-icon>error_outline</mat-icon>
              <div>
                <strong>Echec du pre-remplissage</strong>
                <p>{{ prefillStatus.message }}</p>
              </div>
            </mat-card>

            <mat-card *ngIf="prefillStatus && prefillStatus.status === 'completed' && prefillStatus.prefilled_count !== undefined" class="gen-success-card">
              <mat-icon>check_circle</mat-icon>
              <div>
                <strong>{{ prefillStatus.message }}</strong>
              </div>
            </mat-card>

            <!-- Select all checkbox -->
            <div class="select-all-bar" *ngIf="chapters.length > 0">
              <mat-checkbox
                [checked]="allChaptersSelected()"
                [indeterminate]="someChaptersSelected() && !allChaptersSelected()"
                (change)="toggleSelectAll($event.checked)">
                Tout selectionner
              </mat-checkbox>
            </div>

            <div class="chapter-tree" *ngFor="let group of groupedChapters">
              <!-- Document group header -->
              <div class="doc-group-header" *ngIf="group.document">
                <mat-icon>description</mat-icon>
                <strong>{{ group.document.title }}</strong>
                <mat-chip size="small">{{ group.document.expected_format | uppercase }}</mat-chip>
                <span class="doc-group-count">{{ group.chapters.length }} chapitres</span>
              </div>

              <mat-accordion multi>
                <mat-expansion-panel *ngFor="let ch of group.chapters; let i = index">
                  <mat-expansion-panel-header>
                    <mat-panel-title>
                      <mat-checkbox class="ch-checkbox"
                        [checked]="selectedChapters.has(ch.id)"
                        (change)="toggleChapterSelection(ch, $event.checked)"
                        (click)="$event.stopPropagation()">
                      </mat-checkbox>
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
                      <mat-icon>edit</mat-icon> Editer
                    </button>
                    <button mat-icon-button color="warn" (click)="deleteSingleChapter(ch.id)" matTooltip="Supprimer ce chapitre">
                      <mat-icon>delete</mat-icon>
                    </button>
                  </div>

                  <!-- Sub-chapters -->
                  <div *ngIf="ch.children?.length" class="sub-chapters">
                    <div *ngFor="let sub of ch.children; let j = index" class="sub-chapter-item">
                      <mat-checkbox class="sub-checkbox"
                        [checked]="selectedChapters.has(sub.id)"
                        (change)="toggleSubChapterSelection(sub.id, $event.checked)"
                        (click)="$event.stopPropagation()">
                      </mat-checkbox>
                      <mat-chip [class]="'status-' + sub.status" size="small">{{ statusIcon(sub.status) }}</mat-chip>
                      <span class="ch-numbering">{{ i + 1 }}.{{ j + 1 }}</span>
                      <span>{{ sub.title }}</span>
                      <span class="sub-meta">{{ sub.content ? (sub.content.split(' ').length + ' mots') : 'Vide' }}</span>
                      <button mat-icon-button [routerLink]="['/project', projectId, 'chapter', sub.id]">
                        <mat-icon>edit</mat-icon>
                      </button>
                      <button mat-icon-button color="warn" (click)="deleteSingleChapter(sub.id)" matTooltip="Supprimer">
                        <mat-icon>delete_outline</mat-icon>
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
    .chapter-actions { display: flex; gap: 8px; margin-bottom: 16px; align-items: center; flex-wrap: wrap; }
    .spacer { flex: 1; }
    .ch-numbering { font-weight: bold; color: #2C5F8A; margin-right: 4px; }
    .ch-desc { color: #666; font-size: 13px; }
    .ch-req { font-size: 13px; background: #f5f5f5; padding: 8px; border-radius: 4px; }
    .ch-actions { display: flex; gap: 8px; margin-top: 8px; }
    .sub-chapters { margin-top: 12px; padding-left: 24px; }
    .sub-chapter-item { display: flex; align-items: center; gap: 8px; padding: 8px 0; border-bottom: 1px solid #eee; }
    .sub-meta { color: #888; font-size: 12px; margin-left: auto; }
    .select-all-bar { padding: 8px 0; margin-bottom: 4px; }
    .ch-checkbox { margin-right: 8px; }
    .sub-checkbox { margin-right: 4px; }
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
    .gen-progress-card { margin: 16px 0; padding: 20px; border-left: 4px solid #1976d2; }
    .gen-progress-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
    .gen-progress-header h3 { margin: 0; color: #1976d2; font-size: 15px; }
    .gen-progress-detail { display: flex; justify-content: space-between; margin-top: 8px; }
    .gen-step { font-size: 13px; color: #1976d2; font-weight: 500; }
    .gen-pct { font-size: 13px; color: #888; }
    .gen-message { font-size: 13px; color: #555; margin: 8px 0 0 0; }
    .gen-error-card { margin: 16px 0; padding: 20px; border-left: 4px solid #d32f2f; display: flex; align-items: flex-start; gap: 12px; }
    .gen-error-card mat-icon { color: #d32f2f; }
    .gen-error-card p { margin: 4px 0 0 0; color: #666; font-size: 13px; }
    .gen-success-card { margin: 16px 0; padding: 20px; border-left: 4px solid #4caf50; display: flex; align-items: center; gap: 12px; }
    .gen-success-card mat-icon { color: #4caf50; font-size: 28px; width: 28px; height: 28px; }
    .detect-progress-card { border-left-color: #7b1fa2; }
    .detect-progress-card .gen-progress-header h3 { color: #7b1fa2; }
    .detect-progress-card .spin-icon { color: #7b1fa2; }
    .detect-step { color: #7b1fa2 !important; }
    .deliverables-card { margin: 16px 0; padding: 20px; border-left: 4px solid #7b1fa2; }
    .deliverables-header { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
    .deliverables-header mat-icon { color: #7b1fa2; }
    .deliverables-header h3 { margin: 0; color: #1B3A5C; font-size: 15px; }
    .deliverables-count { margin-left: auto; font-size: 13px; color: #7b1fa2; font-weight: 500; }
    .deliverables-list { display: flex; flex-direction: column; gap: 10px; }
    .deliverable-item { display: flex; align-items: flex-start; gap: 12px; padding: 12px; border-radius: 8px; background: #fafafa; border: 1px solid #eee; transition: opacity 0.2s, border-color 0.2s; }
    .deliverable-item:hover { border-color: #7b1fa2; }
    .deliverable-item.deselected { opacity: 0.45; }
    .deliverable-format-icon { display: flex; flex-direction: column; align-items: center; gap: 2px; min-width: 48px; padding: 6px 0; border-radius: 6px; }
    .deliverable-format-icon mat-icon { font-size: 28px; width: 28px; height: 28px; }
    .format-label { font-size: 10px; font-weight: 600; text-transform: uppercase; }
    .format-docx { background: #e3f2fd; color: #1565c0; }
    .format-docx mat-icon { color: #1565c0; }
    .format-xlsx { background: #e8f5e9; color: #2e7d32; }
    .format-xlsx mat-icon { color: #2e7d32; }
    .format-pdf { background: #fce4ec; color: #c62828; }
    .format-pdf mat-icon { color: #c62828; }
    .format-other { background: #f3e5f5; color: #6a1b9a; }
    .format-other mat-icon { color: #6a1b9a; }
    .deliverable-info { flex: 1; }
    .deliverable-info strong { display: block; color: #1B3A5C; font-size: 14px; }
    .deliverable-desc { display: block; font-size: 13px; color: #666; margin: 4px 0; line-height: 1.4; }
    .deliverable-meta { display: flex; gap: 12px; align-items: center; margin-top: 6px; }
    .meta-icon { font-size: 14px; width: 14px; height: 14px; vertical-align: middle; margin-right: 2px; }
    .deliverable-source { font-size: 12px; color: #888; display: flex; align-items: center; }
    .deliverable-chapters { font-size: 12px; color: #2C5F8A; font-weight: 500; display: flex; align-items: center; }
    .detect-success-card { border-left-color: #7b1fa2; }
    .detect-success-card mat-icon { color: #7b1fa2; }
    .detect-success-hint { display: block; font-size: 13px; color: #666; margin-top: 2px; }
    .doc-group-header { display: flex; align-items: center; gap: 8px; padding: 12px 0 6px 0; border-bottom: 2px solid #7b1fa2; margin-bottom: 8px; margin-top: 16px; }
    .doc-group-header mat-icon { color: #7b1fa2; }
    .doc-group-header strong { color: #1B3A5C; font-size: 15px; }
    .doc-group-count { font-size: 12px; color: #888; margin-left: auto; }
    .prefill-progress-card { border-left-color: #7b1fa2; }
    .prefill-progress-card .gen-progress-header h3 { color: #7b1fa2; }
    .prefill-step { color: #7b1fa2 !important; }
    .prefill-progress-card .spin-icon { color: #7b1fa2; }
    @keyframes spin { 100% { transform: rotate(360deg); } }
    .spin-icon { animation: spin 1.5s linear infinite; color: #1976d2; }
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
  genStatus: GenerationStatus | null = null;
  private genPollSub: Subscription | null = null;
  prefilling = false;
  prefillStatus: PrefillStatus | null = null;
  private prefillPollSub: Subscription | null = null;
  responseDocuments: ResponseDocument[] = [];
  detectingDeliverables = false;
  detectStatus: DetectDeliverablesStatus | null = null;
  private detectPollSub: Subscription | null = null;
  selectedChapters = new Set<string>();
  deletingChapters = false;
  showImprovementForm = false;
  improvementContent = '';
  improvementSource = '';
  private pollSub: Subscription | null = null;

  // Cached computed data to avoid method calls in template (prevents change detection loops)
  groupedChapters: { document: ResponseDocument | null; chapters: Chapter[] }[] = [];
  docsByCategory: Record<string, DocumentInfo[]> = {};

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
    // Resume generation polling if a task was already running (e.g. page refresh)
    this.api.getGenerationStatus(this.projectId).subscribe({
      next: (status) => {
        if (status.status === 'running') {
          this.genStatus = status;
          this.startGenPolling();
        }
      },
    });
    // Resume prefill polling if already running
    this.api.getPrefillStatus(this.projectId).subscribe({
      next: (status) => {
        if (status.status === 'running') {
          this.prefillStatus = status;
          this.prefilling = true;
          this.startPrefillPolling();
        }
      },
    });
    // Resume detect polling if already running
    this.api.getDetectDeliverablesStatus(this.projectId).subscribe({
      next: (status) => {
        if (status.status === 'running') {
          this.detectStatus = status;
          this.detectingDeliverables = true;
          this.startDetectPolling();
        }
      },
    });
  }

  ngOnDestroy(): void {
    this.stopPolling();
    this.stopGenPolling();
    this.stopPrefillPolling();
    this.stopDetectPolling();
  }

  loadAll(): void {
    this.loading = true;
    this.api.getProject(this.projectId).subscribe({
      next: (p) => { this.project = p; this.loading = false; },
      error: () => { this.loading = false; },
    });
    this.api.getChapters(this.projectId).subscribe({
      next: (ch) => { this.chapters = ch; this._refreshGroupedChapters(); },
      error: () => {},
    });
    this.api.getDocuments(this.projectId).subscribe({
      next: (d) => {
        this.documents = d;
        this._refreshDocsByCategory();
        const hasProcessing = d.some(doc => doc.processing_status === 'pending' || doc.processing_status === 'processing');
        if (hasProcessing) {
          this.startPolling();
        } else {
          this.stopPolling();
          this.progressMap = {};
        }
      },
      error: () => {},
    });
    this.api.getStatistics(this.projectId).subscribe({
      next: (s) => this.stats = s,
      error: () => {},
    });
    this.loadResponseDocuments();
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
        if (res.progress.length === 0) {
          // No active progress tracked server-side (e.g. after a restart).
          // Refresh documents only to avoid an infinite loadAll→poll loop.
          this.stopPolling();
          this.progressMap = {};
          this.api.getDocuments(this.projectId).subscribe({
            next: (d) => { this.documents = d; this._refreshDocsByCategory(); },
          });
        } else if (res.progress.every(p => p.step === 'completed' || p.step === 'failed')) {
          this.stopPolling();
          this.loadAll();
        }
      },
      error: () => { this.stopPolling(); },
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

  private _refreshDocsByCategory(): void {
    const map: Record<string, DocumentInfo[]> = {};
    for (const cat of this.categories) {
      map[cat.value] = this.documents.filter((d) => d.category === cat.value);
    }
    this.docsByCategory = map;
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
    // Show progress card immediately instead of null
    this.genStatus = {
      status: 'running',
      step: 'starting',
      progress: 0,
      message: 'Lancement de la generation...',
    };
    this.api.generateStructure(this.projectId).subscribe({
      next: () => {
        this.generatingStructure = false;
        this.startGenPolling();
      },
      error: (err) => {
        this.snackBar.open(err.error?.detail || 'Erreur', 'OK', { duration: 5000 });
        this.generatingStructure = false;
        this.genStatus = null;
      },
    });
  }

  private startGenPolling(): void {
    this.stopGenPolling();
    // timer(0, 2000) emits immediately at t=0, then every 2s (unlike interval which waits)
    this.genPollSub = timer(0, 2000).pipe(
      switchMap(() => this.api.getGenerationStatus(this.projectId))
    ).subscribe({
      next: (status) => {
        this.genStatus = status;
        if (status.status === 'completed') {
          this.stopGenPolling();
          this.snackBar.open(status.message || 'Structure generee', 'OK', { duration: 5000 });
          this.loadAll();
        } else if (status.status === 'error') {
          this.stopGenPolling();
        }
      },
    });
  }

  private stopGenPolling(): void {
    this.genPollSub?.unsubscribe();
    this.genPollSub = null;
  }

  genStepLabel(step: string): string {
    const labels: Record<string, string> = {
      starting: 'Demarrage',
      loading: 'Chargement des documents',
      anonymizing: 'Anonymisation',
      gap_analysis: 'Analyse des ecarts',
      generating: 'Generation IA',
      saving: 'Enregistrement',
      done: 'Termine',
    };
    return labels[step] || step;
  }

  prefillAll(): void {
    this.prefilling = true;
    this.prefillStatus = {
      status: 'running',
      step: 'starting',
      progress: 0,
      message: 'Lancement du pre-remplissage...',
    };
    this.api.prefillChapters(this.projectId).subscribe({
      next: () => {
        this.startPrefillPolling();
      },
      error: (err) => {
        this.snackBar.open(err.error?.detail || 'Erreur', 'OK', { duration: 5000 });
        this.prefilling = false;
        this.prefillStatus = null;
      },
    });
  }

  private startPrefillPolling(): void {
    this.stopPrefillPolling();
    this.prefillPollSub = timer(0, 2000).pipe(
      switchMap(() => this.api.getPrefillStatus(this.projectId))
    ).subscribe({
      next: (status) => {
        this.prefillStatus = status;
        if (status.status === 'completed') {
          this.stopPrefillPolling();
          this.prefilling = false;
          this.snackBar.open(status.message || 'Pre-remplissage termine', 'OK', { duration: 5000 });
          this.loadAll();
        } else if (status.status === 'error') {
          this.stopPrefillPolling();
          this.prefilling = false;
        }
      },
    });
  }

  private stopPrefillPolling(): void {
    this.prefillPollSub?.unsubscribe();
    this.prefillPollSub = null;
  }

  prefillStepLabel(step: string): string {
    const labels: Record<string, string> = {
      starting: 'Demarrage',
      loading: 'Chargement des chapitres',
      prefilling: 'Pre-remplissage IA',
      saving: 'Enregistrement',
      done: 'Termine',
    };
    return labels[step] || step;
  }

  // ── Chapter selection & deletion ──

  toggleChapterSelection(ch: Chapter, checked: boolean): void {
    if (checked) {
      this.selectedChapters.add(ch.id);
      // Also select all children
      for (const sub of (ch.children || [])) {
        this.selectedChapters.add(sub.id);
      }
    } else {
      this.selectedChapters.delete(ch.id);
      for (const sub of (ch.children || [])) {
        this.selectedChapters.delete(sub.id);
      }
    }
  }

  toggleSubChapterSelection(subId: string, checked: boolean): void {
    if (checked) {
      this.selectedChapters.add(subId);
    } else {
      this.selectedChapters.delete(subId);
    }
  }

  allChaptersSelected(): boolean {
    if (this.chapters.length === 0) return false;
    return this.getAllChapterIds().every(id => this.selectedChapters.has(id));
  }

  someChaptersSelected(): boolean {
    return this.selectedChapters.size > 0;
  }

  toggleSelectAll(checked: boolean): void {
    if (checked) {
      for (const id of this.getAllChapterIds()) {
        this.selectedChapters.add(id);
      }
    } else {
      this.selectedChapters.clear();
    }
  }

  private getAllChapterIds(): string[] {
    const ids: string[] = [];
    for (const ch of this.chapters) {
      ids.push(ch.id);
      for (const sub of (ch.children || [])) {
        ids.push(sub.id);
      }
    }
    return ids;
  }

  deleteSingleChapter(chapterId: string): void {
    if (!confirm('Supprimer ce chapitre et ses sous-chapitres ?')) return;
    this.deletingChapters = true;
    this.api.deleteChapter(chapterId).subscribe({
      next: () => {
        this.selectedChapters.delete(chapterId);
        this.snackBar.open('Chapitre supprime', 'OK', { duration: 2000 });
        this.deletingChapters = false;
        this.loadAll();
      },
      error: () => {
        this.snackBar.open('Erreur lors de la suppression', 'OK', { duration: 3000 });
        this.deletingChapters = false;
      },
    });
  }

  deleteSelectedChapters(): void {
    const count = this.selectedChapters.size;
    if (!confirm(`Supprimer ${count} chapitre(s) selectionne(s) et leurs sous-chapitres ?`)) return;
    this.deletingChapters = true;
    // Only send root-level IDs (parents). If a parent is selected, its children
    // are cascade-deleted, so we filter out children whose parent is also selected.
    const rootIds = Array.from(this.selectedChapters).filter(id => {
      // Check if this chapter's parent is also selected
      for (const ch of this.chapters) {
        if (ch.id === id) return true; // top-level chapter
        for (const sub of (ch.children || [])) {
          if (sub.id === id && !this.selectedChapters.has(ch.id)) return true;
        }
      }
      return false;
    });
    this.api.bulkDeleteChapters(rootIds).subscribe({
      next: (res) => {
        this.selectedChapters.clear();
        this.snackBar.open(`${res.deleted} chapitre(s) supprime(s)`, 'OK', { duration: 3000 });
        this.deletingChapters = false;
        this.loadAll();
      },
      error: () => {
        this.snackBar.open('Erreur lors de la suppression', 'OK', { duration: 3000 });
        this.deletingChapters = false;
      },
    });
  }

  deleteAllChapters(): void {
    const total = this.getAllChapterIds().length;
    if (!confirm(`Supprimer TOUS les ${total} chapitres ? Cette action est irreversible.`)) return;
    this.deletingChapters = true;
    // Only send root-level chapter IDs — children are cascade-deleted
    const rootIds = this.chapters.map(ch => ch.id);
    this.api.bulkDeleteChapters(rootIds).subscribe({
      next: (res) => {
        this.selectedChapters.clear();
        this.snackBar.open(`${res.deleted} chapitre(s) supprime(s)`, 'OK', { duration: 3000 });
        this.deletingChapters = false;
        this.loadAll();
      },
      error: () => {
        this.snackBar.open('Erreur lors de la suppression', 'OK', { duration: 3000 });
        this.deletingChapters = false;
      },
    });
  }

  // ── Deliverables detection ──

  loadResponseDocuments(): void {
    this.api.getResponseDocuments(this.projectId).subscribe({
      next: (docs) => { this.responseDocuments = docs; this._refreshGroupedChapters(); },
      error: () => {},
    });
  }

  detectDeliverables(): void {
    this.detectingDeliverables = true;
    this.detectStatus = {
      status: 'running',
      step: 'starting',
      progress: 0,
      message: 'Lancement de la detection...',
    };
    this.api.detectDeliverables(this.projectId).subscribe({
      next: () => {
        this.detectingDeliverables = false;
        this.startDetectPolling();
      },
      error: (err) => {
        this.snackBar.open(err.error?.detail || 'Erreur', 'OK', { duration: 5000 });
        this.detectingDeliverables = false;
        this.detectStatus = null;
      },
    });
  }

  private startDetectPolling(): void {
    this.stopDetectPolling();
    this.detectPollSub = timer(0, 2000).pipe(
      switchMap(() => this.api.getDetectDeliverablesStatus(this.projectId))
    ).subscribe({
      next: (status) => {
        this.detectStatus = status;
        if (status.status === 'completed') {
          this.stopDetectPolling();
          this.detectingDeliverables = false;
          this.snackBar.open(status.message || 'Livrables detectes', 'OK', { duration: 5000 });
          this.loadResponseDocuments();
        } else if (status.status === 'error') {
          this.stopDetectPolling();
          this.detectingDeliverables = false;
        }
      },
    });
  }

  private stopDetectPolling(): void {
    this.detectPollSub?.unsubscribe();
    this.detectPollSub = null;
  }

  toggleDeliverable(rd: ResponseDocument, checked: boolean): void {
    rd.is_selected = checked;
    this.api.updateResponseDocument(this.projectId, rd.id, { is_selected: checked }).subscribe({
      error: () => {
        rd.is_selected = !checked; // revert on error
        this.snackBar.open('Erreur mise a jour', 'OK', { duration: 3000 });
      },
    });
  }

  selectedDocCount(): number {
    return this.responseDocuments.filter(rd => rd.is_selected).length;
  }

  private _refreshGroupedChapters(): void {
    this.groupedChapters = this.getGroupedChapters();
  }

  getGroupedChapters(): { document: ResponseDocument | null; chapters: Chapter[] }[] {
    if (this.responseDocuments.length === 0) {
      // No deliverables detected — show all chapters in a single group
      return [{ document: null, chapters: this.chapters }];
    }

    const groups: { document: ResponseDocument | null; chapters: Chapter[] }[] = [];
    const docMap = new Map<string, ResponseDocument>();
    for (const rd of this.responseDocuments) {
      docMap.set(rd.id, rd);
    }

    // Group chapters by response_document_id
    const grouped = new Map<string | null, Chapter[]>();
    for (const ch of this.chapters) {
      const key = ch.response_document_id || null;
      if (!grouped.has(key)) {
        grouped.set(key, []);
      }
      grouped.get(key)!.push(ch);
    }

    // Build ordered groups: first by document order, then ungrouped at end
    for (const rd of this.responseDocuments) {
      const chs = grouped.get(rd.id);
      if (chs && chs.length > 0) {
        groups.push({ document: rd, chapters: chs });
      }
    }

    // Add chapters not linked to any document
    const ungrouped = grouped.get(null);
    if (ungrouped && ungrouped.length > 0) {
      groups.push({ document: null, chapters: ungrouped });
    }

    return groups;
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
    const icons: Record<string, string> = { pdf: 'picture_as_pdf', docx: 'article', doc: 'article', xlsx: 'table_chart' };
    return icons[type] || 'insert_drive_file';
  }

  statusIcon(status: string): string {
    const icons: Record<string, string> = {
      not_started: '○', in_progress: '◐', completed: '●', needs_review: '◑', validated: '✓',
    };
    return icons[status] || '○';
  }

  formatIcon(format: string): string {
    const icons: Record<string, string> = {
      docx: 'article',
      xlsx: 'table_chart',
      pdf: 'picture_as_pdf',
      other: 'insert_drive_file',
    };
    return icons[format] || 'insert_drive_file';
  }
}
