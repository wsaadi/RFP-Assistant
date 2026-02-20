import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatCardModule } from '@angular/material/card';
import { ReportService } from '../../services/report.service';

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [CommonModule, MatButtonModule, MatIconModule, MatCardModule],
  template: `
    <div class="container">
      <section class="hero">
        <div class="hero-content">
          <h1>Assistant Rapport de Stage TN05</h1>
          <p class="hero-subtitle">
            Rédigez votre rapport de stage UTC en toute sérénité grâce à
            l'intelligence artificielle
          </p>

          <div class="hero-actions">
            @if (reportService.report()) {
              <button class="btn-primary large" (click)="continueReport()">
                <mat-icon>edit</mat-icon>
                Continuer mon rapport
              </button>
              <button class="btn-secondary large" (click)="newReport()">
                Nouveau rapport
              </button>
            } @else {
              <button class="btn-primary large" (click)="startNew()">
                <mat-icon>add</mat-icon>
                Commencer mon rapport
              </button>
            }
          </div>
        </div>

        <div class="hero-illustration">
          <div class="illustration-card">
            <div class="card-header">
              <span class="dot red"></span>
              <span class="dot yellow"></span>
              <span class="dot green"></span>
            </div>
            <div class="card-content">
              <div class="line title"></div>
              <div class="line"></div>
              <div class="line short"></div>
              <div class="line"></div>
              <div class="line medium"></div>
            </div>
          </div>
        </div>
      </section>

      <section class="features">
        <h2>Fonctionnalités</h2>
        <div class="features-grid">
          <mat-card class="feature-card">
            <mat-icon class="feature-icon">auto_awesome</mat-icon>
            <h3>Plan détaillé automatique</h3>
            <p>
              Génération d'un plan de rapport conforme aux exigences UTC TN05
              avec toutes les sections requises
            </p>
          </mat-card>

          <mat-card class="feature-card">
            <mat-icon class="feature-icon">edit_note</mat-icon>
            <h3>Éditeur intuitif</h3>
            <p>
              Interface graphique élégante pour organiser vos notes et rédiger
              chaque section de votre rapport
            </p>
          </mat-card>

          <mat-card class="feature-card">
            <mat-icon class="feature-icon">help_outline</mat-icon>
            <h3>Questions suggérées</h3>
            <p>
              L'IA génère des questions pertinentes à poser pendant votre stage
              pour enrichir chaque section
            </p>
          </mat-card>

          <mat-card class="feature-card">
            <mat-icon class="feature-icon">lightbulb</mat-icon>
            <h3>Recommandations personnalisées</h3>
            <p>
              Conseils adaptés à l'avancement de chaque section pour améliorer
              votre rapport
            </p>
          </mat-card>

          <mat-card class="feature-card">
            <mat-icon class="feature-icon">description</mat-icon>
            <h3>Export Word professionnel</h3>
            <p>
              Génération automatique d'un document Word formaté selon les
              normes UTC
            </p>
          </mat-card>

          <mat-card class="feature-card">
            <mat-icon class="feature-icon">spellcheck</mat-icon>
            <h3>Rédaction assistée</h3>
            <p>
              L'IA vous aide à transformer vos notes en texte professionnel
              sans fautes
            </p>
          </mat-card>
        </div>
      </section>

      <section class="providers">
        <h2>Fournisseurs IA supportés</h2>
        <div class="providers-grid">
          <div class="provider-card">
            <div class="provider-logo openai">OpenAI</div>
            <p>GPT-4o pour une rédaction de qualité</p>
          </div>
          <div class="provider-card">
            <div class="provider-logo mistral">Mistral AI</div>
            <p>Mistral Large pour une alternative française</p>
          </div>
        </div>
      </section>
    </div>
  `,
  styles: [`
    .hero {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 48px;
      padding: 48px 0 64px;
      align-items: center;

      @media (max-width: 968px) {
        grid-template-columns: 1fr;
        text-align: center;
      }
    }

    .hero-content {
      h1 {
        font-size: 42px;
        font-weight: 700;
        color: #1a237e;
        margin-bottom: 16px;
        line-height: 1.2;
      }

      .hero-subtitle {
        font-size: 18px;
        color: #546e7a;
        line-height: 1.6;
        margin-bottom: 32px;
      }
    }

    .hero-actions {
      display: flex;
      gap: 16px;

      @media (max-width: 968px) {
        justify-content: center;
      }

      .large {
        padding: 14px 28px;
        font-size: 16px;

        mat-icon {
          margin-right: 8px;
        }
      }
    }

    .hero-illustration {
      display: flex;
      justify-content: center;

      .illustration-card {
        background: white;
        border-radius: 16px;
        box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
        width: 100%;
        max-width: 400px;
        overflow: hidden;

        .card-header {
          background: #f5f5f5;
          padding: 12px 16px;
          display: flex;
          gap: 8px;

          .dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;

            &.red { background: #ff5f57; }
            &.yellow { background: #ffbd2e; }
            &.green { background: #28c840; }
          }
        }

        .card-content {
          padding: 24px;

          .line {
            height: 12px;
            background: #e0e0e0;
            border-radius: 6px;
            margin-bottom: 12px;

            &.title {
              width: 60%;
              height: 20px;
              background: #1976d2;
              margin-bottom: 20px;
            }

            &.short { width: 40%; }
            &.medium { width: 70%; }
          }
        }
      }
    }

    .features {
      padding: 64px 0;

      h2 {
        text-align: center;
        font-size: 32px;
        color: #1a237e;
        margin-bottom: 48px;
      }
    }

    .features-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 24px;

      @media (max-width: 968px) {
        grid-template-columns: repeat(2, 1fr);
      }

      @media (max-width: 600px) {
        grid-template-columns: 1fr;
      }
    }

    .feature-card {
      padding: 32px;
      text-align: center;
      border-radius: 16px;
      transition: transform 0.3s ease, box-shadow 0.3s ease;

      &:hover {
        transform: translateY(-4px);
        box-shadow: 0 12px 24px rgba(0, 0, 0, 0.1);
      }

      .feature-icon {
        font-size: 48px;
        width: 48px;
        height: 48px;
        color: #1976d2;
        margin-bottom: 16px;
      }

      h3 {
        font-size: 18px;
        color: #37474f;
        margin-bottom: 12px;
      }

      p {
        font-size: 14px;
        color: #78909c;
        line-height: 1.5;
      }
    }

    .providers {
      padding: 48px 0 64px;
      text-align: center;

      h2 {
        font-size: 28px;
        color: #1a237e;
        margin-bottom: 32px;
      }
    }

    .providers-grid {
      display: flex;
      justify-content: center;
      gap: 32px;

      @media (max-width: 600px) {
        flex-direction: column;
        align-items: center;
      }
    }

    .provider-card {
      background: white;
      padding: 32px 48px;
      border-radius: 16px;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);

      .provider-logo {
        font-size: 24px;
        font-weight: 700;
        margin-bottom: 12px;

        &.openai { color: #10a37f; }
        &.mistral { color: #ff6b35; }
      }

      p {
        color: #78909c;
        font-size: 14px;
      }
    }
  `],
})
export class HomeComponent {
  reportService = inject(ReportService);
  private router = inject(Router);

  startNew(): void {
    this.router.navigate(['/setup']);
  }

  continueReport(): void {
    this.router.navigate(['/editor']);
  }

  newReport(): void {
    if (confirm('Êtes-vous sûr de vouloir créer un nouveau rapport ? Les données actuelles seront perdues.')) {
      this.reportService.resetReport();
      this.router.navigate(['/setup']);
    }
  }
}
