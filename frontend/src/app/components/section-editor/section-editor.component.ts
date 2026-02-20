import { Component, Input, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTabsModule } from '@angular/material/tabs';
import { MatChipsModule } from '@angular/material/chips';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatMenuModule } from '@angular/material/menu';
import { ReportService } from '../../services/report.service';
import { ApiService } from '../../services/api.service';
import { ReportSection, SectionStatus } from '../../models/report.model';

@Component({
  selector: 'app-section-editor',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatIconModule,
    MatTabsModule,
    MatChipsModule,
    MatSnackBarModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
    MatMenuModule,
  ],
  template: `
    <div class="section-editor">
      <!-- Header -->
      <div class="editor-header">
        <div class="header-info">
          <h1>{{ section.title }}</h1>
          <p class="section-description">{{ section.description }}</p>
          <div class="page-controls">
            @if (section.min_pages || section.max_pages) {
              <span class="page-info">
                <mat-icon>description</mat-icon>
                {{ section.min_pages || 0 }} - {{ section.max_pages || '?' }} pages attendues
              </span>
            }
            <div class="target-pages-input">
              <mat-icon matTooltip="Définissez le nombre de pages cible pour cette section. L'IA pourra vous aider à ajuster le contenu.">track_changes</mat-icon>
              <label>Pages cible :</label>
              <input
                type="number"
                [(ngModel)]="targetPages"
                (ngModelChange)="onTargetPagesChange($event)"
                min="0.5"
                max="20"
                step="0.5"
                placeholder="Ex: 2"
              />
            </div>
          </div>
        </div>

        <div class="header-actions">
          <div class="status-selector">
            <button mat-button [matMenuTriggerFor]="statusMenu" class="status-button">
              <span class="status-badge" [ngClass]="section.status">
                {{ getStatusLabel(section.status) }}
              </span>
              <mat-icon>arrow_drop_down</mat-icon>
            </button>
            <mat-menu #statusMenu="matMenu">
              <button mat-menu-item (click)="updateStatus('not_started')">
                <mat-icon class="not-started">radio_button_unchecked</mat-icon>
                Non commencé
              </button>
              <button mat-menu-item (click)="updateStatus('in_progress')">
                <mat-icon class="in-progress">pending</mat-icon>
                En cours
              </button>
              <button mat-menu-item (click)="updateStatus('completed')">
                <mat-icon class="completed">check_circle</mat-icon>
                Terminé
              </button>
              <button mat-menu-item (click)="updateStatus('needs_review')">
                <mat-icon class="needs-review">error</mat-icon>
                À relire
              </button>
            </mat-menu>
          </div>
        </div>
      </div>

      <!-- Tabs -->
      <mat-tab-group class="editor-tabs" animationDuration="200ms">
        <!-- Notes Tab -->
        <mat-tab>
          <ng-template mat-tab-label>
            <mat-icon>note_add</mat-icon>
            Notes ({{ section.notes?.length || 0 }})
          </ng-template>

          <div class="tab-content">
            <div class="notes-section">
              <div class="add-note">
                <textarea
                  [(ngModel)]="newNote"
                  placeholder="Ajoutez une note... (informations collectées, observations, idées)"
                  rows="3"
                ></textarea>
                <button
                  class="btn-primary"
                  (click)="addNote()"
                  [disabled]="!newNote.trim()"
                >
                  <mat-icon>add</mat-icon>
                  Ajouter
                </button>
              </div>

              <!-- AI Note Generation -->
              <div class="ai-note-generator">
                <div class="ai-note-header">
                  <mat-icon>auto_awesome</mat-icon>
                  <span>Générer des notes avec l'IA</span>
                </div>
                <div class="ai-note-input">
                  <textarea
                    [(ngModel)]="aiNotePrompt"
                    placeholder="Décrivez ce que vous voulez noter... (ex: 'les technologies utilisées dans le projet', 'l'organisation de l'équipe', 'les défis rencontrés')"
                    rows="2"
                  ></textarea>
                  <button
                    class="btn-secondary"
                    (click)="generateNotesWithAI()"
                    [disabled]="generatingNotes() || !aiNotePrompt.trim()"
                  >
                    @if (generatingNotes()) {
                      <mat-spinner diameter="18"></mat-spinner>
                    } @else {
                      <mat-icon>psychology</mat-icon>
                    }
                    Générer
                  </button>
                </div>
                @if (generatedNotes().length > 0) {
                  <div class="generated-notes-preview">
                    <p class="preview-label">Notes générées (cliquez pour ajouter) :</p>
                    <div class="generated-notes-list">
                      @for (note of generatedNotes(); track $index) {
                        <div class="generated-note-item" (click)="addGeneratedNote(note, $index)">
                          <mat-icon>add_circle</mat-icon>
                          <span>{{ note }}</span>
                        </div>
                      }
                    </div>
                    <button class="btn-small" (click)="addAllGeneratedNotes()">
                      <mat-icon>playlist_add</mat-icon>
                      Ajouter toutes les notes
                    </button>
                  </div>
                }
              </div>

              @if (section.notes?.length) {
                <div class="notes-list">
                  @for (note of section.notes; track note.id) {
                    <div class="note-card">
                      @if (editingNoteId === note.id) {
                        <textarea
                          [(ngModel)]="editingNoteContent"
                          rows="3"
                        ></textarea>
                        <div class="note-actions">
                          <button class="btn-small" (click)="saveEditNote(note.id)">
                            <mat-icon>check</mat-icon>
                          </button>
                          <button class="btn-small secondary" (click)="cancelEditNote()">
                            <mat-icon>close</mat-icon>
                          </button>
                        </div>
                      } @else {
                        <p class="note-content">{{ note.content }}</p>
                        <div class="note-meta">
                          <span class="note-date">
                            {{ note.created_at | date:'dd/MM/yyyy HH:mm' }}
                          </span>
                          <div class="note-actions">
                            <button class="btn-icon" (click)="startEditNote(note)" matTooltip="Modifier">
                              <mat-icon>edit</mat-icon>
                            </button>
                            <button class="btn-icon danger" (click)="deleteNote(note.id)" matTooltip="Supprimer">
                              <mat-icon>delete</mat-icon>
                            </button>
                          </div>
                        </div>
                      }
                    </div>
                  }
                </div>
              } @else {
                <div class="empty-state">
                  <mat-icon>note</mat-icon>
                  <p>Aucune note pour cette section</p>
                  <span>Ajoutez des notes pendant votre stage pour faciliter la rédaction</span>
                </div>
              }
            </div>
          </div>
        </mat-tab>

        <!-- Content Tab -->
        <mat-tab>
          <ng-template mat-tab-label>
            <mat-icon>edit</mat-icon>
            Contenu
          </ng-template>

          <div class="tab-content">
            <div class="content-section">
              <div class="content-actions">
                <button
                  class="btn-secondary"
                  (click)="generateContent()"
                  [disabled]="generatingContent() || !section.notes?.length"
                  matTooltip="Générer le contenu à partir de vos notes"
                >
                  @if (generatingContent()) {
                    <mat-spinner diameter="18"></mat-spinner>
                  } @else {
                    <mat-icon>auto_awesome</mat-icon>
                  }
                  Générer avec l'IA
                </button>
                <button
                  class="btn-secondary"
                  (click)="improveContent()"
                  [disabled]="improvingContent() || !section.content"
                  matTooltip="Reformuler de manière plus élégante, intégrer les notes et corriger les fautes"
                >
                  @if (improvingContent()) {
                    <mat-spinner diameter="18"></mat-spinner>
                  } @else {
                    <mat-icon>spellcheck</mat-icon>
                  }
                  Améliorer
                </button>
                @if (targetPages && section.content) {
                  <button
                    class="btn-secondary"
                    (click)="adjustToTargetPages()"
                    [disabled]="adjustingContent()"
                    matTooltip="Ajuster le contenu pour atteindre {{ targetPages }} page(s)"
                  >
                    @if (adjustingContent()) {
                      <mat-spinner diameter="18"></mat-spinner>
                    } @else {
                      <mat-icon>format_size</mat-icon>
                    }
                    Ajuster à {{ targetPages }} page(s)
                  </button>
                }
              </div>

              <!-- AI Custom Prompt -->
              <div class="ai-custom-prompt">
                <div class="ai-prompt-header">
                  <mat-icon>psychology</mat-icon>
                  <span>Demander à l'IA</span>
                </div>
                <div class="ai-prompt-input">
                  <textarea
                    [(ngModel)]="customPrompt"
                    placeholder="Ex: 'Reformule plus court', 'Ajoute plus de détails techniques', 'Rends le ton plus professionnel', 'Simplifie le vocabulaire'..."
                    rows="2"
                  ></textarea>
                  <button
                    class="btn-primary"
                    (click)="executeCustomPrompt()"
                    [disabled]="executingPrompt() || !customPrompt.trim() || !section.content"
                    matTooltip="Appliquer cette instruction au contenu actuel"
                  >
                    @if (executingPrompt()) {
                      <mat-spinner diameter="18"></mat-spinner>
                    } @else {
                      <mat-icon>send</mat-icon>
                    }
                    Appliquer
                  </button>
                </div>
              </div>

              <textarea
                class="content-editor"
                [(ngModel)]="section.content"
                (ngModelChange)="onContentChange($event)"
                placeholder="Rédigez le contenu de cette section..."
                rows="15"
              ></textarea>

              <div class="content-stats">
                <span>{{ wordCount }} mots</span>
                <span>{{ charCount }} caractères</span>
                @if (targetPages) {
                  <span class="page-estimate" [class.over-limit]="estimatedPages > targetPages" [class.under-limit]="estimatedPages < targetPages * 0.8">
                    ~{{ estimatedPages.toFixed(1) }} page(s) estimée(s) / {{ targetPages }} cible
                  </span>
                }
              </div>
            </div>
          </div>
        </mat-tab>

        <!-- Questions Tab -->
        <mat-tab>
          <ng-template mat-tab-label>
            <mat-icon>help_outline</mat-icon>
            Questions
          </ng-template>

          <div class="tab-content">
            <div class="questions-section">
              <div class="questions-header">
                <p>Questions à poser pendant votre stage pour enrichir cette section</p>
                <button
                  class="btn-primary"
                  (click)="generateQuestions()"
                  [disabled]="generatingQuestions()"
                >
                  @if (generatingQuestions()) {
                    <mat-spinner diameter="18"></mat-spinner>
                    Génération...
                  } @else {
                    <mat-icon>psychology</mat-icon>
                    Générer des questions
                  }
                </button>
              </div>

              @if (section.generated_questions?.length) {
                <div class="questions-list">
                  @for (question of section.generated_questions; track $index) {
                    <div class="question-card">
                      <mat-icon>help</mat-icon>
                      <span>{{ question }}</span>
                    </div>
                  }
                </div>
              } @else {
                <div class="empty-state">
                  <mat-icon>quiz</mat-icon>
                  <p>Pas encore de questions suggérées</p>
                  <span>Cliquez sur "Générer des questions" pour obtenir des suggestions</span>
                </div>
              }
            </div>
          </div>
        </mat-tab>

        <!-- Recommendations Tab -->
        <mat-tab>
          <ng-template mat-tab-label>
            <mat-icon>lightbulb</mat-icon>
            Conseils
          </ng-template>

          <div class="tab-content">
            <div class="recommendations-section">
              <div class="recommendations-header">
                <p>Recommandations personnalisées pour améliorer cette section</p>
                <button
                  class="btn-primary"
                  (click)="generateRecommendations()"
                  [disabled]="generatingRecommendations()"
                >
                  @if (generatingRecommendations()) {
                    <mat-spinner diameter="18"></mat-spinner>
                    Analyse...
                  } @else {
                    <mat-icon>tips_and_updates</mat-icon>
                    Obtenir des conseils
                  }
                </button>
              </div>

              @if (section.recommendations?.length) {
                <div class="recommendations-list">
                  @for (rec of section.recommendations; track $index) {
                    <div class="recommendation-card">
                      <mat-icon>lightbulb</mat-icon>
                      <span>{{ rec }}</span>
                    </div>
                  }
                </div>
              } @else {
                <div class="empty-state">
                  <mat-icon>auto_awesome</mat-icon>
                  <p>Pas encore de recommandations</p>
                  <span>Cliquez sur "Obtenir des conseils" pour des suggestions personnalisées</span>
                </div>
              }
            </div>
          </div>
        </mat-tab>
      </mat-tab-group>
    </div>
  `,
  styles: [`
    .section-editor {
      height: 100%;
      display: flex;
      flex-direction: column;
      background: white;
      margin: 16px;
      border-radius: 16px;
      box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
      overflow: hidden;
    }

    .editor-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      padding: 24px;
      border-bottom: 1px solid #e0e0e0;
      background: linear-gradient(135deg, #fafafa 0%, #f5f5f5 100%);

      .header-info {
        h1 {
          font-size: 24px;
          color: #1a237e;
          margin-bottom: 8px;
        }

        .section-description {
          color: #78909c;
          font-size: 14px;
          max-width: 600px;
          line-height: 1.5;
        }

        .page-controls {
          display: flex;
          align-items: center;
          gap: 24px;
          margin-top: 12px;
          flex-wrap: wrap;
        }

        .page-info {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          font-size: 13px;
          color: #9e9e9e;

          mat-icon {
            font-size: 18px;
            width: 18px;
            height: 18px;
          }
        }

        .target-pages-input {
          display: flex;
          align-items: center;
          gap: 8px;
          background: #e3f2fd;
          padding: 6px 12px;
          border-radius: 8px;
          border: 1px solid #90caf9;

          mat-icon {
            font-size: 18px;
            width: 18px;
            height: 18px;
            color: #1976d2;
          }

          label {
            font-size: 13px;
            color: #1976d2;
            font-weight: 500;
          }

          input {
            width: 60px;
            padding: 4px 8px;
            border: 1px solid #90caf9;
            border-radius: 4px;
            font-size: 13px;
            text-align: center;

            &:focus {
              outline: none;
              border-color: #1976d2;
            }
          }
        }
      }
    }

    .status-button {
      display: flex;
      align-items: center;
      gap: 4px;
    }

    .status-badge {
      padding: 6px 12px;
      border-radius: 20px;
      font-size: 13px;
      font-weight: 500;

      &.not_started {
        background: #f5f5f5;
        color: #757575;
      }
      &.in_progress {
        background: #fff3e0;
        color: #f57c00;
      }
      &.completed {
        background: #e8f5e9;
        color: #43a047;
      }
      &.needs_review {
        background: #fce4ec;
        color: #e91e63;
      }
    }

    .editor-tabs {
      flex: 1;
      display: flex;
      flex-direction: column;

      ::ng-deep .mat-mdc-tab-body-wrapper {
        flex: 1;
      }
    }

    .tab-content {
      padding: 24px;
      height: 100%;
      overflow-y: auto;
    }

    // Notes styles
    .add-note {
      display: flex;
      gap: 12px;
      margin-bottom: 24px;

      textarea {
        flex: 1;
        padding: 12px 16px;
        border: 2px solid #e0e0e0;
        border-radius: 8px;
        font-size: 14px;
        resize: none;

        &:focus {
          outline: none;
          border-color: #1976d2;
        }
      }

      button {
        align-self: flex-end;
      }
    }

    .ai-note-generator {
      background: linear-gradient(135deg, #e8f5e9 0%, #e3f2fd 100%);
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 24px;
      border: 1px solid #c8e6c9;

      .ai-note-header {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 12px;
        color: #1976d2;
        font-weight: 500;

        mat-icon {
          color: #43a047;
        }
      }

      .ai-note-input {
        display: flex;
        gap: 12px;

        textarea {
          flex: 1;
          padding: 10px 14px;
          border: 2px solid #c8e6c9;
          border-radius: 8px;
          font-size: 14px;
          resize: none;
          background: white;

          &:focus {
            outline: none;
            border-color: #43a047;
          }
        }

        button {
          align-self: flex-end;
          display: flex;
          align-items: center;
          gap: 6px;
        }
      }

      .generated-notes-preview {
        margin-top: 16px;
        padding-top: 16px;
        border-top: 1px solid #c8e6c9;

        .preview-label {
          font-size: 13px;
          color: #546e7a;
          margin-bottom: 8px;
        }

        .generated-notes-list {
          max-height: 200px;
          overflow-y: auto;
          padding-right: 8px;

          &::-webkit-scrollbar {
            width: 6px;
          }

          &::-webkit-scrollbar-track {
            background: #e8f5e9;
            border-radius: 3px;
          }

          &::-webkit-scrollbar-thumb {
            background: #a5d6a7;
            border-radius: 3px;

            &:hover {
              background: #81c784;
            }
          }
        }

        .generated-note-item {
          display: flex;
          align-items: flex-start;
          gap: 8px;
          padding: 10px 12px;
          background: white;
          border-radius: 8px;
          margin-bottom: 8px;
          cursor: pointer;
          transition: all 0.2s;
          border: 1px solid transparent;

          &:hover {
            border-color: #43a047;
            background: #f1f8e9;
          }

          mat-icon {
            color: #43a047;
            flex-shrink: 0;
          }

          span {
            color: #37474f;
            font-size: 14px;
            line-height: 1.5;
          }
        }

        button {
          margin-top: 8px;
        }
      }
    }

    .notes-list {
      display: flex;
      flex-direction: column;
      gap: 12px;
      max-height: 400px;
      overflow-y: auto;
      padding-right: 8px;

      &::-webkit-scrollbar {
        width: 8px;
      }

      &::-webkit-scrollbar-track {
        background: #f1f1f1;
        border-radius: 4px;
      }

      &::-webkit-scrollbar-thumb {
        background: #c5cae9;
        border-radius: 4px;

        &:hover {
          background: #9fa8da;
        }
      }
    }

    .note-card {
      background: #f5f7fa;
      padding: 16px;
      border-radius: 10px;
      border-left: 4px solid #1976d2;

      .note-content {
        color: #37474f;
        line-height: 1.6;
        white-space: pre-wrap;
      }

      .note-meta {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-top: 12px;
        padding-top: 12px;
        border-top: 1px solid #e0e0e0;

        .note-date {
          font-size: 12px;
          color: #9e9e9e;
        }
      }

      .note-actions {
        display: flex;
        gap: 8px;
      }

      textarea {
        width: 100%;
        padding: 12px;
        border: 2px solid #1976d2;
        border-radius: 8px;
        font-size: 14px;
        resize: none;
        margin-bottom: 12px;

        &:focus {
          outline: none;
        }
      }
    }

    .btn-icon {
      background: transparent;
      border: none;
      padding: 6px;
      border-radius: 6px;
      cursor: pointer;
      color: #78909c;

      &:hover {
        background: #e0e0e0;
        color: #37474f;
      }

      &.danger:hover {
        background: #ffebee;
        color: #e53935;
      }

      mat-icon {
        font-size: 20px;
        width: 20px;
        height: 20px;
      }
    }

    .btn-small {
      background: #1976d2;
      color: white;
      border: none;
      padding: 6px 12px;
      border-radius: 6px;
      cursor: pointer;
      display: flex;
      align-items: center;

      &.secondary {
        background: #e0e0e0;
        color: #37474f;
      }

      mat-icon {
        font-size: 18px;
        width: 18px;
        height: 18px;
      }
    }

    // Content styles
    .content-section {
      .content-actions {
        display: flex;
        gap: 12px;
        margin-bottom: 16px;

        button {
          display: flex;
          align-items: center;
          gap: 8px;
        }
      }

      .content-editor {
        width: 100%;
        min-height: 400px;
        padding: 16px;
        border: 2px solid #e0e0e0;
        border-radius: 8px;
        font-size: 14px;
        line-height: 1.7;
        resize: vertical;

        &:focus {
          outline: none;
          border-color: #1976d2;
        }
      }

      .content-stats {
        display: flex;
        gap: 16px;
        margin-top: 12px;
        font-size: 13px;
        color: #9e9e9e;

        .page-estimate {
          padding: 2px 8px;
          border-radius: 4px;
          background: #e8f5e9;
          color: #43a047;

          &.over-limit {
            background: #ffebee;
            color: #e53935;
          }

          &.under-limit {
            background: #fff3e0;
            color: #f57c00;
          }
        }
      }
    }

    // AI Custom Prompt styles
    .ai-custom-prompt {
      background: linear-gradient(135deg, #fce4ec 0%, #e8eaf6 100%);
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 16px;
      border: 1px solid #f8bbd9;

      .ai-prompt-header {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 12px;
        color: #7b1fa2;
        font-weight: 500;

        mat-icon {
          color: #9c27b0;
        }
      }

      .ai-prompt-input {
        display: flex;
        gap: 12px;

        textarea {
          flex: 1;
          padding: 10px 14px;
          border: 2px solid #e1bee7;
          border-radius: 8px;
          font-size: 14px;
          resize: none;
          background: white;

          &:focus {
            outline: none;
            border-color: #9c27b0;
          }
        }

        button {
          align-self: flex-end;
          display: flex;
          align-items: center;
          gap: 6px;
        }
      }
    }

    // Questions & Recommendations styles
    .questions-section,
    .recommendations-section {
      .questions-header,
      .recommendations-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 24px;

        p {
          color: #78909c;
          max-width: 500px;
        }

        button {
          display: flex;
          align-items: center;
          gap: 8px;
        }
      }
    }

    .questions-list,
    .recommendations-list {
      display: flex;
      flex-direction: column;
      gap: 12px;
      max-height: 400px;
      overflow-y: auto;
      padding-right: 8px;

      &::-webkit-scrollbar {
        width: 8px;
      }

      &::-webkit-scrollbar-track {
        background: #f1f1f1;
        border-radius: 4px;
      }

      &::-webkit-scrollbar-thumb {
        background: #c5cae9;
        border-radius: 4px;

        &:hover {
          background: #9fa8da;
        }
      }
    }

    .question-card,
    .recommendation-card {
      display: flex;
      align-items: flex-start;
      gap: 12px;
      padding: 16px;
      background: #f5f7fa;
      border-radius: 10px;

      mat-icon {
        color: #1976d2;
        flex-shrink: 0;
      }

      span {
        color: #37474f;
        line-height: 1.5;
      }
    }

    .recommendation-card {
      border-left: 4px solid #ff9800;

      mat-icon {
        color: #ff9800;
      }
    }

    // Empty state
    .empty-state {
      text-align: center;
      padding: 48px;
      color: #9e9e9e;

      mat-icon {
        font-size: 64px;
        width: 64px;
        height: 64px;
        margin-bottom: 16px;
        opacity: 0.5;
      }

      p {
        font-size: 16px;
        margin-bottom: 8px;
        color: #78909c;
      }

      span {
        font-size: 14px;
      }
    }

    ::ng-deep {
      .mat-mdc-tab-labels {
        background: #fafafa;
      }

      .not-started { color: #bdbdbd; }
      .in-progress { color: #ff9800; }
      .completed { color: #43a047; }
      .needs-review { color: #e91e63; }
    }
  `],
})
export class SectionEditorComponent implements OnInit {
  @Input() section!: ReportSection;

