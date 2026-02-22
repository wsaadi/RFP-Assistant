import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatTabsModule } from '@angular/material/tabs';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatListModule } from '@angular/material/list';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Router } from '@angular/router';
import { ApiService } from '../../services/api.service';
import { AuthService } from '../../services/auth.service';
import { Workspace, RFPProject, WorkspaceMember } from '../../models/report.model';

@Component({
  selector: 'app-workspace-detail',
  standalone: true,
  imports: [
    CommonModule, FormsModule, RouterLink,
    MatCardModule, MatButtonModule, MatIconModule, MatInputModule,
    MatTabsModule, MatChipsModule, MatProgressSpinnerModule, MatListModule, MatSnackBarModule,
    MatMenuModule, MatTooltipModule,
  ],
  template: `
    <div class="page-container" *ngIf="workspace">
      <div class="page-header">
        <div>
          <button mat-icon-button routerLink="/workspaces"><mat-icon>arrow_back</mat-icon></button>
          <div *ngIf="!editingWorkspace">
            <h1>{{ workspace.name }}</h1>
            <span class="ws-description" *ngIf="workspace.description">{{ workspace.description }}</span>
          </div>
          <div *ngIf="editingWorkspace" class="edit-ws-inline">
            <mat-form-field appearance="outline">
              <mat-label>Nom</mat-label>
              <input matInput [(ngModel)]="editWsName">
            </mat-form-field>
            <mat-form-field appearance="outline">
              <mat-label>Description</mat-label>
              <input matInput [(ngModel)]="editWsDescription">
            </mat-form-field>
            <button mat-button (click)="editingWorkspace = false">Annuler</button>
            <button mat-raised-button color="primary" (click)="saveWorkspace()">Enregistrer</button>
          </div>
        </div>
        <div class="header-actions">
          <button mat-icon-button (click)="startEditWorkspace()" matTooltip="Modifier le workspace" *ngIf="!editingWorkspace">
            <mat-icon>edit</mat-icon>
          </button>
          <button mat-icon-button color="warn" (click)="deleteWorkspace()" matTooltip="Supprimer le workspace" *ngIf="!editingWorkspace">
            <mat-icon>delete</mat-icon>
          </button>
          <button mat-raised-button color="accent" (click)="onImportBackup()" *ngIf="isAdmin">
            <mat-icon>upload_file</mat-icon> Importer un projet
          </button>
          <button mat-raised-button color="primary" routerLink="/admin/settings/{{ workspaceId }}" *ngIf="isAdmin">
            <mat-icon>settings</mat-icon> Config IA
          </button>
        </div>
      </div>

      <mat-tab-group>
        <mat-tab label="Projets">
          <div class="tab-content">
            <mat-card *ngIf="showCreateProject" class="create-form">
              <h3>Nouveau projet d'appel d'offres</h3>
              <div class="form-grid">
                <mat-form-field appearance="outline">
                  <mat-label>Nom du projet</mat-label>
                  <input matInput [(ngModel)]="newProject.name" required>
                </mat-form-field>
                <mat-form-field appearance="outline">
                  <mat-label>Client</mat-label>
                  <input matInput [(ngModel)]="newProject.client_name">
                </mat-form-field>
                <mat-form-field appearance="outline">
                  <mat-label>Référence AO</mat-label>
                  <input matInput [(ngModel)]="newProject.rfp_reference">
                </mat-form-field>
                <mat-form-field appearance="outline">
                  <mat-label>Date limite</mat-label>
                  <input matInput [(ngModel)]="newProject.deadline" type="date">
                </mat-form-field>
              </div>
              <mat-form-field appearance="outline" class="full-width">
                <mat-label>Description</mat-label>
                <textarea matInput [(ngModel)]="newProject.description" rows="2"></textarea>
              </mat-form-field>
              <div class="form-actions">
                <button mat-button (click)="showCreateProject = false">Annuler</button>
                <button mat-raised-button color="primary" (click)="createProject()" [disabled]="!newProject.name">Créer</button>
              </div>
            </mat-card>

            <button mat-raised-button color="primary" (click)="showCreateProject = true" *ngIf="!showCreateProject" style="margin-bottom:16px">
              <mat-icon>add</mat-icon> Nouveau projet
            </button>

            <div class="project-grid">
              <mat-card *ngFor="let p of projects" class="project-card">
                <!-- Edit form inline -->
                <div *ngIf="editingProject?.id === p.id" class="edit-inline">
                  <div class="form-grid">
                    <mat-form-field appearance="outline">
                      <mat-label>Nom</mat-label>
                      <input matInput [(ngModel)]="editingProject!.name">
                    </mat-form-field>
                    <mat-form-field appearance="outline">
                      <mat-label>Client</mat-label>
                      <input matInput [(ngModel)]="editingProject!.client_name">
                    </mat-form-field>
                    <mat-form-field appearance="outline">
                      <mat-label>Reference AO</mat-label>
                      <input matInput [(ngModel)]="editingProject!.rfp_reference">
                    </mat-form-field>
                    <mat-form-field appearance="outline">
                      <mat-label>Date limite</mat-label>
                      <input matInput [(ngModel)]="editingProject!.deadline" type="date">
                    </mat-form-field>
                  </div>
                  <mat-form-field appearance="outline" class="full-width">
                    <mat-label>Description</mat-label>
                    <textarea matInput [(ngModel)]="editingProject!.description" rows="2"></textarea>
                  </mat-form-field>
                  <div class="form-actions">
                    <button mat-button (click)="editingProject = null">Annuler</button>
                    <button mat-raised-button color="primary" (click)="saveProject(p)">Enregistrer</button>
                  </div>
                </div>

                <!-- Normal display -->
                <div *ngIf="editingProject?.id !== p.id" [routerLink]="['/project', p.id]" class="project-clickable">
                  <mat-card-header>
                    <mat-icon mat-card-avatar class="project-icon" [class]="'status-' + p.status">assignment</mat-icon>
                    <mat-card-title>{{ p.name }}</mat-card-title>
                    <mat-card-subtitle>{{ p.client_name }} - {{ p.rfp_reference }}</mat-card-subtitle>
                  </mat-card-header>
                  <mat-card-content>
                    <p class="project-desc">{{ p.description || 'Aucune description' }}</p>
                    <mat-chip-set>
                      <mat-chip [class]="'status-chip-' + p.status">{{ statusLabel(p.status) }}</mat-chip>
                      <mat-chip>{{ p.document_count }} docs</mat-chip>
                      <mat-chip>{{ p.chapter_count }} chapitres</mat-chip>
                    </mat-chip-set>
                    <p class="deadline" *ngIf="p.deadline">Date limite: {{ p.deadline }}</p>
                  </mat-card-content>
                </div>

                <!-- Action buttons -->
                <div class="project-card-actions" *ngIf="editingProject?.id !== p.id">
                  <button mat-icon-button (click)="startEditProject(p, $event)" matTooltip="Modifier">
                    <mat-icon>edit</mat-icon>
                  </button>
                  <button mat-icon-button color="warn" (click)="deleteProject(p, $event)" matTooltip="Supprimer">
                    <mat-icon>delete</mat-icon>
                  </button>
                </div>
              </mat-card>
            </div>

            <mat-card *ngIf="projects.length === 0" class="empty-state">
              <mat-icon>assignment</mat-icon>
              <p>Aucun projet. Créez votre premier projet de réponse à appel d'offres.</p>
            </mat-card>
          </div>
        </mat-tab>

        <mat-tab label="Membres">
          <div class="tab-content">
            <mat-list>
              <mat-list-item *ngFor="let m of members">
                <mat-icon matListItemIcon>person</mat-icon>
                <span matListItemTitle>{{ m.full_name }} ({{ m.username }})</span>
                <span matListItemLine>{{ m.email }} - {{ m.role }}</span>
              </mat-list-item>
            </mat-list>
          </div>
        </mat-tab>
      </mat-tab-group>
    </div>

    <div *ngIf="loading" class="loading-container">
      <mat-spinner diameter="40"></mat-spinner>
    </div>

    <input type="file" #importInput accept=".zip" (change)="handleImportFile($event)" style="display:none">
  `,
  styles: [`
    .page-container { max-width: 1200px; margin: 0 auto; }
    .page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
    .page-header > div { display: flex; align-items: center; gap: 8px; }
    .page-header h1 { margin: 0; color: #1B3A5C; }
    .header-actions { display: flex; gap: 8px; }
    .tab-content { padding: 16px 0; }
    .create-form { padding: 24px; margin-bottom: 16px; }
    .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 16px; }
    .full-width { width: 100%; }
    .form-actions { display: flex; gap: 8px; justify-content: flex-end; }
    .ws-description { color: #666; font-size: 13px; }
    .edit-ws-inline { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .edit-ws-inline mat-form-field { width: 200px; }
    .project-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 16px; }
    .project-card { position: relative; transition: transform 0.2s; }
    .project-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
    .project-clickable { cursor: pointer; }
    .project-icon { font-size: 36px; width: 36px; height: 36px; color: #2C5F8A; }
    .project-desc { color: #666; font-size: 13px; margin: 8px 0; }
    .deadline { color: #d32f2f; font-size: 12px; margin-top: 8px; }
    .project-card-actions { position: absolute; top: 8px; right: 8px; display: flex; gap: 0; opacity: 0; transition: opacity 0.2s; }
    .project-card:hover .project-card-actions { opacity: 1; }
    .edit-inline { padding: 16px; }
    .status-chip-draft { background: #e0e0e0 !important; }
    .status-chip-in_progress { background: #bbdefb !important; }
    .status-chip-completed { background: #c8e6c9 !important; }
    .empty-state { text-align: center; padding: 48px; color: #888; }
    .empty-state mat-icon { font-size: 64px; width: 64px; height: 64px; color: #ccc; }
    .loading-container { display: flex; justify-content: center; padding: 48px; }
  `],
})
export class WorkspaceDetailComponent implements OnInit {
  workspaceId = '';
  workspace: Workspace | null = null;
  projects: RFPProject[] = [];
  members: WorkspaceMember[] = [];
  loading = true;
  showCreateProject = false;
  isAdmin = false;
  newProject = { name: '', description: '', client_name: '', rfp_reference: '', deadline: '' };
  editingWorkspace = false;
  editWsName = '';
  editWsDescription = '';
  editingProject: { id: string; name: string; description: string; client_name: string; rfp_reference: string; deadline: string } | null = null;

