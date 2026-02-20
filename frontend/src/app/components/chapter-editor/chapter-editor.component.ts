import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatDividerModule } from '@angular/material/divider';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ApiService } from '../../services/api.service';
import { Chapter } from '../../models/report.model';

@Component({
  selector: 'app-chapter-editor',
  standalone: true,
  imports: [
    CommonModule, FormsModule, RouterLink,
    MatCardModule, MatButtonModule, MatIconModule, MatInputModule, MatChipsModule,
    MatProgressSpinnerModule, MatSelectModule, MatSnackBarModule, MatDividerModule, MatTooltipModule,
  ],
  template: `
    <div class="editor-container" *ngIf="chapter">
      <div class="editor-header">
        <div class="header-left">
          <button mat-icon-button [routerLink]="['/project', projectId]"><mat-icon>arrow_back</mat-icon></button>
          <div>
            <h2>{{ chapter.title }}</h2>
            <span class="chapter-meta">{{ chapter.chapter_type }} - {{ chapter.numbering }}</span>
          </div>
        </div>
        <div class="header-actions">
          <mat-chip [class]="'status-chip-' + chapter.status">{{ statusLabel(chapter.status) }}</mat-chip>
          <mat-form-field appearance="outline" class="status-select">
            <mat-label>Statut</mat-label>
            <mat-select [(value)]="chapter.status" (selectionChange)="updateStatus()">
              <mat-option value="not_started">Non commencé</mat-option>
              <mat-option value="in_progress">En cours</mat-option>
              <mat-option value="completed">Terminé</mat-option>
              <mat-option value="needs_review">À relire</mat-option>
              <mat-option value="validated">Validé</mat-option>
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
              matTooltip="Générer le contenu en se basant sur l'AO et l'ancienne réponse">
              <mat-spinner *ngIf="generating" diameter="18"></mat-spinner>
              <mat-icon *ngIf="!generating">auto_fix_high</mat-icon> Générer
            </button>
            <button mat-raised-button color="accent" (click)="generateContent('enrich')" [disabled]="generating || !chapter.content"
              matTooltip="Enrichir le contenu existant">
              <mat-icon>auto_awesome</mat-icon> Enrichir
            </button>
            <button mat-raised-button (click)="showCustomPrompt = !showCustomPrompt"
              matTooltip="Instruction personnalisée à l'IA">
              <mat-icon>chat</mat-icon> Prompt libre
            </button>
          </div>

          <mat-card *ngIf="showCustomPrompt" class="custom-prompt-card">
            <mat-form-field appearance="outline" class="full-width">
              <mat-label>Instruction à l'IA</mat-label>
              <textarea matInput [(ngModel)]="customPrompt" rows="3"
                placeholder="Ex: Ajoute plus de détails sur la méthodologie de test..."></textarea>
            </mat-form-field>
            <button mat-raised-button color="primary" (click)="generateContent('custom')" [disabled]="!customPrompt || generating">
              Exécuter
            </button>
          </mat-card>

          <!-- Content editor -->
          <mat-card class="content-card">
            <div class="content-header">
              <h3>Contenu</h3>
              <span class="word-count" *ngIf="chapter.content">
                {{ chapter.content.split(' ').length }} mots - ~{{ Math.ceil(chapter.content.split(' ').length / 300) }} page(s)
              </span>
            </div>
            <mat-form-field appearance="outline" class="full-width">
              <textarea matInput [(ngModel)]="chapter.content" rows="25"
                placeholder="Rédigez le contenu de ce chapitre..."></textarea>
            </mat-form-field>
          </mat-card>

          <!-- Source references -->
          <mat-card *ngIf="chapter.source_references?.length" class="refs-card">
            <h4><mat-icon>link</mat-icon> Sources utilisées</h4>
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
            <h4><mat-icon>trending_up</mat-icon> Axes d'amélioration</h4>
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
    .content-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
    .content-header h3 { margin: 0; }
    .word-count { color: #888; font-size: 13px; }
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
    @media (max-width: 960px) { .editor-layout { grid-template-columns: 1fr; } }
  `],
})
export class ChapterEditorComponent implements OnInit {
  projectId = '';
  chapterId = '';
  chapter: Chapter | null = null;
  loading = true;
  saving = false;
  generating = false;
  showCustomPrompt = false;
  customPrompt = '';
  newNote = '';
  Math = Math;

  constructor(
    private route: ActivatedRoute,
    private api: ApiService,
    private snackBar: MatSnackBar,
  ) {}

  ngOnInit(): void {
    this.projectId = this.route.snapshot.paramMap.get('projectId') || '';
    this.chapterId = this.route.snapshot.paramMap.get('chapterId') || '';
    this.loadChapter();
  }

  loadChapter(): void {
    this.loading = true;
    this.api.getChapter(this.chapterId).subscribe({
      next: (ch) => { this.chapter = ch; this.loading = false; },
      error: () => { this.loading = false; },
    });
  }

  saveContent(): void {
    if (!this.chapter) return;
    this.saving = true;
    this.api.updateChapter(this.chapterId, { content: this.chapter.content, status: this.chapter.status }).subscribe({
      next: () => {
        this.snackBar.open('Contenu sauvegardé', 'OK', { duration: 2000 });
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
        this.snackBar.open('Contenu généré', 'OK', { duration: 2000 });
        this.generating = false;
        this.showCustomPrompt = false;
        this.customPrompt = '';
      },
      error: (err) => {
        this.snackBar.open(err.error?.detail || 'Erreur de génération', 'OK', { duration: 5000 });
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
        this.snackBar.open('Note ajoutée', 'OK', { duration: 1500 });
      },
    });
  }

  statusLabel(status: string): string {
    const labels: Record<string, string> = {
      not_started: 'Non commencé', in_progress: 'En cours', completed: 'Terminé',
      needs_review: 'À relire', validated: 'Validé',
    };
    return labels[status] || status;
  }

  statusIcon(status: string): string {
    const icons: Record<string, string> = {
      not_started: '○', in_progress: '◐', completed: '●', needs_review: '◑', validated: '✓',
    };
    return icons[status] || '○';
  }
}
