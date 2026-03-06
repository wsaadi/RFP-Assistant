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
  /** If set, the step only shows when this tab label is active (Angular Material mdc-tab--active) */
  tabLabel?: string;
}

export interface OnboardingState {
  active: boolean;
  currentStepId: string;
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
    title: 'Créer un workspace',
    message: 'Cliquez ici pour créer un nouvel espace de travail. Donnez-lui un nom parlant comme "AO Transport 2025".',
    icon: 'add_circle',
    position: 'bottom',
  },

  // ── Workspace detail – always visible (header) ──
  {
    id: 'workspace-admin-actions',
    route: '/workspace/',
    selector: '.header-actions button[color="primary"], .header-actions button[color="accent"]',
    title: 'Actions administrateur',
    message: 'En tant qu\'administrateur, vous pouvez importer un projet depuis un backup, configurer les paramètres IA du workspace et modifier ses propriétés.',
    icon: 'admin_panel_settings',
    position: 'bottom',
  },

  // ── Workspace detail – Projets tab ──
  {
    id: 'workspace-detail-projects',
    route: '/workspace/',
    selector: '.project-grid',
    title: 'Les projets du workspace',
    message: 'Ici vous retrouvez tous les projets de réponse à appel d\'offres. Chaque projet correspond à un AO spécifique avec ses documents, chapitres et analyses. Cliquez pour y accéder.',
    icon: 'assignment',
    position: 'top',
    tabLabel: 'Projets',
  },
  {
    id: 'create-project',
    route: '/workspace/',
    selector: '.create-form, button:has(mat-icon)',
    title: 'Créer un projet',
    message: 'Cliquez sur "Nouveau projet" pour démarrer un projet de réponse à appel d\'offres. Renseignez le nom du client, la référence de l\'AO et la date limite.',
    icon: 'note_add',
    position: 'bottom',
    tabLabel: 'Projets',
  },

  // ── Workspace detail – Membres tab ──
  {
    id: 'workspace-members-manage',
    route: '/workspace/',
    selector: '.members-list .role-inline-field',
    title: 'Gérer les membres',
    message: 'En tant que propriétaire ou admin, vous pouvez ajouter des collaborateurs et changer leurs rôles : Propriétaire, Éditeur ou Lecteur. Chacun aura des droits adaptés.',
    icon: 'group_add',
    position: 'top',
    tabLabel: 'Membres',
  },
  {
    id: 'workspace-members-view',
    route: '/workspace/',
    selector: '.members-list',
    title: 'Les membres du workspace',
    message: 'Voici la liste des membres de cet espace de travail. Chaque membre a un rôle qui détermine ses droits d\'accès aux projets.',
    icon: 'group',
    position: 'top',
    tabLabel: 'Membres',
  },

  // ── Project dashboard – header (always visible, no tabLabel) ──
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
    id: 'project-stats',
    route: '/project/',
    selector: '.stats-row',
    title: 'Statistiques rapides',
    message: 'Un aperçu en un coup d\'œil : nombre de documents, chapitres, pourcentage de complétion et nombre de mots rédigés.',
    icon: 'analytics',
    position: 'bottom',
  },
  {
    id: 'project-actions',
    route: '/project/',
    selector: '.header-actions',
    title: 'Actions du projet',
    message: 'Exportez en Word (DOCX), sauvegardez (Backup), consultez les images extraites, prévisualisez le document ou préparez une soutenance PowerPoint.',
    icon: 'apps',
    position: 'bottom',
  },

  // ── Project – Documents tab ──
  {
    id: 'upload-documents',
    route: '/project/',
    selector: '.upload-section',
    title: 'Charger vos documents 📄',
    message: 'Commencez par uploader les documents de l\'appel d\'offres (CCTP, RC, BPU...) et vos anciens documents de réponse. Classez-les par catégorie pour aider l\'IA à mieux les utiliser.',
    icon: 'upload_file',
    position: 'top',
    tabLabel: 'Documents',
  },
  {
    id: 'upload-categories',
    route: '/project/',
    selector: '.upload-categories',
    title: 'Les catégories de documents',
    message: 'Chaque carte correspond à un type de document : Ancien AO, Nouvel AO, Ancienne réponse, Nouvelle réponse, Inspiration. Glissez-déposez ou cliquez pour sélectionner.',
    icon: 'category',
    position: 'bottom',
    tabLabel: 'Documents',
  },

  // ── Project – Livrables tab ──
  {
    id: 'livrables-detect',
    route: '/project/',
    selector: 'button:has(mat-icon[fontIcon="find_in_page"])',
    title: 'Détecter les livrables',
    message: 'Cliquez pour laisser l\'IA analyser l\'appel d\'offres et identifier tous les documents à produire (mémoire technique, BPU, planning...). C\'est la première étape !',
    icon: 'find_in_page',
    position: 'bottom',
    tabLabel: 'Livrables',
  },
  {
    id: 'livrables-list',
    route: '/project/',
    selector: '.response-doc-card, .deliverable-card',
    title: 'Vos livrables à produire',
    message: 'Les livrables détectés apparaissent ici. Cochez ceux à compléter et lancez le pré-remplissage pour que l\'IA complète les sections manquantes.',
    icon: 'description',
    position: 'top',
    tabLabel: 'Livrables',
  },

  // ── Project – Structure tab ──
  {
    id: 'structure-generate',
    route: '/project/',
    selector: '.chapter-actions button[color="primary"]',
    title: 'Générer la structure ✨',
    message: 'L\'IA analyse le cahier des charges et crée automatiquement la structure de chapitres de votre réponse. Sélectionnez les documents de rédaction concernés.',
    icon: 'auto_fix_high',
    position: 'bottom',
    tabLabel: 'Structure',
  },
  {
    id: 'structure-chapters',
    route: '/project/',
    selector: '.chapter-list',
    title: 'Les chapitres de votre réponse',
    message: 'La liste de tous vos chapitres. Cochez ceux que vous souhaitez, puis utilisez "Générer IA" pour les rédiger ou "Pré-remplir" pour copier depuis vos anciens documents.',
    icon: 'menu_book',
    position: 'top',
    tabLabel: 'Structure',
  },
  {
    id: 'structure-ai-generate',
    route: '/project/',
    selector: '.chapter-actions button[color="accent"]',
    title: 'Génération IA des chapitres',
    message: 'Sélectionnez des chapitres puis cliquez "Générer IA" pour que l\'IA rédige le contenu. Elle s\'appuie sur vos documents de référence et le contexte du projet.',
    icon: 'auto_awesome',
    position: 'bottom',
    tabLabel: 'Structure',
  },

  // ── Project – Outils IA tab ──
  {
    id: 'ai-context',
    route: '/project/',
    selector: '.ai-context-card',
    title: 'Contexte IA du projet',
    message: 'Configurez le contexte IA : décrivez votre entreprise, vos points forts, le ton souhaité. L\'IA utilisera ces informations pour personnaliser toutes ses rédactions.',
    icon: 'psychology',
    position: 'bottom',
    tabLabel: 'Outils IA',
  },
  {
    id: 'ai-tools',
    route: '/project/',
    selector: '.tools-grid, .tool-card',
    title: 'Outils d\'analyse',
    message: 'Lancez l\'analyse de conformité (votre réponse couvre-t-elle toutes les exigences ?), l\'analyse d\'écarts (qu\'est-ce qui a changé ?) ou consultez les statistiques du projet.',
    icon: 'build',
    position: 'top',
    tabLabel: 'Outils IA',
  },

  // ── Project – Q&A Documents tab ──
  {
    id: 'qa-documents',
    route: '/project/',
    selector: '.qa-container',
    title: 'Questions-Réponses 💬',
    message: 'Posez des questions à l\'IA sur vos documents ! Par exemple : "Quelles sont les pénalités de retard ?" ou "Quels sont les SLA demandés ?". L\'IA cherche dans tous vos documents et cite ses sources.',
    icon: 'question_answer',
    position: 'top',
    tabLabel: 'Q&A Documents',
  },

  // ── Project – Membres tab ──
  {
    id: 'project-members-manage',
    route: '/project/',
    selector: '.member-source-info',
    title: 'Membres du projet',
    message: 'Gérez les accès au projet. Ajoutez des membres depuis l\'espace de travail et attribuez-leur un rôle : Propriétaire, Éditeur ou Lecteur.',
    icon: 'group',
    position: 'top',
    tabLabel: 'Membres',
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
    message: '"Générer" rédige le contenu depuis zéro. "Enrichir" améliore votre texte existant. L\'IA utilise les documents de référence et le contexte du projet.',
    icon: 'smart_toy',
    position: 'top',
  },
  {
    id: 'chapter-qa',
    route: '/chapter/',
    selector: '[class*="qa"], [class*="question"], [class*="chat"]',
    title: 'Questions-Réponses 💬',
    message: 'Posez des questions à l\'IA sur le contenu de vos documents ! L\'IA cherche dans tous vos documents pour vous répondre avec les sources.',
    icon: 'question_answer',
    position: 'top',
  },
  {
    id: 'chapter-save',
    route: '/chapter/',
    selector: 'button:has(mat-icon[fontIcon="save"])',
    title: 'Sauvegarder votre travail',
    message: 'N\'oubliez pas de sauvegarder ! Vous pouvez aussi changer le statut du chapitre : En cours, Terminé, À relire ou Validé.',
    icon: 'save',
    position: 'bottom',
  },

  // ── Compliance page ──
  {
    id: 'compliance-page',
    route: '/compliance',
    selector: '.page-container, .compliance',
    title: 'Matrice de conformité',
    message: 'Cette vue liste toutes les exigences du cahier des charges et vérifie point par point si votre réponse y répond. Lancez l\'analyse pour obtenir un rapport complet.',
    icon: 'checklist',
    position: 'top',
  },
  // ── Gap analysis page ──
  {
    id: 'gap-page',
    route: '/gap-analysis',
    selector: '.page-container, .gap',
    title: 'Résultats de l\'analyse d\'écarts',
    message: 'Les différences entre l\'ancien et le nouvel AO. Classées par catégorie : ajouté, modifié, supprimé, inchangé. Cela vous aide à prioriser votre rédaction.',
    icon: 'difference',
    position: 'top',
  },
  // ── Statistics page ──
  {
    id: 'stats-page',
    route: '/statistics',
    selector: '.page-container, .stats',
    title: 'Vue d\'ensemble statistique',
    message: 'Graphiques et indicateurs de progression. Suivez la complétion des chapitres, la couverture des exigences et le score de conformité global.',
    icon: 'monitoring',
    position: 'top',
  },
  // ── Image gallery page ──
  {
    id: 'images-page',
    route: '/images',
    selector: '.page-container, .gallery, .image',
    title: 'Galerie d\'images',
    message: 'Les images extraites de vos documents PDF. L\'IA Vision peut les analyser pour en extraire du texte et des informations utiles à la rédaction.',
    icon: 'photo_library',
    position: 'top',
  },
  // ── Soutenance page ──
  {
    id: 'soutenance-page',
    route: '/soutenance',
    selector: '.page-container, .soutenance',
    title: 'Préparation de soutenance',
    message: 'Générez automatiquement un PowerPoint de soutenance avec un script de présentation. L\'IA structure votre argumentaire.',
    icon: 'co_present',
    position: 'top',
  },
];

