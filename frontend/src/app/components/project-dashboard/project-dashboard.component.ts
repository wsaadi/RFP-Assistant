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
import { AuthService } from '../../services/auth.service';
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
          <button mat-raised-button (click)="exportWord()" [disabled]="exportingWord" matTooltip="Exporter en Word">
            <mat-spinner *ngIf="exportingWord" diameter="18"></mat-spinner>
            <mat-icon *ngIf="!exportingWord">file_download</mat-icon>
            {{ exportingWord ? 'Export...' : 'DOCX' }}
          </button>
          <button mat-raised-button (click)="exportBackup()" [disabled]="exportingBackup" matTooltip="Sauvegarder le projet">
            <mat-spinner *ngIf="exportingBackup" diameter="18"></mat-spinner>
            <mat-icon *ngIf="!exportingBackup">save</mat-icon>
            {{ exportingBackup ? 'Export...' : 'Backup' }}
          </button>
          <button mat-raised-button [routerLink]="['/project', projectId, 'images']"
            matTooltip="Galerie d'images extraites">
            <mat-icon>photo_library</mat-icon> Images
            <span *ngIf="stats?.images_count" class="image-badge">{{ stats!.images_count }}</span>
          </button>
          <button mat-raised-button color="accent" [routerLink]="['/project', projectId, 'preview']">
            <mat-icon>visibility</mat-icon> Aperçu
          </button>
          <button mat-raised-button color="primary" (click)="handleSoutenanceClick()" [disabled]="exportingSoutenance" matTooltip="Soutenance PowerPoint + script">
            <mat-spinner *ngIf="exportingSoutenance" diameter="18"></mat-spinner>
            <mat-icon *ngIf="!exportingSoutenance">co_present</mat-icon>
            {{ exportingSoutenance ? 'Generation...' : 'Soutenance' }}
          </button>
        </div>
      </div>

      <!-- Word export progress -->
      <mat-card *ngIf="wordProgress" class="gen-progress-card word-progress-card">
        <div class="gen-progress-header">
          <mat-spinner diameter="20" class="spin-icon"></mat-spinner>
          <h3>{{ wordProgress.step === 'downloading' ? 'Telechargement Word...' : 'Export Word en cours...' }}</h3>
          <span style="flex:1"></span>
          <button mat-icon-button color="warn" (click)="cancelWordExport()" matTooltip="Annuler l'export" [disabled]="cancellingWord">
            <mat-icon>close</mat-icon>
          </button>
        </div>
        <mat-progress-bar [mode]="wordProgress.step === 'downloading' ? 'indeterminate' : 'determinate'" [value]="wordProgress.progress"></mat-progress-bar>
        <div class="gen-progress-details">
          <span class="gen-step">{{ wordProgress.step }}</span>
          <span class="gen-pct">{{ wordProgress.progress }}%</span>
        </div>
        <p class="gen-message">{{ wordProgress.message }}</p>
      </mat-card>

      <!-- Backup progress -->
      <mat-card *ngIf="backupProgress" class="gen-progress-card backup-progress-card">
        <div class="gen-progress-header">
          <mat-spinner diameter="20" class="spin-icon"></mat-spinner>
          <h3>{{ backupProgress.step === 'downloading' ? 'Telechargement backup...' : 'Export backup en cours...' }}</h3>
        </div>
        <mat-progress-bar [mode]="backupProgress.step === 'downloading' ? 'indeterminate' : 'determinate'" [value]="backupProgress.progress"></mat-progress-bar>
        <div class="gen-progress-details">
          <span class="gen-step">{{ backupProgress.step }}</span>
          <span class="gen-pct">{{ backupProgress.progress }}%</span>
        </div>
        <p class="gen-message">{{ backupProgress.message }}</p>
      </mat-card>

      <!-- Soutenance progress -->
      <mat-card *ngIf="soutenanceProgress" class="gen-progress-card soutenance-progress-card">
        <div class="gen-progress-header">
          <mat-spinner diameter="20" class="spin-icon"></mat-spinner>
          <h3>Preparation de la soutenance en cours...</h3>
          <span style="flex:1"></span>
          <button mat-icon-button color="warn" (click)="cancelSoutenance()" matTooltip="Annuler">
            <mat-icon>close</mat-icon>
          </button>
        </div>
        <mat-progress-bar mode="determinate" [value]="soutenanceProgress.progress"></mat-progress-bar>
        <div class="gen-progress-details">
          <span class="gen-step">{{ soutenanceProgress.step }}</span>
          <span class="gen-pct">{{ soutenanceProgress.progress }}%</span>
        </div>
        <p class="gen-message">{{ soutenanceProgress.message }}</p>
      </mat-card>

      <!-- Soutenance options dialog -->
      <mat-card *ngIf="showSoutenanceOptions" class="gen-progress-card soutenance-options-card">
        <div class="soutenance-options-header">
          <mat-icon>co_present</mat-icon>
          <h3>Preparation de soutenance</h3>
          <span style="flex:1"></span>
          <button mat-icon-button (click)="showSoutenanceOptions = false"><mat-icon>close</mat-icon></button>
        </div>
        <div class="soutenance-options-body">
          <div *ngIf="soutenanceExists" class="soutenance-existing">
            <p><mat-icon>check_circle</mat-icon> Une soutenance a deja ete generee pour ce projet.</p>
            <button mat-raised-button color="primary" (click)="goToSoutenance()">
              <mat-icon>visibility</mat-icon> Voir la soutenance existante
            </button>
          </div>
          <div class="soutenance-generate">
            <p *ngIf="soutenanceExists">Ou regenerer avec de nouveaux parametres :</p>
            <div class="slide-count-row">
              <label>Nombre de slides :</label>
              <mat-select [(value)]="selectedSlideCount" class="slide-select">
                <mat-option [value]="15">15 slides (~15 min)</mat-option>
                <mat-option [value]="20">20 slides (~20 min)</mat-option>
                <mat-option [value]="25">25 slides (~25 min)</mat-option>
                <mat-option [value]="30">30 slides (~30 min)</mat-option>
                <mat-option [value]="35">35 slides (~35 min)</mat-option>
                <mat-option [value]="40">40 slides (~40 min)</mat-option>
                <mat-option [value]="45">45 slides (~45 min)</mat-option>
                <mat-option [value]="50">50 slides (~50 min)</mat-option>
                <mat-option [value]="60">60 slides (~60 min)</mat-option>
              </mat-select>
            </div>
            <button mat-raised-button color="accent" (click)="launchSoutenanceGeneration()">
              <mat-icon>auto_awesome</mat-icon> {{ soutenanceExists ? 'Regenerer la soutenance' : 'Generer la soutenance' }}
            </button>
          </div>
        </div>
      </mat-card>

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
              <h4>{{ cat.label }}
                <span class="doc-count" *ngIf="docsByCategory[cat.value]?.length">({{ docsByCategory[cat.value].length }})</span>
              </h4>
              <mat-list>
                <!-- Files currently uploading (shown immediately) -->
                <div *ngFor="let up of getUploadingByCategory(cat.value)" class="doc-item-wrap uploading-item">
                  <mat-list-item>
                    <mat-icon matListItemIcon class="uploading-icon">cloud_upload</mat-icon>
                    <span matListItemTitle>{{ up.filename }}</span>
                    <span matListItemLine>
                      <mat-chip class="proc-uploading" size="small" *ngIf="up.status === 'uploading'">
                        Envoi {{ up.progress }}%
                      </mat-chip>
                      <mat-chip class="proc-processing" size="small" *ngIf="up.status === 'server_processing'">
                        Traitement...
                      </mat-chip>
                      <mat-chip class="proc-failed" size="small" *ngIf="up.status === 'failed'">
                        {{ up.error || 'Echec' }}
                      </mat-chip>
                    </span>
                  </mat-list-item>
                  <div class="doc-progress" *ngIf="up.status === 'uploading'">
                    <mat-progress-bar mode="determinate" [value]="up.progress" color="accent"></mat-progress-bar>
                  </div>
                  <div class="doc-progress" *ngIf="up.status === 'server_processing'">
                    <mat-progress-bar mode="indeterminate" color="primary"></mat-progress-bar>
                  </div>
                </div>

                <!-- Already uploaded documents -->
                <div *ngFor="let doc of docsByCategory[cat.value]" class="doc-item-wrap">
                  <mat-list-item>
                    <mat-icon matListItemIcon>{{ fileIcon(doc.file_type) }}</mat-icon>
                    <span matListItemTitle>{{ doc.original_filename }}</span>
                    <span matListItemLine>
                      {{ formatSize(doc.file_size) }}
                      <ng-container *ngIf="doc.processing_status === 'completed'">
                        - {{ doc.page_count }} pages - {{ doc.chunk_count }} chunks
                      </ng-container>
                      <mat-chip [class]="'proc-' + getEffectiveStatus(doc)" size="small">
                        {{ statusLabel(getEffectiveStatus(doc)) }}
                      </mat-chip>
                    </span>
                    <button mat-icon-button matListItemMeta (click)="deleteDoc(doc.id)"><mat-icon>delete</mat-icon></button>
                  </mat-list-item>
                  <!-- Processing progress bar with step details -->
                  <div *ngIf="getProgress(doc.id) as prog" class="doc-progress">
                    <div class="progress-info">
                      <mat-icon *ngIf="prog.step === 'queued'" class="progress-queued-icon">schedule</mat-icon>
                      <mat-spinner *ngIf="prog.progress > 0 && prog.step !== 'completed' && prog.step !== 'queued'" diameter="16"></mat-spinner>
                      <mat-icon *ngIf="prog.step === 'completed'" class="progress-done-icon">check_circle</mat-icon>
                      <span class="progress-label">{{ prog.step_label }}</span>
                      <span class="progress-pct" *ngIf="prog.progress > 0">{{ prog.progress }}%</span>
                    </div>
                    <mat-progress-bar
                      [mode]="prog.step === 'queued' ? 'indeterminate' : (prog.progress > 0 ? 'determinate' : 'indeterminate')"
                      [value]="prog.progress"
                      [color]="prog.progress < 0 ? 'warn' : (prog.step === 'queued' ? 'accent' : 'primary')">
                    </mat-progress-bar>
                    <!-- Step indicators (8 steps) -->
                    <div class="progress-steps" *ngIf="prog.progress > 0 && prog.step !== 'completed' && prog.step !== 'failed'">
                      <span class="step-dot" [class.active]="prog.progress >= 5" [class.current]="prog.step === 'reading'" matTooltip="Lecture">1</span>
                      <span class="step-line" [class.active]="prog.progress >= 15"></span>
                      <span class="step-dot" [class.active]="prog.progress >= 15" [class.current]="prog.step === 'extracting_text'" matTooltip="Extraction texte">2</span>
                      <span class="step-line" [class.active]="prog.progress >= 25"></span>
                      <span class="step-dot" [class.active]="prog.progress >= 25" [class.current]="prog.step === 'extracting_images'" matTooltip="Extraction images">3</span>
                      <span class="step-line" [class.active]="prog.progress >= 35"></span>
                      <span class="step-dot" [class.active]="prog.progress >= 35" [class.current]="prog.step === 'chunking'" matTooltip="Decoupage">4</span>
                      <span class="step-line" [class.active]="prog.progress >= 50"></span>
                      <span class="step-dot" [class.active]="prog.progress >= 50" [class.current]="prog.step === 'anonymizing'" matTooltip="Anonymisation">5</span>
                      <span class="step-line" [class.active]="prog.progress >= 65"></span>
                      <span class="step-dot" [class.active]="prog.progress >= 65" [class.current]="prog.step === 'saving_chunks'" matTooltip="Enregistrement">6</span>
                      <span class="step-line" [class.active]="prog.progress >= 80"></span>
                      <span class="step-dot" [class.active]="prog.progress >= 80" [class.current]="prog.step === 'indexing'" matTooltip="Indexation">7</span>
                      <span class="step-line" [class.active]="prog.progress >= 92"></span>
                      <span class="step-dot" [class.active]="prog.progress >= 90" [class.current]="prog.step === 'finalizing'" matTooltip="Finalisation">8</span>
                    </div>
                  </div>
                </div>
              </mat-list>
              <p class="empty-category" *ngIf="!docsByCategory[cat.value]?.length && !getUploadingByCategory(cat.value).length">Aucun document</p>
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
                        matTooltip="Remplir l'Excel avec les informations de l'ancienne reponse et telecharger">
                        <mat-spinner *ngIf="rd._fillingExcel" diameter="16"></mat-spinner>
                        <mat-icon *ngIf="!rd._fillingExcel">download</mat-icon>
                        {{ rd._fillingExcel ? 'Generation en cours...' : 'Telecharger Excel rempli' }}
                      </button>
                      <button mat-raised-button class="fill-pdf-btn"
                        *ngIf="rd.expected_format === 'pdf'"
                        [disabled]="rd._fillingPdf"
                        (click)="fillAndDownloadPdf(rd)"
                        matTooltip="Remplir le PDF avec les informations de l'ancienne reponse et telecharger">
                        <mat-spinner *ngIf="rd._fillingPdf" diameter="16"></mat-spinner>
                        <mat-icon *ngIf="!rd._fillingPdf">picture_as_pdf</mat-icon>
                        {{ rd._fillingPdf ? 'Generation en cours...' : 'Telecharger PDF rempli' }}
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
                      <div class="fill-content-preview" [innerHTML]="getCachedMarkdown(rd.id, rd.fill_content)"></div>
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
              <button mat-raised-button color="accent" (click)="generateSelectedChapters()"
                [disabled]="bulkGenerating || selectedChapters.size === 0"
                *ngIf="chapters.length > 0">
                <mat-spinner *ngIf="bulkGenerating" diameter="18"></mat-spinner>
                <mat-icon *ngIf="!bulkGenerating">auto_awesome</mat-icon>
                {{ selectedChapters.size > 0 ? 'Generer IA (' + selectedChapters.size + ')' : 'Selectionner des chapitres' }}
              </button>
              <button mat-raised-button (click)="prefillAll()"
                [disabled]="prefilling || prefillStatus?.status === 'running'">
                <mat-spinner *ngIf="prefilling || prefillStatus?.status === 'running'" diameter="18"></mat-spinner>
                <mat-icon *ngIf="!prefilling && prefillStatus?.status !== 'running'">content_copy</mat-icon>
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

            <!-- Bulk AI generation progress panel -->
            <mat-card *ngIf="bulkGenerating" class="gen-progress-card" style="border-left-color: #ff6f00;">
              <div class="gen-progress-header">
                <mat-spinner diameter="20" class="spin-icon"></mat-spinner>
                <h3>Generation IA des chapitres selectionnes...</h3>
                <span style="flex:1"></span>
                <button mat-icon-button color="warn" (click)="cancelBulkGenerate()" matTooltip="Annuler les generations restantes">
                  <mat-icon>close</mat-icon>
                </button>
              </div>
              <mat-progress-bar mode="determinate" [value]="bulkGenProgress"></mat-progress-bar>
              <div class="gen-progress-detail">
                <span class="gen-step" style="color: #ff6f00;">{{ bulkGenDone }}/{{ bulkGenTotal }} chapitres</span>
                <span class="gen-pct">{{ bulkGenProgress | number:'1.0-0' }}%</span>
              </div>
              <p class="gen-message">{{ bulkGenMessage }}</p>
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
                      {{ chapterTypeLabel(ch.chapter_type) }} - {{ ch.content ? (getWordCount(ch.content) + ' mots') : 'Vide' }}
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
                      [matTooltip]="getAiGenerateTooltip(ch)">
                      <mat-icon>auto_awesome</mat-icon>
                      {{ ch.content ? 'Regenerer' : 'Remplir avec IA' }}
                      <span *ngIf="ch.children?.length" class="ai-badge">+{{ ch.children.length }}</span>
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
                      <mat-icon *ngIf="aiProgress[ch.id]?.status === 'queued'" class="queued-icon">schedule</mat-icon>
                      <mat-spinner *ngIf="aiProgress[ch.id]?.status !== 'queued'" diameter="16"></mat-spinner>
                      <span>{{ aiProgress[ch.id]?.message || 'Generation IA en cours...' }}</span>
                    </div>
                    <mat-progress-bar [mode]="aiProgress[ch.id]?.progress ? 'determinate' : 'indeterminate'" [value]="aiProgress[ch.id]?.progress || 0" [color]="aiProgress[ch.id]?.status === 'queued' ? 'primary' : 'accent'"></mat-progress-bar>
                    <div *ngIf="aiProgress[ch.id]?.progress" class="ai-progress-pct">{{ aiProgress[ch.id]?.progress }}%</div>
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

                  <!-- Content preview (truncated for performance) -->
                  <div *ngIf="ch.content" class="ch-content-preview" [innerHTML]="getCachedMarkdown(ch.id, ch.content)"></div>

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
                        <span class="sub-meta">{{ sub.content ? (getWordCount(sub.content) + ' mots') : 'Vide' }}</span>
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
                          <mat-icon *ngIf="aiProgress[sub.id]?.status === 'queued'" class="queued-icon">schedule</mat-icon>
                          <mat-spinner *ngIf="aiProgress[sub.id]?.status !== 'queued'" diameter="16"></mat-spinner>
                          <span>{{ aiProgress[sub.id]?.message || 'Generation IA en cours...' }}</span>
                        </div>
                        <mat-progress-bar [mode]="aiProgress[sub.id]?.progress ? 'determinate' : 'indeterminate'" [value]="aiProgress[sub.id]?.progress || 0" [color]="aiProgress[sub.id]?.status === 'queued' ? 'primary' : 'accent'"></mat-progress-bar>
                        <div *ngIf="aiProgress[sub.id]?.progress" class="ai-progress-pct">{{ aiProgress[sub.id]?.progress }}%</div>
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
                      <!-- Sub-chapter content preview (truncated for performance) -->
                      <div *ngIf="sub.content" class="ch-content-preview sub-content-preview" [innerHTML]="getCachedMarkdown(sub.id, sub.content)"></div>
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
            <!-- AI Context -->
            <mat-card class="ai-context-card">
              <div class="ai-context-header">
                <div>
                  <h3><mat-icon>psychology</mat-icon> Contexte IA du projet</h3>
                  <p class="ai-context-hint">Ce contexte sera utilisé par l'IA pour orienter la rédaction de tous les contenus (chapitres, enrichissement, etc.)</p>
                </div>
                <button *ngIf="canManageProject" mat-icon-button (click)="editingAiContext = !editingAiContext" [matTooltip]="editingAiContext ? 'Annuler' : 'Modifier'">
                  <mat-icon>{{ editingAiContext ? 'close' : 'edit' }}</mat-icon>
                </button>
              </div>
              <div *ngIf="!editingAiContext && project.ai_context" class="ai-context-display">
                <pre class="ai-context-content">{{ project.ai_context }}</pre>
              </div>
              <div *ngIf="!editingAiContext && !project.ai_context" class="ai-context-empty">
                <mat-icon>info_outline</mat-icon>
                <span>Aucun contexte défini. <a *ngIf="canManageProject" (click)="editingAiContext = true" class="link">Ajouter un contexte</a><span *ngIf="!canManageProject">Contactez un administrateur ou le propriétaire du projet pour configurer le contexte IA.</span></span>
              </div>
              <div *ngIf="editingAiContext" class="ai-context-edit">
                <mat-form-field appearance="outline" class="full-width">
                  <mat-label>Contexte pour l'IA</mat-label>
                  <textarea matInput [(ngModel)]="aiContextDraft" rows="4"
                    placeholder="Ex: Nous sommes une ESN spécialisée en cybersécurité. Notre point fort est notre SOC 24/7 et nos certifications ISO 27001. Le ton doit être technique et rassurant."></textarea>
                </mat-form-field>
                <div class="form-actions">
                  <button mat-button (click)="editingAiContext = false">Annuler</button>
                  <button mat-raised-button color="primary" (click)="saveAiContext()">Enregistrer</button>
                </div>
              </div>
            </mat-card>

            <mat-card class="ai-context-card" style="margin-top: 12px;">
              <div class="ai-context-header">
                <div>
                  <h3><mat-icon>tune</mat-icon> Mode de contexte IA</h3>
                  <p class="ai-context-hint">Définit comment les documents sont transmis à l'IA pour la rédaction des chapitres.</p>
                </div>
              </div>
              <div style="display: flex; gap: 12px; flex-wrap: wrap; margin-top: 8px;">
                <mat-card [class.selected-mode]="project.context_mode !== 'full'"
                  (click)="canManageProject && setContextMode('rag')"
                  [style.cursor]="canManageProject ? 'pointer' : 'default'"
                  style="flex: 1; min-width: 220px; cursor: pointer; padding: 16px; border: 2px solid transparent; transition: all 0.2s;"
                  [style.borderColor]="project.context_mode !== 'full' ? '#1976d2' : 'transparent'"
                  [style.background]="project.context_mode !== 'full' ? '#e3f2fd' : ''">
                  <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                    <mat-icon [style.color]="project.context_mode !== 'full' ? '#1976d2' : '#999'">search</mat-icon>
                    <strong>RAG (Recherche)</strong>
                  </div>
                  <p style="margin: 0; font-size: 13px; color: #555;">
                    L'IA reçoit uniquement les extraits les plus pertinents de vos documents.
                    <strong>Plus rapide et économique</strong>, adapté aux gros volumes.
                  </p>
                </mat-card>
                <mat-card [class.selected-mode]="project.context_mode === 'full'"
                  (click)="canManageProject && setContextMode('full')"
                  style="flex: 1; min-width: 220px; padding: 16px; border: 2px solid transparent; transition: all 0.2s;"
                  [style.cursor]="canManageProject ? 'pointer' : 'default'"
                  [style.borderColor]="project.context_mode === 'full' ? '#7b1fa2' : 'transparent'"
                  [style.background]="project.context_mode === 'full' ? '#f3e5f5' : ''">
                  <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                    <mat-icon [style.color]="project.context_mode === 'full' ? '#7b1fa2' : '#999'">description</mat-icon>
                    <strong>Contexte complet</strong>
                  </div>
                  <p style="margin: 0; font-size: 13px; color: #555;">
                    L'IA reçoit l'intégralité des documents, comme dans un chat.
                    <strong>Meilleure compréhension</strong>, mais plus lent et coûteux.
                  </p>
                </mat-card>
              </div>
            </mat-card>

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

            <!-- Content Reuse Statistics -->
            <mat-card class="reuse-stats-card" style="margin-top: 16px;">
              <div class="reuse-stats-header">
                <h3><mat-icon>recycling</mat-icon> Statistique de réutilisation du contenu</h3>
                <button mat-raised-button (click)="loadContentReuseStats()" [disabled]="loadingReuseStats">
                  <mat-spinner *ngIf="loadingReuseStats" diameter="18"></mat-spinner>
                  <mat-icon *ngIf="!loadingReuseStats">refresh</mat-icon> Analyser
                </button>
              </div>
              <p class="reuse-stats-hint">Compare le contenu de l'ancienne réponse avec le contenu généré pour mesurer le taux de réutilisation.</p>

              <div *ngIf="reuseStats?.created_at" class="reuse-timestamp">
                <mat-icon>schedule</mat-icon>
                <span>Derniere analyse : {{ reuseStats.created_at | date:'medium' }}</span>
              </div>

              <div *ngIf="reuseStats && reuseStats.has_old_response">
                <div class="reuse-summary-grid">
                  <div class="reuse-summary-item">
                    <span class="reuse-big-number">{{ reuseStats.summary.avg_reuse_percentage }}%</span>
                    <span class="reuse-label">Réutilisation moyenne</span>
                  </div>
                  <div class="reuse-summary-item">
                    <span class="reuse-big-number">{{ reuseStats.summary.chapters_with_reuse }}</span>
                    <span class="reuse-label">Chapitres avec réutilisation (>10%)</span>
                  </div>
                  <div class="reuse-summary-item">
                    <span class="reuse-big-number">{{ reuseStats.summary.old_response_word_count | number }}</span>
                    <span class="reuse-label">Mots ancienne réponse</span>
                  </div>
                  <div class="reuse-summary-item">
                    <span class="reuse-big-number">{{ reuseStats.summary.new_content_word_count | number }}</span>
                    <span class="reuse-label">Mots nouveau contenu</span>
                  </div>
                </div>

                <div class="reuse-bar-chart" *ngIf="reuseStats.chapters.length > 0">
                  <div *ngFor="let ch of reuseStats.chapters" class="reuse-bar-row">
                    <span class="reuse-bar-label" [matTooltip]="ch.title">{{ ch.numbering || '' }} {{ ch.title | slice:0:40 }}{{ ch.title.length > 40 ? '...' : '' }}</span>
                    <div class="reuse-bar-track">
                      <div class="reuse-bar-fill"
                        [style.width.%]="ch.reuse_percentage"
                        [style.background]="ch.reuse_percentage > 50 ? '#4caf50' : ch.reuse_percentage > 20 ? '#ff9800' : '#f44336'">
                      </div>
                    </div>
                    <span class="reuse-bar-pct" [style.color]="ch.reuse_percentage > 50 ? '#4caf50' : ch.reuse_percentage > 20 ? '#ff9800' : '#f44336'">{{ ch.reuse_percentage }}%</span>
                  </div>
                </div>
              </div>

              <div *ngIf="reuseStats && !reuseStats.has_old_response" class="reuse-empty">
                <mat-icon>info</mat-icon>
                <span>Aucune ancienne réponse importée. Importez un document dans la catégorie "Ancienne réponse" pour activer cette fonctionnalité.</span>
              </div>
            </mat-card>

            <!-- AI Cost Tracking link (admin only) -->
            <mat-card *ngIf="isAdmin" class="cost-tracking-link-card" style="margin-top: 16px;">
              <div class="cost-link-content">
                <div class="cost-link-left">
                  <mat-icon class="cost-link-icon">payments</mat-icon>
                  <div>
                    <h3>Suivi des coûts IA</h3>
                    <p>Tarification, consommation par modèle, coûts quotidiens et logs des requêtes IA</p>
                  </div>
                </div>
                <button mat-raised-button color="primary" [routerLink]="['/project', projectId, 'cost-tracking']">
                  <mat-icon>open_in_new</mat-icon> Ouvrir
                </button>
              </div>
            </mat-card>

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

            <div *ngIf="improvementAxes.length > 0" class="axes-list">
              <div class="axes-list-header">
                <h3>Axes d'amélioration enregistrés ({{ improvementAxes.length }})</h3>
                <button mat-icon-button (click)="loadImprovementAxes()" matTooltip="Actualiser">
                  <mat-icon>refresh</mat-icon>
                </button>
              </div>
              <mat-card *ngFor="let axis of improvementAxes" class="axis-item">
                <div *ngIf="editingAxisId !== axis.id" class="axis-display">
                  <div class="axis-content">{{ axis.content }}</div>
                  <div class="axis-meta">
                    <span *ngIf="axis.source" class="axis-source"><mat-icon class="meta-icon">source</mat-icon> {{ axis.source }}</span>
                    <span class="axis-date"><mat-icon class="meta-icon">schedule</mat-icon> {{ axis.created_at | date:'dd/MM/yyyy HH:mm' }}</span>
                  </div>
                  <div class="axis-actions">
                    <button mat-icon-button (click)="startEditAxis(axis)" matTooltip="Modifier">
                      <mat-icon>edit</mat-icon>
                    </button>
                    <button mat-icon-button color="warn" (click)="deleteAxis(axis)" matTooltip="Supprimer">
                      <mat-icon>delete</mat-icon>
                    </button>
                  </div>
                </div>
                <div *ngIf="editingAxisId === axis.id" class="axis-edit">
                  <mat-form-field appearance="outline" class="full-width">
                    <mat-label>Contenu</mat-label>
                    <textarea matInput [(ngModel)]="editAxisContent" rows="3"></textarea>
                  </mat-form-field>
                  <mat-form-field appearance="outline" class="full-width">
                    <mat-label>Source</mat-label>
                    <input matInput [(ngModel)]="editAxisSource">
                  </mat-form-field>
                  <div class="form-actions">
                    <button mat-button (click)="editingAxisId = null">Annuler</button>
                    <button mat-raised-button color="primary" (click)="saveEditAxis(axis)">Enregistrer</button>
                  </div>
                </div>
              </mat-card>
            </div>
          </div>
        </mat-tab>

        <mat-tab label="Q&A Documents">
          <div class="tab-content">
            <div class="qa-container">
              <div class="qa-header">
                <mat-icon>question_answer</mat-icon>
                <div>
                  <h3>Interroger les documents du projet</h3>
                  <p class="qa-subtitle">Posez des questions sur l'ensemble des documents charges. L'IA analysera les documents et citera ses sources.</p>
                </div>
              </div>

              <div class="qa-chat-area">
                <div class="qa-messages" *ngIf="qaMessages.length > 0">
                  <div *ngFor="let msg of qaMessages" class="qa-msg" [class.qa-msg-user]="msg.role === 'user'" [class.qa-msg-ai]="msg.role === 'assistant'" [class.qa-msg-error]="msg.role === 'error'">
                    <div class="qa-msg-icon">
                      <mat-icon *ngIf="msg.role === 'user'">person</mat-icon>
                      <mat-icon *ngIf="msg.role === 'assistant'">auto_awesome</mat-icon>
                      <mat-icon *ngIf="msg.role === 'error'">error</mat-icon>
                    </div>
                    <div class="qa-msg-body">
                      <div *ngIf="msg.role === 'user'" class="qa-msg-text">{{ msg.content }}</div>
                      <div *ngIf="msg.role !== 'user'" class="qa-msg-text rendered-qa" [innerHTML]="renderMarkdown(msg.content)"></div>

                      <div *ngIf="msg.sources?.length" class="qa-sources">
                        <div class="qa-sources-header" (click)="msg._sourcesOpen = !msg._sourcesOpen">
                          <mat-icon>{{ msg._sourcesOpen ? 'expand_less' : 'expand_more' }}</mat-icon>
                          <span>{{ msg.sources?.length }} source(s) consultee(s)</span>
                        </div>
                        <div *ngIf="msg._sourcesOpen" class="qa-sources-list">
                          <div *ngFor="let src of msg.sources" class="qa-source-item">
                            <mat-icon class="qa-source-icon">description</mat-icon>
                            <div class="qa-source-info">
                              <strong>{{ src.document_name }}</strong>
                              <span class="qa-source-meta">
                                <mat-chip class="qa-cat-chip">{{ src.category_label }}</mat-chip>
                                page {{ src.page_number }}
                              </span>
                              <p class="qa-source-excerpt">{{ src.excerpt }}</p>
                            </div>
                          </div>
                        </div>
                      </div>
                      <span class="qa-msg-time">{{ msg.timestamp | date:'HH:mm' }}</span>
                    </div>
                  </div>
                </div>

                <div *ngIf="qaMessages.length === 0" class="qa-empty">
                  <mat-icon>search</mat-icon>
                  <h3>Posez votre question</h3>
                  <p>Exemples :</p>
                  <div class="qa-examples">
                    <button mat-stroked-button (click)="qaInput = 'Quelles sont les exigences techniques du nouvel AO ?'; askQuestion()">
                      Exigences techniques du nouvel AO ?
                    </button>
                    <button mat-stroked-button (click)="qaInput = 'Quelles sont les differences entre ancien et nouvel AO ?'; askQuestion()">
                      Differences ancien vs nouvel AO ?
                    </button>
                    <button mat-stroked-button (click)="qaInput = 'Que contenait notre ancienne reponse concernant la methodologie ?'; askQuestion()">
                      Methodologie dans l'ancienne reponse ?
                    </button>
                  </div>
                </div>

                <div *ngIf="qaLoading" class="qa-loading">
                  <mat-spinner diameter="24"></mat-spinner>
                  <span>Analyse des documents en cours...</span>
                </div>
              </div>

              <div class="qa-input-area">
                <mat-form-field appearance="outline" class="full-width qa-input-field">
                  <mat-label>Votre question sur les documents...</mat-label>
                  <textarea matInput [(ngModel)]="qaInput" (keydown.enter)="onQaKeydown($event)"
                    [disabled]="qaLoading" rows="2"
                    placeholder="Ex: Quels sont les criteres de selection du nouvel AO ?"></textarea>
                </mat-form-field>
                <button mat-mini-fab color="primary" (click)="askQuestion()" [disabled]="!qaInput.trim() || qaLoading" matTooltip="Envoyer">
                  <mat-icon>send</mat-icon>
                </button>
              </div>
            </div>
          </div>
        </mat-tab>

        <mat-tab label="Membres">
          <div class="tab-content">
            <div class="member-source-info">
              <mat-icon>info</mat-icon>
              <span>L'acces au projet est gere individuellement. Seuls les membres de l'espace de travail peuvent etre ajoutes a un projet par un proprietaire ou administrateur.</span>
            </div>

            <!-- Project-specific members section -->
            <h3 class="members-section-title" *ngIf="getProjectSpecificMembers().length > 0">
              <mat-icon>group</mat-icon> Membres du projet
            </h3>
            <mat-list class="members-list" *ngIf="getProjectSpecificMembers().length > 0">
              <mat-list-item *ngFor="let m of getProjectSpecificMembers()" class="member-item">
                <mat-icon matListItemIcon>person</mat-icon>
                <span matListItemTitle>{{ m.full_name }} ({{ m.username }})</span>
                <span matListItemLine>{{ m.email }}</span>
                <div class="member-actions">
                  <mat-form-field *ngIf="canManageProject" appearance="outline" class="role-inline-field">
                    <mat-select [value]="m.role" (selectionChange)="changeProjectMemberRole(m, $event.value)">
                      <mat-option value="owner">Proprietaire</mat-option>
                      <mat-option value="editor">Editeur</mat-option>
                      <mat-option value="viewer">Lecteur</mat-option>
                    </mat-select>
                  </mat-form-field>
                  <mat-chip *ngIf="!canManageProject">{{ m.role === 'owner' ? 'Proprietaire' : m.role === 'editor' ? 'Editeur' : 'Lecteur' }}</mat-chip>
                  <button *ngIf="canManageProject" mat-icon-button color="warn" (click)="removeProjectMember(m)" matTooltip="Retirer du projet">
                    <mat-icon>person_remove</mat-icon>
                  </button>
                </div>
              </mat-list-item>
            </mat-list>

            <!-- Workspace members (not yet project members) - only visible to project owner/admin -->
            <h3 class="members-section-title" *ngIf="canManageProject && getWorkspaceOnlyMembers().length > 0">
              <mat-icon>business</mat-icon> Membres de l'espace de travail
              <span class="section-subtitle">(pas encore ajoutes au projet)</span>
            </h3>
            <mat-list class="members-list" *ngIf="canManageProject && getWorkspaceOnlyMembers().length > 0">
              <mat-list-item *ngFor="let m of getWorkspaceOnlyMembers()" class="member-item ws-member-item">
                <mat-icon matListItemIcon>person_outline</mat-icon>
                <span matListItemTitle>{{ m.full_name }} ({{ m.username }})</span>
                <span matListItemLine>{{ m.email }} <mat-chip class="inherited-chip">Espace de travail</mat-chip></span>
                <div class="member-actions">
                  <button mat-stroked-button color="primary" (click)="quickAddProjectMember(m)" class="quick-add-btn">
                    <mat-icon>person_add</mat-icon> Ajouter au projet
                  </button>
                </div>
              </mat-list-item>
            </mat-list>
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
    .header-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
    .image-badge { background: #1976d2; color: white; font-size: 11px; padding: 1px 6px; border-radius: 10px; margin-left: 4px; }
    .stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 16px; }
    .stat-card { display: flex; align-items: center; gap: 12px; padding: 16px; }
    .stat-card mat-icon { font-size: 32px; width: 32px; height: 32px; color: #2C5F8A; }
    .stat-card div { display: flex; flex-direction: column; }
    .stat-card strong { font-size: 24px; color: #1B3A5C; }
    .stat-card span { font-size: 12px; color: #888; }
    .tab-content { padding: 16px 0; }
    .upload-categories { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
    .upload-card { cursor: pointer; text-align: center; padding: 24px; border: 2px dashed #ccc; transition: border-color 0.2s; }
    .upload-card:hover { border-color: #2C5F8A; }
    .upload-card mat-icon { font-size: 36px; width: 36px; height: 36px; }
    .upload-card strong { display: block; margin: 8px 0 4px; }
    .upload-card span { font-size: 12px; color: #888; }
    .doc-category { margin-bottom: 16px; }
    .doc-category h4 { color: #1B3A5C; display: flex; align-items: center; gap: 6px; }
    .doc-count { font-size: 13px; color: #888; font-weight: 400; }
    .empty-category { color: #aaa; font-size: 13px; font-style: italic; margin: 4px 0 0 16px; }
    .proc-completed { background: #c8e6c9 !important; }
    .proc-processing { background: #fff3e0 !important; }
    .proc-pending { background: #e0e0e0 !important; }
    .proc-failed { background: #ffcdd2 !important; }
    .proc-uploading { background: #e3f2fd !important; color: #1565c0 !important; }
    .uploading-item { background: #f8fbff; }
    .uploading-icon { color: #1976d2 !important; animation: pulse 1.5s ease-in-out infinite; }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
    .progress-done-icon { color: #4caf50; font-size: 16px; width: 16px; height: 16px; }
    .progress-steps { display: flex; align-items: center; gap: 0; margin-top: 6px; padding: 0 2px; }
    .step-dot { width: 20px; height: 20px; border-radius: 50%; background: #e0e0e0; color: #999; font-size: 10px; display: flex; align-items: center; justify-content: center; font-weight: 600; transition: all 0.3s; flex-shrink: 0; }
    .step-dot.active { background: #c8e6c9; color: #2e7d32; }
    .step-dot.current { background: #1976d2; color: white; box-shadow: 0 0 0 3px rgba(25,118,210,0.25); }
    .step-line { flex: 1; height: 2px; background: #e0e0e0; min-width: 8px; transition: background 0.3s; }
    .step-line.active { background: #4caf50; }
    .chapter-actions { display: flex; gap: 8px; margin-bottom: 16px; align-items: center; flex-wrap: wrap; }
    .spacer { flex: 1; }
    .ch-numbering { font-weight: bold; color: #2C5F8A; margin-right: 4px; }
    .ch-desc { color: #666; font-size: 13px; }
    .ch-req { font-size: 13px; background: #f5f5f5; padding: 8px; border-radius: 4px; }
    .ch-actions { display: flex; gap: 8px; margin-top: 8px; align-items: center; }
    .ai-progress-section { margin-top: 12px; padding: 12px; background: #f3e5f5; border-radius: 8px; border-left: 3px solid #7b1fa2; }
    .ai-progress-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; font-size: 13px; color: #7b1fa2; font-weight: 500; }
    .ai-progress-pct { text-align: right; font-size: 12px; font-weight: bold; color: #7b1fa2; margin-top: 4px; }
    .ai-badge { background: #fff; color: #7b1fa2; border-radius: 10px; padding: 1px 6px; font-size: 11px; font-weight: bold; margin-left: 4px; }
    .queued-icon { font-size: 18px; width: 18px; height: 18px; color: #1565c0; }
    .ai-prompt-section { margin-top: 12px; padding: 12px; background: #f3e5f5; border-radius: 8px; }
    .ai-prompt-section .full-width { width: 100%; }
    .ai-prompt-actions { display: flex; gap: 8px; align-items: center; }
    .sub-ai-prompt { margin-left: 0; }
    ::ng-deep .inserted-image { margin: 16px 0; text-align: center; }
    ::ng-deep .inserted-image img { max-width: 100%; height: auto; border-radius: 6px; box-shadow: 0 2px 8px rgba(0,0,0,0.12); }
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
    .axes-list { margin-top: 16px; }
    .axes-list-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
    .axes-list-header h3 { margin: 0; color: #1B3A5C; }
    .axis-item { padding: 16px; margin-bottom: 8px; border-left: 3px solid #7c4dff; }
    .axis-display { position: relative; }
    .axis-content { font-size: 14px; line-height: 1.6; color: #333; margin-bottom: 8px; white-space: pre-wrap; }
    .axis-meta { display: flex; gap: 16px; align-items: center; font-size: 12px; color: #888; }
    .axis-source { display: flex; align-items: center; gap: 2px; }
    .axis-date { display: flex; align-items: center; gap: 2px; }
    .axis-actions { position: absolute; top: -4px; right: -4px; display: flex; gap: 0; opacity: 0.5; transition: opacity 0.2s; }
    .axis-item:hover .axis-actions { opacity: 1; }
    .axis-actions button { width: 32px; height: 32px; }
    .axis-actions mat-icon { font-size: 18px; width: 18px; height: 18px; }
    .axis-edit { padding-top: 8px; }
    .ai-context-card { padding: 24px; margin-bottom: 20px; border-left: 4px solid #7c4dff; }
    .ai-context-header { display: flex; justify-content: space-between; align-items: flex-start; }
    .ai-context-header h3 { margin: 0; color: #1B3A5C; display: flex; align-items: center; gap: 8px; }
    .ai-context-header h3 mat-icon { color: #7c4dff; }
    .ai-context-hint { margin: 4px 0 0; font-size: 13px; color: #666; }
    .ai-context-display { margin-top: 12px; }
    .ai-context-content { white-space: pre-wrap; font-size: 14px; background: #f3e8ff; padding: 12px; border-radius: 4px; color: #333; }
    .ai-context-empty { display: flex; align-items: center; gap: 8px; margin-top: 12px; font-size: 13px; color: #999; }
    .ai-context-empty .link { color: #7c4dff; cursor: pointer; text-decoration: underline; }
    .ai-context-edit { margin-top: 12px; }
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
    .fill-pdf-btn { font-size: 11px !important; background: #b71c1c !important; color: white !important; padding: 0 10px !important; line-height: 28px !important; height: 28px !important; border-radius: 4px !important; }
    .fill-pdf-btn:disabled { opacity: 0.7; }
    .fill-pdf-btn mat-icon { font-size: 16px; width: 16px; height: 16px; margin-right: 4px; }
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
    .word-progress-card { border-left-color: #1565c0; }
    .word-progress-card .gen-progress-header h3 { color: #1565c0; }
    .word-progress-card .spin-icon { color: #1565c0; }
    .backup-progress-card { border-left-color: #00695c; }
    .backup-progress-card .gen-progress-header h3 { color: #00695c; }
    .backup-progress-card .spin-icon { color: #00695c; }
    .soutenance-progress-card { border-left-color: #e65100; }
    .soutenance-progress-card .gen-progress-header h3 { color: #e65100; }
    .soutenance-progress-card .spin-icon { color: #e65100; }
    .soutenance-options-card { border-left-color: #1565c0; padding: 16px 20px; }
    .soutenance-options-header { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
    .soutenance-options-header mat-icon { color: #1565c0; }
    .soutenance-options-header h3 { margin: 0; color: #1565c0; font-size: 16px; }
    .soutenance-options-body { display: flex; flex-direction: column; gap: 16px; }
    .soutenance-existing { display: flex; flex-direction: column; gap: 10px; }
    .soutenance-existing p { display: flex; align-items: center; gap: 8px; margin: 0; color: #2e7d32; font-size: 14px; }
    .soutenance-existing p mat-icon { color: #2e7d32; font-size: 20px; width: 20px; height: 20px; }
    .soutenance-generate { display: flex; flex-direction: column; gap: 12px; }
    .soutenance-generate p { margin: 0; font-size: 13px; color: #666; }
    .slide-count-row { display: flex; align-items: center; gap: 12px; }
    .slide-count-row label { font-size: 14px; font-weight: 500; color: #333; white-space: nowrap; }
    .slide-select { width: 200px; }
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

    /* Q&A Documents */
    .qa-container { max-width: 100%; }
    .qa-header { display: flex; align-items: flex-start; gap: 12px; margin-bottom: 20px; padding: 16px; background: linear-gradient(135deg, #e8eaf6, #e3f2fd); border-radius: 12px; }
    .qa-header mat-icon { font-size: 32px; width: 32px; height: 32px; color: #1B3A5C; margin-top: 4px; }
    .qa-header h3 { margin: 0; color: #1B3A5C; }
    .qa-subtitle { margin: 4px 0 0; font-size: 13px; color: #666; }
    .qa-chat-area { min-height: 200px; }
    .qa-messages { display: flex; flex-direction: column; gap: 16px; margin-bottom: 20px; }
    .qa-msg { display: flex; gap: 10px; }
    .qa-msg-icon { padding-top: 4px; }
    .qa-msg-icon mat-icon { font-size: 20px; width: 20px; height: 20px; }
    .qa-msg-user .qa-msg-icon mat-icon { color: #1B3A5C; }
    .qa-msg-ai .qa-msg-icon mat-icon { color: #7b1fa2; }
    .qa-msg-error .qa-msg-icon mat-icon { color: #c62828; }
    .qa-msg-body { flex: 1; min-width: 0; }
    .qa-msg-user .qa-msg-body { background: #e3f2fd; border-radius: 12px; padding: 12px 16px; }
    .qa-msg-ai .qa-msg-body { background: #f5f5f5; border-radius: 12px; padding: 12px 16px; }
    .qa-msg-error .qa-msg-body { background: #ffebee; border-radius: 12px; padding: 12px 16px; }
    .qa-msg-text { font-size: 14px; line-height: 1.7; color: #333; white-space: pre-wrap; word-break: break-word; }
    ::ng-deep .rendered-qa p { margin: 0 0 10px 0; }
    ::ng-deep .rendered-qa h2, ::ng-deep .rendered-qa h3 { font-size: 15px; font-weight: 700; color: #1B3A5C; margin: 16px 0 8px 0; }
    ::ng-deep .rendered-qa ul, ::ng-deep .rendered-qa ol { margin: 6px 0 10px 0; padding-left: 24px; }
    ::ng-deep .rendered-qa ul { list-style-type: disc; }
    ::ng-deep .rendered-qa li { margin-bottom: 4px; }
    ::ng-deep .rendered-qa strong { color: #1B3A5C; }
    ::ng-deep .rendered-qa code { background: #e8eaf6; padding: 1px 5px; border-radius: 3px; font-size: 12.5px; }
    ::ng-deep .rendered-qa table { border-collapse: collapse; width: 100%; font-size: 13px; margin: 12px 0; }
    ::ng-deep .rendered-qa th, ::ng-deep .rendered-qa td { border: 1px solid #ccc; padding: 8px 10px; text-align: left; }
    ::ng-deep .rendered-qa th { background: #e3f2fd; color: #1B3A5C; font-weight: 600; }
    .qa-msg-time { font-size: 11px; color: #aaa; display: block; margin-top: 6px; }
    .qa-sources { margin-top: 10px; border-top: 1px solid #e0e0e0; padding-top: 8px; }
    .qa-sources-header { display: flex; align-items: center; gap: 4px; cursor: pointer; font-size: 13px; color: #1976d2; font-weight: 500; }
    .qa-sources-header:hover { color: #1565c0; }
    .qa-sources-list { margin-top: 8px; display: flex; flex-direction: column; gap: 8px; }
    .qa-source-item { display: flex; gap: 8px; padding: 8px; background: white; border-radius: 8px; border: 1px solid #e0e0e0; }
    .qa-source-icon { color: #1976d2; font-size: 18px; width: 18px; height: 18px; margin-top: 2px; }
    .qa-source-info { flex: 1; min-width: 0; }
    .qa-source-info strong { font-size: 13px; color: #1B3A5C; }
    .qa-source-meta { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #888; margin-top: 2px; }
    .qa-cat-chip { font-size: 10px !important; height: 20px !important; min-height: 20px !important; }
    .qa-source-excerpt { font-size: 12px; color: #666; margin: 4px 0 0; line-height: 1.5; max-height: 40px; overflow: hidden; text-overflow: ellipsis; }
    .qa-empty { text-align: center; padding: 40px 20px; color: #888; }
    .qa-empty mat-icon { font-size: 48px; width: 48px; height: 48px; color: #ccc; }
    .qa-empty h3 { color: #1B3A5C; margin: 12px 0 4px; }
    .qa-empty p { font-size: 13px; margin: 0 0 12px; }
    .qa-examples { display: flex; flex-direction: column; gap: 8px; max-width: 600px; margin: 0 auto; }
    .qa-examples button { text-align: left; font-size: 13px; color: #1976d2; border-color: #bbdefb; }
    .qa-loading { display: flex; align-items: center; gap: 12px; padding: 16px; background: #fff3e0; border-radius: 8px; margin-bottom: 16px; }
    .qa-loading span { font-size: 13px; color: #e65100; }
    .qa-input-area { display: flex; gap: 12px; align-items: flex-start; }
    .qa-input-field { flex: 1; }

    /* Project Members */
    .add-member-card { padding: 24px; margin-bottom: 16px; }
    .add-member-card h3 { margin-top: 0; color: #1B3A5C; }
    .add-member-form { display: flex; gap: 12px; align-items: flex-start; flex-wrap: wrap; }
    .member-select-field { flex: 1; min-width: 250px; }
    .role-select-field { width: 160px; }
    .members-list .member-item { border-bottom: 1px solid #f0f0f0; height: auto !important; min-height: 56px; padding: 8px 0; }
    .members-list .member-item ::ng-deep .mdc-list-item__content { overflow: visible; }
    .member-actions { display: flex; align-items: center; gap: 4px; margin-left: auto; }
    .role-inline-field { width: 140px; font-size: 13px; }
    .role-inline-field ::ng-deep .mat-mdc-form-field-subscript-wrapper { display: none; }
    .role-badge { background: #e8eaf6; color: #3f51b5; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; }
    .inherited-chip { font-size: 10px !important; height: 20px !important; min-height: 20px !important; }
    .member-source-info { display: flex; align-items: center; gap: 8px; padding: 12px 16px; background: #e3f2fd; border-radius: 8px; margin-bottom: 16px; font-size: 13px; color: #1565c0; }
    .member-source-info mat-icon { font-size: 20px; width: 20px; height: 20px; }
    .members-section-title { display: flex; align-items: center; gap: 8px; color: #1B3A5C; font-size: 15px; margin: 20px 0 8px; }
    .members-section-title mat-icon { font-size: 20px; width: 20px; height: 20px; }
    .section-subtitle { font-size: 12px; color: #888; font-weight: 400; }
    .ws-member-item { opacity: 0.85; }
    .quick-add-btn { font-size: 12px !important; line-height: 32px !important; height: 32px !important; }
    .quick-add-btn mat-icon { font-size: 16px; width: 16px; height: 16px; margin-right: 4px; }

    /* Content Reuse Stats */
    .reuse-stats-card { padding: 24px; }
    .reuse-stats-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
    .reuse-stats-header h3 { display: flex; align-items: center; gap: 8px; color: #1B3A5C; margin: 0; font-size: 16px; }
    .reuse-stats-hint { color: #666; font-size: 13px; margin: 0 0 16px 0; }
    .reuse-timestamp { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #888; margin-bottom: 12px; }
    .reuse-timestamp mat-icon { font-size: 16px; width: 16px; height: 16px; }
    .reuse-summary-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; margin-bottom: 20px; }
    .reuse-summary-item { text-align: center; padding: 12px; background: #f5f5f5; border-radius: 8px; }
    .reuse-big-number { display: block; font-size: 24px; font-weight: bold; color: #1B3A5C; }
    .reuse-label { display: block; font-size: 12px; color: #888; margin-top: 4px; }
    .reuse-bar-chart { margin-top: 12px; }
    .reuse-bar-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
    .reuse-bar-label { width: 200px; font-size: 12px; color: #555; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex-shrink: 0; }
    .reuse-bar-track { flex: 1; height: 20px; background: #eee; border-radius: 4px; overflow: hidden; }
    .reuse-bar-fill { height: 100%; border-radius: 4px; transition: width 0.3s; min-width: 2px; }
    .reuse-bar-pct { width: 50px; font-size: 13px; font-weight: 600; text-align: right; flex-shrink: 0; }
    .reuse-empty { display: flex; align-items: center; gap: 8px; color: #666; font-size: 13px; margin-top: 12px; }
    .reuse-empty mat-icon { color: #1565c0; }

    /* AI Cost Tracking */
    .cost-tracking-link-card { padding: 24px; }
    .cost-link-content { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
    .cost-link-left { display: flex; align-items: center; gap: 16px; }
    .cost-link-icon { font-size: 36px; width: 36px; height: 36px; color: #1976d2; }
    .cost-link-content h3 { margin: 0; color: #1B3A5C; font-size: 16px; }
    .cost-link-content p { margin: 4px 0 0; color: #888; font-size: 13px; }
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
  improvementAxes: { id: string; content: string; source: string; created_at: string }[] = [];
  editingAxisId: string | null = null;
  editAxisContent = '';
  editAxisSource = '';
  editingAiContext = false;
  aiContextDraft = '';
  private pollSub: Subscription | null = null;

  // Cached computed data to avoid method calls in template (prevents change detection loops)
  groupedChapters: { document: ResponseDocument | null; chapters: Chapter[] }[] = [];
  docsByCategory: Record<string, DocumentInfo[]> = {};

  // Track files being uploaded (shown immediately before server confirmation)
  uploadingFiles: { id: string; filename: string; category: string; progress: number; status: 'uploading' | 'server_processing' | 'failed'; error?: string }[] = [];

  // Upload queue to avoid flooding the server with concurrent requests
  private _uploadQueue: { file: File; category: string }[] = [];
  private _activeUploads = 0;
  private readonly MAX_CONCURRENT_UPLOADS = 2;
  private _refreshTimer: ReturnType<typeof setTimeout> | null = null;

  // Per-chapter AI state
  aiProcessing: Record<string, boolean> = {};
  aiProgress: Record<string, { status: string; step: string; progress: number; message: string }> = {};
  private aiPollSubs: Record<string, Subscription> = {};
  aiPromptVisible: Record<string, boolean> = {};

  // Bulk AI generation state
  bulkGenerating = false;
  bulkGenProgress = 0;
  bulkGenDone = 0;
  bulkGenTotal = 0;
  bulkGenMessage = '';
  private bulkGenCancelled = false;

  // Performance: caches for template bindings
  private markdownCache = new Map<string, string>();
  private wordCountCache = new Map<string, number>();
  aiPromptText: Record<string, string> = {};

  // Document Q&A
  qaMessages: { role: 'user' | 'assistant' | 'error'; content: string; sources?: any[]; timestamp: Date; _sourcesOpen?: boolean }[] = [];
  qaInput = '';
  qaLoading = false;

  // Project members & access control
  projectMembers: any[] = [];
  isAdmin = false;
  isProjectOwner = false;
  canManageProject = false;  // owner or admin

  // Content Reuse Stats
  reuseStats: any = null;
  loadingReuseStats = false;


  allCategories = [
    { value: 'old_rfp', label: 'Ancien AO', desc: 'Documents de l\'ancien appel d\'offres', icon: 'history', color: '#1976d2' },
    { value: 'old_response', label: 'Ancienne Réponse', desc: 'Réponse à l\'ancien AO', icon: 'reply', color: '#388e3c' },
    { value: 'new_rfp', label: 'Nouvel AO', desc: 'Documents du nouvel appel d\'offres', icon: 'fiber_new', color: '#d32f2f' },
    { value: 'new_response', label: 'Notre Réponse', desc: 'Notre réponse à analyser', icon: 'task', color: '#7b1fa2' },
    { value: 'inspiration', label: 'Inspiration', desc: 'Réponses d\'autres clients pour inspiration (anonymisées automatiquement)', icon: 'lightbulb', color: '#f57c00' },
  ];
  categories = this.allCategories.slice(0, 3);

  constructor(
    private route: ActivatedRoute,
    private api: ApiService,
    private authService: AuthService,
    private snackBar: MatSnackBar,
    private router: Router,
  ) {
    this.isAdmin = this.authService.isAdmin();
  }

  ngOnInit(): void {
    this.projectId = this.route.snapshot.paramMap.get('projectId') || '';
    this.loadAll();
    // Load persisted content reuse stats on init
    this.api.getContentReuseStatsLatest(this.projectId).subscribe({
      next: (res) => {
        if (res.result) {
          this.reuseStats = res.result;
        }
      },
    });
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
    // Resume backup polling if already running
    this.api.getBackupStatus(this.projectId).subscribe({
      next: (status) => {
        if (status.status === 'running') {
          this.exportingBackup = true;
          this.backupProgress = status;
          this.startBackupPolling();
        }
      },
    });
    // Resume word export polling if already running
    this.api.getWordStatus(this.projectId).subscribe({
      next: (status) => {
        if (status.status === 'running') {
          this.exportingWord = true;
          this.wordProgress = status;
          this.startWordPolling();
        }
      },
    });
    // Resume soutenance polling if already running
    this.api.getSoutenanceStatus(this.projectId).subscribe({
      next: (status) => {
        if (status.status === 'running') {
          this.exportingSoutenance = true;
          this.soutenanceProgress = status;
          this.startSoutenancePolling();
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
    this.stopBackupPolling();
    this.stopWordPolling();
    this.stopSoutenancePolling();
    // Stop all per-chapter AI polls
    for (const sub of Object.values(this.aiPollSubs)) {
      sub.unsubscribe();
    }
    this.aiPollSubs = {};
  }

  loadAll(): void {
    this.loading = true;
    // Clear caches on reload
    this.markdownCache.clear();
    this.wordCountCache.clear();
    this.api.getProject(this.projectId).subscribe({
      next: (p) => {
        this.project = p;
        this.aiContextDraft = p.ai_context || '';
        this.isProjectOwner = p.current_user_role === 'owner';
        this.canManageProject = this.isAdmin || this.isProjectOwner;
        this.loading = false;
        if (p.enabled_categories && p.enabled_categories.length) {
          this.categories = this.allCategories.filter(c => p.enabled_categories.includes(c.value));
        }
      },
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
    this.api.getProjectMembers(this.projectId).subscribe({
      next: (m) => this.projectMembers = m,
      error: () => {},
    });
    this.loadImprovementAxes();
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
          return;
        }

        // Use db_status as source of truth for completion.
        // This avoids the delay between Redis progress reaching 100% and DB commit.
        const allDone = res.progress.every(p => {
          const dbStatus = (p as any).db_status;
          if (dbStatus === 'completed' || dbStatus === 'failed') return true;
          if (p.step === 'completed' || p.step === 'failed' || p.step === 'stalled') return true;
          return false;
        });

        if (allDone) {
          // Also update document list to sync statuses from DB
          this.api.getDocuments(this.projectId).subscribe({
            next: (d) => {
              this.documents = d;
              this._refreshDocsByCategory();
              // Only stop polling if DB confirms no more pending/processing docs
              const stillActive = d.some(doc =>
                doc.processing_status === 'pending' || doc.processing_status === 'processing'
              );
              if (!stillActive) {
                this.stopPolling();
                this.progressMap = {};
                this.loadAll();
              }
            },
          });
        } else {
          // While processing, also refresh document statuses periodically
          // so that the status chip updates in near real-time
          this.api.getDocuments(this.projectId).subscribe({
            next: (d) => { this.documents = d; this._refreshDocsByCategory(); },
          });
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

  /**
   * Get the most up-to-date status for a document by combining
   * the DB status from the document list with real-time progress data.
   * Progress data's db_status is fresher than the document list
   * (which is only refreshed periodically).
   */
  getEffectiveStatus(doc: DocumentInfo): string {
    const prog = this.progressMap[doc.id];
    if (prog?.db_status) {
      return prog.db_status;
    }
    return doc.processing_status;
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
    const input = event.target as HTMLInputElement;
    const files = input.files;
    if (!files) return;
    for (let i = 0; i < files.length; i++) {
      this._uploadQueue.push({ file: files[i], category });
    }
    this._processUploadQueue();
    // Reset input so re-selecting the same file works
    input.value = '';
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
  }

  onDrop(event: DragEvent, category: string): void {
    event.preventDefault();
    const files = event.dataTransfer?.files;
    if (!files) return;
    for (let i = 0; i < files.length; i++) {
      this._uploadQueue.push({ file: files[i], category });
    }
    this._processUploadQueue();
  }

  private _processUploadQueue(): void {
    while (this._activeUploads < this.MAX_CONCURRENT_UPLOADS && this._uploadQueue.length > 0) {
      const item = this._uploadQueue.shift()!;
      this._activeUploads++;
      this._uploadFileWithProgress(item.file, item.category);
    }
  }

  // Collect completed tracking IDs to clean up in one batch refresh
  private _completedTrackingIds: string[] = [];

  private _schedulePostUploadRefresh(trackingId: string): void {
    this._completedTrackingIds.push(trackingId);
    if (this._refreshTimer) { clearTimeout(this._refreshTimer); }
    this._refreshTimer = setTimeout(() => {
      this._refreshTimer = null;
      const ids = [...this._completedTrackingIds];
      this._completedTrackingIds = [];
      // Single batched refresh for all completed uploads
      this.api.getDocuments(this.projectId).subscribe({
        next: (d) => {
          this.documents = d;
          this._refreshDocsByCategory();
          this.uploadingFiles = this.uploadingFiles.filter(f => !ids.includes(f.id));
          const hasProcessing = d.some(doc => doc.processing_status === 'pending' || doc.processing_status === 'processing');
          if (hasProcessing) { this.startPolling(); }
        },
      });
      this.api.getStatistics(this.projectId).subscribe({ next: (s) => this.stats = s });
    }, 500);
  }

  private _uploadFileWithProgress(file: File, category: string): void {
    const trackingId = 'upload_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
    const entry = { id: trackingId, filename: file.name, category, progress: 0, status: 'uploading' as const };
    this.uploadingFiles = [...this.uploadingFiles, entry];

    const { progress$, response$ } = this.api.uploadDocumentWithProgress(this.projectId, file, category);

    progress$.subscribe({
      next: (pct) => {
        const idx = this.uploadingFiles.findIndex(f => f.id === trackingId);
        if (idx >= 0) {
          this.uploadingFiles[idx] = { ...this.uploadingFiles[idx], progress: pct };
          this.uploadingFiles = [...this.uploadingFiles];
        }
      },
    });

    response$.subscribe({
      next: () => {
        this._activeUploads--;
        this._processUploadQueue();
        // Upload done → file is now server-side, switch to "processing" state briefly
        const idx = this.uploadingFiles.findIndex(f => f.id === trackingId);
        if (idx >= 0) {
          this.uploadingFiles[idx] = { ...this.uploadingFiles[idx], status: 'server_processing', progress: 100 };
          this.uploadingFiles = [...this.uploadingFiles];
        }
        this.snackBar.open(`${file.name} envoyé`, 'OK', { duration: 2000 });
        // Debounce the refresh: wait 500ms so multiple completions batch into one call
        this._schedulePostUploadRefresh(trackingId);
      },
      error: (err) => {
        this._activeUploads--;
        this._processUploadQueue();
        const idx = this.uploadingFiles.findIndex(f => f.id === trackingId);
        if (idx >= 0) {
          this.uploadingFiles[idx] = { ...this.uploadingFiles[idx], status: 'failed', error: err.error?.detail || 'Erreur upload' };
          this.uploadingFiles = [...this.uploadingFiles];
        }
        this.snackBar.open(err.error?.detail || 'Erreur upload', 'OK', { duration: 3000 });
        // Auto-remove failed entry after 5s
        setTimeout(() => {
          this.uploadingFiles = this.uploadingFiles.filter(f => f.id !== trackingId);
        }, 5000);
      },
    });
  }

  getUploadingByCategory(category: string): typeof this.uploadingFiles {
    return this.uploadingFiles.filter(f => f.category === category);
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

  renderMarkdown = (text: string) => renderMarkdown(text, (id: string) => this.api.getImageUrl(id));

  /** Cached markdown rendering: avoids re-rendering on every change detection cycle. */
  getCachedMarkdown(id: string, content: string): string {
    if (!content) return '';
    const cached = this.markdownCache.get(id);
    if (cached !== undefined) return cached;
    // Truncate content preview to first 2000 chars for dashboard performance
    const truncated = content.length > 2000 ? content.slice(0, 2000) + '\n\n*[...]*' : content;
    const html = renderMarkdown(truncated, (imgId: string) => this.api.getImageUrl(imgId));
    this.markdownCache.set(id, html);
    return html;
  }

  /** Cached word count to avoid split() on every change detection cycle. */
  getWordCount(content: string): number {
    if (!content) return 0;
    const cached = this.wordCountCache.get(content);
    if (cached !== undefined) return cached;
    const count = content.split(/\s+/).filter(w => w.length > 0).length;
    this.wordCountCache.set(content, count);
    return count;
  }

  // ── Bulk AI generation for selected chapters ──

  generateSelectedChapters(): void {
    if (this.selectedChapters.size === 0) return;
    const ids = Array.from(this.selectedChapters);
    this.bulkGenerating = true;
    this.bulkGenCancelled = false;
    this.bulkGenTotal = ids.length;
    this.bulkGenDone = 0;
    this.bulkGenProgress = 0;
    this.bulkGenMessage = 'Lancement de la generation...';

    // Mark all selected as processing
    for (const id of ids) {
      this.aiProcessing[id] = true;
      this.aiProgress[id] = { status: 'queued', step: 'queued', progress: 0, message: 'En file d\'attente...' };
    }

    const onChapterDone = () => {
      this.bulkGenDone++;
      this.bulkGenProgress = Math.round(100 * this.bulkGenDone / this.bulkGenTotal);
      this.bulkGenMessage = `${this.bulkGenDone}/${this.bulkGenTotal} chapitres generes`;
      if (this.bulkGenDone >= this.bulkGenTotal) {
        this.bulkGenerating = false;
        this.snackBar.open(`${this.bulkGenDone} chapitre(s) genere(s)`, 'OK', { duration: 5000 });
        this.loadAll();
      }
    };

    // Use controlled concurrency (max 3 parallel)
    this._launchBulkWithConcurrency(ids, onChapterDone, 3);
  }

  private _launchBulkWithConcurrency(
    chapterIds: string[], onChapterDone: () => void, maxConcurrent: number,
  ): void {
    let running = 0;
    let index = 0;

    const launchNext = () => {
      while (running < maxConcurrent && index < chapterIds.length && !this.bulkGenCancelled) {
        const id = chapterIds[index++];
        const chapterTitle = this._findChapter(id)?.title || '';
        this.bulkGenMessage = `Generation: ${chapterTitle || 'chapitre ' + index}...`;
        running++;
        this.api.generateChapterContent(id, 'generate', '').subscribe({
          next: () => {
            this._startAiPolling(id, () => {
              running--;
              // Clear markdown cache for this chapter (content changed)
              this.markdownCache.delete(id);
              this.wordCountCache.clear();
              onChapterDone();
              launchNext();
            });
          },
          error: (err) => {
            this.aiProcessing[id] = false;
            delete this.aiProgress[id];
            running--;
            onChapterDone();
            launchNext();
          },
        });
      }
    };

    launchNext();
  }

  cancelBulkGenerate(): void {
    this.bulkGenCancelled = true;
    this.bulkGenerating = false;
    this.snackBar.open('Generations restantes annulees', 'OK', { duration: 3000 });
  }

  // ── Per-chapter AI actions ──

  toggleAiPrompt(chapterId: string): void {
    this.aiPromptVisible[chapterId] = !this.aiPromptVisible[chapterId];
  }

  getAiGenerateTooltip(ch: Chapter): string {
    if (ch.children?.length) {
      return `Generer le contenu du chapitre et de ses ${ch.children.length} sous-chapitres`;
    }
    return 'Generer le contenu a partir de l\u2019AO et de l\u2019ancienne reponse';
  }

  aiGenerate(chapterId: string): void {
    // Find the chapter to check for children
    const chapter = this._findChapter(chapterId);
    const allIds = [chapterId];
    if (chapter?.children?.length) {
      for (const sub of chapter.children) {
        allIds.push(sub.id);
      }
    }
    this._launchAiGenerate(allIds, 'generate');
  }

  aiCustomPrompt(chapterId: string): void {
    const prompt = this.aiPromptText[chapterId];
    if (!prompt) return;
    this.aiPromptVisible[chapterId] = false;
    this.aiPromptText[chapterId] = '';
    this._launchAiGenerate([chapterId], 'custom', prompt);
  }

  private _launchAiGenerate(chapterIds: string[], action: string, customPrompt: string = ''): void {
    // Mark all as processing immediately
    for (const id of chapterIds) {
      this.aiProcessing[id] = true;
      this.aiProgress[id] = { status: 'running', step: 'starting', progress: 0, message: 'Lancement de la generation...' };
    }

    // Track how many are pending so we reload only once all are done
    let pending = chapterIds.length;
    const onDone = () => {
      pending--;
      if (pending <= 0) {
        this.loadAll();
      }
    };

    // Launch with controlled concurrency (max 3 parallel API calls)
    this._launchWithConcurrency(chapterIds, action, customPrompt, onDone, 3);
  }

  private _launchWithConcurrency(
    chapterIds: string[], action: string, customPrompt: string,
    onDone: () => void, maxConcurrent: number,
  ): void {
    let running = 0;
    let index = 0;

    const launchNext = () => {
      while (running < maxConcurrent && index < chapterIds.length) {
        const id = chapterIds[index++];
        running++;
        this.api.generateChapterContent(id, action, customPrompt).subscribe({
          next: () => {
            this._startAiPolling(id, () => {
              running--;
              onDone();
              launchNext();
            });
          },
          error: (err) => {
            this.aiProcessing[id] = false;
            delete this.aiProgress[id];
            this.snackBar.open(err.error?.detail || 'Erreur generation', 'OK', { duration: 5000 });
            running--;
            onDone();
            launchNext();
          },
        });
      }
    };

    launchNext();
  }

  private _findChapter(chapterId: string): Chapter | null {
    for (const group of this.groupedChapters) {
      for (const ch of group.chapters) {
        if (ch.id === chapterId) return ch;
        for (const sub of (ch.children || [])) {
          if (sub.id === chapterId) return sub;
        }
      }
    }
    return null;
  }

  private _startAiPolling(chapterId: string, onComplete?: () => void): void {
    this._stopAiPolling(chapterId);
    // Use longer interval (3s) to reduce HTTP load with many chapters polling simultaneously
    this.aiPollSubs[chapterId] = timer(500, 3000).pipe(
      switchMap(() => this.api.getChapterGenStatus(chapterId))
    ).subscribe({
      next: (status) => {
        if (status.status === 'completed') {
          this._stopAiPolling(chapterId);
          this.aiProcessing[chapterId] = false;
          delete this.aiProgress[chapterId];
          onComplete?.();
        } else if (status.status === 'error') {
          this._stopAiPolling(chapterId);
          this.aiProcessing[chapterId] = false;
          delete this.aiProgress[chapterId];
          this.snackBar.open(status.message || 'Erreur generation', 'OK', { duration: 5000 });
          onComplete?.();
        } else {
          this.aiProgress[chapterId] = status;
        }
      },
    });
  }

  private _stopAiPolling(chapterId: string): void {
    this.aiPollSubs[chapterId]?.unsubscribe();
    delete this.aiPollSubs[chapterId];
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
    this.snackBar.open('Generation de l\'Excel en cours (informations de l\'ancienne reponse)...', '', { duration: 60000 });
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
        this._showBlobError(err, 'Erreur lors de la generation de l\'Excel');
      },
    });
  }

  fillAndDownloadPdf(rd: any): void {
    rd._fillingPdf = true;
    this.snackBar.open('Generation du PDF en cours (informations de l\'ancienne reponse)...', '', { duration: 60000 });
    this.api.fillPdfDocument(this.projectId, rd.id).subscribe({
      next: (blob: Blob) => {
        rd._fillingPdf = false;
        this.snackBar.dismiss();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${rd.title.replace(/[^a-zA-Z0-9_-]/g, '_')}_rempli.pdf`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        this.snackBar.open('PDF rempli telecharge avec succes !', 'OK', { duration: 5000 });
      },
      error: (err) => {
        rd._fillingPdf = false;
        this.snackBar.dismiss();
        this._showBlobError(err, 'Erreur lors de la generation du PDF');
      },
    });
  }

  /** Parse error detail from blob responses (responseType: 'blob' returns errors as Blob too). */
  private _showBlobError(err: any, fallback: string): void {
    if (err.error instanceof Blob) {
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const json = JSON.parse(reader.result as string);
          this.snackBar.open(json.detail || fallback, 'OK', { duration: 8000 });
        } catch {
          this.snackBar.open(fallback, 'OK', { duration: 8000 });
        }
      };
      reader.readAsText(err.error);
    } else {
      const detail = err.error?.detail || fallback;
      this.snackBar.open(detail, 'OK', { duration: 8000 });
    }
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

  loadImprovementAxes(): void {
    this.api.getImprovementAxes(this.projectId).subscribe({
      next: (res) => this.improvementAxes = res.axes || [],
      error: () => {},
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
        this.loadImprovementAxes();
      },
    });
  }

  startEditAxis(axis: any): void {
    this.editingAxisId = axis.id;
    this.editAxisContent = axis.content;
    this.editAxisSource = axis.source || '';
  }

  saveEditAxis(axis: any): void {
    if (!this.editAxisContent.trim()) return;
    this.api.updateImprovementAxis(this.projectId, axis.id, this.editAxisContent, this.editAxisSource).subscribe({
      next: () => {
        this.snackBar.open('Axe mis à jour', 'OK', { duration: 2000 });
        this.editingAxisId = null;
        this.loadImprovementAxes();
      },
      error: (err) => this.snackBar.open(err.error?.detail || 'Erreur', 'OK', { duration: 3000 }),
    });
  }

  deleteAxis(axis: any): void {
    if (!confirm('Supprimer cet axe d\'amélioration ?')) return;
    this.api.deleteImprovementAxis(this.projectId, axis.id).subscribe({
      next: () => {
        this.snackBar.open('Axe supprimé', 'OK', { duration: 2000 });
        this.loadImprovementAxes();
      },
      error: (err) => this.snackBar.open(err.error?.detail || 'Erreur', 'OK', { duration: 3000 }),
    });
  }

  saveAiContext(): void {
    this.api.updateProject(this.projectId, { ai_context: this.aiContextDraft }).subscribe({
      next: () => {
        this.snackBar.open('Contexte IA enregistré', 'OK', { duration: 2000 });
        if (this.project) this.project.ai_context = this.aiContextDraft;
        this.editingAiContext = false;
      },
      error: (err) => this.snackBar.open(err.error?.detail || 'Erreur', 'OK', { duration: 3000 }),
    });
  }

  setContextMode(mode: string): void {
    if (this.project?.context_mode === mode) return;
    this.api.updateProject(this.projectId, { context_mode: mode }).subscribe({
      next: () => {
        if (this.project) this.project.context_mode = mode;
        this.snackBar.open(
          mode === 'full' ? 'Mode contexte complet activé' : 'Mode RAG activé',
          'OK', { duration: 2000 },
        );
      },
      error: (err) => this.snackBar.open(err.error?.detail || 'Erreur', 'OK', { duration: 3000 }),
    });
  }

  exportingWord = false;
  cancellingWord = false;
  wordProgress: { status: string; step: string; progress: number; message: string } | null = null;
  private wordPollSub: Subscription | null = null;

  cancelWordExport(): void {
    this.cancellingWord = true;
    this.stopWordPolling();
    this.api.cancelWordExport(this.projectId).subscribe({
      next: () => {
        this.exportingWord = false;
        this.cancellingWord = false;
        this.wordProgress = null;
        this.snackBar.open('Export Word annule', 'OK', { duration: 3000 });
      },
      error: () => {
        // Even on error, reset the UI so user isn't stuck
        this.exportingWord = false;
        this.cancellingWord = false;
        this.wordProgress = null;
        this.snackBar.open('Export Word annule', 'OK', { duration: 3000 });
      },
    });
  }

  exportWord(): void {
    this.exportingWord = true;
    this.wordProgress = { status: 'running', step: 'starting', progress: 0, message: 'Lancement de l\'export Word...' };
    this.api.exportWord(this.projectId).subscribe({
      next: () => {
        this.startWordPolling();
      },
      error: (err) => {
        this.snackBar.open(err.error?.detail || 'Erreur export', 'OK', { duration: 5000 });
        this.exportingWord = false;
        this.wordProgress = null;
      },
    });
  }

  private startWordPolling(): void {
    this.stopWordPolling();
    this.wordPollSub = timer(500, 1500).pipe(
      switchMap(() => this.api.getWordStatus(this.projectId))
    ).subscribe({
      next: (status) => {
        if (status.status === 'completed') {
          this.wordProgress = { status: 'running', step: 'downloading', progress: 100, message: 'Telechargement du fichier...' };
          this.stopWordPolling();
          this.api.downloadWord(this.projectId).subscribe({
            next: (blob) => {
              const url = window.URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = `reponse_ao_${this.project?.rfp_reference || 'export'}.docx`;
              a.click();
              window.URL.revokeObjectURL(url);
              this.exportingWord = false;
              this.wordProgress = null;
              this.snackBar.open('Export Word telecharge', 'OK', { duration: 3000 });
              this.api.clearWordProgress(this.projectId).subscribe();
            },
            error: () => {
              this.exportingWord = false;
              this.wordProgress = null;
              this.snackBar.open('Erreur telechargement Word', 'OK', { duration: 5000 });
              this.api.clearWordProgress(this.projectId).subscribe();
            },
          });
        } else if (status.status === 'error') {
          this.stopWordPolling();
          this.exportingWord = false;
          this.snackBar.open(status.message || 'Erreur export Word', 'OK', { duration: 5000 });
          this.wordProgress = null;
          this.api.clearWordProgress(this.projectId).subscribe();
        } else if (status.status === 'running') {
          this.wordProgress = status;
        }
      },
    });
  }

  private stopWordPolling(): void {
    this.wordPollSub?.unsubscribe();
    this.wordPollSub = null;
  }

  exportingBackup = false;
  backupProgress: { status: string; step: string; progress: number; message: string } | null = null;
  private backupPollSub: Subscription | null = null;

  exportBackup(): void {
    this.exportingBackup = true;
    this.backupProgress = { status: 'running', step: 'starting', progress: 0, message: 'Lancement de l\'export...' };
    this.api.exportBackup(this.projectId).subscribe({
      next: () => {
        this.startBackupPolling();
      },
      error: (err) => {
        this.snackBar.open(err.error?.detail || 'Erreur export', 'OK', { duration: 5000 });
        this.exportingBackup = false;
        this.backupProgress = null;
      },
    });
  }

  private startBackupPolling(): void {
    this.stopBackupPolling();
    this.backupPollSub = timer(500, 1500).pipe(
      switchMap(() => this.api.getBackupStatus(this.projectId))
    ).subscribe({
      next: (status) => {
        if (status.status === 'completed') {
          this.backupProgress = { status: 'running', step: 'downloading', progress: 100, message: 'Telechargement du fichier...' };
          this.stopBackupPolling();
          this.api.downloadBackup(this.projectId).subscribe({
            next: (blob) => {
              const url = window.URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = `backup_${this.project?.name || 'export'}.zip`;
              a.click();
              window.URL.revokeObjectURL(url);
              this.exportingBackup = false;
              this.backupProgress = null;
              this.snackBar.open('Backup telecharge', 'OK', { duration: 3000 });
              this.api.clearBackupProgress(this.projectId).subscribe();
            },
            error: () => {
              this.exportingBackup = false;
              this.backupProgress = null;
              this.snackBar.open('Erreur telechargement backup', 'OK', { duration: 5000 });
              this.api.clearBackupProgress(this.projectId).subscribe();
            },
          });
        } else if (status.status === 'error') {
          this.stopBackupPolling();
          this.exportingBackup = false;
          this.snackBar.open(status.message || 'Erreur export', 'OK', { duration: 5000 });
          this.backupProgress = null;
          this.api.clearBackupProgress(this.projectId).subscribe();
        } else if (status.status === 'running') {
          this.backupProgress = status;
        }
      },
    });
  }

  private stopBackupPolling(): void {
    this.backupPollSub?.unsubscribe();
    this.backupPollSub = null;
  }

  // ── Soutenance ──
  exportingSoutenance = false;
  soutenanceProgress: { status: string; step: string; progress: number; message: string } | null = null;
  private soutenancePollSub: Subscription | null = null;
  showSoutenanceOptions = false;
  soutenanceExists = false;
  selectedSlideCount = 35;

  handleSoutenanceClick(): void {
    this.api.checkSoutenanceExists(this.projectId).subscribe({
      next: (res) => {
        if (res.exists) {
          this.soutenanceExists = true;
          this.showSoutenanceOptions = true;
        } else {
          this.soutenanceExists = false;
          this.showSoutenanceOptions = true;
        }
      },
      error: () => {
        this.soutenanceExists = false;
        this.showSoutenanceOptions = true;
      },
    });
  }

  goToSoutenance(): void {
    this.showSoutenanceOptions = false;
    this.router.navigate(['/project', this.projectId, 'soutenance']);
  }

  launchSoutenanceGeneration(): void {
    this.showSoutenanceOptions = false;
    this.exportingSoutenance = true;
    this.soutenanceProgress = { status: 'running', step: 'starting', progress: 0, message: 'Lancement de la preparation de soutenance...' };
    this.api.exportSoutenance(this.projectId, this.selectedSlideCount).subscribe({
      next: () => {
        this.startSoutenancePolling();
      },
      error: (err) => {
        this.snackBar.open(err.error?.detail || 'Erreur generation soutenance', 'OK', { duration: 5000 });
        this.exportingSoutenance = false;
        this.soutenanceProgress = null;
      },
    });
  }

  cancelSoutenance(): void {
    this.stopSoutenancePolling();
    this.api.cancelSoutenance(this.projectId).subscribe();
    this.exportingSoutenance = false;
    this.soutenanceProgress = null;
    this.snackBar.open('Generation soutenance annulee', 'OK', { duration: 3000 });
  }

  private startSoutenancePolling(): void {
    this.stopSoutenancePolling();
    this.soutenancePollSub = timer(500, 2000).pipe(
      switchMap(() => this.api.getSoutenanceStatus(this.projectId))
    ).subscribe({
      next: (status) => {
        if (status.status === 'completed') {
          this.stopSoutenancePolling();
          this.exportingSoutenance = false;
          this.soutenanceProgress = null;
          this.snackBar.open('Soutenance generee ! Redirection...', 'OK', { duration: 3000 });
          this.router.navigate(['/project', this.projectId, 'soutenance']);
        } else if (status.status === 'error') {
          this.stopSoutenancePolling();
          this.exportingSoutenance = false;
          this.snackBar.open(status.message || 'Erreur generation soutenance', 'OK', { duration: 5000 });
          this.soutenanceProgress = null;
          this.api.clearSoutenanceProgress(this.projectId).subscribe();
        } else if (status.status === 'running') {
          this.soutenanceProgress = status;
        }
      },
    });
  }

  private stopSoutenancePolling(): void {
    this.soutenancePollSub?.unsubscribe();
    this.soutenancePollSub = null;
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

  // ── Document Q&A ──

  askQuestion(): void {
    const question = this.qaInput.trim();
    if (!question || this.qaLoading) return;

    this.qaMessages.push({ role: 'user', content: question, timestamp: new Date() });
    this.qaInput = '';
    this.qaLoading = true;

    this.api.documentQA(this.projectId, question).subscribe({
      next: (res) => {
        this.qaLoading = false;
        this.qaMessages.push({
          role: 'assistant',
          content: res.answer,
          sources: res.sources,
          timestamp: new Date(),
          _sourcesOpen: false,
        });
      },
      error: (err) => {
        this.qaLoading = false;
        this.qaMessages.push({
          role: 'error',
          content: err.error?.detail || 'Erreur lors de l\'interrogation de l\'IA',
          timestamp: new Date(),
        });
      },
    });
  }

  onQaKeydown(event: Event): void {
    const ke = event as KeyboardEvent;
    if (!ke.shiftKey) {
      ke.preventDefault();
      this.askQuestion();
    }
  }

  // ── Project member management ──

  getProjectSpecificMembers(): any[] {
    return this.projectMembers.filter(m => m.source === 'project');
  }

  getWorkspaceOnlyMembers(): any[] {
    return this.projectMembers.filter(m => m.source === 'workspace');
  }

  quickAddProjectMember(member: any): void {
    this.api.addProjectMember(this.projectId, member.user_id, 'editor').subscribe({
      next: () => {
        this.snackBar.open(`${member.full_name} ajouté au projet`, 'OK', { duration: 2000 });
        this.api.getProjectMembers(this.projectId).subscribe({ next: (m) => this.projectMembers = m });
      },
      error: (err) => this.snackBar.open(err.error?.detail || 'Erreur', 'OK', { duration: 3000 }),
    });
  }

  changeProjectMemberRole(member: any, newRole: string): void {
    this.api.updateProjectMemberRole(this.projectId, member.user_id, newRole).subscribe({
      next: () => {
        member.role = newRole;
        this.snackBar.open('Role mis a jour', 'OK', { duration: 2000 });
      },
      error: (err) => this.snackBar.open(err.error?.detail || 'Erreur', 'OK', { duration: 3000 }),
    });
  }

  removeProjectMember(member: any): void {
    if (!confirm(`Retirer ${member.full_name} de ce projet ?`)) return;
    this.api.removeProjectMember(this.projectId, member.user_id).subscribe({
      next: () => {
        this.snackBar.open('Membre retire du projet', 'OK', { duration: 2000 });
        this.api.getProjectMembers(this.projectId).subscribe({ next: (m) => this.projectMembers = m });
      },
      error: (err) => this.snackBar.open(err.error?.detail || 'Erreur', 'OK', { duration: 3000 }),
    });
  }

  // ── Content Reuse Stats ──

  loadContentReuseStats(): void {
    this.loadingReuseStats = true;
    this.api.getContentReuseStats(this.projectId).subscribe({
      next: (res) => {
        this.reuseStats = res;
        this.loadingReuseStats = false;
      },
      error: (err) => {
        this.snackBar.open(err.error?.detail || 'Erreur', 'OK', { duration: 4000 });
        this.loadingReuseStats = false;
      },
    });
  }

}
