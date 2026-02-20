import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ApiService } from '../../services/api.service';
import { ReportService } from '../../services/report.service';
import { AIProviderConfig } from '../../models/report.model';

@Component({
  selector: 'app-ai-config-dialog',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatDialogModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
  ],
  template: `
    <div class="dialog-container">
      <div class="dialog-header">
        <mat-icon>smart_toy</mat-icon>
        <h2>Configuration de l'IA</h2>
      </div>

      <div class="dialog-content">
        <div class="current-config" *ngIf="currentConfig">
          <div class="config-status success">
            <mat-icon>check_circle</mat-icon>
            <span>IA configurée : {{ currentConfig.provider === 'openai' ? 'OpenAI (GPT-4o)' : 'Mistral AI' }}</span>
          </div>
        </div>

        <div class="form-field">
          <label>Fournisseur</label>
          <select [(ngModel)]="aiProvider">
            <option value="openai">OpenAI (GPT-4o)</option>
            <option value="mistral">Mistral AI (Mistral Large)</option>
          </select>
        </div>

        <div class="form-field">
          <label>Clé API</label>
          <div class="input-with-toggle">
            <input
              [type]="showApiKey ? 'text' : 'password'"
              [(ngModel)]="apiKey"
              [placeholder]="aiProvider === 'openai' ? 'sk-...' : 'Votre clé Mistral'"
            />
            <button class="toggle-visibility" (click)="showApiKey = !showApiKey">
              <mat-icon>{{ showApiKey ? 'visibility_off' : 'visibility' }}</mat-icon>
            </button>
          </div>
          <small class="field-hint">
            @if (aiProvider === 'openai') {
              Obtenez votre clé sur <a href="https://platform.openai.com/api-keys" target="_blank">platform.openai.com</a>
            } @else {
              Obtenez votre clé sur <a href="https://console.mistral.ai/" target="_blank">console.mistral.ai</a>
            }
          </small>
        </div>

        <div class="test-section">
          <button
            class="btn-test"
            (click)="testConnection()"
            [disabled]="!apiKey || testingConnection()"
          >
            @if (testingConnection()) {
              <mat-spinner diameter="18"></mat-spinner>
              Test en cours...
            } @else {
              <mat-icon>sync</mat-icon>
              Tester la connexion
            }
          </button>

          @if (connectionTested()) {
            <div class="test-result" [class.success]="connectionSuccess()" [class.error]="!connectionSuccess()">
              <mat-icon>{{ connectionSuccess() ? 'check_circle' : 'error' }}</mat-icon>
              <span>{{ connectionSuccess() ? 'Connexion réussie !' : 'Échec de la connexion' }}</span>
            </div>
          }
        </div>
      </div>

      <div class="dialog-actions">
        <button class="btn-secondary" (click)="close()">
          Annuler
        </button>
        <button
          class="btn-primary"
          (click)="save()"
          [disabled]="!connectionSuccess()"
        >
          <mat-icon>save</mat-icon>
          Enregistrer
        </button>
      </div>
    </div>
  `,
  styles: [`
    .dialog-container {
      padding: 24px;
      min-width: 400px;
    }

    .dialog-header {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 24px;

      mat-icon {
        font-size: 28px;
        width: 28px;
        height: 28px;
        color: #1976d2;
      }

      h2 {
        margin: 0;
        font-size: 20px;
        color: #37474f;
      }
    }

    .dialog-content {
      margin-bottom: 24px;
    }

    .current-config {
      margin-bottom: 20px;

      .config-status {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 12px 16px;
        border-radius: 8px;

        &.success {
          background: #e8f5e9;
          color: #2e7d32;
        }

        mat-icon {
          font-size: 20px;
          width: 20px;
          height: 20px;
        }
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

      input, select {
        width: 100%;
        padding: 12px 16px;
        border: 2px solid #e0e0e0;
        border-radius: 8px;
        font-size: 14px;
        transition: border-color 0.3s ease;
        box-sizing: border-box;

        &:focus {
          outline: none;
          border-color: #1976d2;
        }
      }

      .input-with-toggle {
        position: relative;
        display: flex;
        align-items: center;

        input {
          padding-right: 48px;
        }

        .toggle-visibility {
          position: absolute;
          right: 8px;
          background: transparent;
          border: none;
          padding: 8px;
          cursor: pointer;
          color: #9e9e9e;

          &:hover {
            color: #616161;
          }

          mat-icon {
            font-size: 20px;
            width: 20px;
            height: 20px;
          }
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

    .test-section {
      display: flex;
      align-items: center;
      gap: 16px;
      padding: 16px;
      background: #f5f7fa;
      border-radius: 8px;

      .btn-test {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 10px 16px;
        background: #fff;
        border: 2px solid #1976d2;
        color: #1976d2;
        border-radius: 8px;
        cursor: pointer;
        font-size: 14px;
        font-weight: 500;

        &:hover:not(:disabled) {
          background: #e3f2fd;
        }

        &:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }

        mat-icon {
          font-size: 18px;
          width: 18px;
          height: 18px;
        }
      }

      .test-result {
        display: flex;
        align-items: center;
        gap: 6px;
        font-weight: 500;

        &.success {
          color: #43a047;
        }

        &.error {
          color: #e53935;
        }

        mat-icon {
          font-size: 20px;
          width: 20px;
          height: 20px;
        }
      }
    }

    .dialog-actions {
      display: flex;
      justify-content: flex-end;
      gap: 12px;
      padding-top: 16px;
      border-top: 1px solid #e0e0e0;

      .btn-secondary {
        padding: 10px 20px;
        background: #f5f5f5;
        color: #616161;
        border: none;
        border-radius: 8px;
        cursor: pointer;
        font-size: 14px;
        font-weight: 500;

        &:hover {
          background: #e0e0e0;
        }
      }

      .btn-primary {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 10px 20px;
        background: #1976d2;
        color: white;
        border: none;
        border-radius: 8px;
        cursor: pointer;
        font-size: 14px;
        font-weight: 500;

        &:hover:not(:disabled) {
          background: #1565c0;
        }

        &:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }

        mat-icon {
          font-size: 18px;
          width: 18px;
          height: 18px;
        }
      }
    }
  `],
})
export class AIConfigDialogComponent {
  private dialogRef = inject(MatDialogRef<AIConfigDialogComponent>);
  private apiService = inject(ApiService);
  private reportService = inject(ReportService);
  private snackBar = inject(MatSnackBar);

  currentConfig = this.reportService.aiConfig();
  aiProvider: 'openai' | 'mistral' = this.currentConfig?.provider || 'openai';
  apiKey = this.currentConfig?.api_key || '';
  showApiKey = false;

  testingConnection = signal(false);
  connectionTested = signal(false);
  connectionSuccess = signal(false);

  testConnection(): void {
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

  save(): void {
    const config: AIProviderConfig = {
      provider: this.aiProvider,
      api_key: this.apiKey,
    };

    this.reportService.saveAIConfig(config);
    this.snackBar.open('Configuration IA enregistrée', 'OK', { duration: 3000 });
    this.dialogRef.close(true);
  }

  close(): void {
    this.dialogRef.close(false);
  }
}