  constructor(
    private route: ActivatedRoute,
    private api: ApiService,
    private authService: AuthService,
    private snackBar: MatSnackBar,
    private router: Router,
  ) {
    this.isAdmin = this.authService.isAdmin();
  }

  ngOnInit(): void {
    this.workspaceId = this.route.snapshot.paramMap.get('workspaceId') || '';
    this.loadData();
  }

  loadData(): void {
    this.loading = true;
    this.api.getWorkspace(this.workspaceId).subscribe({
      next: (ws) => { this.workspace = ws; this.loading = false; },
      error: () => { this.loading = false; },
    });
    this.api.getProjects(this.workspaceId).subscribe({
      next: (p) => this.projects = p,
    });
    this.api.getWorkspaceMembers(this.workspaceId).subscribe({
      next: (m) => this.members = m,
    });
  }

  createProject(): void {
    this.api.createProject(this.workspaceId, this.newProject).subscribe({
      next: () => {
        this.showCreateProject = false;
        this.newProject = { name: '', description: '', client_name: '', rfp_reference: '', deadline: '' };
        this.loadData();
      },
    });
  }

  statusLabel(status: string): string {
    const labels: Record<string, string> = {
      draft: 'Brouillon', documents_uploaded: 'Documents chargés',
      indexing: 'Indexation', ready: 'Prêt', in_progress: 'En cours', completed: 'Terminé',
    };
    return labels[status] || status;
  }

