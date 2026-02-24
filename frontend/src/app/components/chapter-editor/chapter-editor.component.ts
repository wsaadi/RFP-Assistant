import { Component, OnInit, OnDestroy, ViewEncapsulation } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatDividerModule } from '@angular/material/divider';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { ApiService } from '../../services/api.service';
import { renderMarkdown } from '../../services/markdown.service';
import { Chapter } from '../../models/report.model';

@Component({
  selector: 'app-chapter-editor',
  standalone: true,
  imports: [
    CommonModule, FormsModule, RouterLink,
    MatCardModule, MatButtonModule, MatIconModule, MatInputModule, MatChipsModule,
    MatProgressSpinnerModule, MatProgressBarModule, MatSelectModule, MatSnackBarModule,
    MatDividerModule, MatTooltipModule, MatButtonToggleModule,
  ],
  encapsulation: ViewEncapsulation.None,
  template: `
    <div class="editor-container" *ngIf="chapter">
      <div class="editor-header">
        <div class="header-left">
          <button mat-icon-button [routerLink]="['/project', projectId]"><mat-icon>arrow_back</mat-icon></button>
          <div>
            <h2>{{ chapter.title }}</h2>
            <span class="chapter-meta">{{ chapterTypeLabel(chapter.chapter_type) }}{{ chapter.numbering ? ' - ' + chapter.numbering : '' }}</span>
          </div>
        </div>
        <div class="header-actions">
          <mat-chip [class]="'status-chip-' + chapter.status">{{ statusLabel(chapter.status) }}</mat-chip>
          <mat-form-field appearance="outline" class="status-select">
            <mat-label>Statut</mat-label>
            <mat-select [(value)]="chapter.status" (selectionChange)="updateStatus()">
              <mat-option value="not_started">Non commence</mat-option>
              <mat-option value="in_progress">En cours</mat-option>
              <mat-option value="completed">Termine</mat-option>
              <mat-option value="needs_review">A relire</mat-option>
              <mat-option value="validated">Valide</mat-option>
            </mat-select>
          </mat-form-field>
          <button mat-raised-button color="primary" (click)="saveContent()" [disabled]="saving">
            <mat-icon>save</mat-icon> Sauvegarder
          </button>
        </div>
      </div>

      <div class="editor-layout">
        <!-- Main content area -->
        <div class="content-panel">
          <!-- RFP Requirement -->
          <mat-card *ngIf="chapter.rfp_requirement" class="req-card">
            <h4><mat-icon>gavel</mat-icon> Exigence de l'appel d'offres</h4>
            <p>{{ chapter.rfp_requirement }}</p>
          </mat-card>

          <!-- AI Actions -->
          <div class="ai-actions">
            <button mat-raised-button color="primary" (click)="generateContent('generate')" [disabled]="generating"
              matTooltip="Generer le contenu en se basant sur l'AO et l'ancienne reponse">
              <mat-spinner *ngIf="generating" diameter="18"></mat-spinner>
              <mat-icon *ngIf="!generating">auto_fix_high</mat-icon> Generer
            </button>
            <button mat-raised-button color="accent" (click)="generateContent('enrich')" [disabled]="generating || !chapter.content"
              matTooltip="Enrichir le contenu existant">
              <mat-icon>auto_awesome</mat-icon> Enrichir
            </button>
            <button mat-raised-button (click)="showCustomPrompt = !showCustomPrompt"
              matTooltip="Instruction personnalisee a l'IA">
              <mat-icon>chat</mat-icon> Prompt libre
            </button>
          </div>

          <mat-card *ngIf="showCustomPrompt" class="custom-prompt-card">
            <mat-form-field appearance="outline" class="full-width">
              <mat-label>Instruction a l'IA</mat-label>
              <textarea matInput [(ngModel)]="customPrompt" rows="3"
                placeholder="Ex: Ajoute plus de details sur la methodologie de test..."></textarea>
            </mat-form-field>
            <button mat-raised-button color="primary" (click)="generateContent('custom')" [disabled]="!customPrompt || generating">
              Executer
            </button>
          </mat-card>

          <!-- AI progress bar -->
          <div *ngIf="generating" class="ai-gen-progress">
            <div class="ai-gen-progress-header">
              <mat-spinner diameter="18"></mat-spinner>
              <span>Generation IA en cours...</span>
            </div>
            <mat-progress-bar mode="indeterminate" color="accent"></mat-progress-bar>
          </div>

          <!-- Content editor / preview -->
          <mat-card class="content-card">
            <div class="content-header">
              <h3>Contenu</h3>
              <div class="content-header-right">
                <span class="word-count" *ngIf="chapter.content">
                  {{ chapter.content.split(' ').length }} mots - ~{{ Math.ceil(chapter.content.split(' ').length / 300) }} page(s)
                </span>
                <mat-button-toggle-group [(value)]="editorMode" (change)="onModeChange($event.value)" class="editor-mode-toggle">
                  <mat-button-toggle value="edit"><mat-icon>edit</mat-icon> Editer</mat-button-toggle>
                  <mat-button-toggle value="preview"><mat-icon>visibility</mat-icon> Apercu</mat-button-toggle>
                  <mat-button-toggle value="anonymized" matTooltip="Vue anonymisee : ce que l'IA voit">
                    <mat-icon>security</mat-icon> Anonymise
                  </mat-button-toggle>
                </mat-button-toggle-group>
              </div>
            </div>

            <!-- Edit mode -->
            <mat-form-field *ngIf="editorMode === 'edit'" appearance="outline" class="full-width">
              <textarea matInput [(ngModel)]="chapter.content" rows="25"
                placeholder="Redigez le contenu de ce chapitre..."></textarea>
            </mat-form-field>

            <!-- Preview mode (reconciled - real values) -->
            <div *ngIf="editorMode === 'preview' && chapter.content"
              class="rendered-content" [innerHTML]="renderMarkdown(chapter.content)"></div>
            <p *ngIf="editorMode === 'preview' && !chapter.content" class="empty-preview">
              Aucun contenu. Utilisez le mode Editer ou les outils IA pour generer du contenu.
            </p>

            <!-- Anonymized mode (what the AI sees) -->
            <div *ngIf="editorMode === 'anonymized'" class="anon-view-container">
              <div class="anon-view-banner">
                <mat-icon>security</mat-icon>
                <span>Vue anonymisee - C'est ce que l'IA voit. Les donnees sensibles sont remplacees par des placeholders.</span>
              </div>
              <div *ngIf="loadingAnonymized" class="anon-loading">
                <mat-spinner diameter="24"></mat-spinner>
                <span>Chargement de la vue anonymisee...</span>
              </div>
              <div *ngIf="!loadingAnonymized && anonymizedContent"
                class="rendered-content anon-rendered" [innerHTML]="renderMarkdown(anonymizedContent)"></div>
              <p *ngIf="!loadingAnonymized && !anonymizedContent" class="empty-preview">
                Aucun contenu a anonymiser.
              </p>
            </div>
          </mat-card>

          <!-- Source references -->
          <mat-card *ngIf="chapter.source_references?.length" class="refs-card">
            <h4><mat-icon>link</mat-icon> Sources utilisees</h4>
            <div *ngFor="let ref of chapter.source_references" class="ref-item">
              <mat-icon>description</mat-icon>
              <span>{{ ref.document }} - p.{{ ref.page }} (pertinence: {{ (ref.score * 100).toFixed(0) }}%)</span>
            </div>
          </mat-card>
        </div>

        <!-- Side panel -->
        <div class="side-panel">
          <!-- Notes -->
          <mat-card class="notes-card">
            <h4><mat-icon>sticky_note_2</mat-icon> Notes</h4>
            <div class="notes-list">
              <div *ngFor="let note of chapter.notes" class="note-item">
                <p>{{ note.content }}</p>
                <span class="note-meta">{{ note.author }} - {{ note.created_at | date:'short' }}</span>
              </div>
              <p *ngIf="!chapter.notes?.length" class="empty-notes">Aucune note</p>
            </div>
            <mat-divider></mat-divider>
            <div class="add-note">
              <mat-form-field appearance="outline" class="full-width">
                <mat-label>Ajouter une note</mat-label>
                <textarea matInput [(ngModel)]="newNote" rows="2"></textarea>
              </mat-form-field>
              <button mat-raised-button (click)="addNote()" [disabled]="!newNote">
                <mat-icon>add</mat-icon> Ajouter
              </button>
            </div>
          </mat-card>

          <!-- Improvement axes -->
          <mat-card *ngIf="chapter.improvement_axes?.length" class="axes-card">
            <h4><mat-icon>trending_up</mat-icon> Axes d'amelioration</h4>
            <div *ngFor="let axis of chapter.improvement_axes" class="axis-item">
              <p>{{ axis.content || axis }}</p>
            </div>
          </mat-card>

          <!-- Children chapters -->
          <mat-card *ngIf="chapter.children?.length" class="children-card">
            <h4><mat-icon>segment</mat-icon> Sous-chapitres</h4>
            <div *ngFor="let child of chapter.children" class="child-item"
              [routerLink]="['/project', projectId, 'chapter', child.id]">
              <mat-chip [class]="'status-' + child.status" size="small">{{ statusIcon(child.status) }}</mat-chip>
              <span>{{ child.title }}</span>
            </div>
          </mat-card>
        </div>
      </div>
    </div>

    <div *ngIf="loading" class="loading-container">
      <mat-spinner diameter="40"></mat-spinner>
    </div>
  `,
  styles: [`
    .editor-container { max-width: 1600px; margin: 0 auto; }
    .editor-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 8px; }
    .header-left { display: flex; align-items: center; gap: 8px; }
    .header-left h2 { margin: 0; color: #1B3A5C; }
    .chapter-meta { color: #888; font-size: 12px; }
    .header-actions { display: flex; align-items: center; gap: 8px; }
    .status-select { width: 150px; }
    .editor-layout { display: grid; grid-template-columns: 1fr 320px; gap: 16px; }
    .content-panel { min-width: 0; }
    .side-panel { display: flex; flex-direction: column; gap: 16px; }
    .req-card { padding: 16px; margin-bottom: 12px; background: #e3f2fd; }
    .req-card h4 { display: flex; align-items: center; gap: 6px; margin: 0 0 8px; color: #1565c0; }
    .ai-actions { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
    .custom-prompt-card { padding: 16px; margin-bottom: 12px; }
    .content-card { padding: 16px; }
    .content-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
    .content-header h3 { margin: 0; }
    .content-header-right { display: flex; align-items: center; gap: 16px; }
    .word-count { color: #888; font-size: 13px; }
    .editor-mode-toggle .mat-button-toggle-label-content { display: flex; align-items: center; gap: 4px; font-size: 13px; }
    .editor-mode-toggle mat-icon { font-size: 18px; width: 18px; height: 18px; }
    .ai-gen-progress { margin-bottom: 12px; padding: 12px 16px; background: #f3e5f5; border-radius: 8px; }
    .ai-gen-progress-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; font-size: 13px; color: #7b1fa2; font-weight: 500; }
    .rendered-content { padding: 20px; min-height: 300px; line-height: 1.7; font-size: 14px; color: #333; }
    .rendered-content h2, .rendered-content h3 { font-size: 17px; font-weight: 700; color: #1B3A5C; margin: 24px 0 10px 0; padding-bottom: 4px; border-bottom: 1px solid #e0e0e0; }
    .rendered-content h2:first-child, .rendered-content h3:first-child { margin-top: 0; }
    .rendered-content h4 { font-size: 15px; font-weight: 600; color: #2C5F8A; margin: 18px 0 8px 0; }
    .rendered-content h5 { font-size: 14px; font-weight: 600; color: #37474f; margin: 14px 0 6px 0; }
    .rendered-content p { margin: 0 0 12px 0; text-align: justify; }
    .rendered-content ul, .rendered-content ol { margin: 6px 0 12px 0; padding-left: 28px; }
    .rendered-content ul { list-style-type: disc; }
    .rendered-content ul ul { list-style-type: circle; margin: 2px 0; }
    .rendered-content ol { list-style-type: decimal; }
    .rendered-content li { margin-bottom: 4px; line-height: 1.6; }
    .rendered-content strong { color: #1B3A5C; }
    .rendered-content em { color: #555; }
    .rendered-content hr { border: none; border-top: 1px solid #ccc; margin: 20px 0; }
    .rendered-content code { background: #e8eaf6; padding: 1px 5px; border-radius: 3px; font-size: 13px; }
    .rendered-content .table-wrap { overflow-x: auto; margin: 16px 0; }
    .rendered-content table { border-collapse: collapse; width: 100%; font-size: 14px; }
    .rendered-content th, .rendered-content td { border: 1px solid #ccc; padding: 10px 12px; text-align: left; }
    .rendered-content th { background: #e3f2fd; color: #1B3A5C; font-weight: 600; }
    .rendered-content tr:nth-child(even) td { background: #fafafa; }
    .empty-preview { color: #aaa; font-style: italic; padding: 20px; }
    .full-width { width: 100%; }
    .refs-card { padding: 16px; margin-top: 12px; }
    .refs-card h4 { display: flex; align-items: center; gap: 6px; margin: 0 0 8px; }
    .ref-item { display: flex; align-items: center; gap: 6px; padding: 4px 0; font-size: 13px; color: #555; }
    .notes-card { padding: 16px; }
    .notes-card h4 { display: flex; align-items: center; gap: 6px; margin: 0 0 12px; }
    .note-item { padding: 8px; background: #fffde7; border-radius: 4px; margin-bottom: 8px; }
    .note-item p { margin: 0; font-size: 13px; }
    .note-meta { font-size: 11px; color: #888; }
    .empty-notes { color: #aaa; font-size: 13px; font-style: italic; }
    .add-note { margin-top: 12px; }
    .axes-card { padding: 16px; }
    .axis-item { padding: 8px; background: #e8f5e9; border-radius: 4px; margin-bottom: 4px; font-size: 13px; }
    .children-card { padding: 16px; }
    .child-item { display: flex; align-items: center; gap: 8px; padding: 8px; cursor: pointer; border-radius: 4px; }
    .child-item:hover { background: #f5f5f5; }
    .status-chip-not_started { background: #e0e0e0 !important; }
    .status-chip-in_progress { background: #bbdefb !important; }
    .status-chip-completed { background: #c8e6c9 !important; }
    .status-chip-needs_review { background: #fff3e0 !important; }
    .status-chip-validated { background: #b2dfdb !important; }
    .loading-container { display: flex; justify-content: center; padding: 48px; }

    /* Anonymized view */
    .anon-view-container { min-height: 300px; }
    .anon-view-banner { display: flex; align-items: center; gap: 8px; padding: 10px 16px; background: #e8f5e9; border: 1px solid #a5d6a7; border-radius: 6px; margin-bottom: 12px; font-size: 13px; color: #2e7d32; }
    .anon-view-banner mat-icon { font-size: 20px; width: 20px; height: 20px; }
    .anon-loading { display: flex; align-items: center; gap: 12px; padding: 24px; color: #666; font-size: 14px; }
    .anon-rendered { background: #f9fbe7; border: 1px dashed #c5e1a5; border-radius: 6px; }

    @media (max-width: 960px) { .editor-layout { grid-template-columns: 1fr; } }
  `],
})
export class ChapterEditorComponent implements OnInit, OnDestroy {
  projectId = '';
  chapterId = '';
  chapter: Chapter | null = null;
  loading = true;
  saving = false;
  generating = false;
  showCustomPrompt = false;
  customPrompt = '';
  newNote = '';
  editorMode: 'edit' | 'preview' | 'anonymized' = 'preview';
  Math = Math;
  renderMarkdown = renderMarkdown;

