import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatChipsModule } from '@angular/material/chips';
import { MatListModule } from '@angular/material/list';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatDividerModule } from '@angular/material/divider';
import { MatSelectModule } from '@angular/material/select';
import { FormsModule } from '@angular/forms';
import { Subscription, timer } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { ApiService } from '../../services/api.service';
import { ComplianceAnalysis } from '../../models/report.model';
import { renderMarkdown } from '../../services/markdown.service';

interface RecGenProgress {
  status: string;
  step: string;
  progress: number;
  message: string;
  chapterId?: string;
  chapterTitle?: string;
  content?: string;
}

@Component({
  selector: 'app-compliance',
  standalone: true,
  imports: [
    CommonModule, RouterLink,
    MatCardModule, MatButtonModule, MatIconModule, MatProgressSpinnerModule,
    MatProgressBarModule, MatChipsModule, MatListModule, MatSnackBarModule,
    MatTooltipModule, MatDividerModule, MatSelectModule, FormsModule,
  ],
  template: `
    <div class="page-container">
      <div class="page-header">
        <button mat-icon-button [routerLink]="['/project', projectId]"><mat-icon>arrow_back</mat-icon></button>
        <h1>Analyse de conformite et exhaustivite</h1>
        <mat-form-field class="scope-select" appearance="outline" subscriptSizing="dynamic">
          <mat-label>Documents a analyser</mat-label>
          <mat-select [(ngModel)]="targetScope" [disabled]="analyzing">
            <mat-option value="all">
              <mat-icon>select_all</mat-icon> Tout (memoire + documents)
            </mat-option>
            <mat-option value="memoire_only">
              <mat-icon>edit_document</mat-icon> Memoire technique uniquement
            </mat-option>
            <mat-option value="documents_only">
              <mat-icon>upload_file</mat-icon> Documents uploades uniquement
            </mat-option>
          </mat-select>
        </mat-form-field>
        <button mat-raised-button color="primary" (click)="runAnalysis()" [disabled]="analyzing">
          <mat-spinner *ngIf="analyzing" diameter="18"></mat-spinner>
          <mat-icon *ngIf="!analyzing">fact_check</mat-icon>
          {{ analysis ? 'Relancer' : 'Analyser' }}
        </button>
        <button mat-raised-button *ngIf="analysis && !analyzing" (click)="exportPdf()" [disabled]="exportingPdf">
          <mat-spinner *ngIf="exportingPdf" diameter="18"></mat-spinner>
          <mat-icon *ngIf="!exportingPdf">picture_as_pdf</mat-icon>
          Exporter PDF
        </button>
      </div>

      <!-- Loading existing analysis -->
      <div *ngIf="loadingExisting" class="loading-container">
        <mat-spinner diameter="30"></mat-spinner>
        <span>Chargement de l'analyse precedente...</span>
      </div>

      <!-- Progress bar -->
      <mat-card *ngIf="analyzing && analysisProgress" class="progress-card">
        <div class="progress-header">
          <mat-spinner diameter="20"></mat-spinner>
          <h3>Analyse de conformite en cours...</h3>
        </div>
        <mat-progress-bar mode="determinate" [value]="analysisProgress.progress"></mat-progress-bar>
        <div class="progress-details">
          <span class="progress-step">{{ analysisProgress.step }}</span>
          <span class="progress-pct">{{ analysisProgress.progress }}%</span>
        </div>
        <p class="progress-message">{{ analysisProgress.message }}</p>
      </mat-card>

      <div *ngIf="analysis && !analyzing" class="analysis-results">
        <!-- Timestamp -->
        <div *ngIf="analysis.created_at" class="analysis-timestamp">
          <mat-icon>schedule</mat-icon>
          Derniere analyse : {{ analysis.created_at | date:'medium' }}
        </div>

        <!-- Score -->
        <mat-card class="score-card">
          <div class="score-circle" [class]="scoreClass">
            <span class="score-value">{{ analysis.score }}</span>
            <span class="score-label">/ 100</span>
          </div>
          <div class="score-details">
            <h2>Score de conformite</h2>
            <mat-progress-bar [value]="analysis.score" [color]="analysis.score >= 80 ? 'primary' : analysis.score >= 50 ? 'accent' : 'warn'"></mat-progress-bar>
            <p>{{ analysis.summary }}</p>
          </div>
        </mat-card>

        <!-- Covered requirements -->
        <mat-card class="section-card">
          <h3><mat-icon>check_circle</mat-icon> Exigences couvertes ({{ analysis.covered_requirements.length }})</h3>
          <div class="req-list">
            <div *ngFor="let req of analysis.covered_requirements" class="req-item" [class]="'req-border-' + req.coverage">
              <div class="req-header">
                <mat-icon [class]="'coverage-' + req.coverage">
                  {{ req.coverage === 'complete' ? 'check_circle' : req.coverage === 'partial' ? 'remove_circle' : 'cancel' }}
                </mat-icon>
                <span class="req-title">{{ req.requirement }}</span>
                <mat-chip [class]="'cov-chip-' + req.coverage" size="small">{{ coverageLabel(req.coverage) }}</mat-chip>
              </div>
              <p class="req-comment" *ngIf="req.comment">{{ req.comment }}</p>
              <div class="req-sources" *ngIf="req.source_rfp || req.source_response">
                <span class="source-tag source-rfp" *ngIf="req.source_rfp" matTooltip="Document de l'appel d'offres">
                  <mat-icon>description</mat-icon> AO: {{ req.source_rfp }}
                </span>
                <span class="source-tag source-response" *ngIf="req.source_response" matTooltip="Document de notre reponse">
                  <mat-icon>task</mat-icon> Reponse: {{ req.source_response }}
                </span>
              </div>
            </div>
          </div>
        </mat-card>

        <!-- Missing elements with auto-integration -->
        <mat-card *ngIf="analysis.missing_elements?.length" class="section-card missing">
          <h3>
            <mat-icon>warning</mat-icon> Elements manquants ({{ analysis.missing_elements.length }})
            <span class="spacer"></span>
            <button mat-raised-button color="accent" (click)="integrateAllMissing()"
              [disabled]="allMissingLaunched()"
              matTooltip="Lancer l'integration de tous les elements manquants en parallele">
              <mat-icon>playlist_add</mat-icon>
              Tout integrer
            </button>
          </h3>
          <div class="req-list">
            <div *ngFor="let item of analysis.missing_elements; let mi = index" class="req-item req-border-missing">
              <div class="req-header">
                <mat-icon class="coverage-missing">error_outline</mat-icon>
                <span class="req-title">{{ item.requirement }}</span>
              </div>
              <p class="req-comment">{{ item.description }}</p>
              <div class="req-sources" *ngIf="item.source_rfp">
                <span class="source-tag source-rfp" matTooltip="Document de l'appel d'offres">
                  <mat-icon>description</mat-icon> AO: {{ item.source_rfp }}
                </span>
              </div>

              <!-- Integration button (hidden when processing or done) -->
              <div class="integrate-actions" *ngIf="!missingProgress[mi] && !missingDone[mi]">
                <button mat-raised-button color="accent"
                  (click)="integrateMissing(mi, item.requirement, item.description)"
                  matTooltip="L'IA identifie le meilleur chapitre et y ajoute le contenu manquant">
                  <mat-icon>add_circle</mat-icon>
                  Integrer au memoire
                </button>
              </div>

              <!-- Progress bar -->
              <div *ngIf="missingProgress[mi]" class="gen-progress-section">
                <div class="gen-progress-header">
                  <mat-icon *ngIf="missingProgress[mi].status === 'queued'" class="queued-icon">schedule</mat-icon>
                  <mat-spinner *ngIf="missingProgress[mi].status !== 'queued'" diameter="16"></mat-spinner>
                  <span>{{ missingProgress[mi].message }}</span>
                </div>
                <mat-progress-bar
                  [mode]="missingProgress[mi].progress ? 'determinate' : 'indeterminate'"
                  [value]="missingProgress[mi].progress"
                  [color]="missingProgress[mi].status === 'queued' ? 'primary' : 'accent'">
                </mat-progress-bar>
                <div *ngIf="missingProgress[mi].progress" class="gen-progress-pct">{{ missingProgress[mi].progress }}%</div>
              </div>

              <!-- Success result -->
              <div *ngIf="missingDone[mi]" class="integration-result">
                <div class="integration-success">
                  <mat-icon>check_circle</mat-icon>
                  <span>Contenu ajoute dans : <strong>{{ missingDone[mi].chapterTitle }}</strong></span>
                  <a mat-button [routerLink]="['/project', projectId, 'chapter', missingDone[mi].chapterId]" color="primary">
                    <mat-icon>open_in_new</mat-icon> Voir
                  </a>
                </div>
                <div class="generated-content">
                  <div class="generated-header">
                    <mat-icon>description</mat-icon>
                    <span>Contenu genere et integre</span>
                    <button mat-icon-button (click)="copyToClipboard(missingDone[mi].content)" matTooltip="Copier">
                      <mat-icon>content_copy</mat-icon>
                    </button>
                  </div>
                  <div class="generated-body" [innerHTML]="renderMd(missingDone[mi].content)"></div>
                </div>
              </div>
            </div>
          </div>
        </mat-card>

        <!-- Recommendations with auto-integration -->
        <mat-card *ngIf="analysis.recommendations?.length" class="section-card recommendations-card">
          <h3>
            <mat-icon>lightbulb</mat-icon> Recommandations
            <span class="spacer"></span>
            <button mat-raised-button color="accent" (click)="integrateAllRecs()"
              [disabled]="allRecsLaunched()"
              matTooltip="Lancer l'integration de toutes les recommandations en parallele">
              <mat-icon>playlist_add</mat-icon>
              Tout integrer
            </button>
          </h3>
          <div *ngFor="let rec of analysis.recommendations; let i = index" class="recommendation-item">
            <div class="rec-header">
              <mat-icon class="rec-icon">arrow_forward</mat-icon>
              <span class="rec-text">{{ rec }}</span>
            </div>

            <!-- Integration buttons (hidden when processing or done) -->
            <div class="integrate-actions rec-integrate" *ngIf="!recProgress[i] && !recDone[i]">
              <button mat-raised-button color="accent"
                (click)="integrateRec(i, rec)"
                matTooltip="L'IA identifie le meilleur chapitre et y ajoute le contenu">
                <mat-icon>add_circle</mat-icon>
                Integrer au memoire
              </button>
              <button mat-stroked-button
                (click)="previewRec(i, rec)"
                matTooltip="Generer un apercu du contenu sans l'ajouter a un chapitre">
                <mat-icon>visibility</mat-icon>
                Apercu
              </button>
            </div>

            <!-- Progress bar -->
            <div *ngIf="recProgress[i]" class="gen-progress-section rec-integrate">
              <div class="gen-progress-header">
                <mat-icon *ngIf="recProgress[i].status === 'queued'" class="queued-icon">schedule</mat-icon>
                <mat-spinner *ngIf="recProgress[i].status !== 'queued'" diameter="16"></mat-spinner>
                <span>{{ recProgress[i].message }}</span>
              </div>
              <mat-progress-bar
                [mode]="recProgress[i].progress ? 'determinate' : 'indeterminate'"
                [value]="recProgress[i].progress"
                [color]="recProgress[i].status === 'queued' ? 'primary' : 'accent'">
              </mat-progress-bar>
              <div *ngIf="recProgress[i].progress" class="gen-progress-pct">{{ recProgress[i].progress }}%</div>
            </div>

            <!-- Success result (injected) -->
            <div *ngIf="recDone[i]" class="integration-result">
              <div class="integration-success">
                <mat-icon>check_circle</mat-icon>
                <span>Contenu ajoute dans : <strong>{{ recDone[i].chapterTitle }}</strong></span>
                <a mat-button [routerLink]="['/project', projectId, 'chapter', recDone[i].chapterId]" color="primary">
                  <mat-icon>open_in_new</mat-icon> Voir
                </a>
              </div>
              <div class="generated-content">
                <div class="generated-header">
                  <mat-icon>description</mat-icon>
                  <span>Contenu genere et integre</span>
                  <button mat-icon-button (click)="copyToClipboard(recDone[i].content)" matTooltip="Copier">
                    <mat-icon>content_copy</mat-icon>
                  </button>
                </div>
                <div class="generated-body" [innerHTML]="renderMd(recDone[i].content)"></div>
              </div>
            </div>

            <!-- Preview-only content (not injected) -->
            <div *ngIf="!recDone[i] && !recProgress[i] && recPreviews[i]" class="generated-content rec-integrate">
              <div class="generated-header">
                <mat-icon>description</mat-icon>
                <span>Apercu du contenu</span>
                <button mat-icon-button (click)="copyToClipboard(recPreviews[i])" matTooltip="Copier">
                  <mat-icon>content_copy</mat-icon>
                </button>
              </div>
              <div class="generated-body" [innerHTML]="renderMd(recPreviews[i])"></div>
            </div>
            <mat-divider *ngIf="i < analysis.recommendations.length - 1"></mat-divider>
          </div>
        </mat-card>
      </div>

      <!-- Empty state -->
      <mat-card *ngIf="!analysis && !analyzing && !loadingExisting && !error" class="empty-card">
        <mat-icon>fact_check</mat-icon>
        <div>
          <h3>Aucune analyse disponible</h3>
          <p>Lancez une analyse pour evaluer la conformite de votre reponse par rapport au cahier des charges. Fonctionne avec les documents "Notre reponse" charges ou les chapitres rediges.</p>
        </div>
      </mat-card>

      <mat-card *ngIf="error" class="error-card"><mat-icon>error</mat-icon><p>{{ error }}</p></mat-card>
    </div>
  `,
  styles: [`
    .page-container { max-width: 1000px; margin: 0 auto; }
    .page-header { display: flex; align-items: center; gap: 12px; margin-bottom: 24px; }
    .page-header h1 { flex: 1; margin: 0; color: #1B3A5C; font-size: 20px; }
    .scope-select { width: 280px; font-size: 13px; }
    .scope-select mat-icon { font-size: 18px; width: 18px; height: 18px; margin-right: 6px; vertical-align: middle; }
    .loading-container { display: flex; align-items: center; gap: 12px; padding: 24px; color: #666; }
    .analysis-timestamp { display: flex; align-items: center; gap: 6px; font-size: 13px; color: #888; margin-bottom: 16px; }
    .analysis-timestamp mat-icon { font-size: 18px; width: 18px; height: 18px; }
    .progress-card { padding: 24px; margin-bottom: 16px; border-left: 4px solid #1976d2; }
    .progress-header { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
    .progress-header h3 { margin: 0; color: #1976d2; font-size: 15px; }
    .progress-details { display: flex; justify-content: space-between; margin-top: 8px; font-size: 13px; }
    .progress-step { color: #1976d2; }
    .progress-pct { font-weight: bold; }
    .progress-message { margin: 8px 0 0 0; font-size: 13px; color: #666; }
    .score-card { display: flex; align-items: center; gap: 24px; padding: 32px; margin-bottom: 16px; }
    .score-circle { width: 100px; height: 100px; border-radius: 50%; display: flex; flex-direction: column; justify-content: center; align-items: center; }
    .score-circle.high { background: #e8f5e9; border: 4px solid #4caf50; }
    .score-circle.medium { background: #fff3e0; border: 4px solid #ff9800; }
    .score-circle.low { background: #ffebee; border: 4px solid #f44336; }
    .score-value { font-size: 32px; font-weight: bold; }
    .score-label { font-size: 14px; color: #888; }
    .score-details { flex: 1; }
    .score-details h2 { margin: 0 0 8px; }
    .section-card { padding: 20px; margin-bottom: 16px; }
    .section-card h3 { display: flex; align-items: center; gap: 8px; color: #1B3A5C; margin-bottom: 16px; }
    .spacer { flex: 1; }
    .missing h3 { color: #c62828; }
    .coverage-complete { color: #4caf50; }
    .coverage-partial { color: #ff9800; }
    .coverage-missing { color: #f44336; }
    .cov-chip-complete { background: #e8f5e9 !important; }
    .cov-chip-partial { background: #fff3e0 !important; }
    .cov-chip-missing { background: #ffebee !important; }
    .req-list { display: flex; flex-direction: column; gap: 12px; }
    .req-item { padding: 14px 16px; border-radius: 8px; background: #fafafa; border-left: 4px solid #e0e0e0; }
    .req-border-complete { border-left-color: #4caf50; }
    .req-border-partial { border-left-color: #ff9800; }
    .req-border-missing { border-left-color: #f44336; }
    .req-header { display: flex; align-items: flex-start; gap: 10px; }
    .req-header mat-icon { flex-shrink: 0; margin-top: 2px; }
    .req-title { flex: 1; font-weight: 500; font-size: 14px; color: #1B3A5C; line-height: 1.5; }
    .req-header mat-chip { flex-shrink: 0; }
    .req-comment { margin: 8px 0 0 34px; font-size: 13px; color: #555; line-height: 1.6; white-space: pre-wrap; word-break: break-word; }
    .req-sources { display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0 0 34px; }
    .source-tag { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; padding: 3px 10px; border-radius: 12px; }
    .source-tag mat-icon { font-size: 14px; width: 14px; height: 14px; }
    .source-rfp { background: #e3f2fd; color: #1565c0; }
    .source-response { background: #f3e5f5; color: #7b1fa2; }
    .recommendations-card { padding: 20px; }
    .recommendation-item { padding: 12px 0; }
    .rec-header { display: flex; align-items: flex-start; gap: 10px; }
    .rec-icon { color: #1976d2; margin-top: 2px; flex-shrink: 0; }
    .rec-text { flex: 1; font-size: 14px; line-height: 1.5; }
    .generated-content { margin: 12px 0 12px 34px; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden; }
    .generated-header { display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: #e3f2fd; font-size: 13px; font-weight: 500; color: #1565c0; }
    .generated-header span { flex: 1; }
    .generated-body { padding: 16px; font-size: 14px; line-height: 1.6; }
    .generated-body h2, .generated-body h3 { font-size: 16px; color: #1B3A5C; margin: 16px 0 8px 0; }
    .generated-body h2:first-child, .generated-body h3:first-child { margin-top: 0; }
    .generated-body p { margin: 0 0 10px 0; }
    .generated-body ul, .generated-body ol { margin: 4px 0 10px 0; padding-left: 24px; }
    .generated-body li { margin-bottom: 4px; }
    .generated-body strong { color: #1B3A5C; }
    .empty-card { padding: 32px; display: flex; align-items: center; gap: 16px; }
    .empty-card mat-icon { font-size: 40px; width: 40px; height: 40px; color: #bdbdbd; }
    .empty-card h3 { margin: 0 0 4px; color: #1B3A5C; }
    .empty-card p { margin: 0; color: #888; font-size: 14px; }
    .error-card { padding: 24px; display: flex; align-items: center; gap: 12px; color: #c62828; }

    /* Integration actions & progress */
    .integrate-actions { margin: 12px 0 0 34px; display: flex; gap: 10px; flex-wrap: wrap; }
    .rec-integrate { margin-left: 34px; margin-top: 10px; }
    .integration-result { margin: 12px 0 0 34px; }
    .integration-success { display: flex; align-items: center; gap: 8px; padding: 10px 14px; background: #e8f5e9; border-radius: 6px; font-size: 13px; color: #2e7d32; margin-bottom: 8px; }
    .integration-success mat-icon { font-size: 18px; width: 18px; height: 18px; flex-shrink: 0; }
    .integration-success span { flex: 1; }
    .integration-success a { font-size: 13px; flex-shrink: 0; }

    .gen-progress-section { margin: 10px 0 0 34px; }
    .gen-progress-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-size: 13px; color: #555; }
    .gen-progress-pct { text-align: right; font-size: 12px; color: #888; margin-top: 3px; }
    .queued-icon { font-size: 18px; width: 18px; height: 18px; color: #1565c0; }
    .generated-body .inserted-image { margin: 12px 0; text-align: center; }
    .generated-body .inserted-image img { max-width: 100%; height: auto; border-radius: 6px; border: 1px solid #e0e0e0; }
  `],
})
export class ComplianceComponent implements OnInit, OnDestroy {
  projectId = '';
  analysis: ComplianceAnalysis | null = null;
  analyzing = false;
  loadingExisting = false;
  error = '';
  targetScope = 'all';
  renderMd = (text: string) =>
    renderMarkdown(text, (id: string) => this.api.getImageUrl(id));
  analysisProgress: { status: string; step: string; progress: number; message: string } | null = null;
  exportingPdf = false;
  private pollSub: Subscription | null = null;

