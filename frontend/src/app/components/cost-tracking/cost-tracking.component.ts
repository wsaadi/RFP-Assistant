import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatDividerModule } from '@angular/material/divider';
import { MatTabsModule } from '@angular/material/tabs';
import { ApiService } from '../../services/api.service';

interface ProviderModels {
  label: string;
  tag: string;
  tagClass: string;
  models: { value: string; label: string }[];
}

@Component({
  selector: 'app-cost-tracking',
  standalone: true,
  imports: [
    CommonModule, FormsModule, RouterLink,
    MatCardModule, MatButtonModule, MatIconModule, MatInputModule,
    MatSelectModule, MatSnackBarModule, MatTooltipModule,
    MatProgressSpinnerModule, MatDividerModule, MatTabsModule,
  ],
  template: `
    <div class="page-container">
      <div class="page-header">
        <button mat-icon-button [routerLink]="['/project', projectId]">
          <mat-icon>arrow_back</mat-icon>
        </button>
        <h1><mat-icon class="header-icon">payments</mat-icon> Suivi des coûts IA</h1>
        <span class="spacer"></span>
        <button mat-raised-button color="primary" (click)="loadCostTracking()" [disabled]="loading">
          <mat-spinner *ngIf="loading" diameter="18"></mat-spinner>
          <mat-icon *ngIf="!loading">refresh</mat-icon>
          Actualiser
        </button>
      </div>

      <!-- ═══════════ Summary Cards ═══════════ -->
      <div class="cost-summary-grid" *ngIf="costTracking">
        <mat-card class="summary-card">
          <span class="summary-number">{{ costTracking.total_requests }}</span>
          <span class="summary-label">Requêtes IA</span>
          <mat-icon class="summary-icon">send</mat-icon>
        </mat-card>
        <mat-card class="summary-card">
          <span class="summary-number">{{ costTracking.total_input_tokens | number }}</span>
          <span class="summary-label">Tokens en entrée</span>
          <mat-icon class="summary-icon">input</mat-icon>
        </mat-card>
        <mat-card class="summary-card">
          <span class="summary-number">{{ costTracking.total_output_tokens | number }}</span>
          <span class="summary-label">Tokens en sortie</span>
          <mat-icon class="summary-icon">output</mat-icon>
        </mat-card>
        <mat-card class="summary-card total-card">
          <span class="summary-number">{{ costTracking.total_cost | number:'1.2-4' }} EUR</span>
          <span class="summary-label">Coût total estimé</span>
          <mat-icon class="summary-icon">euro</mat-icon>
        </mat-card>
      </div>

      <mat-tab-group *ngIf="costTracking" animationDuration="200ms">
        <!-- ═══════════ Tab 1: Tarification ═══════════ -->
        <mat-tab>
          <ng-template mat-tab-label>
            <mat-icon class="tab-icon">sell</mat-icon> Tarification
          </ng-template>

          <div class="tab-content">
            <!-- Load public pricing button -->
            <mat-card class="section-card catalog-card">
              <div class="section-header">
                <h3><mat-icon>cloud_download</mat-icon> Catalogue de prix publics</h3>
                <button mat-raised-button color="accent" (click)="loadAllPublicPricing()" [disabled]="loadingCatalog">
                  <mat-spinner *ngIf="loadingCatalog" diameter="18"></mat-spinner>
                  <mat-icon *ngIf="!loadingCatalog">auto_fix_high</mat-icon>
                  Charger tous les prix publics
                </button>
              </div>
              <p class="section-hint">
                Charge automatiquement les prix publics de tous les fournisseurs connus (Mistral, OpenAI, Anthropic, Google, DeepSeek, Cohere, Scaleway...).
                Seuls les modèles non encore configurés seront ajoutés. Vous pourrez ensuite éditer chaque prix individuellement.
              </p>
            </mat-card>

            <mat-card class="section-card">
              <div class="section-header">
                <h3><mat-icon>add_circle</mat-icon> Ajouter un tarif</h3>
              </div>
              <p class="section-hint">
                Sélectionnez un fournisseur et un modèle depuis les listes pré-configurées, puis définissez les prix par tranche de 1000 tokens.
              </p>

              <div class="pricing-form">
                <mat-form-field appearance="outline" class="form-field">
                  <mat-label>Fournisseur</mat-label>
                  <mat-select [(ngModel)]="newPricing.provider" (selectionChange)="onProviderChange()">
                    <mat-option *ngFor="let p of providerList" [value]="p.value">
                      {{ p.label }}
                    </mat-option>
                  </mat-select>
                </mat-form-field>

                <mat-form-field appearance="outline" class="form-field">
                  <mat-label>Modèle</mat-label>
                  <mat-select [(ngModel)]="newPricing.model_name" [disabled]="!newPricing.provider">
                    <mat-option *ngFor="let m of availableModels" [value]="m.value">
                      {{ m.label }}
                    </mat-option>
                  </mat-select>
                </mat-form-field>

                <mat-form-field appearance="outline" class="form-field-small">
                  <mat-label>Prix input (/1K)</mat-label>
                  <input matInput type="number" step="0.0001" [(ngModel)]="newPricing.price_per_1k_input">
                  <span matSuffix>EUR</span>
                </mat-form-field>

                <mat-form-field appearance="outline" class="form-field-small">
                  <mat-label>Prix output (/1K)</mat-label>
                  <input matInput type="number" step="0.0001" [(ngModel)]="newPricing.price_per_1k_output">
                  <span matSuffix>EUR</span>
                </mat-form-field>

                <button mat-raised-button color="primary" (click)="addPricing()"
                        [disabled]="!newPricing.provider || !newPricing.model_name">
                  <mat-icon>add</mat-icon> Ajouter
                </button>
              </div>
            </mat-card>

            <!-- Existing pricing table -->
            <mat-card class="section-card" *ngIf="costTracking.pricing.length > 0">
              <div class="section-header">
                <h3><mat-icon>list</mat-icon> Tarifs configurés</h3>
                <button mat-raised-button color="primary" (click)="savePricing()" [disabled]="savingPricing">
                  <mat-spinner *ngIf="savingPricing" diameter="18"></mat-spinner>
                  <mat-icon *ngIf="!savingPricing">save</mat-icon> Sauvegarder
                </button>
              </div>
              <table class="cost-table">
                <thead>
                  <tr>
                    <th>Fournisseur</th>
                    <th>Modèle</th>
                    <th>Prix input (/1K)</th>
                    <th>Prix output (/1K)</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  <tr *ngFor="let p of costTracking.pricing">
                    <td>
                      <span class="provider-badge" [ngClass]="getProviderClass(p.provider)">{{ getProviderLabel(p.provider) }}</span>
                    </td>
                    <td class="model-name">{{ p.model_name }}</td>
                    <td>
                      <mat-form-field appearance="outline" class="inline-field">
                        <input matInput type="number" step="0.0001" [(ngModel)]="p.price_per_1k_input">
                      </mat-form-field>
                    </td>
                    <td>
                      <mat-form-field appearance="outline" class="inline-field">
                        <input matInput type="number" step="0.0001" [(ngModel)]="p.price_per_1k_output">
                      </mat-form-field>
                    </td>
                    <td>
                      <button mat-icon-button color="warn" (click)="deletePricing(p)" matTooltip="Supprimer ce tarif">
                        <mat-icon>delete</mat-icon>
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </mat-card>

            <mat-card class="section-card" *ngIf="costTracking.pricing.length === 0">
              <div class="empty-state">
                <mat-icon>info</mat-icon>
                <p>Aucun tarif configuré. Ajoutez des tarifs ci-dessus pour calculer les coûts automatiquement.</p>
              </div>
            </mat-card>
          </div>
        </mat-tab>

        <!-- ═══════════ Tab 2: Consommation par modèle ═══════════ -->
        <mat-tab>
          <ng-template mat-tab-label>
            <mat-icon class="tab-icon">bar_chart</mat-icon> Par modèle
          </ng-template>

          <div class="tab-content">
            <mat-card class="section-card" *ngIf="costTracking.by_model.length > 0">
              <h3><mat-icon>analytics</mat-icon> Consommation par modèle</h3>
              <table class="cost-table">
                <thead>
                  <tr>
                    <th>Fournisseur</th>
                    <th>Modèle</th>
                    <th>Requêtes</th>
                    <th>Tokens in</th>
                    <th>Tokens out</th>
                    <th>Coût</th>
                  </tr>
                </thead>
                <tbody>
                  <tr *ngFor="let m of costTracking.by_model">
                    <td><span class="provider-badge" [ngClass]="getProviderClass(m.provider)">{{ getProviderLabel(m.provider) }}</span></td>
                    <td class="model-name">{{ m.model }}</td>
                    <td>{{ m.requests }}</td>
                    <td>{{ m.input_tokens | number }}</td>
                    <td>{{ m.output_tokens | number }}</td>
                    <td class="cost-cell">{{ m.cost | number:'1.2-4' }} EUR</td>
                  </tr>
                </tbody>
              </table>
            </mat-card>

            <mat-card class="section-card" *ngIf="costTracking.by_model.length === 0">
              <div class="empty-state">
                <mat-icon>info</mat-icon>
                <p>Aucune donnée de consommation. Les données apparaîtront après l'utilisation des fonctions IA.</p>
              </div>
            </mat-card>
          </div>
        </mat-tab>

        <!-- ═══════════ Tab 3: Coûts quotidiens ═══════════ -->
        <mat-tab>
          <ng-template mat-tab-label>
            <mat-icon class="tab-icon">calendar_today</mat-icon> Par jour
          </ng-template>

          <div class="tab-content">
            <mat-card class="section-card" *ngIf="costTracking.daily.length > 0">
              <h3><mat-icon>show_chart</mat-icon> Évolution des coûts quotidiens</h3>
              <div class="daily-chart-container">
                <div *ngFor="let d of costTracking.daily" class="daily-bar"
                     [matTooltip]="d.date + ' — ' + d.requests + ' requêtes — ' + (d.cost | number:'1.2-4') + ' EUR'">
                  <div class="daily-bar-fill"
                       [style.height.%]="maxDailyCost > 0 ? (d.cost / maxDailyCost * 100) : 0">
                  </div>
                  <span class="daily-bar-cost">{{ d.cost | number:'1.2-2' }}</span>
                  <span class="daily-bar-label">{{ d.date | slice:5 }}</span>
                </div>
              </div>

              <table class="cost-table" style="margin-top: 24px;">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Requêtes</th>
                    <th>Tokens in</th>
                    <th>Tokens out</th>
                    <th>Coût</th>
                  </tr>
                </thead>
                <tbody>
                  <tr *ngFor="let d of costTracking.daily">
                    <td>{{ d.date }}</td>
                    <td>{{ d.requests }}</td>
                    <td>{{ d.input_tokens | number }}</td>
                    <td>{{ d.output_tokens | number }}</td>
                    <td class="cost-cell">{{ d.cost | number:'1.2-4' }} EUR</td>
                  </tr>
                </tbody>
              </table>
            </mat-card>

            <mat-card class="section-card" *ngIf="costTracking.daily.length === 0">
              <div class="empty-state">
                <mat-icon>info</mat-icon>
                <p>Aucune donnée quotidienne disponible.</p>
              </div>
            </mat-card>
          </div>
        </mat-tab>

        <!-- ═══════════ Tab 4: Logs récents ═══════════ -->
        <mat-tab>
          <ng-template mat-tab-label>
            <mat-icon class="tab-icon">receipt_long</mat-icon> Logs
          </ng-template>

          <div class="tab-content">
            <mat-card class="section-card" *ngIf="costTracking.recent_logs.length > 0">
              <h3><mat-icon>history</mat-icon> Dernières requêtes IA ({{ costTracking.recent_logs.length }})</h3>
              <div class="logs-scroll">
                <table class="cost-table cost-table-compact">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Opération</th>
                      <th>Fournisseur</th>
                      <th>Modèle</th>
                      <th>Tokens in</th>
                      <th>Tokens out</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr *ngFor="let log of costTracking.recent_logs">
                      <td>{{ log.created_at | date:'dd/MM/yyyy HH:mm' }}</td>
                      <td><span class="operation-badge">{{ log.operation }}</span></td>
                      <td><span class="provider-badge" [ngClass]="getProviderClass(log.provider)">{{ getProviderLabel(log.provider) }}</span></td>
                      <td class="model-name">{{ log.model_name }}</td>
                      <td>{{ log.input_tokens | number }}</td>
                      <td>{{ log.output_tokens | number }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </mat-card>

            <mat-card class="section-card" *ngIf="costTracking.recent_logs.length === 0">
              <div class="empty-state">
                <mat-icon>info</mat-icon>
                <p>Aucun log de requête IA disponible.</p>
              </div>
            </mat-card>
          </div>
        </mat-tab>
      </mat-tab-group>

      <!-- Empty state when no data loaded -->
      <mat-card class="section-card" *ngIf="!costTracking && !loading">
        <div class="empty-state">
          <mat-icon>cloud_download</mat-icon>
          <p>Cliquez sur <strong>Actualiser</strong> pour charger les données de suivi des coûts.</p>
        </div>
      </mat-card>
    </div>
  `,
  styles: [`
    .page-container { max-width: 1100px; margin: 0 auto; }
    .page-header {
      display: flex; align-items: center; gap: 12px; margin-bottom: 24px;
    }
    .page-header h1 {
      display: flex; align-items: center; gap: 8px;
      margin: 0; color: #1B3A5C; font-size: 22px;
    }
    .header-icon { font-size: 28px; width: 28px; height: 28px; }
    .spacer { flex: 1; }

    /* ── Summary cards ── */
    .cost-summary-grid {
      display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      gap: 16px; margin-bottom: 24px;
    }
    .summary-card {
      padding: 20px; position: relative; overflow: hidden;
      border-left: 4px solid #1B3A5C;
    }
    .summary-card.total-card {
      border-left-color: #1976d2; background: #e3f2fd;
    }
    .summary-number {
      display: block; font-size: 24px; font-weight: 700; color: #1B3A5C;
    }
    .summary-label {
      display: block; font-size: 13px; color: #888; margin-top: 4px;
    }
    .summary-icon {
      position: absolute; right: 16px; top: 16px;
      font-size: 32px; width: 32px; height: 32px;
      color: rgba(27, 58, 92, 0.12);
    }

    /* ── Tabs ── */
    .tab-icon { margin-right: 6px; }
    .tab-content { padding: 16px 0; }

    /* ── Section cards ── */
    .section-card { padding: 24px; margin-bottom: 16px; }
    .section-card h3 {
      display: flex; align-items: center; gap: 8px;
      color: #1B3A5C; margin: 0 0 16px 0; font-size: 16px;
    }
    .section-header {
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 16px;
    }
    .section-header h3 { margin-bottom: 0; }
    .section-hint { color: #666; font-size: 14px; margin: 0 0 20px; }

    /* ── Pricing form ── */
    .pricing-form {
      display: flex; flex-wrap: wrap; align-items: flex-start; gap: 12px;
    }
    .form-field { min-width: 200px; flex: 1; }
    .form-field-small { min-width: 140px; width: 160px; }

    /* ── Tables ── */
    .cost-table { width: 100%; border-collapse: collapse; font-size: 13px; }
    .cost-table th {
      background: #f5f5f5; padding: 10px 14px; text-align: left;
      font-weight: 600; color: #555; border-bottom: 2px solid #e0e0e0;
    }
    .cost-table td { padding: 10px 14px; border-bottom: 1px solid #eee; }
    .cost-table tbody tr:hover { background: #fafafa; }
    .cost-table-compact { font-size: 12px; }
    .cost-table-compact th, .cost-table-compact td { padding: 6px 10px; }
    .cost-cell { font-weight: 600; color: #1976d2; }
    .model-name { font-family: monospace; font-size: 12px; }

    .inline-field { width: 120px; }
    .inline-field .mat-mdc-form-field-subscript-wrapper { display: none; }

    /* ── Provider badges ── */
    .provider-badge {
      display: inline-block; padding: 2px 10px; border-radius: 12px;
      font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;
    }
    .provider-mistral { background: #e3f2fd; color: #1565c0; }
    .provider-ollama { background: #e8f5e9; color: #2e7d32; }
    .provider-scaleway { background: #f3e5f5; color: #7b1fa2; }
    .provider-openai { background: #e8f5e9; color: #1b5e20; }
    .provider-anthropic { background: #fff3e0; color: #e65100; }
    .provider-google { background: #e8eaf6; color: #283593; }
    .provider-deepseek { background: #e0f7fa; color: #00695c; }
    .provider-cohere { background: #fce4ec; color: #880e4f; }
    .provider-other { background: #f5f5f5; color: #666; }

    /* ── Catalog card ── */
    .catalog-card { border-left: 4px solid #ff9800; }

    .operation-badge {
      display: inline-block; padding: 2px 8px; border-radius: 8px;
      font-size: 11px; background: #fff3e0; color: #e65100;
    }

    /* ── Daily chart ── */
    .daily-chart-container {
      display: flex; gap: 6px; align-items: flex-end;
      height: 160px; padding: 12px 0; overflow-x: auto;
    }
    .daily-bar {
      display: flex; flex-direction: column; align-items: center;
      justify-content: flex-end; min-width: 40px; height: 100%;
    }
    .daily-bar-fill {
      width: 28px; background: linear-gradient(to top, #1976d2, #42a5f5);
      border-radius: 4px 4px 0 0; min-height: 2px;
      transition: height 0.3s ease;
    }
    .daily-bar-cost {
      font-size: 9px; color: #1976d2; margin-top: 4px; font-weight: 600;
    }
    .daily-bar-label {
      font-size: 10px; color: #888; margin-top: 2px; white-space: nowrap;
    }

    /* ── Logs ── */
    .logs-scroll { max-height: 500px; overflow-y: auto; }

    /* ── Empty state ── */
    .empty-state {
      display: flex; align-items: center; gap: 12px;
      color: #666; font-size: 14px; padding: 16px 0;
    }
    .empty-state mat-icon { color: #1976d2; font-size: 28px; width: 28px; height: 28px; }
    .empty-state p { margin: 0; }
  `],
})
export class CostTrackingComponent implements OnInit {
  projectId = '';
  costTracking: any = null;
  loading = false;
  savingPricing = false;

