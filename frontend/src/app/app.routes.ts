import { Routes } from '@angular/router';
import { authGuard, adminGuard } from './services/auth.guard';

export const routes: Routes = [
  {
    path: 'login',
    loadComponent: () =>
      import('./components/login/login.component').then((m) => m.LoginComponent),
  },
  {
    path: '',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./components/layout/layout.component').then((m) => m.LayoutComponent),
    children: [
      {
        path: '',
        redirectTo: 'workspaces',
        pathMatch: 'full',
      },
      {
        path: 'workspaces',
        loadComponent: () =>
          import('./components/workspace-list/workspace-list.component').then((m) => m.WorkspaceListComponent),
      },
      {
        path: 'workspace/:workspaceId',
        loadComponent: () =>
          import('./components/workspace-detail/workspace-detail.component').then((m) => m.WorkspaceDetailComponent),
      },
      {
        path: 'project/:projectId',
        loadComponent: () =>
          import('./components/project-dashboard/project-dashboard.component').then((m) => m.ProjectDashboardComponent),
      },
      {
        path: 'project/:projectId/chapter/:chapterId',
        loadComponent: () =>
          import('./components/chapter-editor/chapter-editor.component').then((m) => m.ChapterEditorComponent),
      },
      {
        path: 'project/:projectId/images',
        loadComponent: () =>
          import('./components/image-gallery/image-gallery.component').then((m) => m.ImageGalleryComponent),
      },
      {
        path: 'project/:projectId/preview',
        loadComponent: () =>
          import('./components/preview/preview.component').then((m) => m.PreviewComponent),
      },
      {
        path: 'project/:projectId/gap-analysis',
        loadComponent: () =>
          import('./components/gap-analysis/gap-analysis.component').then((m) => m.GapAnalysisComponent),
      },
      {
        path: 'project/:projectId/compliance',
        loadComponent: () =>
          import('./components/compliance/compliance.component').then((m) => m.ComplianceComponent),
      },
      {
        path: 'project/:projectId/statistics',
        loadComponent: () =>
          import('./components/statistics/statistics.component').then((m) => m.StatisticsComponent),
      },
      {
        path: 'project/:projectId/soutenance',
        loadComponent: () =>
          import('./components/soutenance/soutenance.component').then((m) => m.SoutenanceComponent),
      },
      {
        path: 'project/:projectId/cost-tracking',
        canActivate: [adminGuard],
        loadComponent: () =>
          import('./components/cost-tracking/cost-tracking.component').then((m) => m.CostTrackingComponent),
      },
      {
        path: 'admin',
        canActivate: [adminGuard],
        children: [
          {
            path: 'users',
            loadComponent: () =>
              import('./components/admin-users/admin-users.component').then((m) => m.AdminUsersComponent),
          },
          {
            path: 'settings/:workspaceId',
            loadComponent: () =>
              import('./components/admin-settings/admin-settings.component').then((m) => m.AdminSettingsComponent),
          },
        ],
      },
    ],
  },
  {
    path: '**',
    redirectTo: '',
  },
];
