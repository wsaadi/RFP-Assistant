import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { MatStepperModule } from '@angular/material/stepper';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatSelectModule } from '@angular/material/select';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ApiService } from '../../services/api.service';
import { ReportService } from '../../services/report.service';
import { AIProviderConfig, CreateReportRequest } from '../../models/report.model';

@Component({
  selector: 'app-setup',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatStepperModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatSelectModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
  ],
  template: `
    <div class="container">
      <div class="setup-container">
        <h1>Configuration de votre rapport</h1>
        <p class="setup-subtitle">
          Remplissez les informations ci-dessous pour commencer votre rapport de stage TN05
        </p>

        <mat-stepper linear #stepper class="setup-stepper">
          <!-- Step 1: AI Configuration -->
          <mat-step [completed]="aiConfigValid()">
            <ng-template matStepLabel>Configuration IA</ng-template>
            <div class="step-content">
              <h2>Choisissez votre fournisseur d'IA</h2>
              <p class="step-description">
                Sélectionnez le fournisseur et entrez votre clé API pour bénéficier
                de l'assistance intelligente
              </p>

              <div class="form-field">
                <label>Fournisseur</label>
                <select [(ngModel)]="aiProvider">
                  <option value="openai">OpenAI (GPT-4o)</option>
                  <option value="mistral">Mistral AI (Mistral Large)</option>
                </select>
              </div>

              <div class="form-field">
                <label>Clé API</label>
                <input
                  type="password"
                  [(ngModel)]="apiKey"
                  [placeholder]="aiProvider === 'openai' ? 'sk-...' : 'Votre clé Mistral'"
                />
                <small class="field-hint">
                  @if (aiProvider === 'openai') {
                    Obtenez votre clé sur <a href="https://platform.openai.com/api-keys" target="_blank">platform.openai.com</a>
                  } @else {
                    Obtenez votre clé sur <a href="https://console.mistral.ai/" target="_blank">console.mistral.ai</a>
                  }
                </small>
              </div>

              <div class="step-actions">
                <button
                  class="btn-primary"
                  (click)="testConnection()"
                  [disabled]="!apiKey || testingConnection()"
                >
                  @if (testingConnection()) {
                    <mat-spinner diameter="20"></mat-spinner>
                    Test en cours...
                  } @else {
                    <mat-icon>check_circle</mat-icon>
                    Tester la connexion
                  }
                </button>

                @if (connectionTested() && connectionSuccess()) {
                  <span class="success-message">
                    <mat-icon>check</mat-icon>
                    Connexion réussie
                  </span>
                }
              </div>

              <div class="stepper-nav">
                <button
                  mat-button
                  matStepperNext
                  [disabled]="!aiConfigValid()"
                  class="btn-primary"
                >
                  Suivant
                </button>
              </div>
            </div>
          </mat-step>

          <!-- Step 2: Student Information -->
          <mat-step [completed]="studentInfoValid()">
            <ng-template matStepLabel>Informations étudiant</ng-template>
            <div class="step-content">
              <h2>Vos informations</h2>

              <div class="form-row">
                <div class="form-field">
                  <label>Nom *</label>
                  <input
                    type="text"
                    [(ngModel)]="studentName"
                    placeholder="DUPONT"
                    style="text-transform: uppercase;"
                  />
                </div>

                <div class="form-field">
                  <label>Prénom *</label>
                  <input
                    type="text"
                    [(ngModel)]="studentFirstname"
                    placeholder="Marie"
                  />
                </div>
              </div>

              <div class="form-field">
                <label>Semestre *</label>
                <select [(ngModel)]="semester">
                  <option value="">Sélectionnez votre semestre</option>
                  <option value="A1">A1</option>
                  <option value="A2">A2</option>
                  <option value="P1">P1</option>
                  <option value="P2">P2</option>
                </select>
              </div>

              <div class="stepper-nav">
                <button mat-button matStepperPrevious class="btn-secondary">
                  Retour
                </button>
                <button
                  mat-button
                  matStepperNext
                  [disabled]="!studentInfoValid()"
                  class="btn-primary"
                >
                  Suivant
                </button>
              </div>
            </div>
          </mat-step>

          <!-- Step 3: Internship Information -->
          <mat-step [completed]="internshipInfoValid()">
            <ng-template matStepLabel>Informations stage</ng-template>
            <div class="step-content">
              <h2>Informations sur le stage</h2>

              <div class="form-field">
                <label>Nom de l'entreprise *</label>
                <input
                  type="text"
                  [(ngModel)]="companyName"
                  placeholder="Exemple : SNCF, Airbus, etc."
                />
              </div>

              <div class="form-field">
                <label>Lieu du stage (Ville + Département) *</label>
                <input
                  type="text"
                  [(ngModel)]="companyLocation"
                  placeholder="Compiègne (60)"
                />
              </div>

              <div class="form-row">
                <div class="form-field">
                  <label>Date de début *</label>
                  <input
                    type="date"
                    [(ngModel)]="startDate"
                  />
                </div>

                <div class="form-field">
                  <label>Date de fin *</label>
                  <input
                    type="date"
                    [(ngModel)]="endDate"
                  />
                </div>
              </div>

              <div class="form-field">
                <label>Nom du tuteur entreprise *</label>
                <input
                  type="text"
                  [(ngModel)]="tutorName"
                  placeholder="M. / Mme Prénom NOM"
                />
              </div>

              <div class="stepper-nav">
                <button mat-button matStepperPrevious class="btn-secondary">
                  Retour
                </button>
                <button
                  mat-button
                  matStepperNext
                  [disabled]="!internshipInfoValid()"
                  class="btn-primary"
                >
                  Suivant
                </button>
              </div>
            </div>
          </mat-step>

          <!-- Step 4: Confirmation -->
          <mat-step>
            <ng-template matStepLabel>Confirmation</ng-template>
            <div class="step-content">
              <h2>Récapitulatif</h2>

              <div class="summary-card">
                <div class="summary-section">
                  <h4>Configuration IA</h4>
                  <p>
                    <strong>Fournisseur :</strong>
                    {{ aiProvider === 'openai' ? 'OpenAI (GPT-4o)' : 'Mistral AI' }}
                  </p>
                </div>

                <div class="summary-section">
                  <h4>Étudiant</h4>
                  <p><strong>Nom :</strong> {{ studentName }} {{ studentFirstname }}</p>
                  <p><strong>Semestre :</strong> {{ semester }}</p>
                </div>

                <div class="summary-section">
                  <h4>Stage</h4>
                  <p><strong>Entreprise :</strong> {{ companyName }}</p>
                  <p><strong>Lieu :</strong> {{ companyLocation }}</p>
                  <p><strong>Période :</strong> {{ startDate }} au {{ endDate }}</p>
                  <p><strong>Tuteur :</strong> {{ tutorName }}</p>
                </div>
              </div>

              <div class="stepper-nav">
                <button mat-button matStepperPrevious class="btn-secondary">
                  Retour
                </button>
                <button
                  class="btn-primary"
                  (click)="createReport()"
                  [disabled]="creatingReport()"
                >
                  @if (creatingReport()) {
                    <mat-spinner diameter="20"></mat-spinner>
                    Création en cours...
                  } @else {
                    <mat-icon>rocket_launch</mat-icon>
                    Créer mon rapport
                  }
                </button>
              </div>
            </div>
          </mat-step>
        </mat-stepper>
      </div>
    </div>
  `,
  styles: [`
    .setup-container {
      max-width: 800px;
      margin: 0 auto;
      padding: 32px 0;

      h1 {
        font-size: 32px;
        color: #1a237e;
        margin-bottom: 8px;
        text-align: center;
      }

      .setup-subtitle {
        color: #78909c;
        text-align: center;
        margin-bottom: 40px;
      }
    }

    .setup-stepper {
      background: white;
      padding: 32px;
      border-radius: 16px;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
    }

    .step-content {
      padding: 24px 0;

      h2 {
        font-size: 22px;
        color: #37474f;
        margin-bottom: 8px;
      }

      .step-description {
        color: #78909c;
        margin-bottom: 24px;
      }
    }

    .form-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 24px;

      @media (max-width: 600px) {
        grid-template-columns: 1fr;
      }
    }

    .form-field {
      margin-bottom: 20px;

      label {
        display: block;
        margin-bottom: 8px;
        font-weight: 500;
        color: #424242;
      }

      input, select, textarea {
        width: 100%;
        padding: 12px 16px;
        border: 2px solid #e0e0e0;
        border-radius: 8px;
        font-size: 14px;
        transition: border-color 0.3s ease;

        &:focus {
          outline: none;
          border-color: #1976d2;
        }
      }

      .field-hint {
        display: block;
        margin-top: 6px;
        font-size: 12px;
        color: #9e9e9e;

        a {
          color: #1976d2;
        }
      }
    }

    .step-actions {
      display: flex;
      align-items: center;
      gap: 16px;
      margin-top: 24px;

      .btn-primary {
        display: flex;
        align-items: center;
        gap: 8px;
      }

      .success-message {
        display: flex;
        align-items: center;
        gap: 6px;
        color: #43a047;
        font-weight: 500;

        mat-icon {
          font-size: 20px;
          width: 20px;
          height: 20px;
        }
      }
    }

    .stepper-nav {
      display: flex;
      justify-content: flex-end;
      gap: 16px;
      margin-top: 32px;
      padding-top: 24px;
      border-top: 1px solid #e0e0e0;
    }

    .summary-card {
      background: #f5f7fa;
      border-radius: 12px;
      padding: 24px;
      margin: 24px 0;

      .summary-section {
        margin-bottom: 20px;

        &:last-child {
          margin-bottom: 0;
        }

        h4 {
          color: #1976d2;
          margin-bottom: 8px;
          font-size: 14px;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        p {
          margin: 4px 0;
          color: #37474f;
        }
      }
    }

    ::ng-deep .mat-horizontal-stepper-header-container {
      margin-bottom: 24px;
    }
  `],
})
export class SetupComponent {
  private apiService = inject(ApiService);
  private reportService = inject(ReportService);
  private router = inject(Router);
  private snackBar = inject(MatSnackBar);

