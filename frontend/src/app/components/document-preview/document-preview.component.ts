import { Component, Input, Output, EventEmitter, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ReportService } from '../../services/report.service';
import { ReportSection, SectionStatus } from '../../models/report.model';

@Component({
  selector: 'app-document-preview',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatIconModule,
    MatExpansionModule,
    MatTooltipModule,
    MatSnackBarModule,
  ],
  template: `
    <div class="document-preview">
      <div class="preview-header">
        <div class="header-info">
          <h1>
            <mat-icon>article</mat-icon>
            Aperçu du document
          </h1>
          <p>Visualisez et éditez toutes les sections de votre rapport</p>
        </div>
        <button class="btn-secondary" (click)="close.emit()">
          <mat-icon>close</mat-icon>
          Fermer l'aperçu
        </button>
      </div>

      <div class="document-content">
        <!-- Cover Page Preview -->
        <div class="cover-page-preview">
          <div class="cover-content">
            <span class="utc-logo">[Logo UTC]</span>
            <div class="student-info">
              {{ reportService.report()?.student_name?.toUpperCase() }} {{ reportService.report()?.student_firstname }}
              <br>
              Semestre {{ reportService.report()?.semester }}
            </div>
            <h2 class="report-title">RAPPORT DE STAGE TN05</h2>
            <h3 class="company-name">{{ reportService.report()?.company_name }}</h3>
            <p class="company-location">{{ reportService.report()?.company_location }}</p>
            <p class="dates">
              Du {{ reportService.report()?.internship_start_date }} au {{ reportService.report()?.internship_end_date }}
            </p>
            <p class="tutor">Tuteur entreprise : {{ reportService.report()?.tutor_name }}</p>
          </div>
        </div>

        <!-- Sections -->
        @for (section of reportService.report()?.plan?.sections; track section.id; let i = $index) {
          @if (section.id !== 'cover_page') {
            <div class="section-preview">
              <mat-expansion-panel [expanded]="expandedSections[section.id]">
                <mat-expansion-panel-header>
                  <mat-panel-title>
                    <div class="section-header-content">
                      <span class="section-number">{{ getSectionNumber(i) }}</span>
                      <span class="section-title">{{ section.title }}</span>
                      <span class="status-badge" [ngClass]="section.status">
                        {{ getStatusLabel(section.status) }}
                      </span>
                    </div>
                  </mat-panel-title>
                </mat-expansion-panel-header>

                <div class="section-body">
                  @if (section.id === 'table_of_contents') {
                    <p class="auto-content">[Le sommaire sera généré automatiquement dans Word]</p>
                  } @else {
                    <div class="section-content-area">
                      @if (editingSection === section.id) {
                        <textarea
                          [(ngModel)]="editingContent"
                          class="content-editor"
                          rows="10"
                          placeholder="Rédigez le contenu de cette section..."
                        ></textarea>
                        <div class="edit-actions">
                          <button class="btn-primary" (click)="saveContent(section.id)">
                            <mat-icon>save</mat-icon>
                            Enregistrer
                          </button>
                          <button class="btn-secondary" (click)="cancelEdit()">
                            <mat-icon>close</mat-icon>
                            Annuler
                          </button>
                        </div>
                      } @else {
                        <div class="content-display" (click)="startEdit(section)">
                          @if (section.content) {
                            <p>{{ section.content }}</p>
                          } @else if (section.notes?.length) {
                            <div class="notes-preview">
                              <p class="notes-label">Notes :</p>
                              @for (note of section.notes; track note.id) {
                                <p class="note-item">{{ note.content }}</p>
                              }
                            </div>
                          } @else {
                            <p class="empty-content">[Section à compléter - Cliquez pour éditer]</p>
                          }
                          <button class="edit-overlay-btn" matTooltip="Éditer cette section">
                            <mat-icon>edit</mat-icon>
                          </button>
                        </div>
                      }
                    </div>

                    <!-- Subsections -->
                    @if (section.subsections?.length) {
                      <div class="subsections-preview">
                        @for (subsection of section.subsections; track subsection.id; let j = $index) {
                          <div class="subsection-item">
                            <div class="subsection-header">
                              <span class="subsection-number">{{ getSectionNumber(i) }}.{{ j + 1 }}</span>
                              <span class="subsection-title">{{ subsection.title }}</span>
                              <span class="status-badge small" [ngClass]="subsection.status">
                                {{ getStatusLabel(subsection.status) }}
                              </span>
                            </div>
                            <div class="subsection-content-area">
                              @if (editingSection === subsection.id) {
                                <textarea
                                  [(ngModel)]="editingContent"
                                  class="content-editor"
                                  rows="6"
                                  placeholder="Rédigez le contenu..."
                                ></textarea>
                                <div class="edit-actions">
                                  <button class="btn-primary btn-small" (click)="saveContent(subsection.id)">
                                    <mat-icon>save</mat-icon>
                                    Enregistrer
                                  </button>
                                  <button class="btn-secondary btn-small" (click)="cancelEdit()">
                                    <mat-icon>close</mat-icon>
                                    Annuler
                                  </button>
                                </div>
                              } @else {
                                <div class="content-display small" (click)="startEdit(subsection)">
                                  @if (subsection.content) {
                                    <p>{{ subsection.content }}</p>
                                  } @else if (subsection.notes?.length) {
                                    <div class="notes-preview">
                                      @for (note of subsection.notes; track note.id) {
                                        <p class="note-item small">{{ note.content }}</p>
                                      }
                                    </div>
                                  } @else {
                                    <p class="empty-content">[Cliquez pour éditer]</p>
                                  }
                                  <button class="edit-overlay-btn small" matTooltip="Éditer">
                                    <mat-icon>edit</mat-icon>
                                  </button>
                                </div>
                              }
                            </div>
                          </div>
                        }
                      </div>
                    }
                  }
                </div>
              </mat-expansion-panel>
            </div>
          }
        }
      </div>
    </div>
  `,
  styles: [`
    .document-preview {
      height: 100%;
      display: flex;
      flex-direction: column;
      background: #f5f7fa;
    }

    .preview-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 20px 24px;
      background: white;
      border-bottom: 1px solid #e0e0e0;

      .header-info {
        h1 {
          display: flex;
          align-items: center;
          gap: 10px;
          font-size: 22px;
          color: #1a237e;
          margin-bottom: 4px;

          mat-icon {
            color: #1976d2;
          }
        }

        p {
          color: #78909c;
          font-size: 14px;
        }
      }
    }

    .document-content {
      flex: 1;
      overflow-y: auto;
      padding: 24px;
      max-width: 900px;
      margin: 0 auto;
      width: 100%;
    }

    .cover-page-preview {
      background: white;
      border-radius: 12px;
      padding: 48px;
      margin-bottom: 24px;
      box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
      text-align: center;
      min-height: 400px;
      display: flex;
      flex-direction: column;
      justify-content: center;

      .cover-content {
        .utc-logo {
          display: block;
          text-align: left;
          color: #9e9e9e;
          font-style: italic;
          margin-bottom: 40px;
        }

        .student-info {
          text-align: right;
          color: #37474f;
          margin-bottom: 60px;
        }

        .report-title {
          font-size: 28px;
          color: #1a237e;
          margin-bottom: 24px;
        }

        .company-name {
          font-size: 22px;
          color: #1976d2;
          margin-bottom: 12px;
        }

        .company-location, .dates {
          color: #546e7a;
          margin-bottom: 8px;
        }

        .tutor {
          margin-top: 60px;
          text-align: left;
          color: #37474f;
        }
      }
    }

    .section-preview {
      margin-bottom: 16px;

      ::ng-deep .mat-expansion-panel {
        border-radius: 12px !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06) !important;
      }

      ::ng-deep .mat-expansion-panel-header {
        padding: 16px 24px;
      }
    }

    .section-header-content {
      display: flex;
      align-items: center;
      gap: 12px;
      width: 100%;

      .section-number {
        font-weight: 700;
        color: #1976d2;
        min-width: 30px;
      }

      .section-title {
        flex: 1;
        font-weight: 500;
        color: #37474f;
      }
    }

    .status-badge {
      padding: 4px 10px;
      border-radius: 12px;
      font-size: 11px;
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

      &.small {
        padding: 2px 8px;
        font-size: 10px;
      }
    }

    .section-body {
      padding: 16px 24px 24px;
    }

    .auto-content {
      color: #9e9e9e;
      font-style: italic;
    }

    .section-content-area, .subsection-content-area {
      position: relative;
    }

    .content-display {
      position: relative;
      padding: 16px;
      background: #fafafa;
      border-radius: 8px;
      border: 2px dashed transparent;
      cursor: pointer;
      transition: all 0.2s;

      &:hover {
        border-color: #1976d2;
        background: #f5f7fa;

        .edit-overlay-btn {
          opacity: 1;
        }
      }

      &.small {
        padding: 12px;
      }

      p {
        color: #37474f;
        line-height: 1.7;
        white-space: pre-wrap;
      }

      .empty-content {
        color: #9e9e9e;
        font-style: italic;
      }
    }

    .edit-overlay-btn {
      position: absolute;
      top: 8px;
      right: 8px;
      background: #1976d2;
      color: white;
      border: none;
      border-radius: 6px;
      padding: 6px;
      cursor: pointer;
      opacity: 0;
      transition: opacity 0.2s;

      mat-icon {
        font-size: 18px;
        width: 18px;
        height: 18px;
      }

      &.small {
        padding: 4px;

        mat-icon {
          font-size: 16px;
          width: 16px;
          height: 16px;
        }
      }
    }

    .content-editor {
      width: 100%;
      padding: 16px;
      border: 2px solid #1976d2;
      border-radius: 8px;
      font-size: 14px;
      line-height: 1.7;
      resize: vertical;
      font-family: inherit;

      &:focus {
        outline: none;
      }
    }

    .edit-actions {
      display: flex;
      gap: 12px;
      margin-top: 12px;
    }

    .notes-preview {
      .notes-label {
        font-size: 12px;
        color: #78909c;
        margin-bottom: 8px;
      }

      .note-item {
        padding: 8px 12px;
        background: #e3f2fd;
        border-radius: 6px;
        margin-bottom: 6px;
        font-size: 13px;
        color: #37474f;

        &.small {
          padding: 6px 10px;
          font-size: 12px;
        }
      }
    }

    .subsections-preview {
      margin-top: 24px;
      padding-top: 24px;
      border-top: 1px solid #e0e0e0;
    }

    .subsection-item {
      margin-bottom: 20px;

      .subsection-header {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 12px;

        .subsection-number {
          font-weight: 600;
          color: #1976d2;
          font-size: 14px;
        }

        .subsection-title {
          flex: 1;
          font-weight: 500;
          color: #546e7a;
          font-size: 14px;
        }
      }
    }

    .btn-primary {
      background: #1976d2;
      color: white;
      border: none;
      padding: 10px 20px;
      border-radius: 8px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 14px;

      &:hover {
        background: #1565c0;
      }
    }

    .btn-secondary {
      background: #f5f5f5;
      color: #37474f;
      border: none;
      padding: 10px 20px;
      border-radius: 8px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 14px;

      &:hover {
        background: #e0e0e0;
      }
    }

    .btn-small {
      padding: 6px 14px;
      font-size: 13px;
    }
  `],
})
export class DocumentPreviewComponent {
  @Output() close = new EventEmitter<void>();

  reportService = inject(ReportService);
  private snackBar = inject(MatSnackBar);

  expandedSections: { [key: string]: boolean } = {};
  editingSection: string | null = null;
  editingContent = '';

  getSectionNumber(index: number): string {
    // Skip cover page in numbering
    let num = 0;
    const sections = this.reportService.report()?.plan?.sections || [];
    for (let i = 0; i <= index; i++) {
      if (sections[i].id !== 'cover_page') {
        num++;
      }
    }
    return num.toString();
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

  startEdit(section: ReportSection): void {
    this.editingSection = section.id;
    this.editingContent = section.content || '';
  }

  cancelEdit(): void {
    this.editingSection = null;
    this.editingContent = '';
  }

  saveContent(sectionId: string): void {
    this.reportService.updateSectionContent(sectionId, this.editingContent);
    this.editingSection = null;
    this.editingContent = '';
    this.snackBar.open('Contenu enregistré', 'OK', { duration: 2000 });
  }
}
