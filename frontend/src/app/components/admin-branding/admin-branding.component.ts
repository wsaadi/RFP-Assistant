import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatDividerModule } from '@angular/material/divider';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { BrandingService, BrandingSettings } from '../../services/branding.service';

@Component({
  selector: 'app-admin-branding',
  standalone: true,
  imports: [
    CommonModule, FormsModule, RouterLink,
    MatCardModule, MatButtonModule, MatIconModule, MatInputModule,
    MatSnackBarModule, MatDividerModule, MatTooltipModule, MatProgressSpinnerModule,
  ],
  template: `
    <div class="page-container">
      <div class="page-header">
        <button mat-icon-button routerLink="/admin/users"><mat-icon>arrow_back</mat-icon></button>
        <h1>Personnalisation de l'application</h1>
      </div>

      <!-- App Name -->
      <mat-card class="config-card">
        <h3><mat-icon>badge</mat-icon> Nom de l'application</h3>
        <p class="hint">Ce nom apparaît dans la barre de navigation et la page de connexion.</p>
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Nom de l'application</mat-label>
          <input matInput [(ngModel)]="appName" placeholder="RFP Assistant" maxlength="255">
          <mat-icon matSuffix>edit</mat-icon>
        </mat-form-field>
        <div class="form-actions">
          <button mat-raised-button color="primary" (click)="saveSettings()" [disabled]="saving">
            <mat-icon>save</mat-icon> Enregistrer le nom
          </button>
        </div>
      </mat-card>

      <!-- Logo -->
      <mat-card class="config-card">
        <h3><mat-icon>image</mat-icon> Logo</h3>
        <p class="hint">Le logo apparaît en haut à gauche de l'application. Formats acceptés : PNG, JPG, SVG, WebP (max 2 Mo).</p>

        <div class="upload-zone">
          <div class="preview-area" *ngIf="branding.has_logo">
            <img [src]="branding.logo_url + '?v=' + cacheBreaker" alt="Logo actuel" class="logo-preview">
            <button mat-icon-button color="warn" (click)="removeLogo()" matTooltip="Supprimer le logo">
              <mat-icon>delete</mat-icon>
            </button>
          </div>
          <div class="preview-area empty" *ngIf="!branding.has_logo">
            <mat-icon class="placeholder-icon">add_photo_alternate</mat-icon>
            <span>Aucun logo configuré</span>
          </div>

          <div class="upload-actions">
            <input type="file" #logoInput accept="image/png,image/jpeg,image/svg+xml,image/webp"
                   (change)="onLogoSelected($event)" style="display:none">
            <button mat-raised-button color="primary" (click)="logoInput.click()" [disabled]="uploadingLogo">
              <mat-spinner *ngIf="uploadingLogo" diameter="18"></mat-spinner>
              <mat-icon *ngIf="!uploadingLogo">upload</mat-icon>
              {{ uploadingLogo ? 'Envoi...' : (branding.has_logo ? 'Changer le logo' : 'Importer un logo') }}
            </button>
          </div>
        </div>
      </mat-card>

      <!-- Favicon -->
      <mat-card class="config-card">
        <h3><mat-icon>tab</mat-icon> Favicon</h3>
        <p class="hint">L'icône qui apparaît dans l'onglet du navigateur. Formats acceptés : PNG, ICO, SVG, WebP (max 2 Mo).</p>

        <div class="upload-zone">
          <div class="preview-area" *ngIf="branding.has_favicon">
            <img [src]="branding.favicon_url + '?v=' + cacheBreaker" alt="Favicon actuel" class="favicon-preview">
            <button mat-icon-button color="warn" (click)="removeFavicon()" matTooltip="Supprimer le favicon">
              <mat-icon>delete</mat-icon>
            </button>
          </div>
          <div class="preview-area empty" *ngIf="!branding.has_favicon">
            <mat-icon class="placeholder-icon">add_photo_alternate</mat-icon>
            <span>Aucun favicon configuré</span>
          </div>

          <div class="upload-actions">
            <input type="file" #faviconInput accept="image/png,image/x-icon,image/svg+xml,image/webp,image/vnd.microsoft.icon"
                   (change)="onFaviconSelected($event)" style="display:none">
            <button mat-raised-button color="primary" (click)="faviconInput.click()" [disabled]="uploadingFavicon">
              <mat-spinner *ngIf="uploadingFavicon" diameter="18"></mat-spinner>
              <mat-icon *ngIf="!uploadingFavicon">upload</mat-icon>
              {{ uploadingFavicon ? 'Envoi...' : (branding.has_favicon ? 'Changer le favicon' : 'Importer un favicon') }}
            </button>
          </div>
        </div>
      </mat-card>

      <!-- Preview -->
      <mat-card class="config-card preview-card">
        <h3><mat-icon>preview</mat-icon> Aperçu</h3>
        <div class="preview-toolbar">
          <div class="preview-toolbar-inner">
            <img *ngIf="branding.has_logo" [src]="branding.logo_url + '?v=' + cacheBreaker"
                 alt="Logo" class="preview-toolbar-logo">
            <mat-icon *ngIf="!branding.has_logo" class="preview-toolbar-icon">description</mat-icon>
            <span class="preview-toolbar-title">{{ appName || 'RFP Assistant' }}</span>
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
    .hint { color: #666; font-size: 14px; margin: 0 0 16px; }
    .full-width { width: 100%; }
    .form-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 8px; }

    .upload-zone { display: flex; flex-direction: column; gap: 16px; align-items: center; }
    .preview-area {
      display: flex; align-items: center; gap: 12px;
      padding: 16px; border: 2px dashed #e0e0e0; border-radius: 12px;
      min-height: 80px; justify-content: center; width: 100%;
    }
    .preview-area.empty {
      flex-direction: column; color: #999;
    }
    .placeholder-icon { font-size: 40px; width: 40px; height: 40px; color: #ccc; }
    .logo-preview { max-height: 80px; max-width: 300px; object-fit: contain; }
    .favicon-preview { max-height: 48px; max-width: 48px; object-fit: contain; }
    .upload-actions { display: flex; gap: 8px; }

    /* Preview toolbar mock */
    .preview-card { background: #fafafa; }
    .preview-toolbar {
      background: #1B3A5C; border-radius: 8px; padding: 12px 20px;
      color: white; display: flex; align-items: center;
    }
    .preview-toolbar-inner { display: flex; align-items: center; gap: 10px; }
    .preview-toolbar-logo { height: 32px; max-width: 120px; object-fit: contain; filter: brightness(0) invert(1); }
    .preview-toolbar-icon { font-size: 28px; width: 28px; height: 28px; }
    .preview-toolbar-title { font-size: 16px; font-weight: 500; }
  `],
})
export class AdminBrandingComponent implements OnInit {
  appName = 'RFP Assistant';
  branding: BrandingSettings = {
    app_name: 'RFP Assistant',
    has_logo: false,
    has_favicon: false,
    primary_color: '#1B3A5C',
    logo_url: '',
    favicon_url: '',
  };
  saving = false;
  uploadingLogo = false;
  uploadingFavicon = false;
  cacheBreaker = Date.now();

