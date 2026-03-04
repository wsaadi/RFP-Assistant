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
import { MatRadioModule } from '@angular/material/radio';
import { MatDividerModule } from '@angular/material/divider';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ApiService } from '../../services/api.service';
import { AIConfigUpdate } from '../../models/report.model';

@Component({
  selector: 'app-admin-settings',
  standalone: true,
  imports: [
    CommonModule, FormsModule, RouterLink,
    MatCardModule, MatButtonModule, MatIconModule, MatInputModule,
    MatSelectModule, MatSliderModule, MatSnackBarModule,
    MatRadioModule, MatDividerModule, MatTooltipModule,
  ],
  template: `
    <div class="page-container">
      <div class="page-header">
        <button mat-icon-button routerLink="/workspaces"><mat-icon>arrow_back</mat-icon></button>
        <h1>Configuration IA</h1>
      </div>

      <!-- ═══════════════════════════════════════════ -->
      <!-- SECTION 1: Generation Provider              -->
      <!-- ═══════════════════════════════════════════ -->
      <mat-card class="config-card provider-card">
        <h3><mat-icon>hub</mat-icon> Fournisseur IA pour la génération</h3>
        <p class="provider-hint">Choisissez le fournisseur utilisé pour générer le contenu des réponses.</p>

        <mat-radio-group [(ngModel)]="config.provider" class="provider-radio-group">
          <div class="provider-option" [class.selected]="config.provider === 'mistral'"
               (click)="config.provider = 'mistral'">
            <mat-radio-button value="mistral">
              <div class="provider-label">
                <strong>Mistral AI</strong>
                <span class="provider-tag api-tag">API Cloud</span>
              </div>
            </mat-radio-button>
            <p class="provider-desc">API cloud Mistral — modèles puissants, nécessite une clé API et une connexion internet.</p>
          </div>

          <div class="provider-option" [class.selected]="config.provider === 'ollama'"
               (click)="config.provider = 'ollama'">
            <mat-radio-button value="ollama">
              <div class="provider-label">
                <strong>Ollama</strong>
                <span class="provider-tag local-tag">Local</span>
              </div>
            </mat-radio-button>
            <p class="provider-desc">Serveur Ollama local — modèles open-source, pas de clé API, données 100% en local.</p>
          </div>
        </mat-radio-group>
      </mat-card>

      <!-- Mistral Configuration -->
      <mat-card class="config-card" *ngIf="config.provider === 'mistral'">
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
        </div>
      </mat-card>

      <!-- Ollama Generation Configuration -->
      <mat-card class="config-card" *ngIf="config.provider === 'ollama'">
        <h3><mat-icon>dns</mat-icon> Paramètres Ollama (génération)</h3>
        <div class="form-section">
          <mat-form-field appearance="outline" class="full-width">
            <mat-label>URL du serveur Ollama</mat-label>
            <input matInput [(ngModel)]="config.ollama_base_url" placeholder="http://localhost:11434">
            <mat-icon matSuffix>link</mat-icon>
            <mat-hint>Adresse du serveur Ollama (ex: http://localhost:11434)</mat-hint>
          </mat-form-field>
          <mat-form-field appearance="outline" class="full-width">
            <mat-label>Modèle Ollama</mat-label>
            <mat-select [(ngModel)]="config.ollama_model">
              <mat-option value="mistral:latest">Mistral 7B (recommandé)</mat-option>
              <mat-option value="mistral-nemo:latest">Mistral Nemo 12B</mat-option>
              <mat-option value="mixtral:latest">Mixtral 8x7B</mat-option>
              <mat-option value="llama3.1:latest">Llama 3.1 8B</mat-option>
              <mat-option value="llama3.1:70b">Llama 3.1 70B</mat-option>
              <mat-option value="qwen2.5:latest">Qwen 2.5 7B</mat-option>
              <mat-option value="qwen2.5:32b">Qwen 2.5 32B</mat-option>
              <mat-option value="gemma3:12b">Gemma 3 12B</mat-option>
              <mat-option value="deepseek-r1:latest">DeepSeek R1</mat-option>
              <mat-option value="command-r:latest">Command R</mat-option>
            </mat-select>
          </mat-form-field>
        </div>
      </mat-card>

      <!-- Common Parameters -->
      <mat-card class="config-card">
        <h3><mat-icon>tune</mat-icon> Paramètres de génération</h3>
        <div class="form-section">
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
      </mat-card>

      <mat-divider class="section-divider"></mat-divider>

      <!-- ═══════════════════════════════════════════ -->
      <!-- SECTION 2: NER (Anonymization) Provider     -->
      <!-- ═══════════════════════════════════════════ -->
      <mat-card class="config-card provider-card">
        <h3><mat-icon>security</mat-icon> Fournisseur pour l'anonymisation (NER)</h3>
        <p class="provider-hint">Modèle utilisé pour détecter les entités nommées (noms, emails, téléphones) dans les documents.</p>

        <mat-radio-group [(ngModel)]="config.ner_provider" class="provider-radio-group">
          <div class="provider-option" [class.selected]="config.ner_provider === 'ollama'"
               (click)="config.ner_provider = 'ollama'">
            <mat-radio-button value="ollama">
              <div class="provider-label">
                <strong>Ollama</strong>
                <span class="provider-tag local-tag">Local</span>
              </div>
            </mat-radio-button>
            <p class="provider-desc">Données 100% en local — aucune donnée personnelle ne quitte votre infrastructure.</p>
          </div>

          <div class="provider-option" [class.selected]="config.ner_provider === 'mistral'"
               (click)="config.ner_provider = 'mistral'">
            <mat-radio-button value="mistral">
              <div class="provider-label">
                <strong>Mistral AI</strong>
                <span class="provider-tag api-tag">API Cloud</span>
              </div>
            </mat-radio-button>
            <p class="provider-desc">API Mistral — utilise la clé API configurée ci-dessus.</p>
          </div>

          <div class="provider-option" [class.selected]="config.ner_provider === 'scaleway'"
               (click)="config.ner_provider = 'scaleway'">
            <mat-radio-button value="scaleway">
              <div class="provider-label">
                <strong>Scaleway</strong>
                <span class="provider-tag scw-tag">API EU</span>
              </div>
            </mat-radio-button>
            <p class="provider-desc">Scaleway Generative APIs — hébergé en Europe, compatible OpenAI.</p>
          </div>
        </mat-radio-group>
      </mat-card>

      <!-- NER Model Selection -->
      <mat-card class="config-card">
        <h3><mat-icon>psychology</mat-icon> Modèle d'anonymisation</h3>
        <div class="form-section">
          <!-- Ollama NER models -->
          <mat-form-field appearance="outline" class="full-width" *ngIf="config.ner_provider === 'ollama'">
            <mat-label>Modèle NER (Ollama)</mat-label>
            <mat-select [(ngModel)]="config.ner_model">
              <mat-option value="qwen2.5:14b">Qwen 2.5 14B (recommandé)</mat-option>
              <mat-option value="qwen2.5:7b">Qwen 2.5 7B</mat-option>
              <mat-option value="qwen2.5:32b">Qwen 2.5 32B</mat-option>
              <mat-option value="mistral:latest">Mistral 7B</mat-option>
              <mat-option value="mistral-nemo:latest">Mistral Nemo 12B</mat-option>
              <mat-option value="llama3.1:latest">Llama 3.1 8B</mat-option>
              <mat-option value="gemma3:12b">Gemma 3 12B</mat-option>
            </mat-select>
            <mat-hint>Le modèle doit être téléchargé: ollama pull {{ config.ner_model }}</mat-hint>
          </mat-form-field>

          <!-- Mistral NER models -->
          <mat-form-field appearance="outline" class="full-width" *ngIf="config.ner_provider === 'mistral'">
            <mat-label>Modèle NER (Mistral)</mat-label>
            <mat-select [(ngModel)]="config.ner_model">
              <mat-option value="mistral-large-latest">Mistral Large (recommandé)</mat-option>
              <mat-option value="mistral-medium-latest">Mistral Medium</mat-option>
              <mat-option value="mistral-small-latest">Mistral Small</mat-option>
              <mat-option value="open-mistral-nemo">Open Mistral Nemo</mat-option>
            </mat-select>
          </mat-form-field>

          <!-- Scaleway NER models -->
          <mat-form-field appearance="outline" class="full-width" *ngIf="config.ner_provider === 'scaleway'">
            <mat-label>Modèle NER (Scaleway)</mat-label>
            <mat-select [(ngModel)]="config.ner_model">
              <mat-option value="mistral-large-latest">Mistral Large (recommandé)</mat-option>
              <mat-option value="mistral-small-latest">Mistral Small</mat-option>
              <mat-option value="llama-3.3-70b-instruct">Llama 3.3 70B Instruct</mat-option>
              <mat-option value="llama-3.1-8b-instruct">Llama 3.1 8B Instruct</mat-option>
              <mat-option value="qwen2.5-coder-32b-instruct">Qwen 2.5 Coder 32B</mat-option>
            </mat-select>
          </mat-form-field>
        </div>
      </mat-card>

      <mat-divider class="section-divider"></mat-divider>

      <!-- ═══════════════════════════════════════════ -->
      <!-- SECTION 3: Vision (Image Analysis) Provider -->
      <!-- ═══════════════════════════════════════════ -->
      <mat-card class="config-card provider-card">
        <h3><mat-icon>image_search</mat-icon> Fournisseur pour l'analyse d'images (Vision)</h3>
        <p class="provider-hint">Modèle utilisé pour analyser les images extraites des documents (diagrammes, tableaux, captures).</p>

        <mat-radio-group [(ngModel)]="config.vision_provider" class="provider-radio-group">
          <div class="provider-option" [class.selected]="config.vision_provider === 'ollama'"
               (click)="config.vision_provider = 'ollama'">
            <mat-radio-button value="ollama">
              <div class="provider-label">
                <strong>Ollama</strong>
                <span class="provider-tag local-tag">Local</span>
              </div>
            </mat-radio-button>
            <p class="provider-desc">Images 100% en local — aucune image ne quitte votre infrastructure.</p>
          </div>

          <div class="provider-option" [class.selected]="config.vision_provider === 'mistral'"
               (click)="config.vision_provider = 'mistral'">
            <mat-radio-button value="mistral">
              <div class="provider-label">
                <strong>Mistral AI</strong>
                <span class="provider-tag api-tag">API Cloud</span>
              </div>
            </mat-radio-button>
            <p class="provider-desc">Pixtral — modèles vision de Mistral, utilise la clé API configurée ci-dessus.</p>
          </div>

          <div class="provider-option" [class.selected]="config.vision_provider === 'scaleway'"
               (click)="config.vision_provider = 'scaleway'">
            <mat-radio-button value="scaleway">
              <div class="provider-label">
                <strong>Scaleway</strong>
                <span class="provider-tag scw-tag">API EU</span>
              </div>
            </mat-radio-button>
            <p class="provider-desc">Scaleway Generative APIs — modèles vision hébergés en Europe.</p>
          </div>
        </mat-radio-group>
      </mat-card>

      <!-- Vision Model Selection -->
      <mat-card class="config-card">
        <h3><mat-icon>visibility</mat-icon> Modèle d'analyse d'images</h3>
        <div class="form-section">
          <!-- Ollama Vision models -->
          <mat-form-field appearance="outline" class="full-width" *ngIf="config.vision_provider === 'ollama'">
            <mat-label>Modèle Vision (Ollama)</mat-label>
            <mat-select [(ngModel)]="config.vision_model">
              <mat-option value="llama3.2-vision:11b">Llama 3.2 Vision 11B (recommandé)</mat-option>
              <mat-option value="llama3.2-vision:latest">Llama 3.2 Vision (latest)</mat-option>
              <mat-option value="llava:latest">LLaVA</mat-option>
              <mat-option value="llava:13b">LLaVA 13B</mat-option>
              <mat-option value="bakllava:latest">BakLLaVA</mat-option>
            </mat-select>
            <mat-hint>Le modèle doit être téléchargé: ollama pull {{ config.vision_model }}</mat-hint>
          </mat-form-field>

          <!-- Mistral Vision models -->
          <mat-form-field appearance="outline" class="full-width" *ngIf="config.vision_provider === 'mistral'">
            <mat-label>Modèle Vision (Mistral)</mat-label>
            <mat-select [(ngModel)]="config.vision_model">
              <mat-option value="pixtral-large-latest">Pixtral Large (recommandé)</mat-option>
              <mat-option value="pixtral-12b-2409">Pixtral 12B</mat-option>
            </mat-select>
          </mat-form-field>

          <!-- Scaleway Vision models -->
          <mat-form-field appearance="outline" class="full-width" *ngIf="config.vision_provider === 'scaleway'">
            <mat-label>Modèle Vision (Scaleway)</mat-label>
            <mat-select [(ngModel)]="config.vision_model">
              <mat-option value="pixtral-12b-2409">Pixtral 12B (recommandé)</mat-option>
              <mat-option value="llama-3.2-11b-vision-instruct">Llama 3.2 11B Vision</mat-option>
            </mat-select>
          </mat-form-field>
        </div>
      </mat-card>

      <mat-divider class="section-divider"></mat-divider>

      <!-- ═══════════════════════════════════════════ -->
      <!-- SECTION 4: Scaleway API Key (if needed)     -->
      <!-- ═══════════════════════════════════════════ -->
      <mat-card class="config-card" *ngIf="config.ner_provider === 'scaleway' || config.vision_provider === 'scaleway'">
        <h3><mat-icon>vpn_key</mat-icon> Authentification Scaleway</h3>
        <p class="provider-hint">Nécessaire pour utiliser les Generative APIs de Scaleway. Vous trouverez ces informations dans la console IAM Scaleway.</p>
        <div class="form-section">
          <mat-form-field appearance="outline" class="full-width">
            <mat-label>Project ID Scaleway</mat-label>
            <input matInput [(ngModel)]="config.scaleway_project_id" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx">
            <mat-icon matSuffix>folder</mat-icon>
            <mat-hint>L'ID du projet Scaleway (visible dans Settings > Project du dashboard)</mat-hint>
          </mat-form-field>
          <mat-form-field appearance="outline" class="full-width">
            <mat-label>Secret Key Scaleway</mat-label>
            <input matInput [(ngModel)]="config.scaleway_api_key" type="password" placeholder="SCW...">
            <mat-icon matSuffix>vpn_key</mat-icon>
            <mat-hint>Votre Secret Key Scaleway (SCW...)</mat-hint>
          </mat-form-field>
        </div>
      </mat-card>

      <!-- Save Button -->
      <mat-card class="config-card">
        <div class="form-actions">
          <button mat-button (click)="loadConfig()">Réinitialiser</button>
          <button mat-raised-button color="primary" (click)="saveConfig()">
            <mat-icon>save</mat-icon> Enregistrer
          </button>
        </div>
      </mat-card>

      <!-- Info Summary -->
      <mat-card class="info-card">
        <h3><mat-icon>info</mat-icon> Récapitulatif</h3>
        <div class="info-grid">
          <div class="info-item">
            <strong>Génération</strong>
            <span>{{ getProviderLabel(config.provider) }} — {{ config.provider === 'ollama' ? config.ollama_model : config.model_name }}</span>
          </div>
          <div class="info-item">
            <strong>Anonymisation (NER)</strong>
            <span>{{ getProviderLabel(config.ner_provider) }} — {{ config.ner_model }}</span>
          </div>
          <div class="info-item">
            <strong>Analyse d'images (Vision)</strong>
            <span>{{ getProviderLabel(config.vision_provider) }} — {{ config.vision_model }}</span>
          </div>
          <div class="info-item">
            <strong>Base vectorielle</strong>
            <span>ChromaDB — Indexation et recherche sémantique</span>
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
    .section-divider { margin: 24px 0; }

    /* Provider selection */
    .provider-hint { color: #666; font-size: 14px; margin: 0 0 16px; }
    .provider-radio-group { display: flex; flex-direction: column; gap: 12px; }
    .provider-option {
      border: 2px solid #e0e0e0;
      border-radius: 12px;
      padding: 16px 20px;
      cursor: pointer;
      transition: all 0.2s ease;
    }
    .provider-option:hover { border-color: #90caf9; background: #fafafa; }
    .provider-option.selected { border-color: #1B3A5C; background: #f0f4f8; }
    .provider-label { display: flex; align-items: center; gap: 10px; }
    .provider-label strong { font-size: 15px; color: #1B3A5C; }
    .provider-tag {
      display: inline-block;
      padding: 2px 10px;
      border-radius: 12px;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .api-tag { background: #e3f2fd; color: #1565c0; }
    .local-tag { background: #e8f5e9; color: #2e7d32; }
    .scw-tag { background: #f3e5f5; color: #7b1fa2; }
    .provider-desc { margin: 8px 0 0 32px; color: #777; font-size: 13px; }
  `],
})
export class AdminSettingsComponent implements OnInit {
  workspaceId = '';
  config: AIConfigUpdate = {
    provider: 'mistral',
    mistral_api_key: '',
    model_name: 'mistral-large-latest',
    temperature: 0.3,
    max_tokens: 4096,
    ollama_base_url: 'http://host.docker.internal:11434',
    ollama_model: 'mistral:latest',
    ner_provider: 'ollama',
    ner_model: 'qwen2.5:14b',
    vision_provider: 'ollama',
    vision_model: 'llama3.2-vision:11b',
    scaleway_api_key: '',
    scaleway_project_id: '',
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
      next: (cfg: any) => {
        this.config = {
          provider: cfg.provider || 'mistral',
          mistral_api_key: cfg.mistral_api_key || '',
          model_name: cfg.model_name || 'mistral-large-latest',
          temperature: cfg.temperature ?? 0.3,
          max_tokens: cfg.max_tokens || 4096,
          ollama_base_url: cfg.ollama_base_url || 'http://host.docker.internal:11434',
          ollama_model: cfg.ollama_model || 'mistral:latest',
          ner_provider: cfg.ner_provider || 'ollama',
          ner_model: cfg.ner_model || 'qwen2.5:14b',
          vision_provider: cfg.vision_provider || 'ollama',
          vision_model: cfg.vision_model || 'llama3.2-vision:11b',
          scaleway_api_key: cfg.scaleway_api_key || '',
          scaleway_project_id: cfg.scaleway_project_id || '',
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

  getProviderLabel(provider: string): string {
    switch (provider) {
      case 'ollama': return 'Ollama (local)';
      case 'mistral': return 'Mistral AI (cloud)';
      case 'scaleway': return 'Scaleway (EU)';
      default: return provider;
    }
  }
}
