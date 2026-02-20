import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTableModule } from '@angular/material/table';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatDialogModule } from '@angular/material/dialog';
import { ApiService } from '../../services/api.service';
import { UserInfo } from '../../models/report.model';

@Component({
  selector: 'app-admin-users',
  standalone: true,
  imports: [
    CommonModule, FormsModule, RouterLink,
    MatCardModule, MatButtonModule, MatIconModule, MatInputModule,
    MatSelectModule, MatTableModule, MatSlideToggleModule, MatSnackBarModule, MatDialogModule,
  ],
  template: `
    <div class="page-container">
      <div class="page-header">
        <button mat-icon-button routerLink="/workspaces"><mat-icon>arrow_back</mat-icon></button>
        <h1>Gestion des utilisateurs</h1>
        <button mat-raised-button color="primary" (click)="showCreate = !showCreate">
          <mat-icon>person_add</mat-icon> Nouvel utilisateur
        </button>
      </div>

      <!-- Create form -->
      <mat-card *ngIf="showCreate" class="form-card">
        <h3>Créer un utilisateur</h3>
        <div class="form-grid">
          <mat-form-field appearance="outline">
            <mat-label>Email</mat-label>
            <input matInput [(ngModel)]="newUser.email" type="email" required>
          </mat-form-field>
          <mat-form-field appearance="outline">
            <mat-label>Nom d'utilisateur</mat-label>
            <input matInput [(ngModel)]="newUser.username" required>
          </mat-form-field>
          <mat-form-field appearance="outline">
            <mat-label>Nom complet</mat-label>
            <input matInput [(ngModel)]="newUser.full_name">
          </mat-form-field>
          <mat-form-field appearance="outline">
            <mat-label>Mot de passe</mat-label>
            <input matInput [(ngModel)]="newUser.password" type="password" required>
          </mat-form-field>
          <mat-form-field appearance="outline">
            <mat-label>Rôle</mat-label>
            <mat-select [(ngModel)]="newUser.role">
              <mat-option value="user">Utilisateur</mat-option>
              <mat-option value="admin">Administrateur</mat-option>
            </mat-select>
          </mat-form-field>
        </div>
        <div class="form-actions">
          <button mat-button (click)="showCreate = false">Annuler</button>
          <button mat-raised-button color="primary" (click)="createUser()" [disabled]="!newUser.email || !newUser.username || !newUser.password">
            Créer
          </button>
        </div>
      </mat-card>

      <!-- Users table -->
      <mat-card class="table-card">
        <table mat-table [dataSource]="users" class="users-table">
          <ng-container matColumnDef="username">
            <th mat-header-cell *matHeaderCellDef>Utilisateur</th>
            <td mat-cell *matCellDef="let u">
              <div class="user-cell">
                <mat-icon>person</mat-icon>
                <div>
                  <strong>{{ u.username }}</strong>
                  <small>{{ u.full_name }}</small>
                </div>
              </div>
            </td>
          </ng-container>

          <ng-container matColumnDef="email">
            <th mat-header-cell *matHeaderCellDef>Email</th>
            <td mat-cell *matCellDef="let u">{{ u.email }}</td>
          </ng-container>

          <ng-container matColumnDef="role">
            <th mat-header-cell *matHeaderCellDef>Rôle</th>
            <td mat-cell *matCellDef="let u">
              <span [class]="'role-badge role-' + u.role">{{ u.role === 'admin' ? 'Admin' : 'Utilisateur' }}</span>
            </td>
          </ng-container>

          <ng-container matColumnDef="active">
            <th mat-header-cell *matHeaderCellDef>Actif</th>
            <td mat-cell *matCellDef="let u">
              <mat-slide-toggle [checked]="u.is_active" (change)="toggleActive(u)" [disabled]="u.role === 'admin'">
              </mat-slide-toggle>
            </td>
          </ng-container>

          <ng-container matColumnDef="actions">
            <th mat-header-cell *matHeaderCellDef>Actions</th>
            <td mat-cell *matCellDef="let u">
              <button mat-icon-button color="warn" (click)="deleteUser(u)" [disabled]="u.role === 'admin'" matTooltip="Supprimer">
                <mat-icon>delete</mat-icon>
              </button>
            </td>
          </ng-container>

          <tr mat-header-row *matHeaderRowDef="displayedColumns"></tr>
          <tr mat-row *matRowDef="let row; columns: displayedColumns;"></tr>
        </table>

        <div *ngIf="users.length === 0" class="empty-state">
          <mat-icon>people</mat-icon>
          <p>Aucun utilisateur trouvé.</p>
        </div>
      </mat-card>
    </div>
  `,
  styles: [`
    .page-container { max-width: 1000px; margin: 0 auto; }
    .page-header { display: flex; align-items: center; gap: 12px; margin-bottom: 24px; }
    .page-header h1 { flex: 1; margin: 0; color: #1B3A5C; font-size: 20px; }
    .form-card { padding: 24px; margin-bottom: 16px; }
    .form-card h3 { margin-top: 0; color: #1B3A5C; }
    .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 16px; }
    .form-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 8px; }
    .table-card { padding: 0; overflow: hidden; }
    .users-table { width: 100%; }
    .user-cell { display: flex; align-items: center; gap: 8px; }
    .user-cell small { display: block; color: #888; font-size: 12px; }
    .role-badge { padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; }
    .role-admin { background: #e3f2fd; color: #1565c0; }
    .role-user { background: #f5f5f5; color: #666; }
    .empty-state { text-align: center; padding: 48px; color: #888; }
    .empty-state mat-icon { font-size: 48px; width: 48px; height: 48px; color: #ccc; }
  `],
})
export class AdminUsersComponent implements OnInit {
  users: UserInfo[] = [];
  showCreate = false;
  displayedColumns = ['username', 'email', 'role', 'active', 'actions'];
  newUser = { email: '', username: '', full_name: '', password: '', role: 'user' };

  constructor(private api: ApiService, private snackBar: MatSnackBar) {}

  ngOnInit(): void {
    this.loadUsers();
  }

  loadUsers(): void {
    this.api.getUsers().subscribe({
      next: (users) => this.users = users,
      error: (err) => this.snackBar.open(err.error?.detail || 'Erreur de chargement', 'OK', { duration: 3000 }),
    });
  }

  createUser(): void {
    this.api.createUser(this.newUser).subscribe({
      next: () => {
        this.snackBar.open('Utilisateur créé', 'OK', { duration: 3000 });
        this.showCreate = false;
        this.newUser = { email: '', username: '', full_name: '', password: '', role: 'user' };
        this.loadUsers();
      },
      error: (err) => this.snackBar.open(err.error?.detail || 'Erreur de création', 'OK', { duration: 5000 }),
    });
  }

  toggleActive(user: UserInfo): void {
    this.api.updateUser(user.id, { is_active: !user.is_active }).subscribe({
      next: () => this.loadUsers(),
      error: (err) => this.snackBar.open(err.error?.detail || 'Erreur', 'OK', { duration: 3000 }),
    });
  }

  deleteUser(user: UserInfo): void {
    if (!confirm(`Supprimer l'utilisateur ${user.username} ?`)) return;
    this.api.deleteUser(user.id).subscribe({
      next: () => {
        this.snackBar.open('Utilisateur supprimé', 'OK', { duration: 3000 });
        this.loadUsers();
      },
      error: (err) => this.snackBar.open(err.error?.detail || 'Erreur', 'OK', { duration: 3000 }),
    });
  }
}
