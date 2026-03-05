import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatChipsModule } from '@angular/material/chips';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatMenuModule } from '@angular/material/menu';
import { ApiService } from '../../services/api.service';
import { AuthService } from '../../services/auth.service';
import { Workspace } from '../../models/report.model';

@Component({
  selector: 'app-workspace-list',
  standalone: true,
  imports: [
    CommonModule, FormsModule, RouterLink,
    MatCardModule, MatButtonModule, MatIconModule, MatInputModule, MatProgressSpinnerModule, MatChipsModule,
    MatSnackBarModule, MatMenuModule,
  ],
  template: `
    <div class="page-container">
      <div class="page-header">
        <h1>Espaces de travail</h1>
        <button mat-raised-button color="primary" (click)="showCreateForm = !showCreateForm" *ngIf="isAdmin">
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
        <mat-card *ngFor="let ws of workspaces" class="workspace-card">
          <!-- Edit form inline -->
          <div *ngIf="editingWorkspace?.id === ws.id" class="edit-inline">
            <mat-form-field appearance="outline" class="full-width">
              <mat-label>Nom</mat-label>
              <input matInput [(ngModel)]="editingWorkspace!.name">
            </mat-form-field>
            <mat-form-field appearance="outline" class="full-width">
              <mat-label>Description</mat-label>
              <input matInput [(ngModel)]="editingWorkspace!.description">
            </mat-form-field>
            <div class="form-actions">
              <button mat-button (click)="editingWorkspace = null">Annuler</button>
              <button mat-raised-button color="primary" (click)="saveWorkspace(ws)">Enregistrer</button>
            </div>
          </div>

          <!-- Normal display -->
          <div *ngIf="editingWorkspace?.id !== ws.id" [routerLink]="['/workspace', ws.id]" class="ws-clickable">
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
          </div>

          <!-- Action buttons (admin only) -->
          <div class="ws-card-actions" *ngIf="editingWorkspace?.id !== ws.id && isAdmin">
            <button mat-icon-button (click)="startEditWorkspace(ws, $event)" matTooltip="Modifier">
              <mat-icon>edit</mat-icon>
            </button>
            <button mat-icon-button color="warn" (click)="deleteWorkspace(ws, $event)" matTooltip="Supprimer">
              <mat-icon>delete</mat-icon>
            </button>
          </div>
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
    .workspace-card { position: relative; transition: transform 0.2s, box-shadow 0.2s; }
    .workspace-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
    .ws-clickable { cursor: pointer; }
    .ws-icon { font-size: 40px; width: 40px; height: 40px; color: #2C5F8A; }
    .ws-stats { margin-top: 12px; }
    .ws-card-actions { position: absolute; top: 8px; right: 8px; display: flex; gap: 0; opacity: 0; transition: opacity 0.2s; }
    .workspace-card:hover .ws-card-actions { opacity: 1; }
    .edit-inline { padding: 16px; }
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
  editingWorkspace: { id: string; name: string; description: string } | null = null;
  isAdmin = false;

  constructor(private api: ApiService, private authService: AuthService, private snackBar: MatSnackBar) {
    this.isAdmin = this.authService.isAdmin();
  }

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

  startEditWorkspace(ws: Workspace, event: Event): void {
    event.stopPropagation();
    event.preventDefault();
    this.editingWorkspace = { id: ws.id, name: ws.name, description: ws.description || '' };
  }

  saveWorkspace(ws: Workspace): void {
    if (!this.editingWorkspace) return;
    this.api.updateWorkspace(ws.id, {
      name: this.editingWorkspace.name,
      description: this.editingWorkspace.description,
    }).subscribe({
      next: () => {
        this.editingWorkspace = null;
        this.snackBar.open('Workspace modifie', 'OK', { duration: 2000 });
        this.loadWorkspaces();
      },
      error: () => this.snackBar.open('Erreur de modification', 'OK', { duration: 3000 }),
    });
  }

  deleteWorkspace(ws: Workspace, event: Event): void {
    event.stopPropagation();
    event.preventDefault();
    if (!confirm(`Supprimer le workspace "${ws.name}" et tous ses projets ? Cette action est irreversible.`)) return;
    this.api.deleteWorkspace(ws.id).subscribe({
      next: () => {
        this.snackBar.open('Workspace supprime', 'OK', { duration: 2000 });
        this.loadWorkspaces();
      },
      error: (err) => this.snackBar.open(err.error?.detail || 'Erreur de suppression', 'OK', { duration: 3000 }),
    });
  }
}