  // Known providers and their models (matches admin-settings configuration)
  providers: Record<string, ProviderModels> = {
    mistral: {
      label: 'Mistral AI',
      tag: 'API Cloud',
      tagClass: 'provider-mistral',
      models: [
        { value: 'mistral-large-latest', label: 'Mistral Large' },
        { value: 'mistral-medium-latest', label: 'Mistral Medium' },
        { value: 'mistral-small-latest', label: 'Mistral Small' },
        { value: 'open-mistral-nemo', label: 'Open Mistral Nemo' },
        { value: 'codestral-latest', label: 'Codestral' },
        { value: 'pixtral-large-latest', label: 'Pixtral Large' },
        { value: 'pixtral-12b-2409', label: 'Pixtral 12B' },
      ],
    },
    ollama: {
      label: 'Ollama',
      tag: 'Local',
      tagClass: 'provider-ollama',
      models: [
        { value: 'mistral:latest', label: 'Mistral 7B' },
        { value: 'mistral-nemo:latest', label: 'Mistral Nemo 12B' },
        { value: 'mixtral:latest', label: 'Mixtral 8x7B' },
        { value: 'llama3.1:latest', label: 'Llama 3.1 8B' },
        { value: 'llama3.1:70b', label: 'Llama 3.1 70B' },
        { value: 'qwen2.5:latest', label: 'Qwen 2.5 7B' },
        { value: 'qwen2.5:14b', label: 'Qwen 2.5 14B' },
        { value: 'qwen2.5:32b', label: 'Qwen 2.5 32B' },
        { value: 'gemma3:12b', label: 'Gemma 3 12B' },
        { value: 'deepseek-r1:latest', label: 'DeepSeek R1' },
        { value: 'command-r:latest', label: 'Command R' },
        { value: 'llama3.2-vision:11b', label: 'Llama 3.2 Vision 11B' },
        { value: 'llama3.2-vision:latest', label: 'Llama 3.2 Vision' },
        { value: 'llava:latest', label: 'LLaVA' },
        { value: 'llava:13b', label: 'LLaVA 13B' },
        { value: 'bakllava:latest', label: 'BakLLaVA' },
      ],
    },
    scaleway: {
      label: 'Scaleway',
      tag: 'API EU',
      tagClass: 'provider-scaleway',
      models: [
        { value: 'mistral-large-3-675b-instruct-2512', label: 'Mistral Large 3 675B' },
        { value: 'mistral-small-3.2-24b-instruct-2506', label: 'Mistral Small 3.2 24B' },
        { value: 'mistral-small-3.1-24b-instruct-2503', label: 'Mistral Small 3.1 24B' },
        { value: 'llama-3.3-70b-instruct', label: 'Llama 3.3 70B Instruct' },
        { value: 'qwen2.5-coder-32b-instruct', label: 'Qwen 2.5 Coder 32B' },
        { value: 'pixtral-12b-2409', label: 'Pixtral 12B' },
      ],
    },
    openai: {
      label: 'OpenAI',
      tag: 'API Cloud',
      tagClass: 'provider-openai',
      models: [
        { value: 'gpt-4o', label: 'GPT-4o' },
        { value: 'gpt-4o-mini', label: 'GPT-4o Mini' },
        { value: 'gpt-4-turbo', label: 'GPT-4 Turbo' },
        { value: 'gpt-4', label: 'GPT-4' },
        { value: 'gpt-3.5-turbo', label: 'GPT-3.5 Turbo' },
        { value: 'o1', label: 'o1' },
        { value: 'o1-mini', label: 'o1 Mini' },
        { value: 'o3-mini', label: 'o3 Mini' },
      ],
    },
    anthropic: {
      label: 'Anthropic',
      tag: 'API Cloud',
      tagClass: 'provider-anthropic',
      models: [
        { value: 'claude-opus-4', label: 'Claude Opus 4' },
        { value: 'claude-sonnet-4', label: 'Claude Sonnet 4' },
        { value: 'claude-3.5-sonnet', label: 'Claude 3.5 Sonnet' },
        { value: 'claude-3.5-haiku', label: 'Claude 3.5 Haiku' },
        { value: 'claude-3-opus', label: 'Claude 3 Opus' },
        { value: 'claude-3-haiku', label: 'Claude 3 Haiku' },
      ],
    },
    google: {
      label: 'Google',
      tag: 'API Cloud',
      tagClass: 'provider-google',
      models: [
        { value: 'gemini-2.0-flash', label: 'Gemini 2.0 Flash' },
        { value: 'gemini-2.0-flash-lite', label: 'Gemini 2.0 Flash Lite' },
        { value: 'gemini-1.5-pro', label: 'Gemini 1.5 Pro' },
        { value: 'gemini-1.5-flash', label: 'Gemini 1.5 Flash' },
      ],
    },
    deepseek: {
      label: 'DeepSeek',
      tag: 'API Cloud',
      tagClass: 'provider-deepseek',
      models: [
        { value: 'deepseek-chat', label: 'DeepSeek Chat (V3)' },
        { value: 'deepseek-reasoner', label: 'DeepSeek Reasoner (R1)' },
      ],
    },
    cohere: {
      label: 'Cohere',
      tag: 'API Cloud',
      tagClass: 'provider-cohere',
      models: [
        { value: 'command-r-plus', label: 'Command R+' },
        { value: 'command-r', label: 'Command R' },
      ],
    },
  };

