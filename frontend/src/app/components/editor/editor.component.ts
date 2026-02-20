import { Component, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTabsModule } from '@angular/material/tabs';
import { MatChipsModule } from '@angular/material/chips';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatExpansionModule } from '@angular/material/expansion';
import { ReportService } from '../../services/report.service';
import { ApiService } from '../../services/api.service';
import { ReportSection, SectionStatus } from '../../models/report.model';
import { SectionCardComponent } from '../section-card/section-card.component';
import { SectionEditorComponent } from '../section-editor/section-editor.component';
import { DocumentPreviewComponent } from '../document-preview/document-preview.component';
import { ComplianceCheckComponent } from '../compliance-check/compliance-check.component';

@Component({
  selector: 'app-editor',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatSidenavModule,
    MatButtonModule,
    MatIconModule,
    MatProgressBarModule,
    MatTabsModule,
    MatChipsModule,
    MatSnackBarModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
    MatExpansionModule,
    SectionCardComponent,
    SectionEditorComponent,
    DocumentPreviewComponent,
    ComplianceCheckComponent,
  ],
  template: `
    <div class="editor-container">
      @if (!reportService.report()) {
        <div class="no-report">
          <mat-icon>description</mat-icon>
          <h2>Aucun rapport en cours</h2>
          <p>Commencez par créer un nouveau rapport</p>
          <button class="btn-primary" (click)="goToSetup()">
            Créer un rapport
          </button>
        </div>
      } @else {
        <mat-sidenav-container class="sidenav-container">
          <!-- Sidebar with sections list -->
          <mat-sidenav mode="side" opened class="sections-sidebar">
            <div class="sidebar-header">
              <h2>Plan du rapport</h2>
              <div class="progress-info">
                <div class="progress-text">
                  <span>{{ reportService.progress().completed }}/{{ reportService.progress().total_sections }}</span>
                  <span>{{ reportService.progress().progress_percentage }}%</span>
                </div>
                <mat-progress-bar
                  mode="determinate"
                  [value]="reportService.progress().progress_percentage"
                ></mat-progress-bar>
              </div>
            </div>

            <div class="sections-list">
              @for (section of reportService.report()?.plan?.sections; track section.id) {
                <app-section-card
                  [section]="section"
                  [isSelected]="reportService.selectedSection()?.id === section.id"
                  [selectedSubsectionId]="reportService.selectedSection()?.id || null"
                  (select)="selectSection($event)"
                ></app-section-card>
              }
            </div>

            <!-- PDF Instructions Zone -->
            <div class="instructions-zone">
              <div class="instructions-header">
                <mat-icon>school</mat-icon>
                <span>Instructions de l'école</span>
              </div>
              @if (reportService.schoolInstructions()) {
                <div class="instructions-loaded">
                  <div class="file-info">
                    <mat-icon>description</mat-icon>
                    <span class="filename">{{ reportService.schoolInstructions()?.filename }}</span>
                  </div>
                  <button
                    class="btn-icon-small"
                    (click)="removeInstructions()"
                    matTooltip="Supprimer le PDF"
                  >
                    <mat-icon>close</mat-icon>
                  </button>
                </div>
              } @else {
                <div
                  class="upload-zone"
                  (click)="instructionsFileInput.click()"
                  (dragover)="onDragOver($event)"
                  (drop)="onDrop($event)"
                >
                  @if (uploadingInstructions()) {
                    <mat-spinner diameter="24"></mat-spinner>
                    <span>Chargement...</span>
                  } @else {
                    <mat-icon>upload_file</mat-icon>
                    <span>Importer le PDF des consignes</span>
                  }
                </div>
                <input
                  #instructionsFileInput
                  type="file"
                  accept=".pdf"
                  style="display: none"
                  (change)="onInstructionsFileSelected($event)"
                />
              }
            </div>

            <div class="sidebar-actions">
              <button
                class="btn-primary"
                (click)="showDocumentPreview.set(true)"
                matTooltip="Voir l'aperçu complet du document"
              >
                <mat-icon>article</mat-icon>
                Aperçu document
              </button>
              <button
                class="btn-compliance"
                (click)="showComplianceCheck.set(true)"
                matTooltip="Vérifier la conformité avec les instructions"
              >
                <mat-icon>fact_check</mat-icon>
                Vérifier conformité
              </button>
              <button
                class="btn-secondary"
                (click)="exportReport()"
                [disabled]="exporting()"
                matTooltip="Exporter en Word"
              >
                @if (exporting()) {
                  <mat-spinner diameter="18"></mat-spinner>
                } @else {
                  <mat-icon>download</mat-icon>
                }
                Exporter Word
              </button>
            </div>
          </mat-sidenav>

          <!-- Main content area -->
          <mat-sidenav-content class="main-content">
            @if (showComplianceCheck()) {
              <app-compliance-check
                (close)="showComplianceCheck.set(false)"
              ></app-compliance-check>
            } @else if (showDocumentPreview()) {
              <app-document-preview
                (close)="showDocumentPreview.set(false)"
              ></app-document-preview>
            } @else if (reportService.selectedSection()) {
              <app-section-editor
                [section]="reportService.selectedSection()!"
              ></app-section-editor>
            } @else {
              <div class="welcome-panel">
                <div class="welcome-content">
                  <mat-icon>touch_app</mat-icon>
                  <h2>Sélectionnez une section</h2>
                  <p>Choisissez une section dans le panneau de gauche pour commencer à la rédiger</p>

                  <div class="quick-stats">
                    <div class="stat-card">
                      <span class="stat-value">{{ reportService.progress().not_started }}</span>
                      <span class="stat-label">À commencer</span>
                    </div>
                    <div class="stat-card">
                      <span class="stat-value">{{ reportService.progress().in_progress }}</span>
                      <span class="stat-label">En cours</span>
                    </div>
                    <div class="stat-card">
                      <span class="stat-value">{{ reportService.progress().completed }}</span>
                      <span class="stat-label">Terminées</span>
                    </div>
                  </div>

                  <div class="report-info">
                    <h3>{{ reportService.report()?.company_name }}</h3>
                    <p>{{ reportService.report()?.student_firstname }} {{ reportService.report()?.student_name }}</p>
                    <p class="dates">
                      {{ reportService.report()?.internship_start_date }} - {{ reportService.report()?.internship_end_date }}
                    </p>
                  </div>
                </div>
              </div>
            }
          </mat-sidenav-content>
        </mat-sidenav-container>
      }
    </div>
  `,
  styles: [`
    .editor-container {
      height: calc(100vh - 64px - 48px);
    }

    .no-report {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      height: 100%;
      text-align: center;

      mat-icon {
        font-size: 80px;
        width: 80px;
        height: 80px;
        color: #e0e0e0;
        margin-bottom: 24px;
      }

      h2 {
        color: #37474f;
        margin-bottom: 8px;
      }

      p {
        color: #78909c;
        margin-bottom: 24px;
      }
    }

    .sidenav-container {
      height: 100%;
    }

    .sections-sidebar {
      width: 340px;
      background: white;
      border-right: 1px solid #e0e0e0;
      display: flex;
      flex-direction: column;
    }

    .sidebar-header {
      padding: 20px;
      border-bottom: 1px solid #e0e0e0;

      h2 {
        font-size: 18px;
        color: #1a237e;
        margin-bottom: 16px;
      }

      .progress-info {
        .progress-text {
          display: flex;
          justify-content: space-between;
          font-size: 13px;
          color: #78909c;
          margin-bottom: 8px;
        }
      }
    }

    .sections-list {
      flex: 1;
      overflow-y: auto;
      padding: 12px;
    }

    .sidebar-actions {
      padding: 16px;
      border-top: 1px solid #e0e0e0;
      display: flex;
      flex-direction: column;
      gap: 10px;

      button {
        width: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
      }

      .btn-primary {
        background: #1976d2;
        color: white;
        border: none;
        padding: 12px 20px;
        border-radius: 8px;
        cursor: pointer;
        font-size: 14px;

        &:hover {
          background: #1565c0;
        }
      }

      .btn-compliance {
        background: #43a047;
        color: white;
        border: none;
        padding: 12px 20px;
        border-radius: 8px;
        cursor: pointer;
        font-size: 14px;

        &:hover {
          background: #388e3c;
        }
      }
    }

    .instructions-zone {
      padding: 12px 16px;
      border-bottom: 1px solid #e0e0e0;
      background: linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%);

      .instructions-header {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 10px;
        font-size: 13px;
        font-weight: 500;
        color: #e65100;

        mat-icon {
          font-size: 18px;
          width: 18px;
          height: 18px;
        }
      }

      .instructions-loaded {
        display: flex;
        align-items: center;
        justify-content: space-between;
        background: white;
        padding: 8px 12px;
        border-radius: 8px;
        border: 1px solid #ffcc80;

        .file-info {
          display: flex;
          align-items: center;
          gap: 8px;
          overflow: hidden;

          mat-icon {
            color: #ff9800;
            font-size: 20px;
            width: 20px;
            height: 20px;
            flex-shrink: 0;
          }

          .filename {
            font-size: 12px;
            color: #37474f;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 180px;
          }
        }

        .btn-icon-small {
          background: transparent;
          border: none;
          padding: 4px;
          border-radius: 4px;
          cursor: pointer;
          color: #9e9e9e;
          display: flex;
          align-items: center;
          justify-content: center;

          &:hover {
            background: #ffebee;
            color: #e53935;
          }

          mat-icon {
            font-size: 18px;
            width: 18px;
            height: 18px;
          }
        }
      }

      .upload-zone {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 6px;
        padding: 16px;
        border: 2px dashed #ffcc80;
        border-radius: 8px;
        background: white;
        cursor: pointer;
        transition: all 0.2s;

        &:hover {
          border-color: #ff9800;
          background: #fff8e1;
        }

        mat-icon {
          color: #ff9800;
          font-size: 28px;
          width: 28px;
          height: 28px;
        }

        span {
          font-size: 12px;
          color: #78909c;
          text-align: center;
        }
      }
    }

    .main-content {
      background: #f5f7fa;
    }

    .welcome-panel {
      height: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .welcome-content {
      text-align: center;
      max-width: 500px;

      mat-icon {
        font-size: 64px;
        width: 64px;
        height: 64px;
        color: #1976d2;
        margin-bottom: 16px;
      }

      h2 {
        color: #37474f;
        margin-bottom: 8px;
      }

      p {
        color: #78909c;
        margin-bottom: 32px;
      }
    }

    .quick-stats {
      display: flex;
      justify-content: center;
      gap: 24px;
      margin-bottom: 40px;

      .stat-card {
        background: white;
        padding: 20px 32px;
        border-radius: 12px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);

        .stat-value {
          display: block;
          font-size: 32px;
          font-weight: 700;
          color: #1976d2;
        }

        .stat-label {
          font-size: 13px;
          color: #78909c;
        }
      }
    }

    .report-info {
      background: white;
      padding: 24px;
      border-radius: 12px;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);

      h3 {
        color: #1976d2;
        margin-bottom: 8px;
      }

      p {
        color: #37474f;
        margin: 4px 0;

        &.dates {
          font-size: 13px;
          color: #78909c;
        }
      }
    }

    ::ng-deep .mat-drawer-inner-container {
      display: flex;
      flex-direction: column;
    }
  `],
})
export class EditorComponent {
  reportService = inject(ReportService);
  private apiService = inject(ApiService);
  private router = inject(Router);
  private snackBar = inject(MatSnackBar);