  // Per-item progress tracking (key = index)
  missingProgress: Record<number, RecGenProgress> = {};
  missingDone: Record<number, { chapterId: string; chapterTitle: string; content: string }> = {};
  private missingTaskIds: Record<number, string> = {};
  private missingPollSubs: Record<number, Subscription> = {};

  recProgress: Record<number, RecGenProgress> = {};
  recDone: Record<number, { chapterId: string; chapterTitle: string; content: string }> = {};
  recPreviews: Record<number, string> = {};
  private recTaskIds: Record<number, string> = {};
  private recPollSubs: Record<number, Subscription> = {};

  get scoreClass(): string {
    if (!this.analysis) return '';
    if (this.analysis.score >= 80) return 'high';
    if (this.analysis.score >= 50) return 'medium';
    return 'low';
  }

  constructor(
    private route: ActivatedRoute,
    private api: ApiService,
    private snackBar: MatSnackBar,
  ) {}

  ngOnInit(): void {
    this.projectId = this.route.snapshot.paramMap.get('projectId') || '';
    this.loadExisting();
    this.api.getComplianceAnalysisStatus(this.projectId).subscribe({
      next: (status) => {
        if (status.status === 'running') {
          this.analyzing = true;
          this.analysisProgress = status;
          this.startPolling();
        }
      },
    });
  }

