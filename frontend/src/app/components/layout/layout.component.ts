import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatDividerModule } from '@angular/material/divider';
import { MatTooltipModule } from '@angular/material/tooltip';
import { AuthService } from '../../services/auth.service';
import { BrandingService, BrandingSettings } from '../../services/branding.service';
import { OnboardingGuideComponent } from '../onboarding-guide/onboarding-guide.component';

@Component({
  selector: 'app-layout',
  standalone: true,
  imports: [
    CommonModule, RouterOutlet, RouterLink, RouterLinkActive,
    MatToolbarModule, MatButtonModule, MatIconModule, MatMenuModule, MatDividerModule,
    MatTooltipModule, OnboardingGuideComponent,
  ],
  template: `
    <mat-toolbar color="primary" class="toolbar">
      <a routerLink="/workspaces" class="logo-link">
        <img *ngIf="branding.has_logo" [src]="branding.logo_url + '?v=' + cacheBreaker"
             alt="Logo" class="toolbar-logo">
        <mat-icon *ngIf="!branding.has_logo" class="toolbar-logo-icon">description</mat-icon>
        <span class="app-title">{{ branding.app_name || 'RFP Assistant' }}</span>
      </a>

      <span class="spacer"></span>

      <button mat-icon-button routerLink="/workspaces" matTooltip="Workspaces">
        <mat-icon>workspaces</mat-icon>
      </button>

      <button mat-icon-button *ngIf="isAdmin" [matMenuTriggerFor]="adminMenu" matTooltip="Administration">
        <mat-icon>admin_panel_settings</mat-icon>
      </button>

      <mat-menu #adminMenu="matMenu">
        <button mat-menu-item routerLink="/admin/users">
          <mat-icon>people</mat-icon>
          <span>Utilisateurs</span>
        </button>
        <button mat-menu-item routerLink="/admin/branding">
          <mat-icon>palette</mat-icon>
          <span>Personnalisation</span>
        </button>
      </mat-menu>

      <button mat-icon-button [matMenuTriggerFor]="userMenu">
        <mat-icon>account_circle</mat-icon>
      </button>

      <mat-menu #userMenu="matMenu">
        <div class="user-info-menu">
          <strong>{{ username }}</strong>
          <span class="role-badge">{{ userRole }}</span>
        </div>
        <mat-divider></mat-divider>
        <button mat-menu-item (click)="logout()">
          <mat-icon>logout</mat-icon>
          <span>Se déconnecter</span>
        </button>
      </mat-menu>
    </mat-toolbar>

    <main class="main-content">
      <router-outlet></router-outlet>
    </main>

    <app-onboarding-guide></app-onboarding-guide>
  `,
  styles: [`
    .toolbar { position: sticky; top: 0; z-index: 1000; }
    .logo-link {
      display: flex; align-items: center; gap: 10px;
      text-decoration: none; color: inherit; cursor: pointer;
    }
    .toolbar-logo {
      height: 32px; max-width: 120px; object-fit: contain;
      filter: brightness(0) invert(1);
    }
    .toolbar-logo-icon { font-size: 28px; width: 28px; height: 28px; }
    .app-title { font-size: 18px; font-weight: 500; white-space: nowrap; }
    .spacer { flex: 1; }
    .main-content { min-height: calc(100vh - 64px); background: #f5f5f5; padding: 24px; }
    .user-info-menu { padding: 12px 16px; }
    .user-info-menu strong { display: block; }
    .role-badge { font-size: 11px; color: #666; text-transform: uppercase; }
  `],
})
export class LayoutComponent {
  username = '';
  userRole = '';
  isAdmin = false;
  branding: BrandingSettings = {
    app_name: 'RFP Assistant',
    has_logo: false,
    has_favicon: false,
    primary_color: '#1B3A5C',
    logo_url: '',
    favicon_url: '',
  };
  cacheBreaker = Date.now();

  constructor(
    private authService: AuthService,
    private brandingService: BrandingService,
  ) {
    this.authService.currentUser$.subscribe((user) => {
      this.username = user?.username || '';
      this.userRole = user?.role || '';
      this.isAdmin = user?.role === 'admin';
    });

    this.brandingService.branding$.subscribe((b) => {
      this.branding = b;
      this.cacheBreaker = Date.now();
    });
  }

  logout(): void {
    this.authService.logout();
  }
}
