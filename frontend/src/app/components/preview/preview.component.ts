import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService } from '../../services/api.service';
import { DocumentPreview, PreviewChapter } from '../../models/report.model';

@Component({
  selector: 'app-preview',
  standalone: true,
  imports: [CommonModule, RouterLink, MatCardModule, MatButtonModule, MatIconModule, MatProgressSpinnerModule],
  template: `
    <div class="preview-container" *ngIf="preview">
      <div class="preview-header no-print">
        <button mat-icon-button [routerLink]="['/project', projectId]"><mat-icon>arrow_back</mat-icon></button>
        <h1>Aperçu du document</h1>
        <button mat-raised-button color="primary" (click)="printPreview()">
          <mat-icon>print</mat-icon> Imprimer
        </button>
      </div>

      <div class="document-preview">
        <!-- Cover page -->
        <div class="page cover-page">
          <h1 class="doc-title">RÉPONSE À L'APPEL D'OFFRES</h1>
          <h2 *ngIf="preview.rfp_reference">Référence: {{ preview.rfp_reference }}</h2>
          <h2 class="project-name">{{ preview.project_name }}</h2>
          <div class="separator"></div>
          <p *ngIf="preview.client_name">Client: {{ preview.client_name }}</p>
          <p class="confidential">DOCUMENT CONFIDENTIEL</p>
        </div>

        <!-- TOC -->
        <div class="page toc-page">
          <h2>SOMMAIRE</h2>
          <div *ngFor="let ch of preview.chapters" class="toc-entry" [class.toc-sub]="ch.level > 1">
            <span>{{ ch.numbering }} {{ ch.title }}</span>
            <ng-container *ngIf="ch.children?.length">
              <div *ngFor="let sub of ch.children" class="toc-entry toc-sub">
                <span>{{ sub.numbering }} {{ sub.title }}</span>
              </div>
            </ng-container>
          </div>
        </div>

        <!-- Chapters -->
        <ng-container *ngFor="let ch of preview.chapters">
          <div class="page">
            <h2 class="chapter-title">{{ ch.numbering }} {{ ch.title }}</h2>
            <div class="chapter-content" *ngIf="ch.content">
              <p *ngFor="let para of ch.content.split('\\n\\n')">{{ para }}</p>
            </div>
            <p *ngIf="!ch.content" class="empty-content">[Section à compléter]</p>

            <ng-container *ngFor="let sub of ch.children">
              <h3 class="sub-title">{{ sub.numbering }} {{ sub.title }}</h3>
              <div class="chapter-content" *ngIf="sub.content">
                <p *ngFor="let para of sub.content.split('\\n\\n')">{{ para }}</p>
              </div>
              <p *ngIf="!sub.content" class="empty-content">[Section à compléter]</p>
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
    .document-preview { background: white; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
    .page { padding: 48px; min-height: 600px; border-bottom: 2px dashed #ddd; }
    .cover-page { text-align: center; display: flex; flex-direction: column; justify-content: center; align-items: center; min-height: 700px; }
    .doc-title { font-size: 28px; color: #1B3A5C; }
    .project-name { font-size: 22px; color: #2C5F8A; }
    .separator { width: 200px; height: 2px; background: #2C5F8A; margin: 24px 0; }
    .confidential { color: #990000; font-weight: bold; font-size: 12px; margin-top: 48px; }
    .toc-page h2 { color: #1B3A5C; margin-bottom: 24px; }
    .toc-entry { padding: 6px 0; border-bottom: 1px dotted #ddd; }
    .toc-sub { padding-left: 24px; font-size: 14px; }
    .chapter-title { color: #1B3A5C; font-size: 20px; border-bottom: 2px solid #2C5F8A; padding-bottom: 8px; }
    .sub-title { color: #2C5F8A; font-size: 16px; margin-top: 24px; }
    .chapter-content p { text-indent: 1em; line-height: 1.6; text-align: justify; }
    .empty-content { color: #999; font-style: italic; }
    .loading-container { display: flex; justify-content: center; padding: 48px; }
    @media print { .no-print { display: none !important; } .page { border: none; page-break-after: always; } }
  `],
})
export class PreviewComponent implements OnInit {
  projectId = '';
  preview: DocumentPreview | null = null;
  loading = true;

  constructor(private route: ActivatedRoute, private api: ApiService) {}

  ngOnInit(): void {
    this.projectId = this.route.snapshot.paramMap.get('projectId') || '';
    this.api.getPreview(this.projectId).subscribe({
      next: (p) => { this.preview = p; this.loading = false; },
      error: () => { this.loading = false; },
    });
  }

  printPreview(): void {
    window.print();
  }
}