  ngOnDestroy(): void {
    this.stopPolling();
    for (const sub of Object.values(this.missingPollSubs)) sub.unsubscribe();
    for (const sub of Object.values(this.recPollSubs)) sub.unsubscribe();
  }

  loadExisting(): void {
    this.loadingExisting = true;
    this.api.getComplianceAnalysis(this.projectId).subscribe({
      next: (res) => {
        this.analysis = res.analysis;
        this.loadingExisting = false;
      },
      error: () => { this.loadingExisting = false; },
    });
  }

  runAnalysis(): void {
    this.analyzing = true;
    this.error = '';
    this.missingProgress = {};
    this.missingDone = {};
    this.recProgress = {};
    this.recDone = {};
    this.recPreviews = {};
    this.analysisProgress = { status: 'running', step: 'starting', progress: 0, message: 'Lancement...' };
    this.api.analyzeCompliance(this.projectId, this.targetScope).subscribe({
      next: () => this.startPolling(),
      error: (err) => {
        this.error = err.error?.detail || 'Erreur';
        this.analyzing = false;
        this.analysisProgress = null;
      },
    });
  }

  private startPolling(): void {
    this.stopPolling();
    this.pollSub = timer(1000, 1500).pipe(
      switchMap(() => this.api.getComplianceAnalysisStatus(this.projectId))
    ).subscribe({
      next: (status) => {
        this.analysisProgress = status;
        if (status.status === 'completed') {
          this.stopPolling();
          this.analyzing = false;
          this.analysisProgress = null;
          this.snackBar.open('Analyse de conformite terminee', 'OK', { duration: 3000 });
          this.loadExisting();
        } else if (status.status === 'error') {
          this.stopPolling();
          this.analyzing = false;
          this.error = status.message;
          this.analysisProgress = null;
        }
      },
    });
  }

