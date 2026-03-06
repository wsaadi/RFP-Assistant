import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';
import { Router, NavigationEnd } from '@angular/router';
import { filter } from 'rxjs/operators';

export interface OnboardingStep {
  id: string;
  route: string;
  selector: string;
  title: string;
  message: string;
  icon: string;
  position: 'top' | 'bottom' | 'left' | 'right';
  action?: 'click' | 'observe';
  nextRoute?: string;
}

export interface OnboardingState {
  active: boolean;
  currentStepIndex: number;
  completedSteps: string[];
  dismissed: boolean;
}

const ALL_STEPS: OnboardingStep[] = [
  // ── Workspaces page ──
  {
    id: 'welcome',
    route: '/workspaces',
    selector: '.page-header h1',
    title: 'Bienvenue sur RFP Assistant ! 🎉',
    message: 'Je suis votre guide ! Je vais vous accompagner pas à pas dans la découverte de l\'application. Vous pouvez me désactiver à tout moment en cliquant sur le bouton en bas à droite.',
    icon: 'waving_hand',
    position: 'bottom',
  },
  {
    id: 'workspace-list',
    route: '/workspaces',
    selector: '.workspace-grid',
    title: 'Vos espaces de travail',
    message: 'Voici la liste de vos espaces de travail. Chaque workspace regroupe des projets de réponse à appel d\'offres et des membres. Cliquez sur un workspace pour y accéder.',
    icon: 'workspaces',
    position: 'top',
  },
  {
    id: 'create-workspace',
    route: '/workspaces',
    selector: '.page-header button[color="primary"]',
    title: 'Créer un workspace (Admin)',
    message: 'Si vous êtes administrateur, cliquez ici pour créer un nouvel espace de travail. Donnez-lui un nom parlant comme "AO Transport 2025".',
    icon: 'add_circle',
    position: 'bottom',
  },
  // ── Workspace detail ──
  {
    id: 'workspace-detail-projects',
    route: '/workspace/',
    selector: '.tab-content',
    title: 'Les projets du workspace',
    message: 'Ici vous retrouvez tous les projets de réponse à appel d\'offres de ce workspace. Chaque projet correspond à un AO spécifique avec ses documents, chapitres et analyses.',
    icon: 'assignment',
    position: 'top',
  },
  {
    id: 'create-project',
    route: '/workspace/',
    selector: 'button:has(mat-icon)',
    title: 'Créer un projet',
    message: 'Cliquez sur "Nouveau projet" pour démarrer un nouveau projet de réponse. Renseignez le nom du client, la référence de l\'AO, la date limite et les catégories de documents à inclure.',
    icon: 'note_add',
    position: 'bottom',
  },
  {
    id: 'workspace-members',
    route: '/workspace/',
    selector: '.mat-mdc-tab:nth-child(2)',
    title: 'Gérer les membres',
    message: 'Dans l\'onglet "Membres", vous pouvez ajouter des collaborateurs avec différents rôles : Propriétaire, Éditeur ou Lecteur. Chacun aura des droits adaptés.',
    icon: 'group',
    position: 'bottom',
  },
  // ── Project dashboard ──
  {
    id: 'project-overview',
    route: '/project/',
    selector: '.page-header',
    title: 'Tableau de bord du projet',
    message: 'Voici le cœur de votre projet ! D\'ici vous gérez vos documents, vos chapitres, lancez les analyses IA et suivez votre progression.',
    icon: 'dashboard',
    position: 'bottom',
  },
  {
    id: 'upload-documents',
    route: '/project/',
    selector: '.upload-zone, .drop-zone, [class*="upload"], [class*="document"]',
    title: 'Uploader vos documents 📄',
    message: 'Commencez par uploader les documents de l\'appel d\'offres (CCTP, RC, BPU...) et vos anciens documents de réponse. Glissez-déposez ou cliquez pour sélectionner. L\'IA va les analyser automatiquement.',
    icon: 'upload_file',
    position: 'top',
  },
  {
    id: 'chapters-section',
    route: '/project/',
    selector: '.mat-mdc-tab:nth-child(2), [class*="chapter"]',
    title: 'Les chapitres de votre réponse',
    message: 'L\'onglet "Chapitres" contient la structure de votre réponse. Vous pouvez créer des chapitres manuellement ou laisser l\'IA les détecter automatiquement depuis le cahier des charges.',
    icon: 'menu_book',
    position: 'bottom',
  },
  {
    id: 'ai-generation',
    route: '/project/',
    selector: 'button:has(mat-icon[fontIcon="auto_fix_high"]), [class*="generate"], [class*="prefill"]',
    title: 'Génération IA des contenus ✨',
    message: 'Le bouton "Pré-remplir tous les chapitres" lance la rédaction automatique par IA. Elle s\'appuie sur vos documents de référence pour rédiger chaque chapitre de façon personnalisée.',
    icon: 'auto_awesome',
    position: 'bottom',
  },
  {
    id: 'project-actions',
    route: '/project/',
    selector: '.header-actions',
    title: 'Actions du projet',
    message: 'Depuis la barre d\'actions, vous pouvez : exporter en Word (DOCX), sauvegarder (Backup), consulter les images extraites, prévisualiser le document ou préparer une soutenance PowerPoint.',
    icon: 'apps',
    position: 'bottom',
  },
  {
    id: 'nav-images',
    route: '/project/',
    selector: 'button:has(mat-icon[fontIcon="photo_library"]), [routerLink*="images"]',
    title: 'Galerie d\'images 🖼️',
    message: 'Les images sont automatiquement extraites de vos documents PDF. Accédez à la galerie pour les consulter et les réutiliser dans vos chapitres.',
    icon: 'photo_library',
    position: 'bottom',
  },
  {
    id: 'nav-compliance',
    route: '/project/',
    selector: 'button:has(mat-icon[fontIcon="checklist"]), [routerLink*="compliance"], [class*="compliance"]',
    title: 'Analyse de conformité ✅',
    message: 'L\'analyse de conformité vérifie que votre réponse répond bien à toutes les exigences du cahier des charges. Chaque exigence est évaluée avec un score de conformité.',
    icon: 'fact_check',
    position: 'bottom',
  },
  {
    id: 'nav-gap',
    route: '/project/',
    selector: 'button:has(mat-icon[fontIcon="compare"]), [routerLink*="gap"], [class*="gap"]',
    title: 'Analyse d\'écarts 📊',
    message: 'L\'analyse d\'écarts compare votre ancienne réponse avec le nouveau cahier des charges pour identifier ce qui a changé, ce qui est nouveau et ce qui a été supprimé.',
    icon: 'compare_arrows',
    position: 'bottom',
  },
  {
    id: 'nav-stats',
    route: '/project/',
    selector: 'button:has(mat-icon[fontIcon="bar_chart"]), [routerLink*="statistics"], [class*="stat"]',
    title: 'Statistiques 📈',
    message: 'Suivez l\'avancement de votre projet : progression par chapitre, couverture des exigences, score de conformité global et métriques de qualité.',
    icon: 'analytics',
    position: 'bottom',
  },
  // ── Chapter editor ──
  {
    id: 'chapter-editor',
    route: '/chapter/',
    selector: '.editor-container, .editor-header',
    title: 'Éditeur de chapitre ✏️',
    message: 'C\'est ici que vous rédigez ! En haut, vous voyez l\'exigence de l\'AO. En dessous, l\'éditeur pour rédiger votre réponse. Vous pouvez écrire manuellement ou utiliser l\'IA.',
    icon: 'edit_note',
    position: 'bottom',
  },
  {
    id: 'chapter-ai-generate',
    route: '/chapter/',
    selector: '.ai-actions, button:has(mat-icon[fontIcon="auto_fix_high"])',
    title: 'Actions IA du chapitre',
    message: '"Générer" rédige le contenu depuis zéro. "Enrichir" améliore votre texte existant. L\'IA utilise les documents de référence et le contexte du projet pour produire un contenu pertinent.',
    icon: 'smart_toy',
    position: 'top',
  },
  {
    id: 'chapter-qa',
    route: '/chapter/',
    selector: '[class*="qa"], [class*="question"], [class*="chat"]',
    title: 'Questions-Réponses 💬',
    message: 'Posez des questions à l\'IA sur le contenu de vos documents ! Par exemple : "Quelles sont les pénalités de retard ?" ou "Quel est le SLA demandé ?". L\'IA cherche dans tous vos documents pour vous répondre.',
    icon: 'question_answer',
    position: 'top',
  },
  {
    id: 'chapter-save',
    route: '/chapter/',
    selector: 'button:has(mat-icon[fontIcon="save"])',
    title: 'Sauvegarder votre travail',
    message: 'N\'oubliez pas de sauvegarder régulièrement ! Vous pouvez aussi changer le statut du chapitre : En cours, Terminé, À relire ou Validé.',
    icon: 'save',
    position: 'bottom',
  },
  // ── Compliance page ──
  {
    id: 'compliance-page',
    route: '/compliance',
    selector: '.page-container, .compliance',
    title: 'Matrice de conformité',
    message: 'Cette vue liste toutes les exigences du cahier des charges et vérifie point par point si votre réponse y répond. Les scores sont calculés automatiquement par l\'IA. Lancez l\'analyse pour obtenir un rapport complet.',
    icon: 'checklist',
    position: 'top',
  },
  // ── Gap analysis page ──
  {
    id: 'gap-page',
    route: '/gap-analysis',
    selector: '.page-container, .gap',
    title: 'Résultats de l\'analyse d\'écarts',
    message: 'Visualisez les différences entre l\'ancien et le nouvel AO. Les éléments sont classés par catégorie : ajouté, modifié, supprimé, inchangé. Cela vous aide à prioriser votre rédaction.',
    icon: 'difference',
    position: 'top',
  },
  // ── Statistics page ──
  {
    id: 'stats-page',
    route: '/statistics',
    selector: '.page-container, .stats',
    title: 'Vue d\'ensemble statistique',
    message: 'Graphiques et indicateurs de progression de votre projet. Suivez le taux de complétion des chapitres, la couverture des exigences et le score de conformité global.',
    icon: 'monitoring',
    position: 'top',
  },
  // ── Final step ──
  {
    id: 'guide-complete',
    route: '*',
    selector: 'body',
    title: 'Vous êtes prêt ! 🚀',
    message: 'Vous connaissez maintenant les principales fonctionnalités de RFP Assistant. N\'hésitez pas à réactiver ce guide à tout moment depuis le bouton en bas à droite. Bonne rédaction !',
    icon: 'celebration',
    position: 'bottom',
  },
];