  providerList = [
    { value: 'mistral', label: 'Mistral AI (Cloud)' },
    { value: 'ollama', label: 'Ollama (Local)' },
    { value: 'scaleway', label: 'Scaleway (EU)' },
    { value: 'openai', label: 'OpenAI' },
    { value: 'anthropic', label: 'Anthropic' },
    { value: 'google', label: 'Google' },
    { value: 'deepseek', label: 'DeepSeek' },
    { value: 'cohere', label: 'Cohere' },
  ];

  loadingCatalog = false;

  availableModels: { value: string; label: string }[] = [];

  newPricing = {
    provider: '',
    model_name: '',
    price_per_1k_input: 0,
    price_per_1k_output: 0,
  };

  get maxDailyCost(): number {
    if (!this.costTracking?.daily?.length) return 0;
    return Math.max(...this.costTracking.daily.map((d: any) => d.cost));
  }

  constructor(
    private route: ActivatedRoute,
    private api: ApiService,
    private snackBar: MatSnackBar,
  ) {}

  ngOnInit(): void {
    this.projectId = this.route.snapshot.paramMap.get('projectId') || '';
    if (this.projectId) {
      this.loadCostTracking();
    }
  }

  onProviderChange(): void {
    const provider = this.providers[this.newPricing.provider];
    this.availableModels = provider ? provider.models : [];
    this.newPricing.model_name = '';
  }

