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
import { renderMarkdown } from '../../services/markdown.service';
import { RFPProject, Chapter, DocumentInfo, DocumentProgress, ProjectStatistics, GenerationStatus, PrefillStatus, DetectDeliverablesStatus, FillDeliverablesStatus, ResponseDocument } from '../../models/report.model';

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

        <!-- Livrables tab (NEW - separated from Structure) -->
        <mat-tab label="Livrables">
          <div class="tab-content">
            <div class="chapter-actions">
              <button mat-raised-button (click)="detectDeliverables()"
                [disabled]="detectingDeliverables || detectStatus?.status === 'running'"
                style="background: #7b1fa2; color: white;">
                <mat-spinner *ngIf="detectingDeliverables || detectStatus?.status === 'running'" diameter="18"></mat-spinner>
                <mat-icon *ngIf="!detectingDeliverables && detectStatus?.status !== 'running'">find_in_page</mat-icon>
                Detecter les livrables attendus
              </button>
              <button mat-raised-button (click)="fillDeliverables()"
                *ngIf="hasCompletionDocs()"
                [disabled]="fillingDeliverables || fillStatus?.status === 'running'"
                style="background: #2e7d32; color: white;">
                <mat-spinner *ngIf="fillingDeliverables || fillStatus?.status === 'running'" diameter="18"></mat-spinner>
                <mat-icon *ngIf="!fillingDeliverables && fillStatus?.status !== 'running'">auto_fix_high</mat-icon>
                Auto-completer les Excel/PDF
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
                <span class="detect-success-hint">Selectionnez les documents a produire puis passez a l'onglet Structure pour generer les chapitres.</span>
              </div>
            </mat-card>

            <!-- Fill progress -->
            <mat-card *ngIf="fillStatus && fillStatus.status === 'running'" class="gen-progress-card fill-progress-card">
              <div class="gen-progress-header">
                <mat-icon class="spin-icon">auto_fix_high</mat-icon>
                <h3>Auto-remplissage des documents a completer...</h3>
              </div>
              <mat-progress-bar mode="determinate" [value]="fillStatus.progress"></mat-progress-bar>
              <div class="gen-progress-detail">
                <span class="gen-step fill-step">{{ fillStatus.step === 'filling' ? 'Remplissage IA' : 'Chargement' }}</span>
                <span class="gen-pct">{{ fillStatus.progress }}%</span>
              </div>
              <p class="gen-message">{{ fillStatus.message }}</p>
            </mat-card>

            <mat-card *ngIf="fillStatus && fillStatus.status === 'error'" class="gen-error-card">
              <mat-icon>error_outline</mat-icon>
              <div>
                <strong>Echec de l'auto-remplissage</strong>
                <p>{{ fillStatus.message }}</p>
              </div>
            </mat-card>

            <mat-card *ngIf="fillStatus && fillStatus.status === 'completed'" class="gen-success-card fill-success-card">
              <mat-icon>check_circle</mat-icon>
              <div>
                <strong>{{ fillStatus.message }}</strong>
              </div>
            </mat-card>

            <!-- Deliverables list - Redaction type -->
            <div *ngIf="redactionDocs.length > 0" class="deliverables-section">
              <h3 class="section-title"><mat-icon>edit_document</mat-icon> Documents a rediger ({{ redactionDocs.length }})</h3>
              <p class="section-subtitle">Ces documents necessitent la redaction de chapitres. Utilisez l'onglet Structure pour generer et rediger le contenu.</p>
              <div class="deliverables-list">
                <div *ngFor="let rd of redactionDocs" class="deliverable-item"
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
                      <mat-chip class="type-redaction" size="small">Redaction</mat-chip>
                      <button mat-button class="type-toggle-btn" (click)="toggleContentType(rd, 'completion')"
                        matTooltip="Basculer en document a completer (Excel/PDF)">
                        <mat-icon>swap_horiz</mat-icon> Changer en "A completer"
                      </button>
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
            </div>

            <!-- Deliverables list - Completion type -->
            <div *ngIf="completionDocs.length > 0" class="deliverables-section">
              <h3 class="section-title"><mat-icon>assignment</mat-icon> Documents a completer ({{ completionDocs.length }})</h3>
              <p class="section-subtitle">Ces documents (Excel, PDF, formulaires) sont fournis par l'acheteur et doivent etre completes. L'IA peut pre-remplir le contenu.</p>
              <div class="deliverables-list">
                <div *ngFor="let rd of completionDocs" class="deliverable-item completion-item"
                  [class.deselected]="!rd.is_selected">
                  <mat-checkbox [checked]="rd.is_selected"
                    (change)="toggleDeliverable(rd, $event.checked)">
                  </mat-checkbox>
                  <div class="deliverable-format-icon" [class]="'format-' + rd.expected_format">
                    <mat-icon>{{ formatIcon(rd.expected_format) }}</mat-icon>
                    <span class="format-label">{{ rd.expected_format | uppercase }}</span>
                  </div>
                  <div class="deliverable-info" style="flex: 1;">
                    <strong>{{ rd.title }}</strong>
                    <span class="deliverable-desc">{{ rd.description }}</span>
                    <div class="deliverable-meta">
                      <mat-chip class="type-completion" size="small">A completer</mat-chip>
                      <button mat-button class="type-toggle-btn" (click)="toggleContentType(rd, 'redaction')"
                        matTooltip="Basculer en document a rediger (chapitres)">
                        <mat-icon>swap_horiz</mat-icon> Changer en "Redaction"
                      </button>
                      <mat-chip *ngIf="rd.fill_status === 'completed'" class="fill-done" size="small">Contenu genere</mat-chip>
                      <mat-chip *ngIf="rd.fill_status === 'generating'" class="fill-running" size="small">En cours...</mat-chip>
                      <button mat-button class="reset-fill-btn"
                        *ngIf="rd.fill_status === 'completed' || rd.fill_content"
                        (click)="resetFillContent(rd)"
                        matTooltip="Supprimer le contenu genere pour pouvoir le regenerer">
                        <mat-icon>delete_outline</mat-icon> Supprimer le contenu
                      </button>
                      <button mat-raised-button class="fill-excel-btn"
                        *ngIf="rd.expected_format === 'xlsx' || rd.expected_format === 'xls'"
                        [disabled]="rd._fillingExcel"
                        (click)="fillAndDownloadExcel(rd)"
                        matTooltip="Remplir l'Excel avec les tarifs de l'ancienne reponse et telecharger">
                        <mat-spinner *ngIf="rd._fillingExcel" diameter="16"></mat-spinner>
                        <mat-icon *ngIf="!rd._fillingExcel">download</mat-icon>
                        {{ rd._fillingExcel ? 'Generation en cours...' : 'Telecharger Excel rempli' }}
                      </button>
                      <span class="deliverable-source" *ngIf="rd.rfp_source">
                        <mat-icon class="meta-icon">source</mat-icon> {{ rd.rfp_source }}
                      </span>
                    </div>
                    <!-- Fill content preview -->
                    <mat-expansion-panel *ngIf="rd.fill_content" class="fill-content-panel">
                      <mat-expansion-panel-header>
                        <mat-panel-title>
                          <mat-icon>visibility</mat-icon> Voir le contenu de remplissage
                        </mat-panel-title>
                      </mat-expansion-panel-header>
                      <div class="fill-content-preview" [innerHTML]="renderMarkdown(rd.fill_content)"></div>
                    </mat-expansion-panel>
                  </div>
                </div>
              </div>
            </div>

            <!-- Empty state -->
            <div *ngIf="responseDocuments.length === 0" class="empty-state">
              <mat-icon>find_in_page</mat-icon>
              <p>Aucun livrable detecte. Cliquez sur "Detecter les livrables attendus" pour analyser l'AO.</p>
            </div>
          </div>
        </mat-tab>

        <!-- Structure tab (cleaned up - only chapters) -->
        <mat-tab label="Structure">
          <div class="tab-content">
            <div class="chapter-actions">
              <button mat-raised-button color="primary" (click)="generateStructure()"
                [disabled]="generatingStructure || genStatus?.status === 'running' || (responseDocuments.length > 0 && selectedRedactionCount() === 0)">
                <mat-spinner *ngIf="generatingStructure || genStatus?.status === 'running'" diameter="18"></mat-spinner>
                <mat-icon *ngIf="!generatingStructure && genStatus?.status !== 'running'">auto_fix_high</mat-icon>
                {{ redactionDocs.length > 0 ? 'Generer la structure (' + selectedRedactionCount() + '/' + redactionDocs.length + ')' : 'Generer la structure' }}
              </button>
              <button mat-raised-button color="accent" (click)="prefillAll()"
                [disabled]="prefilling || prefillStatus?.status === 'running'">
                <mat-spinner *ngIf="prefilling || prefillStatus?.status === 'running'" diameter="18"></mat-spinner>
                <mat-icon *ngIf="!prefilling && prefillStatus?.status !== 'running'">auto_awesome</mat-icon>
                {{ selectedChapters.size > 0 ? 'Pre-remplir (' + selectedChapters.size + ')' : 'Pre-remplir tout' }}
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

            <!-- Document selector for structure generation -->
            <mat-card *ngIf="redactionDocs.length > 0" class="doc-selector-card">
              <div class="doc-selector-header">
                <mat-icon>checklist</mat-icon>
                <div>
                  <strong>Documents a rediger ({{ selectedRedactionCount() }}/{{ redactionDocs.length }} selectionnes)</strong>
                  <p class="doc-selector-hint">Cochez les documents pour lesquels generer la structure de chapitres.</p>
                </div>
                <span class="spacer"></span>
                <button mat-button (click)="selectAllRedaction(true)" *ngIf="selectedRedactionCount() < redactionDocs.length">
                  <mat-icon>check_box</mat-icon> Tout selectionner
                </button>
                <button mat-button (click)="selectAllRedaction(false)" *ngIf="selectedRedactionCount() > 0">
                  <mat-icon>check_box_outline_blank</mat-icon> Tout deselectionner
                </button>
              </div>
              <div class="doc-selector-list">
                <div *ngFor="let rd of redactionDocs" class="doc-selector-item"
                  [class.deselected]="!rd.is_selected">
                  <mat-checkbox [checked]="rd.is_selected"
                    (change)="toggleDeliverable(rd, $event.checked)">
                  </mat-checkbox>
                  <div class="doc-selector-format" [class]="'format-' + rd.expected_format">
                    <mat-icon>{{ formatIcon(rd.expected_format) }}</mat-icon>
                  </div>
                  <div class="doc-selector-info">
                    <strong>{{ rd.title }}</strong>
                    <span class="doc-selector-desc">{{ rd.description }}</span>
                  </div>
                  <mat-chip *ngIf="rd.chapter_count > 0" size="small" class="doc-selector-chapters">
                    {{ rd.chapter_count }} chapitres
                  </mat-chip>
                </div>
              </div>
            </mat-card>

            <!-- Hint if no deliverables detected yet -->
            <mat-card *ngIf="responseDocuments.length === 0 && chapters.length === 0" class="hint-card">
              <mat-icon>info</mat-icon>
              <div>
                <strong>Conseil</strong>
                <p>Detectez d'abord les livrables dans l'onglet "Livrables" pour une generation de structure adaptee a chaque document.</p>
              </div>
            </mat-card>

            <!-- Warning if all deliverables are completion-type -->
            <mat-card *ngIf="responseDocuments.length > 0 && redactionDocs.length === 0 && chapters.length === 0" class="hint-card">
              <mat-icon>check_circle</mat-icon>
              <div>
                <strong>Aucun document a rediger</strong>
                <p>Tous les livrables detectes ({{ completionDocs.length }}) sont des documents a completer (Excel, PDF, formulaires).
                Ils sont a traiter dans l'onglet "Livrables". Aucune structure de chapitres n'est necessaire.</p>
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

            <!-- Info card when generation completed but no chapters created (e.g. only completion docs selected) -->
            <mat-card *ngIf="genStatus && genStatus.status === 'completed' && !genStatus.chapters_created" class="gen-info-card">
              <mat-icon>info</mat-icon>
              <div>
                <strong>{{ genStatus.message || 'Aucun chapitre genere' }}</strong>
                <p *ngIf="genStatus.completion_docs_count">
                  Les documents a completer (Excel, PDF, formulaires) ne generent pas de chapitres.
                  Utilisez le bouton <strong>"Auto-completer les Excel/PDF"</strong> dans l'onglet <strong>Livrables</strong> pour generer leur contenu.
                </p>
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
                      {{ chapterTypeLabel(ch.chapter_type) }} - {{ ch.content ? (ch.content.split(' ').length + ' mots') : 'Vide' }}
                    </mat-panel-description>
                  </mat-expansion-panel-header>

                  <p class="ch-desc" *ngIf="ch.description">{{ ch.description }}</p>
                  <p class="ch-req" *ngIf="ch.rfp_requirement"><strong>Exigence AO:</strong> {{ ch.rfp_requirement }}</p>

                  <div class="ch-actions">
                    <button mat-raised-button color="primary" [routerLink]="['/project', projectId, 'chapter', ch.id]">
                      <mat-icon>edit</mat-icon> Editer
                    </button>
                    <button mat-raised-button color="accent" (click)="aiGenerate(ch.id)"
                      [disabled]="aiProcessing[ch.id]"
                      matTooltip="Generer le contenu a partir de l'AO et de l'ancienne reponse">
                      <mat-icon>auto_awesome</mat-icon>
                      {{ ch.content ? 'Regenerer' : 'Remplir avec IA' }}
                    </button>
                    <button mat-icon-button (click)="toggleAiPrompt(ch.id)" matTooltip="Instruction personnalisee a l'IA">
                      <mat-icon>psychology</mat-icon>
                    </button>
                    <button mat-icon-button color="warn" (click)="deleteSingleChapter(ch.id)" matTooltip="Supprimer ce chapitre">
                      <mat-icon>delete</mat-icon>
                    </button>
                  </div>

                  <!-- AI progress bar -->
                  <div *ngIf="aiProcessing[ch.id]" class="ai-progress-section">
                    <div class="ai-progress-header">
                      <mat-spinner diameter="16"></mat-spinner>
                      <span>Generation IA en cours...</span>
                    </div>
                    <mat-progress-bar mode="indeterminate" color="accent"></mat-progress-bar>
                  </div>

                  <!-- AI custom prompt -->
                  <div *ngIf="aiPromptVisible[ch.id]" class="ai-prompt-section">
                    <mat-form-field appearance="outline" class="full-width">
                      <mat-label>Instruction pour l'IA</mat-label>
                      <textarea matInput [(ngModel)]="aiPromptText[ch.id]" rows="2"
                        placeholder="Ex: Ajoute plus de details sur la methodologie, insiste sur notre experience en cybersecurite..."></textarea>
                    </mat-form-field>
                    <div class="ai-prompt-actions">
                      <button mat-raised-button color="accent" (click)="aiCustomPrompt(ch.id)"
                        [disabled]="aiProcessing[ch.id] || !aiPromptText[ch.id]">
                        <mat-spinner *ngIf="aiProcessing[ch.id]" diameter="16"></mat-spinner>
                        <mat-icon *ngIf="!aiProcessing[ch.id]">send</mat-icon>
                        Envoyer
                      </button>
                      <button mat-button (click)="toggleAiPrompt(ch.id)">Annuler</button>
                    </div>
                  </div>

                  <!-- Content preview -->
                  <div *ngIf="ch.content" class="ch-content-preview" [innerHTML]="renderMarkdown(ch.content)"></div>

                  <!-- Sub-chapters -->
                  <div *ngIf="ch.children?.length" class="sub-chapters">
                    <div *ngFor="let sub of ch.children; let j = index" class="sub-chapter-block">
                      <div class="sub-chapter-item">
                        <mat-checkbox class="sub-checkbox"
                          [checked]="selectedChapters.has(sub.id)"
                          (change)="toggleSubChapterSelection(sub.id, $event.checked)"
                          (click)="$event.stopPropagation()">
                        </mat-checkbox>
                        <mat-chip [class]="'status-' + sub.status" size="small">{{ statusIcon(sub.status) }}</mat-chip>
                        <span class="ch-numbering">{{ i + 1 }}.{{ j + 1 }}</span>
                        <span>{{ sub.title }}</span>
                        <span class="sub-meta">{{ sub.content ? (sub.content.split(' ').length + ' mots') : 'Vide' }}</span>
                        <button mat-icon-button [routerLink]="['/project', projectId, 'chapter', sub.id]"
                          matTooltip="Editer">
                          <mat-icon>edit</mat-icon>
                        </button>
                        <button mat-icon-button color="accent" (click)="aiGenerate(sub.id)"
                          [disabled]="aiProcessing[sub.id]"
                          [matTooltip]="sub.content ? 'Regenerer avec IA' : 'Remplir avec IA'">
                          <mat-spinner *ngIf="aiProcessing[sub.id]" diameter="16"></mat-spinner>
                          <mat-icon *ngIf="!aiProcessing[sub.id]">auto_awesome</mat-icon>
                        </button>
                        <button mat-icon-button (click)="toggleAiPrompt(sub.id)" matTooltip="Instruction personnalisee">
                          <mat-icon>psychology</mat-icon>
                        </button>
                        <button mat-icon-button color="warn" (click)="deleteSingleChapter(sub.id)" matTooltip="Supprimer">
                          <mat-icon>delete_outline</mat-icon>
                        </button>
                      </div>
                      <!-- AI progress bar for sub-chapter -->
                      <div *ngIf="aiProcessing[sub.id]" class="ai-progress-section">
                        <div class="ai-progress-header">
                          <mat-spinner diameter="16"></mat-spinner>
                          <span>Generation IA en cours...</span>
                        </div>
                        <mat-progress-bar mode="indeterminate" color="accent"></mat-progress-bar>
                      </div>
                      <!-- AI custom prompt for sub-chapter -->
                      <div *ngIf="aiPromptVisible[sub.id]" class="ai-prompt-section sub-ai-prompt">
                        <mat-form-field appearance="outline" class="full-width">
                          <mat-label>Instruction pour l'IA</mat-label>
                          <textarea matInput [(ngModel)]="aiPromptText[sub.id]" rows="2"
                            placeholder="Ex: Detaille la methodologie, ajoute des references techniques..."></textarea>
                        </mat-form-field>
                        <div class="ai-prompt-actions">
                          <button mat-raised-button color="accent" (click)="aiCustomPrompt(sub.id)"
                            [disabled]="aiProcessing[sub.id] || !aiPromptText[sub.id]">
                            <mat-spinner *ngIf="aiProcessing[sub.id]" diameter="16"></mat-spinner>
                            <mat-icon *ngIf="!aiProcessing[sub.id]">send</mat-icon>
                            Envoyer
                          </button>
                          <button mat-button (click)="toggleAiPrompt(sub.id)">Annuler</button>
                        </div>
                      </div>
                      <!-- Sub-chapter content preview -->
                      <div *ngIf="sub.content" class="ch-content-preview sub-content-preview" [innerHTML]="renderMarkdown(sub.content)"></div>
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
    .ch-actions { display: flex; gap: 8px; margin-top: 8px; align-items: center; }
    .ai-progress-section { margin-top: 12px; padding: 12px; background: #f3e5f5; border-radius: 8px; }
    .ai-progress-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; font-size: 13px; color: #7b1fa2; font-weight: 500; }
    .ai-prompt-section { margin-top: 12px; padding: 12px; background: #f3e5f5; border-radius: 8px; }
    .ai-prompt-section .full-width { width: 100%; }
    .ai-prompt-actions { display: flex; gap: 8px; align-items: center; }
    .sub-ai-prompt { margin-left: 0; }
    .ch-content-preview {
      margin-top: 12px; padding: 16px 20px; background: #fafafa; border: 1px solid #e0e0e0;
      border-radius: 8px; font-size: 13.5px; line-height: 1.7; color: #333; max-height: 400px; overflow-y: auto;
    }
    ::ng-deep .ch-content-preview h2, ::ng-deep .ch-content-preview h3 {
      font-size: 15px; font-weight: 700; color: #1B3A5C; margin: 20px 0 8px 0;
      padding-bottom: 4px; border-bottom: 1px solid #e0e0e0;
    }
    ::ng-deep .ch-content-preview h2:first-child, ::ng-deep .ch-content-preview h3:first-child { margin-top: 0; }
    ::ng-deep .ch-content-preview h4 { font-size: 14px; font-weight: 600; color: #2C5F8A; margin: 16px 0 6px 0; }
    ::ng-deep .ch-content-preview h5 { font-size: 13.5px; font-weight: 600; color: #37474f; margin: 12px 0 4px 0; }
    ::ng-deep .ch-content-preview p { margin: 0 0 10px 0; }
    ::ng-deep .ch-content-preview ul, ::ng-deep .ch-content-preview ol { margin: 6px 0 10px 0; padding-left: 24px; }
    ::ng-deep .ch-content-preview ul { list-style-type: disc; }
    ::ng-deep .ch-content-preview ul ul { list-style-type: circle; margin: 2px 0 2px 0; }
    ::ng-deep .ch-content-preview ol { list-style-type: decimal; }
    ::ng-deep .ch-content-preview li { margin-bottom: 4px; }
    ::ng-deep .ch-content-preview li li { margin-bottom: 2px; }
    ::ng-deep .ch-content-preview strong { color: #1B3A5C; }
    ::ng-deep .ch-content-preview em { color: #555; }
    ::ng-deep .ch-content-preview code { background: #e8eaf6; padding: 1px 5px; border-radius: 3px; font-size: 12.5px; }
    ::ng-deep .ch-content-preview hr { border: none; border-top: 1px solid #ccc; margin: 16px 0; }
    ::ng-deep .ch-content-preview .table-wrap { overflow-x: auto; margin: 12px 0; }
    ::ng-deep .ch-content-preview table { border-collapse: collapse; width: 100%; font-size: 13px; }
    ::ng-deep .ch-content-preview th, ::ng-deep .ch-content-preview td { border: 1px solid #ccc; padding: 8px 10px; text-align: left; }
    ::ng-deep .ch-content-preview th { background: #e3f2fd; color: #1B3A5C; font-weight: 600; }
    ::ng-deep .ch-content-preview tr:nth-child(even) td { background: #fafafa; }
    .sub-content-preview { max-height: 250px; margin-top: 8px; font-size: 13px; }
    .sub-chapters { margin-top: 12px; padding-left: 24px; }
    .sub-chapter-block { border-bottom: 1px solid #eee; }
    .sub-chapter-item { display: flex; align-items: center; gap: 8px; padding: 8px 0; }
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
    .gen-info-card { margin: 16px 0; padding: 20px; border-left: 4px solid #ff9800; display: flex; align-items: flex-start; gap: 12px; background: #fff8e1; }
    .gen-info-card mat-icon { color: #ff9800; font-size: 28px; width: 28px; height: 28px; }
    .gen-info-card strong { color: #e65100; }
    .gen-info-card p { margin: 6px 0 0 0; color: #555; font-size: 13px; line-height: 1.5; }
    .detect-progress-card { border-left-color: #7b1fa2; }
    .detect-progress-card .gen-progress-header h3 { color: #7b1fa2; }
    .detect-progress-card .spin-icon { color: #7b1fa2; }
    .detect-step { color: #7b1fa2 !important; }
    .deliverables-card { margin: 16px 0; padding: 20px; border-left: 4px solid #7b1fa2; }
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
    .fill-progress-card { border-left-color: #2e7d32; }
    .fill-progress-card .gen-progress-header h3 { color: #2e7d32; }
    .fill-progress-card .spin-icon { color: #2e7d32; }
    .fill-step { color: #2e7d32 !important; }
    .fill-success-card { border-left-color: #2e7d32; }
    .fill-success-card mat-icon { color: #2e7d32; }
    .fill-done { background: #c8e6c9 !important; color: #2e7d32 !important; font-weight: 500; }
    .fill-running { background: #fff3e0 !important; color: #e65100 !important; }
    .deliverables-section { margin: 20px 0; }
    .section-title { display: flex; align-items: center; gap: 8px; color: #1B3A5C; font-size: 16px; margin-bottom: 4px; }
    .section-title mat-icon { color: #7b1fa2; }
    .section-subtitle { color: #888; font-size: 13px; margin: 0 0 12px 0; }
    .type-redaction { background: #e3f2fd !important; color: #1565c0 !important; font-weight: 500; }
    .type-completion { background: #fff3e0 !important; color: #e65100 !important; font-weight: 500; }
    .completion-item { border-left: 3px solid #e65100; }
    .type-toggle-btn { font-size: 11px !important; color: #888 !important; min-width: auto !important; padding: 0 6px !important; line-height: 24px !important; height: 24px !important; }
    .type-toggle-btn mat-icon { font-size: 14px; width: 14px; height: 14px; margin-right: 2px; }
    .type-toggle-btn:hover { color: #1976d2 !important; background: #e3f2fd !important; }
    .fill-excel-btn { font-size: 11px !important; background: #1b5e20 !important; color: white !important; padding: 0 10px !important; line-height: 28px !important; height: 28px !important; border-radius: 4px !important; }
    .reset-fill-btn { font-size: 11px !important; color: #c62828 !important; padding: 0 8px !important; line-height: 28px !important; height: 28px !important; }
    .reset-fill-btn mat-icon { font-size: 16px; width: 16px; height: 16px; margin-right: 4px; }
    .fill-excel-btn:disabled { opacity: 0.7; }
    .fill-excel-btn mat-icon { font-size: 16px; width: 16px; height: 16px; margin-right: 4px; }
    .fill-content-panel { margin-top: 10px; box-shadow: none !important; border: 1px solid #e0e0e0; }
    .fill-content-preview { font-size: 13px; line-height: 1.7; color: #333; max-height: 500px; overflow-y: auto; padding: 8px 0; }
    ::ng-deep .fill-content-preview h2, ::ng-deep .fill-content-preview h3 { font-size: 15px; font-weight: 700; color: #1B3A5C; margin: 16px 0 8px 0; }
    ::ng-deep .fill-content-preview h2:first-child, ::ng-deep .fill-content-preview h3:first-child { margin-top: 0; }
    ::ng-deep .fill-content-preview table { border-collapse: collapse; width: 100%; font-size: 13px; margin: 12px 0; }
    ::ng-deep .fill-content-preview th, ::ng-deep .fill-content-preview td { border: 1px solid #ccc; padding: 8px 10px; text-align: left; }
    ::ng-deep .fill-content-preview th { background: #e8f5e9; color: #2e7d32; font-weight: 600; }
    ::ng-deep .fill-content-preview tr:nth-child(even) td { background: #fafafa; }
    ::ng-deep .fill-content-preview ul { list-style-type: disc; padding-left: 24px; }
    ::ng-deep .fill-content-preview strong { color: #e65100; }
    .empty-state { text-align: center; padding: 48px 24px; color: #888; }
    .empty-state mat-icon { font-size: 48px; width: 48px; height: 48px; margin-bottom: 8px; color: #ccc; }
    .hint-card { margin: 16px 0; padding: 16px 20px; border-left: 4px solid #1976d2; display: flex; align-items: flex-start; gap: 12px; }
    .hint-card mat-icon { color: #1976d2; }
    .hint-card p { margin: 4px 0 0 0; color: #666; font-size: 13px; }
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
    .doc-selector-card { margin: 0 0 16px 0; padding: 16px 20px; border-left: 4px solid #1976d2; background: #f8faff; }
    .doc-selector-header { display: flex; align-items: flex-start; gap: 10px; margin-bottom: 12px; }
    .doc-selector-header mat-icon { color: #1976d2; margin-top: 2px; }
    .doc-selector-header strong { color: #1B3A5C; font-size: 14px; }
    .doc-selector-hint { color: #888; font-size: 13px; margin: 2px 0 0 0; }
    .doc-selector-list { display: flex; flex-direction: column; gap: 6px; }
    .doc-selector-item { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border-radius: 6px; background: white; border: 1px solid #e0e0e0; transition: opacity 0.2s, border-color 0.2s; }
    .doc-selector-item:hover { border-color: #1976d2; }
    .doc-selector-item.deselected { opacity: 0.45; }
    .doc-selector-format { display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border-radius: 6px; }
    .doc-selector-format mat-icon { font-size: 20px; width: 20px; height: 20px; }
    .doc-selector-info { flex: 1; min-width: 0; }
    .doc-selector-info strong { display: block; font-size: 13px; color: #1B3A5C; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .doc-selector-desc { display: block; font-size: 12px; color: #888; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .doc-selector-chapters { font-size: 11px !important; }
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
  redactionDocs: ResponseDocument[] = [];
  completionDocs: ResponseDocument[] = [];
  detectingDeliverables = false;
  detectStatus: DetectDeliverablesStatus | null = null;
  private detectPollSub: Subscription | null = null;
  fillingDeliverables = false;
  fillStatus: FillDeliverablesStatus | null = null;
  private fillPollSub: Subscription | null = null;
  selectedChapters = new Set<string>();
  deletingChapters = false;
  showImprovementForm = false;
  improvementContent = '';
  improvementSource = '';
  private pollSub: Subscription | null = null;

  // Cached computed data to avoid method calls in template (prevents change detection loops)
  groupedChapters: { document: ResponseDocument | null; chapters: Chapter[] }[] = [];
  docsByCategory: Record<string, DocumentInfo[]> = {};

  // Per-chapter AI state
  aiProcessing: Record<string, boolean> = {};
  aiPromptVisible: Record<string, boolean> = {};
  aiPromptText: Record<string, string> = {};

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
    // Resume fill polling if already running
    this.api.getFillDeliverablesStatus(this.projectId).subscribe({
      next: (status) => {
        if (status.status === 'running') {
          this.fillStatus = status;
          this.fillingDeliverables = true;
          this.startFillPolling();
        }
      },
    });
  }

  ngOnDestroy(): void {
    this.stopPolling();
    this.stopGenPolling();
    this.stopPrefillPolling();
    this.stopDetectPolling();
    this.stopFillPolling();
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
    const chapterIds = this.selectedChapters.size > 0 ? Array.from(this.selectedChapters) : [];
    this._launchPrefill(chapterIds);
  }

  prefillChapter(chapterId: string): void {
    this._launchPrefill([chapterId]);
  }

  private _launchPrefill(chapterIds: string[]): void {
    this.prefilling = true;
    this.prefillStatus = {
      status: 'running',
      step: 'starting',
      progress: 0,
      message: 'Lancement du pre-remplissage...',
    };
    this.api.prefillChapters(this.projectId, chapterIds).subscribe({
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

  // ── Markdown rendering ──

  renderMarkdown = renderMarkdown;

  // ── Per-chapter AI actions ──

  toggleAiPrompt(chapterId: string): void {
    this.aiPromptVisible[chapterId] = !this.aiPromptVisible[chapterId];
  }

  aiGenerate(chapterId: string): void {
    this.aiProcessing[chapterId] = true;
    this.api.generateChapterContent(chapterId, 'generate').subscribe({
      next: () => {
        this.aiProcessing[chapterId] = false;
        this.snackBar.open('Contenu genere', 'OK', { duration: 3000 });
        this.loadAll();
      },
      error: (err) => {
        this.aiProcessing[chapterId] = false;
        this.snackBar.open(err.error?.detail || 'Erreur generation', 'OK', { duration: 5000 });
      },
    });
  }

  aiCustomPrompt(chapterId: string): void {
    const prompt = this.aiPromptText[chapterId];
    if (!prompt) return;
    this.aiProcessing[chapterId] = true;
    this.api.generateChapterContent(chapterId, 'custom', prompt).subscribe({
      next: () => {
        this.aiProcessing[chapterId] = false;
        this.aiPromptVisible[chapterId] = false;
        this.aiPromptText[chapterId] = '';
        this.snackBar.open('Contenu mis a jour', 'OK', { duration: 3000 });
        this.loadAll();
      },
      error: (err) => {
        this.aiProcessing[chapterId] = false;
        this.snackBar.open(err.error?.detail || 'Erreur', 'OK', { duration: 5000 });
      },
    });
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
      next: (docs) => {
        this.responseDocuments = docs;
        this.redactionDocs = docs.filter(d => d.content_type === 'redaction');
        this.completionDocs = docs.filter(d => d.content_type === 'completion');
        this._refreshGroupedChapters();
      },
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

  // ── Fill deliverables (Excel/PDF completion) ──

  hasCompletionDocs(): boolean {
    return this.completionDocs.some(d => d.is_selected);
  }

  fillDeliverables(): void {
    this.fillingDeliverables = true;
    this.fillStatus = {
      status: 'running',
      step: 'starting',
      progress: 0,
      message: 'Lancement de l\'auto-remplissage...',
    };
    this.api.fillDeliverables(this.projectId).subscribe({
      next: () => {
        this.fillingDeliverables = false;
        this.startFillPolling();
      },
      error: (err) => {
        this.snackBar.open(err.error?.detail || 'Erreur', 'OK', { duration: 5000 });
        this.fillingDeliverables = false;
        this.fillStatus = null;
      },
    });
  }

  private startFillPolling(): void {
    this.stopFillPolling();
    this.fillPollSub = timer(0, 2000).pipe(
      switchMap(() => this.api.getFillDeliverablesStatus(this.projectId))
    ).subscribe({
      next: (status) => {
        this.fillStatus = status;
        if (status.status === 'completed') {
          this.stopFillPolling();
          this.fillingDeliverables = false;
          this.snackBar.open(status.message || 'Auto-remplissage termine', 'OK', { duration: 5000 });
          this.loadResponseDocuments();
        } else if (status.status === 'error') {
          this.stopFillPolling();
          this.fillingDeliverables = false;
        }
      },
    });
  }

  private stopFillPolling(): void {
    this.fillPollSub?.unsubscribe();
    this.fillPollSub = null;
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

  toggleContentType(rd: ResponseDocument, newType: 'redaction' | 'completion'): void {
    const oldType = rd.content_type;
    rd.content_type = newType;
    this.api.updateResponseDocument(this.projectId, rd.id, { content_type: newType }).subscribe({
      next: () => {
        // Re-sort into the correct lists
        this.redactionDocs = this.responseDocuments.filter(d => d.content_type === 'redaction');
        this.completionDocs = this.responseDocuments.filter(d => d.content_type === 'completion');
        this._refreshGroupedChapters();
        this.snackBar.open(
          newType === 'completion'
            ? `"${rd.title}" deplace dans Documents a completer`
            : `"${rd.title}" deplace dans Documents a rediger`,
          'OK', { duration: 3000 }
        );
      },
      error: () => {
        rd.content_type = oldType; // revert on error
        this.snackBar.open('Erreur mise a jour', 'OK', { duration: 3000 });
      },
    });
  }

  fillAndDownloadExcel(rd: any): void {
    rd._fillingExcel = true;
    this.snackBar.open('Generation de l\'Excel en cours (tarifs de l\'ancienne reponse)...', '', { duration: 60000 });
    this.api.fillExcelDocument(this.projectId, rd.id).subscribe({
      next: (blob: Blob) => {
        rd._fillingExcel = false;
        this.snackBar.dismiss();
        // Trigger browser download
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${rd.title.replace(/[^a-zA-Z0-9_-]/g, '_')}_rempli.xlsx`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        this.snackBar.open('Excel rempli telecharge avec succes !', 'OK', { duration: 5000 });
      },
      error: (err) => {
        rd._fillingExcel = false;
        this.snackBar.dismiss();
        const detail = err.error?.detail || 'Erreur lors de la generation de l\'Excel';
        this.snackBar.open(detail, 'OK', { duration: 8000 });
      },
    });
  }

  resetFillContent(rd: ResponseDocument): void {
    if (!confirm('Supprimer le contenu genere pour "' + rd.title + '" ? Vous pourrez ensuite le regenerer.')) {
      return;
    }
    this.api.resetFillContent(this.projectId, rd.id).subscribe({
      next: (updated) => {
        rd.fill_content = updated.fill_content;
        rd.fill_status = updated.fill_status;
        this.snackBar.open('Contenu supprime. Vous pouvez maintenant regenerer.', 'OK', { duration: 4000 });
      },
      error: () => {
        this.snackBar.open('Erreur lors de la suppression du contenu', 'OK', { duration: 3000 });
      },
    });
  }

  selectedDocCount(): number {
    return this.responseDocuments.filter(rd => rd.is_selected).length;
  }

  selectedRedactionCount(): number {
    return this.redactionDocs.filter(rd => rd.is_selected).length;
  }

  selectAllRedaction(selected: boolean): void {
    for (const rd of this.redactionDocs) {
      if (rd.is_selected !== selected) {
        this.toggleDeliverable(rd, selected);
      }
    }
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

  chapterTypeLabel(type: string): string {
    const labels: Record<string, string> = {
      chapter: 'Chapitre',
      sub_chapter: 'Sous-chapitre',
      annexe: 'Annexe',
      document_to_provide: 'Document a fournir',
    };
    return labels[type] || type;
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