@Injectable({ providedIn: 'root' })
export class OnboardingService {
  private readonly STORAGE_KEY = 'rfp_onboarding_state';

  private stateSubject = new BehaviorSubject<OnboardingState>(this.loadState());
  state$ = this.stateSubject.asObservable();

  private currentRoute = '';

  constructor(private router: Router) {
    this.router.events.pipe(
      filter((e): e is NavigationEnd => e instanceof NavigationEnd),
    ).subscribe((e) => {
      this.currentRoute = e.urlAfterRedirects;
    });
  }

  private loadState(): OnboardingState {
    try {
      const saved = localStorage.getItem(this.STORAGE_KEY);
      if (saved) return JSON.parse(saved);
    } catch {}
    return { active: false, currentStepIndex: 0, completedSteps: [], dismissed: false };
  }

  private saveState(state: OnboardingState): void {
    localStorage.setItem(this.STORAGE_KEY, JSON.stringify(state));
    this.stateSubject.next(state);
  }

  get state(): OnboardingState {
    return this.stateSubject.value;
  }

  get allSteps(): OnboardingStep[] {
    return ALL_STEPS;
  }

  get currentStep(): OnboardingStep | null {
    const s = this.state;
    if (!s.active || s.currentStepIndex >= ALL_STEPS.length) return null;
    return ALL_STEPS[s.currentStepIndex];
  }