  private reportService = inject(ReportService);
  private apiService = inject(ApiService);
  private snackBar = inject(MatSnackBar);

  newNote = '';
  editingNoteId: string | null = null;
  editingNoteContent = '';
  aiNotePrompt = '';
  customPrompt = '';
  targetPages: number | null = null;

  generatingContent = signal(false);
  improvingContent = signal(false);
  generatingQuestions = signal(false);
  generatingRecommendations = signal(false);
  generatingNotes = signal(false);
  generatedNotes = signal<string[]>([]);
  executingPrompt = signal(false);
  adjustingContent = signal(false);

  // Estimation: ~500 mots par page en moyenne pour un rapport
  private readonly WORDS_PER_PAGE = 500;

  get wordCount(): number {
    return this.section.content?.split(/\s+/).filter(w => w).length || 0;
  }

  get charCount(): number {
    return this.section.content?.length || 0;
  }

  get estimatedPages(): number {
    return this.wordCount / this.WORDS_PER_PAGE;
  }

  ngOnInit(): void {
    // Charger le nombre de pages cible depuis le localStorage
    const savedTargetPages = localStorage.getItem(`target_pages_${this.section.id}`);
    if (savedTargetPages) {
      this.targetPages = parseFloat(savedTargetPages);
    }
  }

