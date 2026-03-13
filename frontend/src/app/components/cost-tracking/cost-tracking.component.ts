import { Component, OnInit, OnDestroy, ViewChild, ElementRef, AfterViewInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatDividerModule } from '@angular/material/divider';
import { MatTabsModule } from '@angular/material/tabs';
import { ApiService } from '../../services/api.service';
import {
  Chart, ChartConfiguration, registerables,
} from 'chart.js';

Chart.register(...registerables);

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
    MatCardModule, MatButtonModule, MatButtonToggleModule, MatIconModule, MatInputModule,
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
        <button mat-raised-button color="primary" (click)="loadAll()" [disabled]="loading">
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

      <mat-tab-group *ngIf="costTracking" animationDuration="200ms" (selectedTabChange)="onTabChange($event)">

        <!-- ═══════════ Tab 1: Tarification ═══════════ -->
        <mat-tab>
          <ng-template mat-tab-label>
            <mat-icon class="tab-icon">sell</mat-icon> Tarification
          </ng-template>
          <div class="tab-content">
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
                Sélectionnez un fournisseur et un modèle, puis définissez les prix par tranche de 1000 tokens.
              </p>
              <div class="pricing-form">
                <mat-form-field appearance="outline" class="form-field">
                  <mat-label>Fournisseur</mat-label>
                  <mat-select [(ngModel)]="newPricing.provider" (selectionChange)="onProviderChange()">
                    <mat-option *ngFor="let p of providerList" [value]="p.value">{{ p.label }}</mat-option>
                  </mat-select>
                </mat-form-field>
                <mat-form-field appearance="outline" class="form-field">
                  <mat-label>Modèle</mat-label>
                  <mat-select [(ngModel)]="newPricing.model_name" [disabled]="!newPricing.provider">
                    <mat-option *ngFor="let m of availableModels" [value]="m.value">{{ m.label }}</mat-option>
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
                  <tr><th>Fournisseur</th><th>Modèle</th><th>Prix input (/1K)</th><th>Prix output (/1K)</th><th></th></tr>
                </thead>
                <tbody>
                  <tr *ngFor="let p of costTracking.pricing">
                    <td><span class="provider-badge" [ngClass]="getProviderClass(p.provider)">{{ getProviderLabel(p.provider) }}</span></td>
                    <td class="model-name">{{ p.model_name }}</td>
                    <td><mat-form-field appearance="outline" class="inline-field"><input matInput type="number" step="0.0001" [(ngModel)]="p.price_per_1k_input"></mat-form-field></td>
                    <td><mat-form-field appearance="outline" class="inline-field"><input matInput type="number" step="0.0001" [(ngModel)]="p.price_per_1k_output"></mat-form-field></td>
                    <td><button mat-icon-button color="warn" (click)="deletePricing(p)" matTooltip="Supprimer"><mat-icon>delete</mat-icon></button></td>
                  </tr>
                </tbody>
              </table>
            </mat-card>
            <mat-card class="section-card" *ngIf="costTracking.pricing.length === 0">
              <div class="empty-state"><mat-icon>info</mat-icon><p>Aucun tarif configuré.</p></div>
            </mat-card>
          </div>
        </mat-tab>

        <!-- ═══════════ Tab 2: Par modèle ═══════════ -->
        <mat-tab>
          <ng-template mat-tab-label>
            <mat-icon class="tab-icon">bar_chart</mat-icon> Par modèle
          </ng-template>
          <div class="tab-content">
            <mat-card class="section-card" *ngIf="costTracking.by_model.length > 0">
              <h3><mat-icon>analytics</mat-icon> Consommation par modèle</h3>
              <table class="cost-table">
                <thead><tr><th>Fournisseur</th><th>Modèle</th><th>Requêtes</th><th>Tokens in</th><th>Tokens out</th><th>Coût</th></tr></thead>
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
              <div class="empty-state"><mat-icon>info</mat-icon><p>Aucune donnée de consommation.</p></div>
            </mat-card>
          </div>
        </mat-tab>

        <!-- ═══════════ Tab 3: Analytique (Charts) ═══════════ -->
        <mat-tab>
          <ng-template mat-tab-label>
            <mat-icon class="tab-icon">insights</mat-icon> Analytique
          </ng-template>
          <div class="tab-content">
            <!-- Controls bar -->
            <mat-card class="section-card controls-card">
              <div class="chart-controls">
                <div class="control-group">
                  <label>Granularité</label>
                  <mat-button-toggle-group [(ngModel)]="chartGranularity" (change)="rebuildChart()">
                    <mat-button-toggle value="day">Jour</mat-button-toggle>
                    <mat-button-toggle value="week">Semaine</mat-button-toggle>
                    <mat-button-toggle value="month">Mois</mat-button-toggle>
                  </mat-button-toggle-group>
                </div>
                <div class="control-group">
                  <label>Type de graphe</label>
                  <mat-button-toggle-group [(ngModel)]="chartType" (change)="rebuildChart()">
                    <mat-button-toggle value="bar"><mat-icon>bar_chart</mat-icon></mat-button-toggle>
                    <mat-button-toggle value="line"><mat-icon>show_chart</mat-icon></mat-button-toggle>
                    <mat-button-toggle value="pie"><mat-icon>pie_chart</mat-icon></mat-button-toggle>
                    <mat-button-toggle value="doughnut"><mat-icon>donut_large</mat-icon></mat-button-toggle>
                  </mat-button-toggle-group>
                </div>
                <div class="control-group">
                  <label>Métrique</label>
                  <mat-button-toggle-group [(ngModel)]="chartMetric" (change)="rebuildChart()">
                    <mat-button-toggle value="cost">Coût (EUR)</mat-button-toggle>
                    <mat-button-toggle value="tokens">Tokens</mat-button-toggle>
                    <mat-button-toggle value="requests">Requêtes</mat-button-toggle>
                  </mat-button-toggle-group>
                </div>
              </div>
              <div class="chart-controls" style="margin-top: 12px;">
                <div class="control-group">
                  <label>Période</label>
                  <div class="date-range">
                    <mat-form-field appearance="outline" class="date-field">
                      <mat-label>Début</mat-label>
                      <input matInput type="date" [(ngModel)]="chartDateStart" (change)="rebuildChart()">
                    </mat-form-field>
                    <mat-form-field appearance="outline" class="date-field">
                      <mat-label>Fin</mat-label>
                      <input matInput type="date" [(ngModel)]="chartDateEnd" (change)="rebuildChart()">
                    </mat-form-field>
                    <button mat-stroked-button (click)="resetDateRange()"><mat-icon>restart_alt</mat-icon> Tout</button>
                  </div>
                </div>
              </div>
            </mat-card>

            <!-- Chart canvas -->
            <mat-card class="section-card" *ngIf="costTracking.daily.length > 0">
              <div class="chart-wrapper">
                <canvas #analyticsCanvas></canvas>
              </div>
            </mat-card>

            <!-- Summary table below chart -->
            <mat-card class="section-card" *ngIf="aggregatedData.length > 0">
              <h3><mat-icon>table_chart</mat-icon> Détail ({{ granularityLabel }})</h3>
              <table class="cost-table">
                <thead><tr><th>Période</th><th>Requêtes</th><th>Tokens in</th><th>Tokens out</th><th>Coût</th></tr></thead>
                <tbody>
                  <tr *ngFor="let d of aggregatedData">
                    <td>{{ d.label }}</td>
                    <td>{{ d.requests }}</td>
                    <td>{{ d.input_tokens | number }}</td>
                    <td>{{ d.output_tokens | number }}</td>
                    <td class="cost-cell">{{ d.cost | number:'1.2-4' }} EUR</td>
                  </tr>
                </tbody>
              </table>
            </mat-card>

            <mat-card class="section-card" *ngIf="costTracking.daily.length === 0">
              <div class="empty-state"><mat-icon>info</mat-icon><p>Aucune donnée disponible.</p></div>
            </mat-card>
          </div>
        </mat-tab>

        <!-- ═══════════ Tab 4: Empreinte Carbone ═══════════ -->
        <mat-tab>
          <ng-template mat-tab-label>
            <mat-icon class="tab-icon">eco</mat-icon> Empreinte Carbone
          </ng-template>
          <div class="tab-content" *ngIf="carbon">
            <!-- Carbon summary cards -->
            <div class="cost-summary-grid">
              <mat-card class="summary-card carbon-card">
                <span class="summary-number carbon-number">{{ carbon.total_co2_g | number:'1.1-1' }} g</span>
                <span class="summary-label">CO₂ équivalent</span>
                <mat-icon class="summary-icon">cloud</mat-icon>
              </mat-card>
              <mat-card class="summary-card carbon-card">
                <span class="summary-number carbon-number">{{ carbon.total_energy_wh | number:'1.1-1' }} Wh</span>
                <span class="summary-label">Énergie consommée</span>
                <mat-icon class="summary-icon">bolt</mat-icon>
              </mat-card>
              <mat-card class="summary-card carbon-card">
                <span class="summary-number carbon-number">{{ carbon.total_water_l | number:'1.2-2' }} L</span>
                <span class="summary-label">Eau (refroidissement)</span>
                <mat-icon class="summary-icon">water_drop</mat-icon>
              </mat-card>
              <mat-card class="summary-card carbon-card">
                <span class="summary-number carbon-number">{{ carbon.total_tokens | number }}</span>
                <span class="summary-label">Tokens traités</span>
                <mat-icon class="summary-icon">token</mat-icon>
              </mat-card>
            </div>

            <!-- Equivalences ADEME -->
            <mat-card class="section-card equiv-card" *ngIf="carbon.equivalences">
              <h3><mat-icon>compare_arrows</mat-icon> Équivalences (source ADEME)</h3>
              <div class="equiv-grid">
                <div class="equiv-item">
                  <mat-icon>directions_car</mat-icon>
                  <span class="equiv-value">{{ carbon.equivalences.km_voiture | number:'1.1-1' }}</span>
                  <span class="equiv-label">km en voiture</span>
                </div>
                <div class="equiv-item">
                  <mat-icon>ondemand_video</mat-icon>
                  <span class="equiv-value">{{ carbon.equivalences.heures_streaming | number:'1.1-1' }}</span>
                  <span class="equiv-label">h de streaming vidéo</span>
                </div>
                <div class="equiv-item">
                  <mat-icon>email</mat-icon>
                  <span class="equiv-value">{{ carbon.equivalences.emails | number:'1.0-0' }}</span>
                  <span class="equiv-label">emails envoyés</span>
                </div>
                <div class="equiv-item">
                  <mat-icon>smartphone</mat-icon>
                  <span class="equiv-value">{{ carbon.equivalences.charges_smartphone | number:'1.0-0' }}</span>
                  <span class="equiv-label">charges de smartphone</span>
                </div>
                <div class="equiv-item">
                  <mat-icon>water_drop</mat-icon>
                  <span class="equiv-value">{{ carbon.equivalences.litres_eau | number:'1.1-1' }}</span>
                  <span class="equiv-label">litres d'eau</span>
                </div>
              </div>
            </mat-card>

            <!-- Carbon charts -->
            <div class="carbon-charts-row">
              <mat-card class="section-card carbon-chart-card">
                <h3><mat-icon>donut_large</mat-icon> CO₂ par fournisseur</h3>
                <div class="chart-wrapper chart-wrapper-sm">
                  <canvas #carbonProviderCanvas></canvas>
                </div>
              </mat-card>
              <mat-card class="section-card carbon-chart-card">
                <h3><mat-icon>show_chart</mat-icon> CO₂ quotidien</h3>
                <div class="chart-wrapper chart-wrapper-sm">
                  <canvas #carbonDailyCanvas></canvas>
                </div>
              </mat-card>
            </div>

            <!-- Carbon by model table -->
            <mat-card class="section-card" *ngIf="carbon.by_model?.length > 0">
              <h3><mat-icon>format_list_numbered</mat-icon> Détail par modèle</h3>
              <table class="cost-table">
                <thead>
                  <tr><th>Fournisseur</th><th>Modèle</th><th>Classe</th><th>Tokens</th><th>Énergie (Wh)</th><th>CO₂ (g)</th><th>Eau (L)</th></tr>
                </thead>
                <tbody>
                  <tr *ngFor="let m of carbon.by_model">
                    <td><span class="provider-badge" [ngClass]="getProviderClass(m.provider)">{{ getProviderLabel(m.provider) }}</span></td>
                    <td class="model-name">{{ m.model }}</td>
                    <td><span class="size-badge" [ngClass]="'size-' + m.size_class">{{ m.size_class }}</span></td>
                    <td>{{ m.tokens | number }}</td>
                    <td>{{ m.energy_wh | number:'1.2-2' }}</td>
                    <td class="co2-cell">{{ m.co2_g | number:'1.2-2' }}</td>
                    <td>{{ m.water_l | number:'1.3-3' }}</td>
                  </tr>
                </tbody>
              </table>
            </mat-card>

            <!-- Methodology -->
            <mat-card class="section-card methodology-card" *ngIf="carbon.methodology">
              <h3><mat-icon>science</mat-icon> Méthodologie</h3>
              <p class="section-hint">
                Estimations basées sur la <strong>Base Carbone ADEME 2024</strong> et les données <strong>IEA 2023</strong>.
                PUE (Power Usage Effectiveness) : {{ carbon.methodology.pue }}.
                Consommation d'eau : {{ carbon.methodology.water_l_per_kwh }} L/kWh.
              </p>
              <div class="methodology-grid">
                <div>
                  <h4>Intensité carbone par provider (gCO₂eq/kWh)</h4>
                  <table class="cost-table cost-table-compact">
                    <tbody>
                      <tr *ngFor="let entry of carbonIntensityEntries">
                        <td><span class="provider-badge" [ngClass]="getProviderClass(entry[0])">{{ getProviderLabel(entry[0]) }}</span></td>
                        <td>{{ entry[1] }} gCO₂/kWh</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div>
                  <h4>Énergie par classe de modèle (Wh/1K tokens)</h4>
                  <table class="cost-table cost-table-compact">
                    <tbody>
                      <tr *ngFor="let entry of energyClassEntries">
                        <td><span class="size-badge" [ngClass]="'size-' + entry[0]">{{ entry[0] }}</span></td>
                        <td>{{ entry[1] }} Wh/1K tokens</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </mat-card>
          </div>
          <div class="tab-content" *ngIf="!carbon && !loadingCarbon">
            <mat-card class="section-card">
              <div class="empty-state"><mat-icon>eco</mat-icon><p>Cliquez sur Actualiser pour charger les données carbone.</p></div>
            </mat-card>
          </div>
          <div class="tab-content" *ngIf="loadingCarbon">
            <div style="text-align:center;padding:40px;"><mat-spinner diameter="40"></mat-spinner></div>
          </div>
        </mat-tab>

        <!-- ═══════════ Tab 5: Logs ═══════════ -->
        <mat-tab>
          <ng-template mat-tab-label>
            <mat-icon class="tab-icon">receipt_long</mat-icon> Logs
          </ng-template>
          <div class="tab-content">
            <mat-card class="section-card" *ngIf="costTracking.recent_logs.length > 0">
              <h3><mat-icon>history</mat-icon> Dernières requêtes IA ({{ costTracking.recent_logs.length }})</h3>
              <div class="logs-scroll">
                <table class="cost-table cost-table-compact">
                  <thead><tr><th>Date</th><th>Opération</th><th>Fournisseur</th><th>Modèle</th><th>Tokens in</th><th>Tokens out</th></tr></thead>
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
              <div class="empty-state"><mat-icon>info</mat-icon><p>Aucun log disponible.</p></div>
            </mat-card>
          </div>
        </mat-tab>
      </mat-tab-group>

      <mat-card class="section-card" *ngIf="!costTracking && !loading">
        <div class="empty-state">
          <mat-icon>cloud_download</mat-icon>
          <p>Cliquez sur <strong>Actualiser</strong> pour charger les données.</p>
        </div>
      </mat-card>
    </div>
  `,
  styles: [`
    .page-container { max-width: 1200px; margin: 0 auto; }
    .page-header { display: flex; align-items: center; gap: 12px; margin-bottom: 24px; }
    .page-header h1 { display: flex; align-items: center; gap: 8px; margin: 0; color: #1B3A5C; font-size: 22px; }
    .header-icon { font-size: 28px; width: 28px; height: 28px; }
    .spacer { flex: 1; }

    /* ── Summary cards ── */
    .cost-summary-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }
    .summary-card { padding: 20px; position: relative; overflow: hidden; border-left: 4px solid #1B3A5C; }
    .summary-card.total-card { border-left-color: #1976d2; background: #e3f2fd; }
    .summary-card.carbon-card { border-left-color: #2e7d32; background: #e8f5e9; }
    .summary-number { display: block; font-size: 24px; font-weight: 700; color: #1B3A5C; }
    .carbon-number { color: #2e7d32; }
    .summary-label { display: block; font-size: 13px; color: #888; margin-top: 4px; }
    .summary-icon { position: absolute; right: 16px; top: 16px; font-size: 32px; width: 32px; height: 32px; color: rgba(27,58,92,0.12); }

    /* ── Tabs ── */
    .tab-icon { margin-right: 6px; }
    .tab-content { padding: 16px 0; }

    /* ── Section cards ── */
    .section-card { padding: 24px; margin-bottom: 16px; }
    .section-card h3 { display: flex; align-items: center; gap: 8px; color: #1B3A5C; margin: 0 0 16px 0; font-size: 16px; }
    .section-card h4 { color: #555; font-size: 14px; margin: 0 0 8px 0; }
    .section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
    .section-header h3 { margin-bottom: 0; }
    .section-hint { color: #666; font-size: 14px; margin: 0 0 20px; }

    /* ── Pricing form ── */
    .pricing-form { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 12px; }
    .form-field { min-width: 200px; flex: 1; }
    .form-field-small { min-width: 140px; width: 160px; }

    /* ── Tables ── */
    .cost-table { width: 100%; border-collapse: collapse; font-size: 13px; }
    .cost-table th { background: #f5f5f5; padding: 10px 14px; text-align: left; font-weight: 600; color: #555; border-bottom: 2px solid #e0e0e0; }
    .cost-table td { padding: 10px 14px; border-bottom: 1px solid #eee; }
    .cost-table tbody tr:hover { background: #fafafa; }
    .cost-table-compact { font-size: 12px; }
    .cost-table-compact th, .cost-table-compact td { padding: 6px 10px; }
    .cost-cell { font-weight: 600; color: #1976d2; }
    .co2-cell { font-weight: 600; color: #2e7d32; }
    .model-name { font-family: monospace; font-size: 12px; }

    .inline-field { width: 120px; }
    .inline-field .mat-mdc-form-field-subscript-wrapper { display: none; }

    /* ── Provider badges ── */
    .provider-badge { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
    .provider-mistral { background: #e3f2fd; color: #1565c0; }
    .provider-ollama { background: #e8f5e9; color: #2e7d32; }
    .provider-scaleway { background: #f3e5f5; color: #7b1fa2; }
    .provider-openai { background: #e8f5e9; color: #1b5e20; }
    .provider-anthropic { background: #fff3e0; color: #e65100; }
    .provider-google { background: #e8eaf6; color: #283593; }
    .provider-deepseek { background: #e0f7fa; color: #00695c; }
    .provider-cohere { background: #fce4ec; color: #880e4f; }
    .provider-other { background: #f5f5f5; color: #666; }

    .operation-badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 11px; background: #fff3e0; color: #e65100; }

    /* ── Size class badges ── */
    .size-badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 10px; font-weight: 600; text-transform: uppercase; }
    .size-small { background: #e8f5e9; color: #2e7d32; }
    .size-medium { background: #fff3e0; color: #e65100; }
    .size-large { background: #fce4ec; color: #c62828; }
    .size-xlarge { background: #f3e5f5; color: #6a1b9a; }

    .catalog-card { border-left: 4px solid #ff9800; }

    /* ── Chart controls ── */
    .controls-card { border-left: 4px solid #1976d2; }
    .chart-controls { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 20px; }
    .control-group { display: flex; flex-direction: column; gap: 6px; }
    .control-group label { font-size: 12px; font-weight: 600; color: #666; text-transform: uppercase; letter-spacing: 0.5px; }
    .date-range { display: flex; align-items: center; gap: 8px; }
    .date-field { width: 160px; }
    .date-field .mat-mdc-form-field-subscript-wrapper { display: none; }

    /* ── Chart wrapper ── */
    .chart-wrapper { position: relative; height: 350px; width: 100%; }
    .chart-wrapper-sm { position: relative; height: 280px; width: 100%; }

    /* ── Carbon ── */
    .carbon-charts-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    @media (max-width: 768px) { .carbon-charts-row { grid-template-columns: 1fr; } }
    .carbon-chart-card { min-height: 340px; }

    .equiv-card { border-left: 4px solid #2e7d32; }
    .equiv-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 16px; }
    .equiv-item { display: flex; flex-direction: column; align-items: center; text-align: center; padding: 16px; border-radius: 12px; background: #f9fbe7; }
    .equiv-item mat-icon { font-size: 32px; width: 32px; height: 32px; color: #558b2f; margin-bottom: 8px; }
    .equiv-value { font-size: 22px; font-weight: 700; color: #33691e; }
    .equiv-label { font-size: 12px; color: #666; margin-top: 4px; }

    .methodology-card { background: #fafafa; }
    .methodology-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
    @media (max-width: 768px) { .methodology-grid { grid-template-columns: 1fr; } }

    /* ── Logs ── */
    .logs-scroll { max-height: 500px; overflow-y: auto; }

    /* ── Empty state ── */
    .empty-state { display: flex; align-items: center; gap: 12px; color: #666; font-size: 14px; padding: 16px 0; }
    .empty-state mat-icon { color: #1976d2; font-size: 28px; width: 28px; height: 28px; }
    .empty-state p { margin: 0; }
  `],
})
export class CostTrackingComponent implements OnInit, OnDestroy {
  @ViewChild('analyticsCanvas') analyticsCanvas!: ElementRef<HTMLCanvasElement>;
  @ViewChild('carbonProviderCanvas') carbonProviderCanvas!: ElementRef<HTMLCanvasElement>;
  @ViewChild('carbonDailyCanvas') carbonDailyCanvas!: ElementRef<HTMLCanvasElement>;

  projectId = '';
  costTracking: any = null;
  carbon: any = null;
  loading = false;
  loadingCarbon = false;
  savingPricing = false;
  loadingCatalog = false;

  // Chart state
  chartGranularity: 'day' | 'week' | 'month' = 'day';
  chartType: 'bar' | 'line' | 'pie' | 'doughnut' = 'bar';
  chartMetric: 'cost' | 'tokens' | 'requests' = 'cost';
  chartDateStart = '';
  chartDateEnd = '';
  aggregatedData: any[] = [];

  private analyticsChart: Chart | null = null;
  private carbonProviderChart: Chart | null = null;
  private carbonDailyChart: Chart | null = null;

  // Provider colors for charts
  private providerColors: Record<string, string> = {
    mistral: '#1565c0', ollama: '#2e7d32', scaleway: '#7b1fa2',
    openai: '#1b5e20', anthropic: '#e65100', google: '#283593',
    deepseek: '#00695c', cohere: '#880e4f',
  };

  providers: Record<string, ProviderModels> = {
    mistral: { label: 'Mistral AI', tag: 'API Cloud', tagClass: 'provider-mistral', models: [
      { value: 'mistral-large-latest', label: 'Mistral Large' },
      { value: 'mistral-medium-latest', label: 'Mistral Medium' },
      { value: 'mistral-small-latest', label: 'Mistral Small' },
      { value: 'open-mistral-nemo', label: 'Open Mistral Nemo' },
      { value: 'codestral-latest', label: 'Codestral' },
      { value: 'pixtral-large-latest', label: 'Pixtral Large' },
      { value: 'pixtral-12b-2409', label: 'Pixtral 12B' },
    ]},
    ollama: { label: 'Ollama', tag: 'Local', tagClass: 'provider-ollama', models: [
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
    ]},
    scaleway: { label: 'Scaleway', tag: 'API EU', tagClass: 'provider-scaleway', models: [
      { value: 'mistral-large-3-675b-instruct-2512', label: 'Mistral Large 3 675B' },
      { value: 'mistral-small-3.2-24b-instruct-2506', label: 'Mistral Small 3.2 24B' },
      { value: 'mistral-small-3.1-24b-instruct-2503', label: 'Mistral Small 3.1 24B' },
      { value: 'llama-3.3-70b-instruct', label: 'Llama 3.3 70B Instruct' },
      { value: 'qwen2.5-coder-32b-instruct', label: 'Qwen 2.5 Coder 32B' },
      { value: 'pixtral-12b-2409', label: 'Pixtral 12B' },
    ]},
    openai: { label: 'OpenAI', tag: 'API Cloud', tagClass: 'provider-openai', models: [
      { value: 'gpt-4o', label: 'GPT-4o' },
      { value: 'gpt-4o-mini', label: 'GPT-4o Mini' },
      { value: 'gpt-4-turbo', label: 'GPT-4 Turbo' },
      { value: 'gpt-4', label: 'GPT-4' },
      { value: 'gpt-3.5-turbo', label: 'GPT-3.5 Turbo' },
      { value: 'o1', label: 'o1' },
      { value: 'o1-mini', label: 'o1 Mini' },
      { value: 'o3-mini', label: 'o3 Mini' },
    ]},
    anthropic: { label: 'Anthropic', tag: 'API Cloud', tagClass: 'provider-anthropic', models: [
      { value: 'claude-opus-4', label: 'Claude Opus 4' },
      { value: 'claude-sonnet-4', label: 'Claude Sonnet 4' },
      { value: 'claude-3.5-sonnet', label: 'Claude 3.5 Sonnet' },
      { value: 'claude-3.5-haiku', label: 'Claude 3.5 Haiku' },
      { value: 'claude-3-opus', label: 'Claude 3 Opus' },
      { value: 'claude-3-haiku', label: 'Claude 3 Haiku' },
    ]},
    google: { label: 'Google', tag: 'API Cloud', tagClass: 'provider-google', models: [
      { value: 'gemini-2.0-flash', label: 'Gemini 2.0 Flash' },
      { value: 'gemini-2.0-flash-lite', label: 'Gemini 2.0 Flash Lite' },
      { value: 'gemini-1.5-pro', label: 'Gemini 1.5 Pro' },
      { value: 'gemini-1.5-flash', label: 'Gemini 1.5 Flash' },
    ]},
    deepseek: { label: 'DeepSeek', tag: 'API Cloud', tagClass: 'provider-deepseek', models: [
      { value: 'deepseek-chat', label: 'DeepSeek Chat (V3)' },
      { value: 'deepseek-reasoner', label: 'DeepSeek Reasoner (R1)' },
    ]},
    cohere: { label: 'Cohere', tag: 'API Cloud', tagClass: 'provider-cohere', models: [
      { value: 'command-r-plus', label: 'Command R+' },
      { value: 'command-r', label: 'Command R' },
    ]},
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

  availableModels: { value: string; label: string }[] = [];
  newPricing = { provider: '', model_name: '', price_per_1k_input: 0, price_per_1k_output: 0 };

  // Computed from carbon methodology
  carbonIntensityEntries: [string, number][] = [];
  energyClassEntries: [string, number][] = [];

  get granularityLabel(): string {
    return { day: 'par jour', week: 'par semaine', month: 'par mois' }[this.chartGranularity];
  }

  constructor(
    private route: ActivatedRoute,
    private api: ApiService,
    private snackBar: MatSnackBar,
  ) {}

  ngOnInit(): void {
    this.projectId = this.route.snapshot.paramMap.get('projectId') || '';
    if (this.projectId) {
      this.loadAll();
    }
  }

  ngOnDestroy(): void {
    this.destroyAllCharts();
  }

  loadAll(): void {
    this.loadCostTracking();
    this.loadCarbonTracking();
  }

  onTabChange(event: any): void {
    // Rebuild charts when switching to analytics or carbon tabs
    setTimeout(() => {
      if (event.index === 2) this.rebuildChart();
      if (event.index === 3) this.rebuildCarbonCharts();
    }, 100);
  }

  // ── Cost Tracking ──

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

  // ── Carbon Tracking ──

  loadCarbonTracking(): void {
    this.loadingCarbon = true;
    this.api.getAICarbonTracking(this.projectId).subscribe({
      next: (res) => {
        this.carbon = res;
        this.loadingCarbon = false;
        if (res.methodology) {
          this.carbonIntensityEntries = Object.entries(res.methodology.carbon_intensities) as [string, number][];
          this.energyClassEntries = Object.entries(res.methodology.energy_per_1k_tokens_wh) as [string, number][];
        }
      },
      error: (err) => {
        this.snackBar.open(err.error?.detail || 'Erreur carbone', 'OK', { duration: 4000 });
        this.loadingCarbon = false;
      },
    });
  }

  // ── Analytics Chart ──

  rebuildChart(): void {
    if (!this.costTracking?.daily?.length) return;
    const canvas = this.analyticsCanvas?.nativeElement;
    if (!canvas) return;

    // Filter by date range
    let dailyData = [...this.costTracking.daily];
    if (this.chartDateStart) {
      dailyData = dailyData.filter((d: any) => d.date >= this.chartDateStart);
    }
    if (this.chartDateEnd) {
      dailyData = dailyData.filter((d: any) => d.date <= this.chartDateEnd);
    }

    // Aggregate by granularity
    this.aggregatedData = this.aggregateData(dailyData);

    // Destroy previous chart
    if (this.analyticsChart) {
      this.analyticsChart.destroy();
      this.analyticsChart = null;
    }

    const labels = this.aggregatedData.map(d => d.label);
    const values = this.aggregatedData.map(d => {
      if (this.chartMetric === 'cost') return d.cost;
      if (this.chartMetric === 'tokens') return d.input_tokens + d.output_tokens;
      return d.requests;
    });

    const metricLabel = { cost: 'Coût (EUR)', tokens: 'Tokens', requests: 'Requêtes' }[this.chartMetric];
    const isPieType = this.chartType === 'pie' || this.chartType === 'doughnut';

    const colors = this.generateColors(labels.length);

    const config: ChartConfiguration = {
      type: this.chartType as any,
      data: {
        labels,
        datasets: [{
          label: metricLabel,
          data: values,
          backgroundColor: isPieType ? colors : 'rgba(25, 118, 210, 0.6)',
          borderColor: isPieType ? '#fff' : 'rgba(25, 118, 210, 1)',
          borderWidth: isPieType ? 2 : 2,
          fill: this.chartType === 'line' ? 'origin' : undefined,
          tension: 0.3,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: isPieType, position: 'right' },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const val = ctx.parsed.y ?? ctx.parsed;
                if (this.chartMetric === 'cost') return ` ${(val as number).toFixed(4)} EUR`;
                return ` ${val.toLocaleString()}`;
              },
            },
          },
        },
        scales: isPieType ? {} : {
          y: { beginAtZero: true, title: { display: true, text: metricLabel } },
          x: { title: { display: true, text: this.granularityLabel } },
        },
      },
    };

    this.analyticsChart = new Chart(canvas, config);
  }

  resetDateRange(): void {
    this.chartDateStart = '';
    this.chartDateEnd = '';
    this.rebuildChart();
  }

  private aggregateData(dailyData: any[]): any[] {
    if (this.chartGranularity === 'day') {
      return dailyData.map(d => ({ ...d, label: d.date }));
    }

    const buckets: Record<string, any> = {};
    for (const d of dailyData) {
      let key: string;
      if (this.chartGranularity === 'week') {
        const dt = new Date(d.date);
        const dayOfWeek = dt.getDay() || 7;
        const monday = new Date(dt);
        monday.setDate(dt.getDate() - dayOfWeek + 1);
        key = 'S' + monday.toISOString().slice(0, 10);
      } else {
        key = d.date.slice(0, 7); // YYYY-MM
      }
      if (!buckets[key]) {
        buckets[key] = { label: key, cost: 0, input_tokens: 0, output_tokens: 0, requests: 0 };
      }
      buckets[key].cost += d.cost;
      buckets[key].input_tokens += d.input_tokens;
      buckets[key].output_tokens += d.output_tokens;
      buckets[key].requests += d.requests;
    }

    return Object.values(buckets).sort((a, b) => a.label.localeCompare(b.label)).map(b => ({
      ...b,
      cost: Math.round(b.cost * 10000) / 10000,
    }));
  }

  // ── Carbon Charts ──

  rebuildCarbonCharts(): void {
    if (!this.carbon) return;
    this.buildCarbonProviderChart();
    this.buildCarbonDailyChart();
  }

  private buildCarbonProviderChart(): void {
    const canvas = this.carbonProviderCanvas?.nativeElement;
    if (!canvas || !this.carbon?.by_provider?.length) return;

    if (this.carbonProviderChart) {
      this.carbonProviderChart.destroy();
      this.carbonProviderChart = null;
    }

    const labels = this.carbon.by_provider.map((p: any) => this.getProviderLabel(p.provider));
    const values = this.carbon.by_provider.map((p: any) => p.co2_g);
    const colors = this.carbon.by_provider.map((p: any) => this.providerColors[p.provider] || '#999');

    this.carbonProviderChart = new Chart(canvas, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{ data: values, backgroundColor: colors, borderColor: '#fff', borderWidth: 2 }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom', labels: { padding: 12, font: { size: 11 } } },
          tooltip: { callbacks: { label: (ctx) => ` ${(ctx.parsed as number).toFixed(2)} gCO₂` } },
        },
      },
    });
  }

  private buildCarbonDailyChart(): void {
    const canvas = this.carbonDailyCanvas?.nativeElement;
    if (!canvas || !this.carbon?.daily?.length) return;

    if (this.carbonDailyChart) {
      this.carbonDailyChart.destroy();
      this.carbonDailyChart = null;
    }

    const labels = this.carbon.daily.map((d: any) => d.date.slice(5));
    const co2Values = this.carbon.daily.map((d: any) => d.co2_g);
    const energyValues = this.carbon.daily.map((d: any) => d.energy_wh);

    this.carbonDailyChart = new Chart(canvas, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: 'CO₂ (g)', data: co2Values,
            borderColor: '#2e7d32', backgroundColor: 'rgba(46,125,50,0.15)',
            fill: true, tension: 0.3, yAxisID: 'y',
          },
          {
            label: 'Énergie (Wh)', data: energyValues,
            borderColor: '#ff9800', backgroundColor: 'rgba(255,152,0,0.1)',
            fill: true, tension: 0.3, yAxisID: 'y1',
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { position: 'bottom' } },
        scales: {
          y: { type: 'linear', position: 'left', beginAtZero: true, title: { display: true, text: 'CO₂ (g)' } },
          y1: { type: 'linear', position: 'right', beginAtZero: true, grid: { drawOnChartArea: false }, title: { display: true, text: 'Énergie (Wh)' } },
        },
      },
    });
  }

  // ── Pricing CRUD ──

  onProviderChange(): void {
    const provider = this.providers[this.newPricing.provider];
    this.availableModels = provider ? provider.models : [];
    this.newPricing.model_name = '';
  }

  addPricing(): void {
    if (!this.newPricing.provider || !this.newPricing.model_name) return;
    if (!this.costTracking) this.costTracking = { pricing: [] };
    this.costTracking.pricing.push({ id: '', ...this.newPricing, currency: 'EUR' });
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
        next: () => { this.snackBar.open('Tarif supprimé', 'OK', { duration: 2000 }); this.loadCostTracking(); },
        error: () => this.snackBar.open('Erreur de suppression', 'OK', { duration: 3000 }),
      });
    } else {
      this.costTracking.pricing = this.costTracking.pricing.filter((x: any) => x !== p);
    }
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
        this.snackBar.open(err.error?.detail || 'Erreur', 'OK', { duration: 4000 });
      },
    });
  }

  // ── Helpers ──

  getProviderLabel(provider: string): string {
    return this.providers[provider]?.label || provider;
  }

  getProviderClass(provider: string): string {
    const known = ['mistral', 'ollama', 'scaleway', 'openai', 'anthropic', 'google', 'deepseek', 'cohere'];
    return known.includes(provider) ? `provider-${provider}` : 'provider-other';
  }

  private generateColors(count: number): string[] {
    const palette = [
      '#1976d2', '#388e3c', '#f57c00', '#7b1fa2', '#c62828',
      '#00838f', '#4e342e', '#283593', '#ad1457', '#558b2f',
      '#ef6c00', '#1565c0', '#2e7d32', '#6a1b9a', '#d84315',
    ];
    const colors: string[] = [];
    for (let i = 0; i < count; i++) {
      colors.push(palette[i % palette.length]);
    }
    return colors;
  }

  private destroyAllCharts(): void {
    if (this.analyticsChart) { this.analyticsChart.destroy(); this.analyticsChart = null; }
    if (this.carbonProviderChart) { this.carbonProviderChart.destroy(); this.carbonProviderChart = null; }
    if (this.carbonDailyChart) { this.carbonDailyChart.destroy(); this.carbonDailyChart = null; }
  }
}