  loadCostTracking(): void {
    this.loading = true;
    this.api.getAICostTracking(this.projectId).subscribe({
      next: (res) => {
        this.costTracking = res;
        this.loading = false;
      },
      error: (err) => {
        this.snackBar.open(err.error?.detail || 'Erreur de chargement', 'OK', { duration: 4000 });
        this.loading = false;
      },
    });
  }

  addPricing(): void {
    if (!this.newPricing.provider || !this.newPricing.model_name) return;
    if (!this.costTracking) this.costTracking = { pricing: [] };
    this.costTracking.pricing.push({
      id: '',
      ...this.newPricing,
      currency: 'EUR',
    });
    const provider = this.newPricing.provider;
    this.newPricing = { provider: '', model_name: '', price_per_1k_input: 0, price_per_1k_output: 0 };
    this.availableModels = [];
    this.snackBar.open('Tarif ajouté (pensez à sauvegarder)', 'OK', { duration: 2000 });
  }

  savePricing(): void {
    if (!this.costTracking) return;
    this.savingPricing = true;
    this.api.updateAIPricing(this.projectId, this.costTracking.pricing).subscribe({
      next: () => {
        this.snackBar.open('Tarifs sauvegardés', 'OK', { duration: 2000 });
        this.savingPricing = false;
        this.loadCostTracking();
      },
      error: (err) => {
        this.snackBar.open(err.error?.detail || 'Erreur', 'OK', { duration: 4000 });
        this.savingPricing = false;
      },
    });
  }

