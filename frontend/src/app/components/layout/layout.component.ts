import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatDividerModule } from '@angular/material/divider';
import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-layout',
  standalone: true,
  imports: [
    CommonModule, RouterOutlet, RouterLink, RouterLinkActive,
    MatToolbarModule, MatButtonModule, MatIconModule, MatMenuModule, MatDividerModule,
  ],
  template: `
    <mat-toolbar color="primary" class="toolbar">
      <button mat-icon-button routerLink="/workspaces">
        <mat-icon>description</mat-icon>
      </button>
      <span class="app-title" routerLink="/workspaces" style="cursor:pointer">RFP Assistant</span>

      <span class="spacer"></span>

      <button mat-icon-button routerLink="/workspaces" matTooltip="Workspaces">
        <mat-icon>workspaces</mat-icon>
      </button>

      <button mat-icon-button *ngIf="isAdmin" routerLink="/admin/users" matTooltip="Administration">
        <mat-icon>admin_panel_settings</mat-icon>
      </button>

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
  `,
  styles: [`
    .toolbar { position: sticky; top: 0; z-index: 1000; }
    .app-title { margin-left: 8px; font-size: 18px; font-weight: 500; }
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

  constructor(private authService: AuthService) {
    this.authService.currentUser$.subscribe((user) => {
      this.username = user?.username || '';
      this.userRole = user?.role || '';
      this.isAdmin = user?.role === 'admin';
    });
  }

  logout(): void {
    this.authService.logout();
  }
}