/** Check if a step's route pattern matches a given URL */
function stepMatchesRoute(step: OnboardingStep, url: string): boolean {
  if (step.route === '*') return true;
  return url.includes(step.route);
}

@Injectable({ providedIn: 'root' })
export class OnboardingService {
  private readonly STORAGE_KEY = 'rfp_onboarding_state';

  private stateSubject = new BehaviorSubject<OnboardingState>(this.loadState());
  state$ = this.stateSubject.asObservable();

  private currentRouteSubject = new BehaviorSubject<string>('');
  currentRoute$ = this.currentRouteSubject.asObservable();

  constructor(private router: Router) {
    this.router.events.pipe(
      filter((e): e is NavigationEnd => e instanceof NavigationEnd),
    ).subscribe((e) => {
      const prevRoute = this.currentRouteSubject.value;
      this.currentRouteSubject.next(e.urlAfterRedirects);

      if (this.state.active && prevRoute !== e.urlAfterRedirects) {
        const filtered = this.getStepsForRoute(e.urlAfterRedirects);
        if (filtered.length > 0) {
          const firstUncompleted = filtered.find(s => !this.state.completedSteps.includes(s.id));
          this.saveState({
            ...this.state,
            currentStepId: (firstUncompleted || filtered[0]).id,
          });
        }
      }
    });
  }