  getStepsForRoute(route: string): OnboardingStep[] {
    return ALL_STEPS.filter((s) => {
      if (s.route === '*') return true;
      return route.startsWith(s.route) || route.includes(s.route);
    });
  }

  startGuide(): void {
    this.saveState({ active: true, currentStepIndex: 0, completedSteps: [], dismissed: false });
  }

  stopGuide(): void {
    const s = this.state;
    this.saveState({ ...s, active: false, dismissed: true });
  }

  toggleGuide(): void {
    if (this.state.active) {
      this.stopGuide();
    } else {
      this.startGuide();
    }
  }

  nextStep(): void {
    const s = this.state;
    if (!s.active) return;
    const step = ALL_STEPS[s.currentStepIndex];
    const completed = step ? [...s.completedSteps, step.id] : s.completedSteps;
    const next = s.currentStepIndex + 1;
    if (next >= ALL_STEPS.length) {
      this.saveState({ ...s, active: false, currentStepIndex: 0, completedSteps: completed, dismissed: true });
    } else {
      this.saveState({ ...s, currentStepIndex: next, completedSteps: completed });
    }
  }

  prevStep(): void {
    const s = this.state;
    if (!s.active || s.currentStepIndex <= 0) return;
    this.saveState({ ...s, currentStepIndex: s.currentStepIndex - 1 });
  }

  goToStep(index: number): void {
    const s = this.state;
    if (index >= 0 && index < ALL_STEPS.length) {
      this.saveState({ ...s, currentStepIndex: index, active: true });
    }
  }

  /** Find the first step that matches the current route */
  jumpToRouteStep(route: string): void {
    const s = this.state;
    if (!s.active) return;
    const idx = ALL_STEPS.findIndex((step) =>
      route.startsWith(step.route) || route.includes(step.route),
    );
    if (idx >= 0 && idx !== s.currentStepIndex) {
      this.saveState({ ...s, currentStepIndex: idx });
    }
  }

  isFirstVisit(): boolean {
    return !localStorage.getItem(this.STORAGE_KEY);
  }

  resetGuide(): void {
    localStorage.removeItem(this.STORAGE_KEY);
    this.stateSubject.next({ active: false, currentStepIndex: 0, completedSteps: [], dismissed: false });
  }
}