  onTargetPagesChange(value: number | null): void {
    if (value !== null && value > 0) {
      localStorage.setItem(`target_pages_${this.section.id}`, value.toString());
    } else {
      localStorage.removeItem(`target_pages_${this.section.id}`);
    }
  }

  getStatusLabel(status: SectionStatus): string {
    const labels: Record<SectionStatus, string> = {
      [SectionStatus.NOT_STARTED]: 'Non commencé',
      [SectionStatus.IN_PROGRESS]: 'En cours',
      [SectionStatus.COMPLETED]: 'Terminé',
      [SectionStatus.NEEDS_REVIEW]: 'À relire',
    };
    return labels[status];
  }

  updateStatus(status: string): void {
    this.reportService.updateSectionStatus(this.section.id, status as SectionStatus);
    this.section.status = status as SectionStatus;
  }

  addNote(): void {
    if (!this.newNote.trim()) return;
    this.reportService.addNoteToSection(this.section.id, this.newNote.trim());
    this.newNote = '';
    this.snackBar.open('Note ajoutée', 'OK', { duration: 2000 });
  }

  startEditNote(note: { id: string; content: string }): void {
    this.editingNoteId = note.id;
    this.editingNoteContent = note.content;
  }

  saveEditNote(noteId: string): void {
    this.reportService.updateNoteInSection(this.section.id, noteId, this.editingNoteContent);
    this.editingNoteId = null;
    this.editingNoteContent = '';
    this.snackBar.open('Note modifiée', 'OK', { duration: 2000 });
  }