  // Anonymized view state
  anonymizedContent = '';
  loadingAnonymized = false;

  private paramSub?: Subscription;

  constructor(
    private route: ActivatedRoute,
    private api: ApiService,
    private snackBar: MatSnackBar,
  ) {}

  ngOnInit(): void {
    this.paramSub = this.route.paramMap.subscribe(params => {
      this.projectId = params.get('projectId') || '';
      const newChapterId = params.get('chapterId') || '';
      if (newChapterId !== this.chapterId) {
        this.chapterId = newChapterId;
        this.loadChapter();
      } else if (!this.chapterId) {
        this.chapterId = newChapterId;
        this.loadChapter();
      }
    });
  }

  ngOnDestroy(): void {
    this.paramSub?.unsubscribe();
  }

  loadChapter(): void {
    this.loading = true;
    this.anonymizedContent = '';
    this.api.getChapter(this.chapterId).subscribe({
      next: (ch) => { this.chapter = ch; this.loading = false; },
      error: () => { this.loading = false; },
    });
  }

  onModeChange(mode: string): void {
    if (mode === 'anonymized' && this.projectId && this.chapterId) {
      this.loadAnonymizedContent();
    }
  }

  loadAnonymizedContent(): void {
    this.loadingAnonymized = true;
    this.api.getChapterAnonymizedContent(this.projectId, this.chapterId).subscribe({
      next: (res) => {
        this.anonymizedContent = res.anonymized_content;
        this.loadingAnonymized = false;
      },
      error: () => {
        this.anonymizedContent = '';
        this.loadingAnonymized = false;
        this.snackBar.open('Erreur lors du chargement de la vue anonymisee', 'OK', { duration: 3000 });
      },
    });
  }

