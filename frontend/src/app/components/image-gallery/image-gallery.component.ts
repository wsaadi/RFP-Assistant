import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatSelectModule } from '@angular/material/select';
import { MatBadgeModule } from '@angular/material/badge';
import { MatMenuModule } from '@angular/material/menu';
import { Subscription, interval } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { ApiService } from '../../services/api.service';
import { DocumentImage, ImageAnalysisStatus, RFPProject } from '../../models/report.model';

interface CategoryDef {
  value: string;
  label: string;
  icon: string;
  color: string;
}

@Component({
  selector: 'app-image-gallery',
  standalone: true,
  imports: [
    CommonModule, FormsModule, RouterLink,
    MatCardModule, MatButtonModule, MatIconModule, MatChipsModule,
    MatCheckboxModule, MatProgressSpinnerModule, MatProgressBarModule,
    MatSnackBarModule, MatTooltipModule, MatSelectModule,
    MatBadgeModule, MatMenuModule,
  ],
  template: `
    <div class="page-container" *ngIf="project">
      <div class="page-header">
        <div class="header-left">
          <button mat-icon-button [routerLink]="['/project', projectId]">
            <mat-icon>arrow_back</mat-icon>
          </button>
          <div>
            <h1>Galerie d'images</h1>
            <span class="subtitle">{{ project.name }} - {{ images.length }} images uniques
              <span *ngIf="totalRawCount > images.length"> ({{ totalRawCount }} au total)</span>
            </span>
          </div>
        </div>
        <div class="header-actions">
          <button mat-raised-button color="primary"
            (click)="analyzeSelected()"
            [disabled]="selectedCount === 0 || analyzing"
            matTooltip="Lancer l'analyse Vision AI sur les images selectionnees">
            <mat-spinner *ngIf="analyzing" diameter="18"></mat-spinner>
            <mat-icon *ngIf="!analyzing">auto_fix_high</mat-icon>
            Analyser ({{ selectedCount }})
          </button>
        </div>
      </div>

      <!-- Analysis progress -->
      <mat-card *ngIf="analysisStatus && analysisStatus.status === 'running'" class="progress-card">
        <div class="progress-header">
          <mat-spinner diameter="20"></mat-spinner>
          <h3>Analyse Vision AI en cours...</h3>
        </div>
        <mat-progress-bar mode="determinate" [value]="analysisStatus.progress"></mat-progress-bar>
        <p class="progress-message">{{ analysisStatus.message }}</p>
      </mat-card>

      <mat-card *ngIf="analysisStatus && analysisStatus.status === 'completed'" class="success-card">
        <mat-icon>check_circle</mat-icon>
        <span>{{ analysisStatus.message }}</span>
        <button mat-icon-button (click)="analysisStatus = null"><mat-icon>close</mat-icon></button>
      </mat-card>

      <mat-card *ngIf="analysisStatus && analysisStatus.status === 'error'" class="error-card">
        <mat-icon>error_outline</mat-icon>
        <span>{{ analysisStatus.message }}</span>
        <button mat-icon-button (click)="analysisStatus = null"><mat-icon>close</mat-icon></button>
      </mat-card>

      <!-- Category filter chips -->
      <div class="filter-bar">
        <div class="filter-chips">
          <button mat-stroked-button
            [class.active]="activeFilter === 'all'"
            (click)="setFilter('all')">
            Toutes ({{ images.length }})
          </button>
          <button mat-stroked-button *ngFor="let cat of categories"
            [class.active]="activeFilter === cat.value"
            (click)="setFilter(cat.value)">
            <mat-icon [style.color]="cat.color" class="chip-icon">{{ cat.icon }}</mat-icon>
            {{ cat.label }} ({{ countByCategory(cat.value) }})
          </button>
        </div>
        <div class="filter-actions">
          <button mat-stroked-button (click)="selectAllVisible()" matTooltip="Selectionner toutes les images visibles">
            <mat-icon>select_all</mat-icon> Tout selectionner
          </button>
          <button mat-stroked-button (click)="deselectAllVisible()" matTooltip="Deselectionner toutes les images visibles">
            <mat-icon>deselect</mat-icon> Tout deselectionner
          </button>
          <button mat-stroked-button [matMenuTriggerFor]="batchCatMenu"
            [disabled]="selectedCount === 0"
            matTooltip="Changer la categorie des images selectionnees">
            <mat-icon>category</mat-icon> Categoriser ({{ selectedCount }})
          </button>
          <mat-menu #batchCatMenu="matMenu">
            <button mat-menu-item *ngFor="let cat of categories" (click)="batchSetCategory(cat.value)">
              <mat-icon [style.color]="cat.color">{{ cat.icon }}</mat-icon>
              {{ cat.label }}
            </button>
          </mat-menu>
        </div>
      </div>

      <!-- Loading state -->
      <div class="loading" *ngIf="loading">
        <mat-spinner diameter="40"></mat-spinner>
        <p>Chargement des images...</p>
      </div>

      <!-- Empty state -->
      <div class="empty-state" *ngIf="!loading && images.length === 0">
        <mat-icon>image_not_supported</mat-icon>
        <p>Aucune image extraite. Chargez des documents contenant des images (PDF, DOCX) pour les voir ici.</p>
      </div>

      <!-- Image grid -->
      <div class="image-grid" *ngIf="!loading && filteredImages.length > 0">
        <div class="image-card" *ngFor="let img of filteredImages"
          [class.selected]="img.selected"
          [class.analyzed]="img.analysis_status === 'completed'">
          <div class="image-select">
            <mat-checkbox
              [checked]="img.selected"
              (change)="toggleSelect(img, $event.checked)">
            </mat-checkbox>
          </div>
          <div class="image-thumb" (click)="toggleSelect(img, !img.selected)">
            <img [src]="getImageUrl(img.id)" [alt]="img.stored_filename"
              loading="lazy" (error)="onImageError($event)">
            <span class="occurrence-badge" *ngIf="img.occurrence_count > 1"
              [matTooltip]="getOccurrenceTooltip(img)">
              x{{ img.occurrence_count }}
            </span>
          </div>
          <div class="image-info">
            <div class="image-meta">
              <span class="image-dims">{{ img.width }}x{{ img.height }}</span>
              <span class="image-page" *ngIf="img.occurrence_count <= 1 && img.page_number > 0">p.{{ img.page_number }}</span>
              <span class="image-page" *ngIf="img.occurrence_count > 1">{{ getPagesList(img) }}</span>
            </div>
            <div class="image-category-row">
              <mat-select class="cat-select"
                [value]="img.image_category"
                (selectionChange)="changeCategory(img, $event.value)">
                <mat-option *ngFor="let cat of categories" [value]="cat.value">
                  {{ cat.label }}
                </mat-option>
              </mat-select>
            </div>
            <div class="image-status">
              <mat-icon *ngIf="img.analysis_status === 'completed'" class="status-done"
                matTooltip="Analyse terminee">check_circle</mat-icon>
              <mat-icon *ngIf="img.analysis_status === 'analyzing'" class="status-running"
                matTooltip="En cours d'analyse...">hourglass_top</mat-icon>
              <mat-icon *ngIf="img.analysis_status === 'failed'" class="status-error"
                matTooltip="Analyse echouee">error</mat-icon>
              <span *ngIf="img.analysis_status === 'completed' && img.image_type" class="analysis-type">
                {{ img.image_type }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .page-container { max-width: 1400px; margin: 0 auto; }

    .page-header {
      display: flex; justify-content: space-between; align-items: center;
      margin-bottom: 16px;
    }
    .header-left { display: flex; align-items: center; gap: 12px; }
    .header-left h1 { margin: 0; font-size: 22px; }
    .subtitle { color: #666; font-size: 13px; }
    .header-actions { display: flex; gap: 8px; align-items: center; }

    .progress-card, .success-card, .error-card {
      padding: 16px; margin-bottom: 16px; display: flex; align-items: center; gap: 12px;
    }
    .progress-card { flex-direction: column; align-items: stretch; }
    .progress-header { display: flex; align-items: center; gap: 8px; }
    .progress-header h3 { margin: 0; }
    .progress-message { margin: 8px 0 0; color: #666; font-size: 13px; }
    .success-card { background: #e8f5e9; }
    .success-card mat-icon { color: #2e7d32; }
    .success-card span { flex: 1; }
    .error-card { background: #fbe9e7; }
    .error-card mat-icon { color: #c62828; }
    .error-card span { flex: 1; }

    .filter-bar {
      display: flex; justify-content: space-between; align-items: center;
      margin-bottom: 16px; flex-wrap: wrap; gap: 8px;
    }
    .filter-chips { display: flex; gap: 6px; flex-wrap: wrap; }
    .filter-chips button { font-size: 12px; min-height: 32px; border-radius: 16px; }
    .filter-chips button.active { background: #1976d2; color: white; border-color: #1976d2; }
    .chip-icon { font-size: 16px; width: 16px; height: 16px; margin-right: 2px; }
    .filter-actions { display: flex; gap: 6px; flex-wrap: wrap; }
    .filter-actions button { font-size: 12px; min-height: 32px; }

    .loading { text-align: center; padding: 60px 0; }
    .loading p { color: #666; margin-top: 12px; }

    .empty-state { text-align: center; padding: 60px 0; color: #999; }
    .empty-state mat-icon { font-size: 64px; width: 64px; height: 64px; opacity: 0.4; }
    .empty-state p { margin-top: 12px; }

    .image-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
      gap: 12px;
    }

    .image-card {
      border: 2px solid #e0e0e0; border-radius: 8px;
      overflow: hidden; background: white;
      transition: border-color 0.2s, box-shadow 0.2s;
      position: relative;
    }
    .image-card:hover { border-color: #90caf9; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
    .image-card.selected { border-color: #1976d2; box-shadow: 0 0 0 1px #1976d2; }
    .image-card.analyzed { border-color: #81c784; }
    .image-card.selected.analyzed { border-color: #1976d2; }

    .image-select {
      position: absolute; top: 4px; left: 4px; z-index: 2;
      background: rgba(255,255,255,0.85); border-radius: 4px; padding: 0 2px;
    }

    .image-thumb {
      width: 100%; height: 160px; display: flex; align-items: center;
      justify-content: center; background: #fafafa; cursor: pointer;
      overflow: hidden; position: relative;
    }
    .image-thumb img {
      max-width: 100%; max-height: 100%; object-fit: contain;
    }
    .occurrence-badge {
      position: absolute; bottom: 4px; right: 4px;
      background: #1976d2; color: white; font-size: 11px; font-weight: 600;
      padding: 2px 6px; border-radius: 10px; line-height: 1.2;
    }

    .image-info { padding: 8px; }

    .image-meta {
      display: flex; justify-content: space-between; align-items: center;
      font-size: 11px; color: #999; margin-bottom: 4px;
    }

    .image-category-row { margin-bottom: 4px; }
    .cat-select { width: 100%; font-size: 12px; }
    ::ng-deep .cat-select .mat-mdc-select-trigger { min-height: 28px; }

    .image-status {
      display: flex; align-items: center; gap: 4px; font-size: 11px;
    }
    .status-done { color: #2e7d32; font-size: 16px; width: 16px; height: 16px; }
    .status-running { color: #f57c00; font-size: 16px; width: 16px; height: 16px; animation: spin 1.5s linear infinite; }
    .status-error { color: #c62828; font-size: 16px; width: 16px; height: 16px; }
    .analysis-type { color: #666; font-style: italic; }

    @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
  `],
})
export class ImageGalleryComponent implements OnInit, OnDestroy {
  projectId = '';
  project: RFPProject | null = null;
  images: DocumentImage[] = [];
  filteredImages: DocumentImage[] = [];
  loading = true;
  analyzing = false;
  activeFilter = 'all';
  analysisStatus: ImageAnalysisStatus | null = null;