  deletePricing(p: any): void {
    if (p.id) {
      this.api.deleteAIPricing(this.projectId, p.id).subscribe({
        next: () => {
          this.snackBar.open('Tarif supprimé', 'OK', { duration: 2000 });
          this.loadCostTracking();
        },
        error: () => this.snackBar.open('Erreur de suppression', 'OK', { duration: 3000 }),
      });
    } else {
      this.costTracking.pricing = this.costTracking.pricing.filter((x: any) => x !== p);
    }
  }

  getProviderLabel(provider: string): string {
    return this.providers[provider]?.label || provider;
  }

  getProviderClass(provider: string): string {
    const known = ['mistral', 'ollama', 'scaleway', 'openai', 'anthropic', 'google', 'deepseek', 'cohere'];
    return known.includes(provider) ? `provider-${provider}` : 'provider-other';
  }

  loadAllPublicPricing(): void {
    this.loadingCatalog = true;
    this.api.loadPublicPricing(this.projectId, []).subscribe({
      next: (res) => {
        this.loadingCatalog = false;
        const msg = res.added > 0
          ? `${res.added} tarif(s) ajouté(s) depuis le catalogue public`
          : 'Tous les tarifs du catalogue sont déjà configurés';
        this.snackBar.open(msg, 'OK', { duration: 4000 });
        this.loadCostTracking();
      },
      error: (err) => {
        this.loadingCatalog = false;
        this.snackBar.open(err.error?.detail || 'Erreur de chargement du catalogue', 'OK', { duration: 4000 });
      },
    });
  }
}