  constructor(
    private brandingService: BrandingService,
    private snackBar: MatSnackBar,
  ) {}

  ngOnInit(): void {
    this.brandingService.branding$.subscribe((b) => {
      this.branding = b;
      this.appName = b.app_name;
      this.cacheBreaker = Date.now();
    });
  }

  saveSettings(): void {
    this.saving = true;
    this.brandingService.updateSettings(this.appName, this.branding.primary_color).subscribe({
      next: () => {
        this.snackBar.open('Paramètres enregistrés', 'OK', { duration: 3000 });
        this.saving = false;
      },
      error: (err) => {
        this.snackBar.open(err.error?.detail || 'Erreur de sauvegarde', 'OK', { duration: 5000 });
        this.saving = false;
      },
    });
  }

  onLogoSelected(event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    this.uploadingLogo = true;
    this.brandingService.uploadLogo(file).subscribe({
      next: () => {
        this.snackBar.open('Logo mis à jour', 'OK', { duration: 3000 });
        this.uploadingLogo = false;
      },
      error: (err) => {
        this.snackBar.open(err.error?.detail || 'Erreur lors de l\'envoi', 'OK', { duration: 5000 });
        this.uploadingLogo = false;
      },
    });
  }

  onFaviconSelected(event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    this.uploadingFavicon = true;
    this.brandingService.uploadFavicon(file).subscribe({
      next: () => {
        this.snackBar.open('Favicon mis à jour', 'OK', { duration: 3000 });
        this.uploadingFavicon = false;
      },
      error: (err) => {
        this.snackBar.open(err.error?.detail || 'Erreur lors de l\'envoi', 'OK', { duration: 5000 });
        this.uploadingFavicon = false;
      },
    });
  }

  removeLogo(): void {
    this.brandingService.deleteLogo().subscribe({
      next: () => this.snackBar.open('Logo supprimé', 'OK', { duration: 3000 }),
      error: () => this.snackBar.open('Erreur lors de la suppression', 'OK', { duration: 5000 }),
    });
  }

  removeFavicon(): void {
    this.brandingService.deleteFavicon().subscribe({
      next: () => this.snackBar.open('Favicon supprimé', 'OK', { duration: 3000 }),
      error: () => this.snackBar.open('Erreur lors de la suppression', 'OK', { duration: 5000 }),
    });
  }
}