  // AI Configuration
  aiProvider: 'openai' | 'mistral' = 'openai';
  apiKey = '';
  testingConnection = signal(false);
  connectionTested = signal(false);
  connectionSuccess = signal(false);

  // Student Info
  studentName = '';
  studentFirstname = '';
  semester = '';

  // Internship Info
  companyName = '';
  companyLocation = '';
  startDate = '';
  endDate = '';
  tutorName = '';

  // State
  creatingReport = signal(false);

  aiConfigValid(): boolean {
    return this.connectionTested() && this.connectionSuccess();
  }

  studentInfoValid(): boolean {
    return !!(this.studentName && this.studentFirstname && this.semester);
  }

  internshipInfoValid(): boolean {
    return !!(
      this.companyName &&
      this.companyLocation &&
      this.startDate &&
      this.endDate &&
      this.tutorName
    );
  }

  async testConnection(): Promise<void> {
    this.testingConnection.set(true);
    this.connectionTested.set(false);

    const config: AIProviderConfig = {
      provider: this.aiProvider,
      api_key: this.apiKey,
    };

    this.apiService.testAIConnection(config).subscribe({
      next: (response) => {
        this.connectionTested.set(true);
        this.connectionSuccess.set(response.success);
        this.testingConnection.set(false);

        if (response.success) {
          this.reportService.saveAIConfig(config);
          this.snackBar.open('Connexion réussie !', 'OK', { duration: 3000 });
        }
      },
      error: (error) => {
        this.connectionTested.set(true);
        this.connectionSuccess.set(false);
        this.testingConnection.set(false);
        this.snackBar.open(
          'Erreur de connexion. Vérifiez votre clé API.',
          'OK',
          { duration: 5000 }
        );
      },
    });
  }

  createReport(): void {
    this.creatingReport.set(true);

    const request: CreateReportRequest = {
      student_name: this.studentName.toUpperCase(),
      student_firstname: this.studentFirstname,
      semester: this.semester,
      company_name: this.companyName,
      company_location: this.companyLocation,
      internship_start_date: this.startDate,
      internship_end_date: this.endDate,
      tutor_name: this.tutorName,
    };

    this.apiService.createReport(request).subscribe({
      next: (report) => {
        this.reportService.setReport(report);
        this.creatingReport.set(false);
        this.snackBar.open('Rapport créé avec succès !', 'OK', {
          duration: 3000,
        });
        this.router.navigate(['/editor']);
      },
      error: (error) => {
        this.creatingReport.set(false);
        this.snackBar.open(
          'Erreur lors de la création du rapport.',
          'OK',
          { duration: 5000 }
        );
      },
    });
  }
}