  cancelEditNote(): void {
    this.editingNoteId = null;
    this.editingNoteContent = '';
  }

  deleteNote(noteId: string): void {
    if (confirm('Supprimer cette note ?')) {
      this.reportService.deleteNoteFromSection(this.section.id, noteId);
      this.snackBar.open('Note supprimée', 'OK', { duration: 2000 });
    }
  }

  onContentChange(content: string): void {
    this.reportService.updateSectionContent(this.section.id, content);
  }

  generateContent(): void {
    const aiConfig = this.reportService.aiConfig();
    if (!aiConfig) {
      this.snackBar.open('Veuillez configurer l\'IA dans les paramètres', 'OK', { duration: 3000 });
      return;
    }

    if (!this.section.notes?.length) {
      this.snackBar.open('Ajoutez d\'abord des notes pour générer le contenu', 'OK', { duration: 3000 });
      return;
    }

    this.generatingContent.set(true);

    const notesText = this.section.notes.map(n => n.content).join('\n\n');

    this.apiService.generateContent(
      this.section.title,
      this.section.description,
      notesText,
      this.reportService.getCompanyContext(),
      aiConfig
    ).subscribe({
      next: (response) => {
        this.section.content = response.content;
        this.reportService.updateSectionContent(this.section.id, response.content);
        this.generatingContent.set(false);
        this.snackBar.open('Contenu généré avec succès', 'OK', { duration: 3000 });
      },
      error: (error) => {
        this.generatingContent.set(false);
        this.snackBar.open('Erreur lors de la génération', 'OK', { duration: 5000 });
      }
    });
  }