  private pollSub: Subscription | null = null;

  categories: CategoryDef[] = [
    { value: 'icone', label: 'Icones', icon: 'interests', color: '#9e9e9e' },
    { value: 'logo', label: 'Logos', icon: 'branding_watermark', color: '#7b1fa2' },
    { value: 'schema', label: 'Schemas', icon: 'account_tree', color: '#1565c0' },
    { value: 'illustration', label: 'Illustrations', icon: 'image', color: '#2e7d32' },
    { value: 'photo', label: 'Photos', icon: 'photo_camera', color: '#e65100' },
    { value: 'graphique', label: 'Graphiques', icon: 'bar_chart', color: '#00838f' },
    { value: 'tableau', label: 'Tableaux', icon: 'table_chart', color: '#4e342e' },
    { value: 'autre', label: 'Autres', icon: 'help_outline', color: '#616161' },
  ];

  get selectedCount(): number {
    return this.images.filter(i => i.selected).length;
  }

  get totalRawCount(): number {
    return this.images.reduce((sum, img) => sum + (img.occurrence_count || 1), 0);
  }

  constructor(
    private route: ActivatedRoute,
    private api: ApiService,
    private snackBar: MatSnackBar,
  ) {}

  ngOnInit(): void {
    this.projectId = this.route.snapshot.paramMap.get('projectId') || '';
    this.loadData();
  }

