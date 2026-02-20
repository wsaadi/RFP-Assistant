import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ReportService } from '../../services/report.service';
import { ApiService } from '../../services/api.service';
import { GrammarReviewDialogComponent } from '../grammar-review-dialog/grammar-review-dialog.component';
import { AIConfigDialogComponent } from '../ai-config-dialog/ai-config-dialog.component';

@Component({
  selector: 'app-header',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    RouterLinkActive,
    MatToolbarModule,
    MatButtonModule,
    MatIconModule,
    MatMenuModule,
    MatDialogModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
  ],
  template: `
    <mat-toolbar class="header">
      <div class="container header-content">
        <a routerLink="/" class="logo">
          <span class="logo-icon">📝</span>
          <span class="logo-text">UTC TN05 Assistant</span>
        </a>

        <nav class="nav-links">
          <a routerLink="/" routerLinkActive="active" [routerLinkActiveOptions]="{exact: true}">
            Accueil
          </a>
          @if (reportService.report()) {
            <a routerLink="/editor" routerLinkActive="active">
              Éditeur
            </a>
          }
        </nav>

        <div class="header-actions">
          <button
            class="ai-config-button"
            (click)="openAIConfig()"
            matTooltip="Configurer l'IA"
          >
            <mat-icon>smart_toy</mat-icon>
            @if (reportService.aiConfig()) {
              <span class="ai-provider">{{ reportService.aiConfig()?.provider === 'openai' ? 'OpenAI' : 'Mistral' }}</span>
              <mat-icon class="config-status success">check_circle</mat-icon>
            } @else {
              <span class="ai-provider">Configurer</span>
              <mat-icon class="config-status warning">warning</mat-icon>
            }
          </button>

          @if (reportService.report()) {
            <span class="progress-badge">
              {{ reportService.progress().progress_percentage }}% complété
            </span>
          }

          @if (reportService.report()) {
            <button mat-icon-button [matMenuTriggerFor]="menu" class="menu-button">
              <mat-icon>more_vert</mat-icon>
            </button>
            <mat-menu #menu="matMenu">
              <button mat-menu-item (click)="exportData()">
                <mat-icon>download</mat-icon>
                <span>Exporter le travail</span>
              </button>
              <button mat-menu-item (click)="importData()">
                <mat-icon>upload</mat-icon>
                <span>Importer le travail</span>
              </button>
              <button mat-menu-item (click)="reviewGrammar()" [disabled]="isReviewing">
                <mat-icon>spellcheck</mat-icon>
                <span>Revue orthographique</span>
              </button>
            </mat-menu>
          }
        </div>

        <input type="file" #fileInput accept=".json" style="display: none" (change)="onFileSelected($event)" />
      </div>
    </mat-toolbar>
  `,
  styles: [`
    .header {
      background: linear-gradient(135deg, #1976d2 0%, #1565c0 100%);
      color: white;
      position: sticky;
      top: 0;
      z-index: 1000;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
    }

    .header-content {
      display: flex;
      align-items: center;
      justify-content: space-between;
      width: 100%;
      max-width: 1400px;
      margin: 0 auto;
    }

    .logo {
      display: flex;
      align-items: center;
      gap: 12px;
      text-decoration: none;
      color: white;

      .logo-icon {
        font-size: 28px;
      }

      .logo-text {
        font-size: 20px;
        font-weight: 500;
        letter-spacing: 0.5px;
      }
    }

    .nav-links {
      display: flex;
      gap: 8px;

      a {
        color: rgba(255, 255, 255, 0.85);
        text-decoration: none;
        padding: 8px 16px;
        border-radius: 8px;
        font-weight: 500;
        transition: all 0.2s ease;

        &:hover {
          background: rgba(255, 255, 255, 0.1);
          color: white;
        }

        &.active {
          background: rgba(255, 255, 255, 0.2);
          color: white;
        }
      }
    }

    .header-actions {
      display: flex;
      align-items: center;
      gap: 16px;
    }

    .ai-config-button {
      display: flex;
      align-items: center;
      gap: 6px;
      background: rgba(255, 255, 255, 0.15);
      padding: 6px 12px;
      border-radius: 20px;
      font-size: 13px;
      border: none;
      color: white;
      cursor: pointer;
      transition: all 0.2s;

      &:hover {
        background: rgba(255, 255, 255, 0.25);
      }

      mat-icon {
        font-size: 18px;
        width: 18px;
        height: 18px;
      }

      .ai-provider {
        font-weight: 500;
      }

      .config-status {
        font-size: 14px;
        width: 14px;
        height: 14px;

        &.success {
          color: #69f0ae;
        }

        &.warning {
          color: #ffab40;
        }
      }
    }

    .progress-badge {
      background: rgba(76, 175, 80, 0.9);
      padding: 6px 12px;
      border-radius: 20px;
      font-size: 13px;
      font-weight: 500;
    }

    .menu-button {
      color: white;
    }

    @media (max-width: 768px) {
      .logo-text {
        display: none;
      }

      .nav-links a {
        padding: 8px 12px;
        font-size: 14px;
      }
    }
  `],
})
export class HeaderComponent {
  reportService = inject(ReportService);
  private apiService = inject(ApiService);
  private dialog = inject(MatDialog);

  isReviewing = false;

  openAIConfig(): void {
    this.dialog.open(AIConfigDialogComponent, {
      width: '500px',
      disableClose: false,
    });
  }

  exportData(): void {
    this.reportService.downloadExport();
  }

  importData(): void {
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    if (fileInput) {
      fileInput.click();
    }
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (!input.files || input.files.length === 0) {
      return;
    }

    const file = input.files[0];
    const reader = new FileReader();

    reader.onload = (e) => {
      try {
        const content = e.target?.result as string;
        const result = this.reportService.importAllData(content);

        if (result.success) {
          alert('Import réussi ! Vos données ont été restaurées.');
          window.location.reload();
        } else {
          alert(`Erreur d'import: ${result.error}`);
        }
      } catch (error) {
        alert(`Erreur lors de la lecture du fichier: ${error}`);
      }
    };

    reader.readAsText(file);
    input.value = '';
  }

  reviewGrammar(): void {
    const report = this.reportService.report();
    const aiConfig = this.reportService.aiConfig();

    if (!report || !aiConfig) {
      alert('Impossible de lancer la revue. Assurez-vous d\'avoir configuré l\'IA et d\'avoir un rapport en cours.');
      return;
    }

    // Build report content from all sections
    const buildReportContent = (sections: any[]): string => {
      let content = '';
      for (const section of sections) {
        if (section.content && section.content.trim()) {
          content += `\n\n${section.title}\n\n${section.content}`;
        }
        if (section.subsections && section.subsections.length > 0) {
          content += buildReportContent(section.subsections);
        }
      }
      return content;
    };

    const reportContent = buildReportContent(report.plan.sections);

    if (!reportContent.trim()) {
      alert('Aucun contenu à analyser. Veuillez d\'abord rédiger du contenu dans vos sections.');
      return;
    }

    this.isReviewing = true;

    this.apiService.reviewGrammar(reportContent, aiConfig).subscribe({
      next: (response) => {
        this.isReviewing = false;
        if (response.success) {
          this.dialog.open(GrammarReviewDialogComponent, {
            width: '800px',
            maxHeight: '80vh',
            data: response.review,
          });
        }
      },
      error: (error) => {
        this.isReviewing = false;
        console.error('Error reviewing grammar:', error);
        alert('Erreur lors de la revue grammaticale. Veuillez réessayer.');
      },
    });
  }
}