  exporting = signal(false);
  showDocumentPreview = signal(false);
  showComplianceCheck = signal(false);
  uploadingInstructions = signal(false);

  goToSetup(): void {
    this.router.navigate(['/setup']);
  }

  selectSection(section: ReportSection): void {
    this.reportService.selectSection(section);
  }

  exportReport(): void {
    const report = this.reportService.report();
    const aiConfig = this.reportService.aiConfig();

    if (!report) return;

    this.exporting.set(true);

    const exportObservable = aiConfig
      ? this.apiService.generateWordDocument(report, aiConfig)
      : this.apiService.generateWordDocumentSimple(report);

    exportObservable.subscribe({
      next: (blob) => {
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `rapport_stage_${report.student_name}_${report.student_firstname}.docx`;
        link.click();
        window.URL.revokeObjectURL(url);

        this.exporting.set(false);
        this.snackBar.open('Rapport exporté avec succès !', 'OK', {
          duration: 3000,
        });
      },
      error: (error) => {
        this.exporting.set(false);
        this.snackBar.open('Erreur lors de l\'export du rapport', 'OK', {
          duration: 5000,
        });
        console.error('Export error:', error);
      },
    });
  }

  onInstructionsFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (input.files && input.files[0]) {
      this.uploadInstructionsPdf(input.files[0]);
    }
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    const files = event.dataTransfer?.files;
    if (files && files[0] && files[0].type === 'application/pdf') {
      this.uploadInstructionsPdf(files[0]);
    } else {
      this.snackBar.open('Veuillez déposer un fichier PDF', 'OK', { duration: 3000 });
    }
  }

  uploadInstructionsPdf(file: File): void {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      this.snackBar.open('Le fichier doit être un PDF', 'OK', { duration: 3000 });
      return;
    }

    this.uploadingInstructions.set(true);

    this.apiService.extractPdfText(file).subscribe({
      next: (response) => {
        this.reportService.saveSchoolInstructions(response.filename, response.text);
        this.uploadingInstructions.set(false);
        this.snackBar.open('Instructions importées avec succès', 'OK', { duration: 3000 });
      },
      error: (error) => {
        this.uploadingInstructions.set(false);
        this.snackBar.open('Erreur lors de l\'import du PDF', 'OK', { duration: 5000 });
        console.error('PDF upload error:', error);
      },
    });
  }

  removeInstructions(): void {
    this.reportService.removeSchoolInstructions();
    this.snackBar.open('Instructions supprimées', 'OK', { duration: 2000 });
  }
}