  saveContent(): void {
    if (!this.chapter) return;
    this.saving = true;
    this.api.updateChapter(this.chapterId, { content: this.chapter.content, status: this.chapter.status }).subscribe({
      next: () => {
        this.snackBar.open('Contenu sauvegarde', 'OK', { duration: 2000 });
        this.saving = false;
      },
      error: () => { this.saving = false; },
    });
  }

  updateStatus(): void {
    if (!this.chapter) return;
    this.api.updateChapter(this.chapterId, { status: this.chapter.status }).subscribe();
  }

  generateContent(action: string): void {
    this.generating = true;
    this.api.generateChapterContent(this.chapterId, action, this.customPrompt).subscribe({
      next: (res) => {
        if (this.chapter) {
          this.chapter.content = res.content;
        }
        this.snackBar.open('Contenu genere', 'OK', { duration: 2000 });
        this.generating = false;
        this.showCustomPrompt = false;
        this.customPrompt = '';
      },
      error: (err) => {
        this.snackBar.open(err.error?.detail || 'Erreur de generation', 'OK', { duration: 5000 });
        this.generating = false;
      },
    });
  }

  addNote(): void {
    if (!this.newNote) return;
    this.api.addChapterNote(this.chapterId, this.newNote).subscribe({
      next: (res) => {
        if (this.chapter) {
          this.chapter.notes = res.notes;
        }
        this.newNote = '';
        this.snackBar.open('Note ajoutee', 'OK', { duration: 1500 });
      },
    });
  }

  statusLabel(status: string): string {
    const labels: Record<string, string> = {
      not_started: 'Non commence', in_progress: 'En cours', completed: 'Termine',
      needs_review: 'A relire', validated: 'Valide',
    };
    return labels[status] || status;
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

  statusIcon(status: string): string {
    const icons: Record<string, string> = {
      not_started: '○', in_progress: '◐', completed: '●', needs_review: '◑', validated: '✓',
    };
    return icons[status] || '○';
  }
}