  private loadState(): OnboardingState {
    try {
      const saved = localStorage.getItem(this.STORAGE_KEY);
      if (saved) return JSON.parse(saved);
    } catch {}
    return { active: false, currentStepId: '', completedSteps: [], dismissed: false };
  }

  private saveState(state: OnboardingState): void {
    localStorage.setItem(this.STORAGE_KEY, JSON.stringify(state));
    this.stateSubject.next(state);
  }

  get state(): OnboardingState {
    return this.stateSubject.value;
  }

  get currentRoute(): string {
    return this.currentRouteSubject.value;
  }

  get allSteps(): OnboardingStep[] {
    return ALL_STEPS;
  }

  get currentPageSteps(): OnboardingStep[] {
    return this.getStepsForRoute(this.currentRoute);
  }

  get currentStep(): OnboardingStep | null {
    const s = this.state;
    if (!s.active || !s.currentStepId) return null;
    return ALL_STEPS.find(step => step.id === s.currentStepId) || null;
  }

  getStepsForRoute(route: string): OnboardingStep[] {
    return ALL_STEPS.filter(s => stepMatchesRoute(s, route));
  }

  get totalStepCount(): number {
    return ALL_STEPS.length;
  }

  get completedStepCount(): number {
    return this.state.completedSteps.length;
  }