  ngOnDestroy(): void {
    this.stopPolling();
  }

  loadData(): void {
    this.loading = true;
    this.api.getProject(this.projectId).subscribe({
      next: (p) => this.project = p,
      error: () => this.snackBar.open('Erreur chargement projet', 'OK', { duration: 3000 }),
    });
    this.api.getProjectImages(this.projectId).subscribe({
      next: (imgs) => {
        this.images = imgs;
        this.applyFilter();
        this.loading = false;
      },
      error: () => {
        this.loading = false;
        this.snackBar.open('Erreur chargement images', 'OK', { duration: 3000 });
      },
    });
  }

  getImageUrl(imageId: string): string {
    return this.api.getImageUrl(imageId);
  }

  onImageError(event: Event): void {
    (event.target as HTMLImageElement).src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><text x="10" y="50" fill="grey">?</text></svg>';
  }

  getOccurrenceTooltip(img: DocumentImage): string {
    if (!img.occurrences?.length) return '';
    const pages = img.occurrences
      .map(o => o.page_number)
      .filter(p => p > 0)
      .sort((a, b) => a - b);
    if (pages.length === 0) return `${img.occurrence_count} occurrences`;
    return `${img.occurrence_count} occurrences (pages ${pages.join(', ')})`;
  }

  getPagesList(img: DocumentImage): string {
    if (!img.occurrences?.length) return '';
    const pages = [...new Set(
      img.occurrences
        .map(o => o.page_number)
        .filter(p => p > 0)
    )].sort((a, b) => a - b);
    if (pages.length === 0) return '';
    if (pages.length <= 4) return 'p.' + pages.join(', ');
    return `p.${pages[0]}...${pages[pages.length - 1]}`;
  }