  private stopPolling(): void {
    this.pollSub?.unsubscribe();
    this.pollSub = null;
  }

  // ── Missing elements ──

  integrateMissing(index: number, requirement: string, description: string): void {
    if (this.missingProgress[index] || this.missingDone[index]) return;

    const taskId = `missing-${Date.now()}-${index}`;
    this.missingTaskIds[index] = taskId;
    this.missingProgress[index] = { status: 'queued', step: 'queued', progress: 0, message: 'En file d\'attente...' };

    this.api.launchRecommendationGeneration(this.projectId, requirement, taskId, {
      missingDescription: description, inject: true,
    }).subscribe({
      next: () => this._startRecPolling('missing', index, taskId),
      error: (err) => {
        delete this.missingProgress[index];
        this.snackBar.open(err.error?.detail || 'Erreur', 'OK', { duration: 4000 });
      },
    });
  }

  integrateAllMissing(): void {
    if (!this.analysis?.missing_elements) return;
    for (let i = 0; i < this.analysis.missing_elements.length; i++) {
      if (!this.missingProgress[i] && !this.missingDone[i]) {
        const item = this.analysis.missing_elements[i];
        this.integrateMissing(i, item.requirement, item.description);
      }
    }
  }

  allMissingLaunched(): boolean {
    if (!this.analysis?.missing_elements) return true;
    return this.analysis.missing_elements.every((_, i) => !!this.missingProgress[i] || !!this.missingDone[i]);
  }