  improveContent(): void {
    const aiConfig = this.reportService.aiConfig();
    if (!aiConfig) {
      this.snackBar.open('Veuillez configurer l\'IA dans les paramètres', 'OK', { duration: 3000 });
      return;
    }

    if (!this.section.content) {
      this.snackBar.open('Rédigez d\'abord du contenu à améliorer', 'OK', { duration: 3000 });
      return;
    }

    this.improvingContent.set(true);

    // Récupérer les notes pour les intégrer dans l'amélioration
    const notesText = this.section.notes?.map(n => n.content).join('\n\n') || '';

    this.apiService.improveText(
      this.section.content,
      this.section.title,
      notesText,
      aiConfig
    ).subscribe({
      next: (response) => {
        this.section.content = response.improved_text;
        this.reportService.updateSectionContent(this.section.id, response.improved_text);
        this.improvingContent.set(false);
        this.snackBar.open('Contenu amélioré et reformulé', 'OK', { duration: 3000 });
      },
      error: (error) => {
        this.improvingContent.set(false);
        this.snackBar.open('Erreur lors de l\'amélioration', 'OK', { duration: 5000 });
      }
    });
  }

  generateQuestions(): void {
    const aiConfig = this.reportService.aiConfig();
    if (!aiConfig) {
      this.snackBar.open('Veuillez configurer l\'IA dans les paramètres', 'OK', { duration: 3000 });
      return;
    }

    this.generatingQuestions.set(true);

    const notesText = this.section.notes?.map(n => n.content).join('\n') || '';
    const schoolInstructions = this.reportService.getSchoolInstructionsText();

    this.apiService.generateQuestions(
      this.section.id,
      this.section.title,
      this.section.description,
      notesText,
      this.section.content || '',
      schoolInstructions,
      aiConfig
    ).subscribe({
      next: (response) => {
        this.section.generated_questions = response.questions;
        this.reportService.updateSectionQuestions(this.section.id, response.questions);
        this.generatingQuestions.set(false);
        this.snackBar.open('Questions générées', 'OK', { duration: 3000 });
      },
      error: (error) => {
        this.generatingQuestions.set(false);
        this.snackBar.open('Erreur lors de la génération des questions', 'OK', { duration: 5000 });
      }
    });
  }

