import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatDialogModule, MatDialog } from '@angular/material/dialog';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatChipsModule } from '@angular/material/chips';
import { ApiService } from '../../services/api.service';
import { Workspace } from '../../models/report.model';

@Component({
  selector: 'app-workspace-list',
  standalone: true,
  imports: [
    CommonModule, FormsModule, RouterLink,
    MatCardModule, MatButtonModule, MatIconModule, MatInputModule, MatProgressSpinnerModule, MatChipsModule,
  ],
  template: `
    <div class="page-container">
      <div class="page-header">
        <h1>Espaces de travail</h1>
        <button mat-raised-button color="primary" (click)="showCreateForm = !showCreateForm">
          <mat-icon>add</mat-icon> Nouveau workspace
        </button>
      </div>

      <mat-card *ngIf="showCreateForm" class="create-form">
        <h3>Créer un espace de travail</h3>
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Nom</mat-label>
          <input matInput [(ngModel)]="newName" placeholder="Ex: AO Transport 2025">
        </mat-form-field>
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Description</mat-label>
          <input matInput [(ngModel)]="newDescription" placeholder="Description du workspace">
        </mat-form-field>
        <div class="form-actions">
          <button mat-button (click)="showCreateForm = false">Annuler</button>
          <button mat-raised-button color="primary" (click)="createWorkspace()" [disabled]="!newName">Créer</button>
        </div>
      </mat-card>

      <div *ngIf="loading" class="loading-container">
        <mat-spinner diameter="40"></mat-spinner>
      </div>

      <div class="workspace-grid" *ngIf="!loading">
        <mat-card *ngFor="let ws of workspaces" class="workspace-card" [routerLink]="['/workspace', ws.id]">
          <mat-card-header>
            <mat-icon mat-card-avatar class="ws-icon">folder_shared</mat-icon>
            <mat-card-title>{{ ws.name }}</mat-card-title>
            <mat-card-subtitle>{{ ws.description || 'Aucune description' }}</mat-card-subtitle>
          </mat-card-header>
          <mat-card-content>
            <div class="ws-stats">
              <mat-chip-set>
                <mat-chip>
                  <mat-icon matChipAvatar>people</mat-icon>
                  {{ ws.member_count }} membre{{ ws.member_count > 1 ? 's' : '' }}
                </mat-chip>
                <mat-chip>
                  <mat-icon matChipAvatar>assignment</mat-icon>
                  {{ ws.project_count }} projet{{ ws.project_count > 1 ? 's' : '' }}
                </mat-chip>
              </mat-chip-set>
            </div>
          </mat-card-content>
        </mat-card>

        <mat-card *ngIf="workspaces.length === 0" class="empty-state">
          <mat-icon>folder_open</mat-icon>
          <p>Aucun espace de travail. Créez-en un pour commencer.</p>
        </mat-card>
      </div>
    </div>
  `,
  styles: [`
    .page-container { max-width: 1200px; margin: 0 auto; }
    .page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
    .page-header h1 { margin: 0; color: #1B3A5C; }
    .create-form { padding: 24px; margin-bottom: 24px; }
    .full-width { width: 100%; }
    .form-actions { display: flex; gap: 8px; justify-content: flex-end; }
    .loading-container { display: flex; justify-content: center; padding: 48px; }
    .workspace-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 16px; }
    .workspace-card { cursor: pointer; transition: transform 0.2s, box-shadow 0.2s; }
    .workspace-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
    .ws-icon { font-size: 40px; width: 40px; height: 40px; color: #2C5F8A; }
    .ws-stats { margin-top: 12px; }
    .empty-state { text-align: center; padding: 48px; color: #888; }
    .empty-state mat-icon { font-size: 64px; width: 64px; height: 64px; color: #ccc; }
  `],
})
export class WorkspaceListComponent implements OnInit {
  workspaces: Workspace[] = [];
  loading = true;
  showCreateForm = false;
  newName = '';
  newDescription = '';

  constructor(private api: ApiService) {}

  ngOnInit(): void {
    this.loadWorkspaces();
  }

  loadWorkspaces(): void {
    this.loading = true;
    this.api.getWorkspaces().subscribe({
      next: (ws) => { this.workspaces = ws; this.loading = false; },
      error: () => { this.loading = false; },
    });
  }

  createWorkspace(): void {
    if (!this.newName) return;
    this.api.createWorkspace({ name: this.newName, description: this.newDescription }).subscribe({
      next: () => {
        this.showCreateForm = false;
        this.newName = '';
        this.newDescription = '';
        this.loadWorkspaces();
      },
    });
  }
}
