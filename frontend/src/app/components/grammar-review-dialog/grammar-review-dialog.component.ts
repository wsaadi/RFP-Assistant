import { Component, Inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatCardModule } from '@angular/material/card';
import { MatExpansionModule } from '@angular/material/expansion';

interface GrammarError {
  texte_errone: string;
  correction: string;
  explication: string;
}

interface GrammarReview {
  nombre_erreurs: number;
  erreurs: GrammarError[];
  message: string;
}

@Component({
  selector: 'app-grammar-review-dialog',
  standalone: true,
  imports: [
    CommonModule,
    MatDialogModule,
    MatButtonModule,
    MatIconModule,
    MatCardModule,
    MatExpansionModule,
  ],
  template: `
    <div class="dialog-container">
      <h2 mat-dialog-title>
        <mat-icon>spellcheck</mat-icon>
        Revue Orthographique, Grammaticale et Conjugaison
      </h2>

      <mat-dialog-content>
        <div class="summary-card">
          @if (data.nombre_erreurs === 0) {
            <div class="success-message">
              <mat-icon class="success-icon">check_circle</mat-icon>
              <h3>Excellent travail !</h3>
              <p>{{ data.message }}</p>
            </div>
          } @else {
            <div class="warning-message">
              <mat-icon class="warning-icon">info</mat-icon>
              <h3>{{ data.nombre_erreurs }} erreur(s) détectée(s)</h3>
              <p>Voici les corrections suggérées pour améliorer votre rapport :</p>
            </div>
          }
        </div>

        @if (data.erreurs && data.erreurs.length > 0) {
          <div class="errors-list">
            <mat-accordion>
              @for (error of data.erreurs; track $index) {
                <mat-expansion-panel>
                  <mat-expansion-panel-header>
                    <mat-panel-title>
                      <mat-icon class="error-icon">error_outline</mat-icon>
                      <span class="error-text">{{ truncate(error.texte_errone, 60) }}</span>
                    </mat-panel-title>
                  </mat-expansion-panel-header>

                  <div class="error-details">
                    <div class="error-section">
                      <h4><mat-icon>close</mat-icon> Texte erroné :</h4>
                      <p class="error-content">{{ error.texte_errone }}</p>
                    </div>

                    <div class="correction-section">
                      <h4><mat-icon>check</mat-icon> Correction :</h4>
                      <p class="correction-content">{{ error.correction }}</p>
                    </div>

                    <div class="explanation-section">
                      <h4><mat-icon>info</mat-icon> Explication :</h4>
                      <p class="explanation-content">{{ error.explication }}</p>
                    </div>
                  </div>
                </mat-expansion-panel>
              }
            </mat-accordion>
          </div>
        }
      </mat-dialog-content>

      <mat-dialog-actions>
        <button mat-raised-button color="primary" (click)="close()">
          Fermer
        </button>
      </mat-dialog-actions>
    </div>
  `,
  styles: [`
    .dialog-container {
      max-width: 100%;
    }

    h2 {
      display: flex;
      align-items: center;
      gap: 12px;
      color: #1976d2;
      margin: 0;

      mat-icon {
        font-size: 32px;
        width: 32px;
        height: 32px;
      }
    }

    mat-dialog-content {
      padding: 24px 0;
      min-height: 200px;
    }

    .summary-card {
      background: #f5f5f5;
      border-radius: 8px;
      padding: 24px;
      margin-bottom: 24px;
    }

    .success-message,
    .warning-message {
      text-align: center;

      mat-icon {
        font-size: 64px;
        width: 64px;
        height: 64px;
        margin-bottom: 16px;
      }

      h3 {
        margin: 0 0 12px 0;
        font-size: 24px;
      }

      p {
        margin: 0;
        color: #666;
        font-size: 16px;
      }
    }

    .success-icon {
      color: #4caf50;
    }

    .warning-icon {
      color: #ff9800;
    }

    .errors-list {
      margin-top: 24px;

      mat-expansion-panel {
        margin-bottom: 12px;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);

        &:hover {
          box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
        }
      }

      .mat-expansion-panel-header {
        padding: 16px 24px;
      }

      mat-panel-title {
        display: flex;
        align-items: center;
        gap: 12px;

        .error-icon {
          color: #f44336;
          font-size: 24px;
          width: 24px;
          height: 24px;
          flex-shrink: 0;
        }

        .error-text {
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
      }
    }

    .error-details {
      padding: 16px 24px 24px;
      background: #fafafa;
    }

    .error-section,
    .correction-section,
    .explanation-section {
      margin-bottom: 16px;
      padding: 12px;
      border-radius: 4px;

      h4 {
        display: flex;
        align-items: center;
        gap: 8px;
        margin: 0 0 8px 0;
        font-size: 14px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;

        mat-icon {
          font-size: 18px;
          width: 18px;
          height: 18px;
        }
      }

      p {
        margin: 0;
        line-height: 1.6;
        font-size: 15px;
      }
    }

    .error-section {
      background: #ffebee;
      border-left: 4px solid #f44336;

      h4 {
        color: #c62828;
      }

      .error-content {
        color: #d32f2f;
      }
    }

    .correction-section {
      background: #e8f5e9;
      border-left: 4px solid #4caf50;

      h4 {
        color: #2e7d32;
      }

      .correction-content {
        color: #388e3c;
        font-weight: 500;
      }
    }

    .explanation-section {
      background: #e3f2fd;
      border-left: 4px solid #2196f3;

      h4 {
        color: #1565c0;
      }

      .explanation-content {
        color: #1976d2;
      }
    }

    mat-dialog-actions {
      justify-content: center;
      padding: 16px 24px;
    }
  `],
})
export class GrammarReviewDialogComponent {
  constructor(
    @Inject(MAT_DIALOG_DATA) public data: GrammarReview,
    private dialogRef: MatDialogRef<GrammarReviewDialogComponent>
  ) {}

  close(): void {
    this.dialogRef.close();
  }

  truncate(text: string, maxLength: number): string {
    if (text.length <= maxLength) {
      return text;
    }
    return text.substring(0, maxLength) + '...';
  }
}