  generateRecommendations(): void {
    const aiConfig = this.reportService.aiConfig();
    if (!aiConfig) {
      this.snackBar.open('Veuillez configurer l\'IA dans les paramètres', 'OK', { duration: 3000 });
      return;
    }

    this.generatingRecommendations.set(true);

    const notesText = this.section.notes?.map(n => n.content).join('\n') || '';
    const schoolInstructions = this.reportService.getSchoolInstructionsText();

    this.apiService.generateRecommendations(
      this.section.id,
      this.section.title,
      this.section.description,
      this.section.status,
      notesText,
      this.section.content || '',
      schoolInstructions,
      aiConfig
    ).subscribe({
      next: (response) => {
        this.section.recommendations = response.recommendations;
        this.reportService.updateSectionRecommendations(this.section.id, response.recommendations);
        this.generatingRecommendations.set(false);
        this.snackBar.open('Recommandations générées', 'OK', { duration: 3000 });
      },
      error: (error) => {
        this.generatingRecommendations.set(false);
        this.snackBar.open('Erreur lors de la génération des recommandations', 'OK', { duration: 5000 });
      }
    });
  }

  generateNotesWithAI(): void {
    const aiConfig = this.reportService.aiConfig();
    if (!aiConfig) {
      this.snackBar.open('Veuillez configurer l\'IA dans les paramètres', 'OK', { duration: 3000 });
      return;
    }

    if (!this.aiNotePrompt.trim()) {
      return;
    }

    this.generatingNotes.set(true);
    this.generatedNotes.set([]);

    const existingNotes = this.section.notes?.map(n => n.content).join('\n') || '';

    this.apiService.generateNotes(
      this.section.title,
      this.section.description,
      this.aiNotePrompt,
      existingNotes,
      aiConfig
    ).subscribe({
      next: (response) => {
        this.generatedNotes.set(response.notes);
        this.generatingNotes.set(false);
        this.snackBar.open(`${response.notes.length} notes générées`, 'OK', { duration: 3000 });
      },
      error: (error) => {
        this.generatingNotes.set(false);
        this.snackBar.open('Erreur lors de la génération des notes', 'OK', { duration: 5000 });
      }
    });
  }