  // ── Recommendations ──

  integrateRec(index: number, recommendation: string): void {
    if (this.recProgress[index] || this.recDone[index]) return;

    const taskId = `rec-${Date.now()}-${index}`;
    this.recTaskIds[index] = taskId;
    this.recProgress[index] = { status: 'queued', step: 'queued', progress: 0, message: 'En file d\'attente...' };

    this.api.launchRecommendationGeneration(this.projectId, recommendation, taskId, {
      inject: true,
    }).subscribe({
      next: () => this._startRecPolling('rec', index, taskId),
      error: (err) => {
        delete this.recProgress[index];
        this.snackBar.open(err.error?.detail || 'Erreur', 'OK', { duration: 4000 });
      },
    });
  }

  previewRec(index: number, recommendation: string): void {
    if (this.recProgress[index]) return;

    const taskId = `rec-preview-${Date.now()}-${index}`;
    this.recTaskIds[index] = taskId;
    this.recProgress[index] = { status: 'queued', step: 'queued', progress: 0, message: 'En file d\'attente...' };

    this.api.launchRecommendationGeneration(this.projectId, recommendation, taskId, {
      inject: false,
    }).subscribe({
      next: () => this._startRecPolling('rec-preview', index, taskId),
      error: (err) => {
        delete this.recProgress[index];
        this.snackBar.open(err.error?.detail || 'Erreur', 'OK', { duration: 4000 });
      },
    });
  }