  // ── Filtering ──

  setFilter(filter: string): void {
    this.activeFilter = filter;
    this.applyFilter();
  }

  applyFilter(): void {
    if (this.activeFilter === 'all') {
      this.filteredImages = [...this.images];
    } else {
      this.filteredImages = this.images.filter(i => i.image_category === this.activeFilter);
    }
  }

  countByCategory(cat: string): number {
    return this.images.filter(i => i.image_category === cat).length;
  }

  // ── Selection ──

  toggleSelect(img: DocumentImage, selected: boolean): void {
    img.selected = selected;
    const ids = img.duplicate_ids?.length > 1 ? img.duplicate_ids : [img.id];
    this.api.batchUpdateImages(this.projectId, ids, { selected }).subscribe();
  }

  selectAllVisible(): void {
    const ids = this.filteredImages.flatMap(i => i.duplicate_ids?.length ? i.duplicate_ids : [i.id]);
    this.filteredImages.forEach(i => i.selected = true);
    this.api.batchUpdateImages(this.projectId, ids, { selected: true }).subscribe();
  }

  deselectAllVisible(): void {
    const ids = this.filteredImages.flatMap(i => i.duplicate_ids?.length ? i.duplicate_ids : [i.id]);
    this.filteredImages.forEach(i => i.selected = false);
    this.api.batchUpdateImages(this.projectId, ids, { selected: false }).subscribe();
  }

  // ── Category change ──

  changeCategory(img: DocumentImage, category: string): void {
    img.image_category = category;
    const ids = img.duplicate_ids?.length > 1 ? img.duplicate_ids : [img.id];
    this.api.batchUpdateImages(this.projectId, ids, { image_category: category }).subscribe();
  }

  batchSetCategory(category: string): void {
    const selected = this.images.filter(i => i.selected);
    if (selected.length === 0) return;

    const allIds = selected.flatMap(i => i.duplicate_ids?.length ? i.duplicate_ids : [i.id]);
    selected.forEach(i => i.image_category = category);
    this.applyFilter();

    this.api.batchUpdateImages(this.projectId, allIds, { image_category: category }).subscribe({
      next: (res) => this.snackBar.open(
        `${res.updated} images recategorisees`, 'OK', { duration: 2000 }
      ),
    });
  }

  // ── Analysis ──

  analyzeSelected(): void {
    // Only send representative IDs (no need to analyze same image twice)
    const selectedIds = this.images.filter(i => i.selected).map(i => i.id);
    if (selectedIds.length === 0) return;

    this.analyzing = true;
    this.images.filter(i => i.selected).forEach(i => i.analysis_status = 'analyzing');

    this.api.analyzeImages(this.projectId, selectedIds).subscribe({
      next: () => {
        this.startPolling();
      },
      error: (err) => {
        this.analyzing = false;
        this.snackBar.open('Erreur lancement analyse', 'OK', { duration: 3000 });
      },
    });
  }

  private startPolling(): void {
    this.stopPolling();
    this.pollSub = interval(3000).pipe(
      switchMap(() => this.api.getImageAnalysisStatus(this.projectId))
    ).subscribe({
      next: (status) => {
        this.analysisStatus = status;
        if (status.status === 'completed' || status.status === 'error') {
          this.analyzing = false;
          this.stopPolling();
          // Reload images to get updated analysis results
          this.api.getProjectImages(this.projectId).subscribe({
            next: (imgs) => {
              this.images = imgs;
              this.applyFilter();
            },
          });
        }
      },
    });
  }

  private stopPolling(): void {
    if (this.pollSub) {
      this.pollSub.unsubscribe();
      this.pollSub = null;
    }
  }
}
