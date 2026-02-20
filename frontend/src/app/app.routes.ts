import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () =>
      import('./components/home/home.component').then((m) => m.HomeComponent),
  },
  {
    path: 'setup',
    loadComponent: () =>
      import('./components/setup/setup.component').then((m) => m.SetupComponent),
  },
  {
    path: 'editor',
    loadComponent: () =>
      import('./components/editor/editor.component').then((m) => m.EditorComponent),
  },
  {
    path: '**',
    redirectTo: '',
  },
];
