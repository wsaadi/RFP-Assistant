import { Component, OnInit, ViewEncapsulation } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ApiService } from '../../services/api.service';
import { renderMarkdown } from '../../services/markdown.service';
import { DocumentPreview, PreviewChapter } from '../../models/report.model';

@Component({
  selector: 'app-preview',
  standalone: true,
  imports: [
    CommonModule, RouterLink, MatCardModule, MatButtonModule, MatIconModule,
    MatProgressSpinnerModule, MatButtonToggleModule, MatTooltipModule,
  ],
  encapsulation: ViewEncapsulation.None,
  template: `
    <div class="preview-container" *ngIf="preview">
      <div class="preview-header no-print">
        <button mat-icon-button [routerLink]="['/project', projectId]"><mat-icon>arrow_back</mat-icon></button>
        <h1>Apercu du document</h1>

        <mat-button-toggle-group [(value)]="viewMode" (change)="onViewModeChange($event.value)" class="view-mode-toggle">
          <mat-button-toggle value="final" matTooltip="Contenu final avec les vraies valeurs">
            <mat-icon>visibility</mat-icon> Final
          </mat-button-toggle>
          <mat-button-toggle value="anonymized" matTooltip="Ce que l'IA Mistral voit (donnees sensibles masquees)">
            <mat-icon>security</mat-icon> Vue IA
          </mat-button-toggle>
        </mat-button-toggle-group>

        <button mat-raised-button color="primary" (click)="printPreview()">
          <mat-icon>print</mat-icon> Imprimer
        </button>
      </div>

      <div *ngIf="viewMode === 'anonymized'" class="anon-banner no-print">
        <mat-icon>security</mat-icon>
        <span>Vue anonymisee — C'est ce que l'IA Mistral voit. Les donnees sensibles sont remplacees par des placeholders.</span>
      </div>

      <div class="document-preview" [class.anon-mode]="viewMode === 'anonymized'">
        <!-- Cover page -->
        <div class="page cover-page">
          <h1 class="doc-title">REPONSE A L'APPEL D'OFFRES</h1>
          <h2 *ngIf="currentPreview.rfp_reference">Reference: {{ currentPreview.rfp_reference }}</h2>
          <h2 class="project-name">{{ currentPreview.project_name }}</h2>
          <div class="separator"></div>
          <p *ngIf="currentPreview.client_name">Client: {{ currentPreview.client_name }}</p>
          <p class="confidential">DOCUMENT CONFIDENTIEL</p>
        </div>

        <!-- TOC -->
        <div class="page toc-page">
          <h2>SOMMAIRE</h2>
          <div *ngFor="let ch of currentPreview.chapters" class="toc-entry" [class.toc-sub]="ch.level > 1">
            <span>{{ ch.numbering }} {{ ch.title }}</span>
            <ng-container *ngIf="ch.children?.length">
              <div *ngFor="let sub of ch.children" class="toc-entry toc-sub">
                <span>{{ sub.numbering }} {{ sub.title }}</span>
              </div>
            </ng-container>
          </div>
        </div>

        <!-- Chapters -->
        <ng-container *ngFor="let ch of currentPreview.chapters">
          <div class="page">
            <h2 class="chapter-title">{{ ch.numbering }} {{ ch.title }}</h2>
            <div class="chapter-content" *ngIf="ch.content" [innerHTML]="renderMarkdown(ch.content)"></div>
            <p *ngIf="!ch.content" class="empty-content">[Section a completer]</p>

            <ng-container *ngFor="let sub of ch.children">
              <h3 class="sub-title">{{ sub.numbering }} {{ sub.title }}</h3>
              <div class="chapter-content" *ngIf="sub.content" [innerHTML]="renderMarkdown(sub.content)"></div>
              <p *ngIf="!sub.content" class="empty-content">[Section a completer]</p>
            </ng-container>
          </div>
        </ng-container>
      </div>
    </div>

    <div *ngIf="loading" class="loading-container"><mat-spinner diameter="40"></mat-spinner></div>
  `,
  styles: [`
    .preview-container { max-width: 900px; margin: 0 auto; }
    .preview-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
    .preview-header h1 { flex: 1; margin: 0; color: #1B3A5C; }
    .view-mode-toggle .mat-button-toggle-label-content { display: flex; align-items: center; gap: 4px; font-size: 13px; }
    .view-mode-toggle mat-icon { font-size: 18px; width: 18px; height: 18px; }
    .anon-banner { display: flex; align-items: center; gap: 8px; padding: 10px 16px; margin-bottom: 12px; background: #e8f5e9; border: 1px solid #a5d6a7; border-radius: 8px; color: #2e7d32; font-size: 13px; }
    .anon-banner mat-icon { color: #2e7d32; }
    .document-preview { background: white; box-shadow: 0 2px 8px rgba(0,0,0,0.1); border-radius: 4px; overflow: hidden; }
    .document-preview.anon-mode { border: 2px solid #a5d6a7; }
    .page { padding: 48px 56px; min-height: 600px; border-bottom: 1px solid #e0e0e0; }
    .cover-page { text-align: center; display: flex; flex-direction: column; justify-content: center; align-items: center; min-height: 700px; background: linear-gradient(180deg, #f8fafd 0%, #ffffff 100%); }
    .doc-title { font-size: 28px; color: #1B3A5C; letter-spacing: 0.5px; }
    .project-name { font-size: 22px; color: #2C5F8A; }
    .separator { width: 200px; height: 2px; background: #2C5F8A; margin: 24px 0; }
    .confidential { color: #990000; font-weight: bold; font-size: 12px; margin-top: 48px; }
    .toc-page h2 { color: #1B3A5C; margin-bottom: 24px; border-bottom: 2px solid #2C5F8A; padding-bottom: 8px; }
    .toc-entry { padding: 8px 0; border-bottom: 1px dotted #ddd; font-size: 15px; color: #333; }
    .toc-sub { padding-left: 28px; font-size: 14px; color: #555; }
    .chapter-title { color: #1B3A5C; font-size: 20px; border-bottom: 2px solid #2C5F8A; padding-bottom: 8px; margin-bottom: 16px; }
    .sub-title { color: #2C5F8A; font-size: 17px; margin-top: 28px; margin-bottom: 12px; padding-bottom: 4px; border-bottom: 1px solid #e0e0e0; }
    .chapter-content { line-height: 1.7; font-size: 14px; color: #333; }
    .chapter-content p { margin: 0 0 12px 0; line-height: 1.7; text-align: justify; }
    .chapter-content h2, .chapter-content h3 { font-size: 17px; font-weight: 700; color: #1B3A5C; margin: 24px 0 10px 0; padding-bottom: 4px; border-bottom: 1px solid #e0e0e0; }
    .chapter-content h2:first-child, .chapter-content h3:first-child { margin-top: 0; }
    .chapter-content h4 { font-size: 15px; font-weight: 600; color: #2C5F8A; margin: 18px 0 8px 0; }
    .chapter-content h5 { font-size: 14px; font-weight: 600; color: #37474f; margin: 14px 0 6px 0; }
    .chapter-content ul, .chapter-content ol { margin: 6px 0 12px 0; padding-left: 28px; }
    .chapter-content ul { list-style-type: disc; }
    .chapter-content ul ul { list-style-type: circle; margin: 2px 0; }
    .chapter-content ol { list-style-type: decimal; }
    .chapter-content li { margin-bottom: 4px; line-height: 1.6; }
    .chapter-content strong { color: #1B3A5C; }
    .chapter-content em { color: #555; }
    .chapter-content hr { border: none; border-top: 1px solid #ccc; margin: 20px 0; }
    .chapter-content code { background: #e8eaf6; padding: 1px 5px; border-radius: 3px; font-size: 13px; }
    .chapter-content .table-wrap { overflow-x: auto; margin: 16px 0; }
    .chapter-content table { border-collapse: collapse; width: 100%; font-size: 14px; }
    .chapter-content th, .chapter-content td { border: 1px solid #ccc; padding: 10px 12px; text-align: left; }
    .chapter-content th { background: #e3f2fd; color: #1B3A5C; font-weight: 600; }
    .chapter-content tr:nth-child(even) td { background: #fafafa; }
    .empty-content { color: #999; font-style: italic; }
    .loading-container { display: flex; justify-content: center; padding: 48px; }
    @media print { .no-print { display: none !important; } .page { border: none; page-break-after: always; } }
  `],
})
export class PreviewComponent implements OnInit {
  projectId = '';
  preview: DocumentPreview | null = null;
  anonPreview: DocumentPreview | null = null;
  loading = true;
  viewMode: 'final' | 'anonymized' = 'final';

  constructor(private route: ActivatedRoute, private api: ApiService) {}

  get currentPreview(): DocumentPreview {
    return (this.viewMode === 'anonymized' && this.anonPreview) ? this.anonPreview : this.preview!;
  }

  ngOnInit(): void {
    this.projectId = this.route.snapshot.paramMap.get('projectId') || '';
    this.api.getPreview(this.projectId).subscribe({
      next: (p) => { this.preview = p; this.loading = false; },
      error: () => { this.loading = false; },
    });
  }

  onViewModeChange(mode: 'final' | 'anonymized'): void {
    this.viewMode = mode;
    if (mode === 'anonymized' && !this.anonPreview) {
      this.loading = true;
      this.api.getPreview(this.projectId, true).subscribe({
        next: (p) => { this.anonPreview = p; this.loading = false; },
        error: () => { this.loading = false; },
      });
    }
  }

  printPreview(): void {
    window.print();
  }

  renderMarkdown = renderMarkdown;
}
