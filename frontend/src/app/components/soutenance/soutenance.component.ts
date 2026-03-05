import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatTabsModule } from '@angular/material/tabs';
import { MatChipsModule } from '@angular/material/chips';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ApiService } from '../../services/api.service';
import { SoutenanceScript } from '../../models/report.model';

@Component({
  selector: 'app-soutenance',
  standalone: true,
  imports: [
    CommonModule, RouterLink, MatCardModule, MatButtonModule, MatIconModule,
    MatProgressSpinnerModule, MatExpansionModule, MatTabsModule, MatChipsModule,
    MatTooltipModule, MatSnackBarModule,
  ],
  template: `
    <div class="soutenance-container" *ngIf="!loading">
      <!-- Header -->
      <div class="soutenance-header">
        <div class="header-left">
          <button mat-icon-button [routerLink]="['/project', projectId]"><mat-icon>arrow_back</mat-icon></button>
          <div>
            <h1>Preparation de la soutenance</h1>
            <span class="subtitle" *ngIf="script">{{ script.project_name }} - {{ script.client_name }}</span>
          </div>
        </div>
        <div class="header-actions">
          <button mat-raised-button color="primary" (click)="downloadPptx()" [disabled]="downloadingPptx">
            <mat-spinner *ngIf="downloadingPptx" diameter="18"></mat-spinner>
            <mat-icon *ngIf="!downloadingPptx">slideshow</mat-icon>
            Telecharger le PowerPoint
          </button>
          <button mat-raised-button (click)="printScript()">
            <mat-icon>print</mat-icon> Imprimer le script
          </button>
        </div>
      </div>

      <!-- No data -->
      <mat-card *ngIf="!script" class="empty-card">
        <mat-icon>co_present</mat-icon>
        <h2>Aucune soutenance generee</h2>
        <p>Retournez au tableau de bord du projet et cliquez sur "Soutenance" pour generer le PowerPoint et le script.</p>
        <button mat-raised-button color="primary" [routerLink]="['/project', projectId]">
          <mat-icon>arrow_back</mat-icon> Retour au projet
        </button>
      </mat-card>

      <!-- Main content -->
      <div *ngIf="script" class="soutenance-content">

        <!-- Overview cards -->
        <div class="overview-row">
          <mat-card class="overview-card duration-card">
            <mat-icon>schedule</mat-icon>
            <div class="overview-value">{{ script.total_duration || 'N/A' }}</div>
            <div class="overview-label">Duree totale</div>
          </mat-card>
          <mat-card class="overview-card sections-card">
            <mat-icon>view_list</mat-icon>
            <div class="overview-value">{{ script.sections?.length || 0 }}</div>
            <div class="overview-label">Sections</div>
          </mat-card>
          <mat-card class="overview-card strengths-card">
            <mat-icon>star</mat-icon>
            <div class="overview-value">{{ script.strengths?.length || 0 }}</div>
            <div class="overview-label">Forces cles</div>
          </mat-card>
          <mat-card class="overview-card qa-card">
            <mat-icon>help_outline</mat-icon>
            <div class="overview-value">{{ script.qa_preparation?.expected_questions?.length || 0 }}</div>
            <div class="overview-label">Questions anticipees</div>
          </mat-card>
        </div>

        <mat-tab-group animationDuration="200ms" class="soutenance-tabs">
          <!-- Tab 1: Deroulement -->
          <mat-tab>
            <ng-template mat-tab-label>
              <mat-icon>play_circle_outline</mat-icon>
              <span>Deroulement</span>
            </ng-template>

            <!-- Introduction -->
            <mat-card class="script-card intro-card">
              <div class="script-card-header">
                <mat-icon>mic</mat-icon>
                <h2>Introduction</h2>
              </div>
              <div class="script-text">{{ script.introduction }}</div>
            </mat-card>

            <!-- Sections -->
            <mat-accordion multi>
              <mat-expansion-panel *ngFor="let section of script.sections; let i = index" class="section-panel">
                <mat-expansion-panel-header>
                  <mat-panel-title>
                    <span class="section-number">{{ i + 1 }}</span>
                    {{ section.title }}
                  </mat-panel-title>
                  <mat-panel-description>
                    <mat-icon>schedule</mat-icon> {{ section.duration }}
                  </mat-panel-description>
                </mat-expansion-panel-header>

                <!-- Presenter guide -->
                <div class="section-content">
                  <div class="guide-block">
                    <h3><mat-icon>record_voice_over</mat-icon> Guide du presentateur</h3>
                    <div class="guide-text">{{ section.presenter_guide }}</div>
                  </div>

                  <!-- Key messages -->
                  <div class="messages-block" *ngIf="section.key_messages?.length">
                    <h3><mat-icon>campaign</mat-icon> Messages cles</h3>
                    <div class="message-chips">
                      <span class="key-message" *ngFor="let msg of section.key_messages">{{ msg }}</span>
                    </div>
                  </div>

                  <!-- Anticipated Q&A for this section -->
                  <div class="qa-block" *ngIf="section.anticipated_questions?.length">
                    <h3><mat-icon>help</mat-icon> Questions probables</h3>
                    <div *ngFor="let q of section.anticipated_questions; let qi = index" class="qa-item">
                      <div class="qa-question"><strong>Q:</strong> {{ q }}</div>
                      <div class="qa-answer" *ngIf="section.suggested_answers?.[qi]"><strong>R:</strong> {{ section.suggested_answers[qi] }}</div>
                    </div>
                  </div>
                </div>
              </mat-expansion-panel>
            </mat-accordion>

            <!-- Closing -->
            <mat-card class="script-card closing-card">
              <div class="script-card-header">
                <mat-icon>flag</mat-icon>
                <h2>Conclusion</h2>
              </div>
              <div class="script-text">{{ script.closing }}</div>
            </mat-card>
          </mat-tab>

          <!-- Tab 2: Forces -->
          <mat-tab>
            <ng-template mat-tab-label>
              <mat-icon>star</mat-icon>
              <span>Forces</span>
            </ng-template>

            <div class="tab-content">
              <!-- Key figures -->
              <div class="key-figures-section" *ngIf="script.key_figures?.length">
                <h2><mat-icon>insights</mat-icon> Chiffres cles</h2>
                <div class="figures-grid">
                  <mat-card *ngFor="let fig of script.key_figures" class="figure-card">
                    <div class="figure-value">{{ fig.value }}</div>
                    <div class="figure-label">{{ fig.label }}</div>
                  </mat-card>
                </div>
              </div>

              <!-- Strengths -->
              <div class="strengths-section" *ngIf="script.strengths?.length">
                <h2><mat-icon>emoji_events</mat-icon> Nos forces</h2>
                <div class="strengths-list">
                  <div *ngFor="let strength of script.strengths; let i = index" class="strength-item">
                    <div class="strength-number">{{ i + 1 }}</div>
                    <div class="strength-text">{{ strength }}</div>
                  </div>
                </div>
              </div>
            </div>
          </mat-tab>

          <!-- Tab 3: Questions & Reponses -->
          <mat-tab>
            <ng-template mat-tab-label>
              <mat-icon>question_answer</mat-icon>
              <span>Q&R</span>
            </ng-template>

            <div class="tab-content">
              <!-- Expected questions -->
              <div class="expected-questions" *ngIf="script.qa_preparation?.expected_questions?.length">
                <h2><mat-icon>quiz</mat-icon> Questions anticipees du jury</h2>
                <mat-accordion>
                  <mat-expansion-panel *ngFor="let qa of script.qa_preparation.expected_questions; let i = index" class="qa-panel">
                    <mat-expansion-panel-header>
                      <mat-panel-title>
                        <span class="qa-number">Q{{ i + 1 }}</span>
                        {{ qa.question }}
                      </mat-panel-title>
                    </mat-expansion-panel-header>
                    <div class="qa-answer-block">
                      <h4>Reponse recommandee</h4>
                      <p>{{ qa.answer }}</p>
                      <div class="qa-tips" *ngIf="qa.tips">
                        <mat-icon>lightbulb</mat-icon>
                        <span>{{ qa.tips }}</span>
                      </div>
                    </div>
                  </mat-expansion-panel>
                </mat-accordion>
              </div>

              <!-- Difficult topics -->
              <div class="difficult-topics" *ngIf="script.qa_preparation?.difficult_topics?.length">
                <h2><mat-icon>warning</mat-icon> Sujets delicats</h2>
                <div class="topics-list">
                  <mat-card *ngFor="let topic of script.qa_preparation.difficult_topics" class="topic-card">
                    <h3>{{ topic.topic }}</h3>
                    <p>{{ topic.strategy }}</p>
                  </mat-card>
                </div>
              </div>
            </div>
          </mat-tab>

          <!-- Tab 4: Conseils -->
          <mat-tab>
            <ng-template mat-tab-label>
              <mat-icon>tips_and_updates</mat-icon>
              <span>Conseils</span>
            </ng-template>

            <div class="tab-content">
              <div class="tips-section" *ngIf="script.general_tips?.length">
                <h2><mat-icon>tips_and_updates</mat-icon> Conseils pratiques</h2>
                <div class="tips-list">
                  <div *ngFor="let tip of script.general_tips; let i = index" class="tip-item">
                    <div class="tip-icon"><mat-icon>check_circle</mat-icon></div>
                    <div class="tip-text">{{ tip }}</div>
                  </div>
                </div>
              </div>

              <!-- Agenda overview -->
              <div class="agenda-section" *ngIf="script.sections_overview?.length">
                <h2><mat-icon>event_note</mat-icon> Plan de la presentation</h2>
                <div class="agenda-timeline">
                  <div *ngFor="let item of script.sections_overview; let i = index" class="agenda-item">
                    <div class="agenda-dot"></div>
                    <div class="agenda-content">
                      <span class="agenda-title">{{ item.title }}</span>
                      <span class="agenda-duration">{{ item.duration }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </mat-tab>
        </mat-tab-group>
      </div>
    </div>

    <div *ngIf="loading" class="loading-container"><mat-spinner diameter="40"></mat-spinner></div>
  `,
  styles: [`
    .soutenance-container { max-width: 1100px; margin: 0 auto; padding: 16px; }
    .soutenance-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; flex-wrap: wrap; gap: 12px; }
    .header-left { display: flex; align-items: center; gap: 12px; }
    .header-left h1 { margin: 0; color: #1B3A5C; font-size: 22px; }
    .subtitle { color: #777; font-size: 13px; }
    .header-actions { display: flex; gap: 8px; }

    .empty-card { text-align: center; padding: 48px 24px; }
    .empty-card mat-icon { font-size: 64px; width: 64px; height: 64px; color: #ccc; }
    .empty-card h2 { color: #666; }
    .empty-card p { color: #999; max-width: 500px; margin: 12px auto; }

    /* Overview cards */
    .overview-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }
    .overview-card { text-align: center; padding: 20px 16px; }
    .overview-card mat-icon { font-size: 28px; width: 28px; height: 28px; margin-bottom: 8px; }
    .overview-value { font-size: 24px; font-weight: 700; }
    .overview-label { font-size: 12px; color: #888; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
    .duration-card mat-icon, .duration-card .overview-value { color: #1565c0; }
    .sections-card mat-icon, .sections-card .overview-value { color: #2e7d32; }
    .strengths-card mat-icon, .strengths-card .overview-value { color: #e65100; }
    .qa-card mat-icon, .qa-card .overview-value { color: #7b1fa2; }

    /* Tabs */
    .soutenance-tabs { margin-top: 8px; }
    .soutenance-tabs .mat-mdc-tab .mdc-tab__content { gap: 6px; }
    .tab-content { padding: 16px 0; }

    /* Script cards */
    .script-card { margin: 16px 0; padding: 24px; }
    .script-card-header { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
    .script-card-header h2 { margin: 0; font-size: 18px; color: #1B3A5C; }
    .script-card-header mat-icon { color: #2C5F8A; }
    .script-text { line-height: 1.8; color: #333; font-size: 14.5px; white-space: pre-wrap; }
    .intro-card { border-left: 4px solid #1565c0; }
    .closing-card { border-left: 4px solid #2e7d32; }

    /* Section panels */
    .section-panel { margin-bottom: 8px; }
    .section-number { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; background: #1B3A5C; color: white; border-radius: 50%; font-size: 13px; font-weight: 700; margin-right: 10px; }
    .section-content { padding: 8px 0; }

    .guide-block, .messages-block, .qa-block { margin-bottom: 20px; }
    .guide-block h3, .messages-block h3, .qa-block h3 { display: flex; align-items: center; gap: 8px; color: #1B3A5C; font-size: 15px; margin-bottom: 10px; }
    .guide-block h3 mat-icon, .messages-block h3 mat-icon, .qa-block h3 mat-icon { font-size: 20px; width: 20px; height: 20px; }
    .guide-text { background: #f5f7fa; padding: 16px; border-radius: 8px; line-height: 1.8; color: #333; font-size: 14px; white-space: pre-wrap; }

    .message-chips { display: flex; flex-wrap: wrap; gap: 8px; }
    .key-message { background: #e3f2fd; color: #1565c0; padding: 6px 14px; border-radius: 16px; font-size: 13px; font-weight: 500; }

    .qa-item { background: #fafafa; border-radius: 8px; padding: 12px 16px; margin-bottom: 8px; border-left: 3px solid #7b1fa2; }
    .qa-question { color: #333; font-size: 14px; margin-bottom: 6px; }
    .qa-answer { color: #555; font-size: 13px; }

    /* Key figures */
    .key-figures-section h2, .strengths-section h2, .expected-questions h2, .difficult-topics h2, .tips-section h2, .agenda-section h2 {
      display: flex; align-items: center; gap: 8px; color: #1B3A5C; font-size: 18px; margin-bottom: 16px;
    }
    .figures-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
    .figure-card { text-align: center; padding: 24px 16px; }
    .figure-value { font-size: 32px; font-weight: 700; color: #1565c0; }
    .figure-label { font-size: 13px; color: #666; margin-top: 8px; }

    /* Strengths */
    .strengths-list { display: flex; flex-direction: column; gap: 10px; }
    .strength-item { display: flex; align-items: flex-start; gap: 12px; padding: 14px 18px; background: #f5f7fa; border-radius: 8px; }
    .strength-number { display: flex; align-items: center; justify-content: center; min-width: 32px; height: 32px; background: #e65100; color: white; border-radius: 50%; font-weight: 700; font-size: 14px; }
    .strength-text { flex: 1; line-height: 1.6; font-size: 14px; color: #333; padding-top: 4px; }

    /* Q&A panel */
    .qa-panel { margin-bottom: 6px; }
    .qa-number { display: inline-flex; align-items: center; justify-content: center; width: 30px; height: 30px; background: #7b1fa2; color: white; border-radius: 50%; font-size: 12px; font-weight: 700; margin-right: 10px; }
    .qa-answer-block { padding: 8px 0; }
    .qa-answer-block h4 { color: #1B3A5C; margin-bottom: 8px; }
    .qa-answer-block p { line-height: 1.7; color: #333; font-size: 14px; }
    .qa-tips { display: flex; align-items: flex-start; gap: 8px; margin-top: 12px; padding: 12px; background: #fff8e1; border-radius: 8px; color: #e65100; font-size: 13px; }
    .qa-tips mat-icon { font-size: 18px; width: 18px; height: 18px; color: #ffa000; }

    /* Difficult topics */
    .topics-list { display: flex; flex-direction: column; gap: 10px; }
    .topic-card { padding: 16px 20px; border-left: 4px solid #ff9800; }
    .topic-card h3 { margin: 0 0 8px 0; color: #e65100; font-size: 15px; }
    .topic-card p { margin: 0; line-height: 1.6; color: #555; font-size: 14px; }

    /* Tips */
    .tips-list { display: flex; flex-direction: column; gap: 10px; }
    .tip-item { display: flex; gap: 10px; padding: 12px 16px; background: #e8f5e9; border-radius: 8px; }
    .tip-icon mat-icon { color: #2e7d32; font-size: 20px; width: 20px; height: 20px; }
    .tip-text { flex: 1; line-height: 1.6; color: #333; font-size: 14px; }

    /* Agenda timeline */
    .agenda-timeline { position: relative; padding-left: 24px; border-left: 2px solid #1B3A5C; }
    .agenda-item { position: relative; padding: 12px 0 12px 16px; }
    .agenda-dot { position: absolute; left: -31px; top: 16px; width: 12px; height: 12px; background: #2C5F8A; border-radius: 50%; border: 2px solid white; }
    .agenda-content { display: flex; justify-content: space-between; align-items: center; }
    .agenda-title { font-size: 14px; color: #333; font-weight: 500; }
    .agenda-duration { font-size: 12px; color: #888; background: #f5f5f5; padding: 2px 10px; border-radius: 10px; }

    .loading-container { display: flex; justify-content: center; padding: 48px; }

    @media (max-width: 768px) {
      .overview-row { grid-template-columns: repeat(2, 1fr); }
      .soutenance-header { flex-direction: column; align-items: flex-start; }
    }
    @media print {
      .header-actions { display: none !important; }
      .soutenance-tabs .mat-mdc-tab-header { display: none !important; }
    }
  `],
})
export class SoutenanceComponent implements OnInit {
  projectId = '';
  script: SoutenanceScript | null = null;
  loading = true;
  downloadingPptx = false;

  constructor(
    private route: ActivatedRoute,
    private api: ApiService,
    private snackBar: MatSnackBar,
  ) {}

  ngOnInit(): void {
    this.projectId = this.route.snapshot.paramMap.get('projectId') || '';
    this.loadScript();
  }

  loadScript(): void {
    this.loading = true;
    this.api.getSoutenanceScript(this.projectId).subscribe({
      next: (data) => {
        this.script = data;
        this.loading = false;
      },
      error: () => {
        this.script = null;
        this.loading = false;
      },
    });
  }

  downloadPptx(): void {
    this.downloadingPptx = true;
    this.api.downloadSoutenancePptx(this.projectId).subscribe({
      next: (blob) => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `soutenance_${this.script?.rfp_reference || 'presentation'}.pptx`;
        a.click();
        window.URL.revokeObjectURL(url);
        this.downloadingPptx = false;
        this.snackBar.open('PowerPoint telecharge', 'OK', { duration: 3000 });
      },
      error: () => {
        this.downloadingPptx = false;
        this.snackBar.open('Erreur telechargement PowerPoint', 'OK', { duration: 5000 });
      },
    });
  }

  printScript(): void {
    window.print();
  }
}
