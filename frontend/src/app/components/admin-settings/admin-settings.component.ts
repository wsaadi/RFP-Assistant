import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSliderModule } from '@angular/material/slider';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ApiService } from '../../services/api.service';
import { AIConfig } from '../../models/report.model';

@Component({
  selector: 'app-admin-settings',
  standalone: true,
  imports: [
    CommonModule, FormsModule, RouterLink,
    MatCardModule, MatButtonModule, MatIconModule, MatInputModule,
    MatSelectModule, MatSliderModule, MatSnackBarModule,
  ],
  template: `
    <div class="page-container">
      <div class="page-header">
        <button mat-icon-button routerLink="/workspaces"><mat-icon>arrow_back</mat-icon></button>
        <h1>Configuration IA</h1>
      </div>

      <mat-card class="config-card">
        <h3><mat-icon>smart_toy</mat-icon> Paramètres Mistral AI</h3>

        <div class="form-section">
          <mat-form-field appearance="outline" class="full-width">
            <mat-label>Clé API Mistral</mat-label>
            <input matInput [(ngModel)]="config.mistral_api_key" type="password" placeholder="sk-...">
            <mat-icon matSuffix>vpn_key</mat-icon>
          </mat-form-field>

          <mat-form-field appearance="outline" class="full-width">
            <mat-label>Modèle</mat-label>
            <mat-select [(ngModel)]="config.model_name">
              <mat-option value="mistral-large-latest">Mistral Large (recommandé)</mat-option>
              <mat-option value="mistral-medium-latest">Mistral Medium</mat-option>
              <mat-option value="mistral-small-latest">Mistral Small</mat-option>
              <mat-option value="open-mistral-nemo">Open Mistral Nemo</mat-option>
              <mat-option value="codestral-latest">Codestral</mat-option>
            </mat-select>
          </mat-form-field>

          <div class="slider-field">
            <label>Température: {{ config.temperature }}</label>
            <mat-slider min="0" max="1" step="0.05" discrete>
              <input matSliderThumb [(ngModel)]="config.temperature">
            </mat-slider>
            <small>Basse = plus déterministe, Haute = plus créatif</small>
          </div>

          <mat-form-field appearance="outline" class="full-width">
            <mat-label>Tokens maximum</mat-label>
            <input matInput [(ngModel)]="config.max_tokens" type="number" min="256" max="32000">
            <mat-hint>Entre 256 et 32000</mat-hint>
          </mat-form-field>
        </div>

        <div class="form-actions">
          <button mat-button (click)="loadConfig()">Réinitialiser</button>
          <button mat-raised-button color="primary" (click)="saveConfig()">
            <mat-icon>save</mat-icon> Enregistrer
          </button>
        </div>
      </mat-card>

      <mat-card class="info-card">
        <h3><mat-icon>info</mat-icon> Informations</h3>
        <div class="info-grid">
          <div class="info-item">
            <strong>Fournisseur IA</strong>
            <span>Mistral AI (exclusivement)</span>
          </div>
          <div class="info-item">
            <strong>Anonymisation</strong>
            <span>GLiNER2 - Reconnaissance d'entités nommées locale</span>
          </div>
          <div class="info-item">
            <strong>Base vectorielle</strong>
            <span>ChromaDB - Indexation et recherche sémantique</span>
          </div>
          <div class="info-item">
            <strong>Modèle recommandé</strong>
            <span>mistral-large-latest pour la meilleure qualité de rédaction</span>
          </div>
        </div>
      </mat-card>
    </div>
  `,
  styles: [`
    .page-container { max-width: 800px; margin: 0 auto; }
    .page-header { display: flex; align-items: center; gap: 12px; margin-bottom: 24px; }
    .page-header h1 { flex: 1; margin: 0; color: #1B3A5C; font-size: 20px; }
    .config-card { padding: 24px; margin-bottom: 16px; }
    .config-card h3 { display: flex; align-items: center; gap: 8px; color: #1B3A5C; margin-top: 0; }
    .form-section { display: flex; flex-direction: column; gap: 8px; }
    .full-width { width: 100%; }
    .slider-field { margin: 8px 0 16px; }
    .slider-field label { display: block; margin-bottom: 4px; font-weight: 500; color: #333; }
    .slider-field small { color: #888; font-size: 12px; }
    .slider-field mat-slider { width: 100%; }
    .form-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }
    .info-card { padding: 24px; }
    .info-card h3 { display: flex; align-items: center; gap: 8px; color: #1B3A5C; margin-top: 0; }
    .info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .info-item { display: flex; flex-direction: column; gap: 4px; }
    .info-item strong { color: #1B3A5C; font-size: 13px; }
    .info-item span { color: #666; font-size: 14px; }
  `],
})
export class AdminSettingsComponent implements OnInit {
  workspaceId = '';
  config: AIConfig = {
    mistral_api_key: '',
    model_name: 'mistral-large-latest',
    temperature: 0.3,
    max_tokens: 4096,
  };

  constructor(
    private route: ActivatedRoute,
    private api: ApiService,
    private snackBar: MatSnackBar,
  ) {}

  ngOnInit(): void {
    this.workspaceId = this.route.snapshot.paramMap.get('workspaceId') || '';
    if (this.workspaceId) {
      this.loadConfig();
    }
  }

  loadConfig(): void {
    this.api.getAIConfig(this.workspaceId).subscribe({
      next: (cfg) => {
        this.config = {
          mistral_api_key: cfg.mistral_api_key || '',
          model_name: cfg.model_name || 'mistral-large-latest',
          temperature: cfg.temperature ?? 0.3,
          max_tokens: cfg.max_tokens || 4096,
        };
      },
      error: () => {
        // No config yet, keep defaults
      },
    });
  }

  saveConfig(): void {
    this.api.updateAIConfig(this.workspaceId, this.config).subscribe({
      next: () => this.snackBar.open('Configuration enregistrée', 'OK', { duration: 3000 }),
      error: (err) => this.snackBar.open(err.error?.detail || 'Erreur de sauvegarde', 'OK', { duration: 5000 }),
    });
  }
}