  addGeneratedNote(note: string, index: number): void {
    this.reportService.addNoteToSection(this.section.id, note);
    const currentNotes = this.generatedNotes();
    this.generatedNotes.set(currentNotes.filter((_, i) => i !== index));
    this.snackBar.open('Note ajoutée', 'OK', { duration: 2000 });
  }

  addAllGeneratedNotes(): void {
    const notes = this.generatedNotes();
    for (const note of notes) {
      this.reportService.addNoteToSection(this.section.id, note);
    }
    this.generatedNotes.set([]);
    this.aiNotePrompt = '';
    this.snackBar.open(`${notes.length} notes ajoutées`, 'OK', { duration: 3000 });
  }

  executeCustomPrompt(): void {
    const aiConfig = this.reportService.aiConfig();
    if (!aiConfig) {
      this.snackBar.open('Veuillez configurer l\'IA dans les paramètres', 'OK', { duration: 3000 });
      return;
    }

    if (!this.section.content || !this.customPrompt.trim()) {
      return;
    }

    this.executingPrompt.set(true);

    this.apiService.executeCustomPrompt(
      this.section.content,
      this.customPrompt,
      this.section.title,
      aiConfig
    ).subscribe({
      next: (response) => {
        this.section.content = response.content;
        this.reportService.updateSectionContent(this.section.id, response.content);
        this.executingPrompt.set(false);
        this.customPrompt = '';
        this.snackBar.open('Contenu modifié selon votre demande', 'OK', { duration: 3000 });
      },
      error: (error) => {
        this.executingPrompt.set(false);
        this.snackBar.open('Erreur lors de l\'exécution de la demande', 'OK', { duration: 5000 });
      }
    });
  }

  adjustToTargetPages(): void {
    const aiConfig = this.reportService.aiConfig();
    if (!aiConfig) {
      this.snackBar.open('Veuillez configurer l\'IA dans les paramètres', 'OK', { duration: 3000 });
      return;
    }

    if (!this.section.content || !this.targetPages) {
      return;
    }

    this.adjustingContent.set(true);

    const targetWords = Math.round(this.targetPages * this.WORDS_PER_PAGE);
    const currentWords = this.wordCount;
    const direction = currentWords > targetWords ? 'raccourcir' : 'développer';

    this.apiService.adjustContentLength(
      this.section.content,
      this.section.title,
      this.targetPages,
      targetWords,
      aiConfig
    ).subscribe({
      next: (response) => {
        this.section.content = response.content;
        this.reportService.updateSectionContent(this.section.id, response.content);
        this.adjustingContent.set(false);
        this.snackBar.open(`Contenu ajusté pour ${this.targetPages} page(s)`, 'OK', { duration: 3000 });
      },
      error: (error) => {
        this.adjustingContent.set(false);
        this.snackBar.open('Erreur lors de l\'ajustement du contenu', 'OK', { duration: 5000 });
      }
    });
  }
}