  integrateAllRecs(): void {
    if (!this.analysis?.recommendations) return;
    for (let i = 0; i < this.analysis.recommendations.length; i++) {
      if (!this.recProgress[i] && !this.recDone[i]) {
        this.integrateRec(i, this.analysis.recommendations[i]);
      }
    }
  }

  allRecsLaunched(): boolean {
    if (!this.analysis?.recommendations) return true;
    return this.analysis.recommendations.every((_, i) => !!this.recProgress[i] || !!this.recDone[i]);
  }

  // ── Generic polling for recommendation generation tasks ──

  private _startRecPolling(type: 'missing' | 'rec' | 'rec-preview', index: number, taskId: string): void {
    const pollSubs = type === 'missing' ? this.missingPollSubs : this.recPollSubs;

    pollSubs[index]?.unsubscribe();
    pollSubs[index] = timer(500, 1500).pipe(
      switchMap(() => this.api.getRecommendationGenStatus(this.projectId, taskId))
    ).subscribe({
      next: (status) => {
        if (status.status === 'completed') {
          pollSubs[index]?.unsubscribe();
          delete pollSubs[index];

          if (type === 'missing') {
            delete this.missingProgress[index];
            this.missingDone[index] = {
              chapterId: status.chapter_id || '',
              chapterTitle: status.chapter_title || 'Chapitre',
              content: status.content || '',
            };
          } else if (type === 'rec') {
            delete this.recProgress[index];
            this.recDone[index] = {
              chapterId: status.chapter_id || '',
              chapterTitle: status.chapter_title || 'Chapitre',
              content: status.content || '',
            };
          } else {
            // rec-preview
            delete this.recProgress[index];
            this.recPreviews[index] = status.content || '';
          }

          const msg = type === 'rec-preview'
            ? 'Apercu genere'
            : `Contenu integre dans "${status.chapter_title}"`;
          this.snackBar.open(msg, 'OK', { duration: 3000 });

        } else if (status.status === 'error') {
          pollSubs[index]?.unsubscribe();
          delete pollSubs[index];
          if (type === 'missing') {
            delete this.missingProgress[index];
          } else {
            delete this.recProgress[index];
          }
          this.snackBar.open(status.message || 'Erreur de generation', 'OK', { duration: 5000 });

        } else {
          // running / queued → update progress
          const progress: RecGenProgress = {
            status: status.status,
            step: status.step,
            progress: status.progress,
            message: status.message,
            chapterId: status.chapter_id,
            chapterTitle: status.chapter_title,
          };
          if (type === 'missing') {
            this.missingProgress[index] = progress;
          } else {
            this.recProgress[index] = progress;
          }
        }
      },
    });
  }

  // ── Utilities ──

  copyToClipboard(text: string): void {
    navigator.clipboard.writeText(text).then(() => {
      this.snackBar.open('Copie dans le presse-papier', 'OK', { duration: 1500 });
    });
  }

  coverageLabel(coverage: string): string {
    const labels: Record<string, string> = { complete: 'Complet', partial: 'Partiel', missing: 'Manquant' };
    return labels[coverage] || coverage;
  }

  exportPdf(): void {
    this.exportingPdf = true;
    this.api.exportCompliancePdf(this.projectId).subscribe({
      next: (blob) => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `conformite_${new Date().toISOString().slice(0, 10)}.pdf`;
        a.click();
        window.URL.revokeObjectURL(url);
        this.exportingPdf = false;
        this.snackBar.open('PDF exporte', 'OK', { duration: 2000 });
      },
      error: (err) => {
        this.exportingPdf = false;
        this.snackBar.open(err.error?.detail || 'Erreur export PDF', 'OK', { duration: 3000 });
      },
    });
  }
}