  startGuide(): void {
    const filtered = this.getStepsForRoute(this.currentRoute);
    const firstId = filtered.length > 0 ? filtered[0].id : ALL_STEPS[0].id;
    this.saveState({ active: true, currentStepId: firstId, completedSteps: [], dismissed: false });
  }

  stopGuide(): void {
    this.saveState({ ...this.state, active: false, dismissed: true });
  }

  toggleGuide(): void {
    if (this.state.active) {
      this.stopGuide();
    } else {
      const filtered = this.getStepsForRoute(this.currentRoute);
      const firstUncompleted = filtered.find(s => !this.state.completedSteps.includes(s.id));
      const firstId = (firstUncompleted || filtered[0])?.id || ALL_STEPS[0].id;
      this.saveState({ active: true, currentStepId: firstId, completedSteps: this.state.completedSteps, dismissed: false });
    }
  }

  nextStepIn(visibleSteps: OnboardingStep[]): void {
    const s = this.state;
    if (!s.active) return;

    const currentIdx = visibleSteps.findIndex(step => step.id === s.currentStepId);
    const completed = s.currentStepId ? [...new Set([...s.completedSteps, s.currentStepId])] : s.completedSteps;

    if (currentIdx < visibleSteps.length - 1) {
      this.saveState({ ...s, currentStepId: visibleSteps[currentIdx + 1].id, completedSteps: completed });
    } else {
      this.saveState({ ...s, active: false, currentStepId: '', completedSteps: completed, dismissed: false });
    }
  }

  prevStepIn(visibleSteps: OnboardingStep[]): void {
    const s = this.state;
    if (!s.active) return;

    const currentIdx = visibleSteps.findIndex(step => step.id === s.currentStepId);
    if (currentIdx > 0) {
      this.saveState({ ...s, currentStepId: visibleSteps[currentIdx - 1].id });
    }
  }

  goToStep(stepId: string): void {
    const step = ALL_STEPS.find(s => s.id === stepId);
    if (step) {
      this.saveState({ ...this.state, currentStepId: stepId, active: true });
    }
  }

  isFirstVisit(): boolean {
    return !localStorage.getItem(this.STORAGE_KEY);
  }

  resetGuide(): void {
    localStorage.removeItem(this.STORAGE_KEY);
    this.stateSubject.next({ active: false, currentStepId: '', completedSteps: [], dismissed: false });
  }

  get currentPageCompleted(): boolean {
    const pageSteps = this.currentPageSteps;
    return pageSteps.length > 0 && pageSteps.every(s => this.state.completedSteps.includes(s.id));
  }

  get hasStepsForCurrentPage(): boolean {
    return this.currentPageSteps.length > 0;
  }
}