  onImportBackup(): void {
    const input = document.querySelector('input[type=file]') as HTMLInputElement;
    input?.click();
  }

  handleImportFile(event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    this.api.importBackup(this.workspaceId, file).subscribe({
      next: (res) => {
        this.snackBar.open(res.message, 'OK', { duration: 3000 });
        this.loadData();
      },
      error: (err) => this.snackBar.open(err.error?.detail || 'Erreur d\'import', 'OK', { duration: 5000 }),
    });
  }

  // ── Workspace edit/delete ──

  startEditWorkspace(): void {
    if (!this.workspace) return;
    this.editWsName = this.workspace.name;
    this.editWsDescription = this.workspace.description || '';
    this.editingWorkspace = true;
  }

  saveWorkspace(): void {
    this.api.updateWorkspace(this.workspaceId, {
      name: this.editWsName,
      description: this.editWsDescription,
    }).subscribe({
      next: () => {
        this.editingWorkspace = false;
        this.snackBar.open('Workspace modifie', 'OK', { duration: 2000 });
        this.loadData();
      },
      error: () => this.snackBar.open('Erreur de modification', 'OK', { duration: 3000 }),
    });
  }

  deleteWorkspace(): void {
    if (!this.workspace) return;
    if (!confirm(`Supprimer le workspace "${this.workspace.name}" et tous ses projets ? Cette action est irreversible.`)) return;
    this.api.deleteWorkspace(this.workspaceId).subscribe({
      next: () => {
        this.snackBar.open('Workspace supprime', 'OK', { duration: 2000 });
        this.router.navigate(['/workspaces']);
      },
      error: (err) => this.snackBar.open(err.error?.detail || 'Erreur de suppression', 'OK', { duration: 3000 }),
    });
  }

  // ── Project edit/delete ──

  startEditProject(p: RFPProject, event: Event): void {
    event.stopPropagation();
    event.preventDefault();
    this.editingProject = {
      id: p.id,
      name: p.name,
      description: p.description || '',
      client_name: p.client_name || '',
      rfp_reference: p.rfp_reference || '',
      deadline: p.deadline || '',
    };
  }

  saveProject(p: RFPProject): void {
    if (!this.editingProject) return;
    this.api.updateProject(p.id, {
      name: this.editingProject.name,
      description: this.editingProject.description,
      client_name: this.editingProject.client_name,
      rfp_reference: this.editingProject.rfp_reference,
      deadline: this.editingProject.deadline || null,
    }).subscribe({
      next: () => {
        this.editingProject = null;
        this.snackBar.open('Projet modifie', 'OK', { duration: 2000 });
        this.loadData();
      },
      error: () => this.snackBar.open('Erreur de modification', 'OK', { duration: 3000 }),
    });
  }

  deleteProject(p: RFPProject, event: Event): void {
    event.stopPropagation();
    event.preventDefault();
    if (!confirm(`Supprimer le projet "${p.name}" et toutes ses donnees ? Cette action est irreversible.`)) return;
    this.api.deleteProject(p.id).subscribe({
      next: () => {
        this.snackBar.open('Projet supprime', 'OK', { duration: 2000 });
        this.loadData();
      },
      error: (err) => this.snackBar.open(err.error?.detail || 'Erreur de suppression', 'OK', { duration: 3000 }),
    });
  }
}
