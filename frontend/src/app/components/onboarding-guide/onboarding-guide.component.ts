import { Component, OnInit, OnDestroy, HostListener, ViewEncapsulation } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, NavigationEnd } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Subscription } from 'rxjs';
import { filter } from 'rxjs/operators';
import { OnboardingService, OnboardingStep, OnboardingState } from '../../services/onboarding.service';

@Component({
  selector: 'app-onboarding-guide',
  standalone: true,
  imports: [CommonModule, MatButtonModule, MatIconModule, MatTooltipModule],
  encapsulation: ViewEncapsulation.None,
  template: `
    <!-- Floating toggle button -->
    <button class="onboarding-fab" (click)="toggleGuide()"
      [class.active]="state.active"
      [class.has-steps]="!state.active && pageSteps.length > 0 && !pageCompleted"
      [matTooltip]="state.active ? 'Désactiver le guide' : (pageSteps.length > 0 ? 'Lancer le guide pour cette page' : 'Pas de guide sur cette page')">
      <div class="fab-avatar" [class.waving]="state.active && showWave">
        <svg viewBox="0 0 64 64" class="avatar-svg">
          <!-- Body -->
          <ellipse cx="32" cy="56" rx="18" ry="8" fill="#1976d2"/>
          <!-- Head -->
          <circle cx="32" cy="24" r="16" fill="#FFD54F"/>
          <!-- Eyes -->
          <ellipse cx="26" cy="22" rx="2.5" ry="3" fill="#333">
            <animate attributeName="ry" values="3;0.5;3" dur="3s" repeatCount="indefinite"/>
          </ellipse>
          <ellipse cx="38" cy="22" rx="2.5" ry="3" fill="#333">
            <animate attributeName="ry" values="3;0.5;3" dur="3s" repeatCount="indefinite"/>
          </ellipse>
          <!-- Smile -->
          <path d="M24 30 Q32 38 40 30" stroke="#333" stroke-width="2" fill="none" stroke-linecap="round"/>
          <!-- Glasses -->
          <circle cx="26" cy="22" r="5" stroke="#555" stroke-width="1.5" fill="none"/>
          <circle cx="38" cy="22" r="5" stroke="#555" stroke-width="1.5" fill="none"/>
          <line x1="31" y1="22" x2="33" y2="22" stroke="#555" stroke-width="1.5"/>
          <!-- Hand waving -->
          <g [attr.class]="state.active ? 'wave-hand' : ''">
            <circle cx="50" cy="34" r="4" fill="#FFD54F"/>
            <line x1="48" y1="38" x2="46" y2="46" stroke="#FFD54F" stroke-width="3" stroke-linecap="round"/>
          </g>
        </svg>
      </div>
      <span class="fab-label" *ngIf="!state.active">Guide</span>
      <span class="fab-badge" *ngIf="!state.active && pageSteps.length > 0 && !pageCompleted">
        {{ pageSteps.length }}
      </span>
    </button>

    <!-- Welcome modal for first visit -->
    <div class="onboarding-welcome-overlay" *ngIf="showFirstVisitModal" (click)="dismissWelcome()">
      <div class="onboarding-welcome-modal" (click)="$event.stopPropagation()">
        <div class="welcome-avatar-large">
          <svg viewBox="0 0 64 64" class="avatar-svg">
            <ellipse cx="32" cy="56" rx="18" ry="8" fill="#1976d2"/>
            <circle cx="32" cy="24" r="16" fill="#FFD54F"/>
            <ellipse cx="26" cy="22" rx="2.5" ry="3" fill="#333">
              <animate attributeName="ry" values="3;0.5;3" dur="3s" repeatCount="indefinite"/>
            </ellipse>
            <ellipse cx="38" cy="22" rx="2.5" ry="3" fill="#333">
              <animate attributeName="ry" values="3;0.5;3" dur="3s" repeatCount="indefinite"/>
            </ellipse>
            <path d="M24 30 Q32 38 40 30" stroke="#333" stroke-width="2" fill="none" stroke-linecap="round"/>
            <circle cx="26" cy="22" r="5" stroke="#555" stroke-width="1.5" fill="none"/>
            <circle cx="38" cy="22" r="5" stroke="#555" stroke-width="1.5" fill="none"/>
            <line x1="31" y1="22" x2="33" y2="22" stroke="#555" stroke-width="1.5"/>
          </svg>
        </div>
        <h2>Bienvenue sur RFP Assistant !</h2>
        <p>Je suis votre assistant personnel. Je peux vous guider à travers toutes les fonctionnalités de l'application.</p>
        <p class="welcome-sub">Sur chaque page, je vous expliquerai ce que vous pouvez faire. Souhaitez-vous commencer ?</p>
        <div class="welcome-actions">
          <button class="welcome-btn secondary" (click)="dismissWelcome()">Plus tard</button>
          <button class="welcome-btn primary" (click)="startTour()">Oui, guidez-moi !</button>
        </div>
      </div>
    </div>

    <!-- Step tooltip overlay -->
    <ng-container *ngIf="state.active && currentStep && pageSteps.length > 0">
      <div class="onboarding-backdrop" (click)="onboardingService.nextStep()"></div>

      <div class="onboarding-spotlight" *ngIf="spotlightStyle"
        [style.top]="spotlightStyle.top"
        [style.left]="spotlightStyle.left"
        [style.width]="spotlightStyle.width"
        [style.height]="spotlightStyle.height">
      </div>

      <div class="onboarding-tooltip" [class]="'position-' + tooltipPosition"
        [style.top]="tooltipStyle.top"
        [style.left]="tooltipStyle.left"
        [class.animate-in]="animateTooltip">
        <div class="tooltip-avatar">
          <svg viewBox="0 0 64 64" class="avatar-svg-small">
            <circle cx="32" cy="24" r="16" fill="#FFD54F"/>
            <ellipse cx="26" cy="22" rx="2.5" ry="3" fill="#333">
              <animate attributeName="ry" values="3;0.5;3" dur="3s" repeatCount="indefinite"/>
            </ellipse>
            <ellipse cx="38" cy="22" rx="2.5" ry="3" fill="#333">
              <animate attributeName="ry" values="3;0.5;3" dur="3s" repeatCount="indefinite"/>
            </ellipse>
            <path d="M24 30 Q32 38 40 30" stroke="#333" stroke-width="2" fill="none" stroke-linecap="round"/>
            <circle cx="26" cy="22" r="5" stroke="#555" stroke-width="1.5" fill="none"/>
            <circle cx="38" cy="22" r="5" stroke="#555" stroke-width="1.5" fill="none"/>
            <line x1="31" y1="22" x2="33" y2="22" stroke="#555" stroke-width="1.5"/>
          </svg>
        </div>
        <div class="tooltip-content">
          <div class="tooltip-header">
            <mat-icon class="tooltip-icon">{{ currentStep.icon }}</mat-icon>
            <h3>{{ currentStep.title }}</h3>
          </div>
          <p>{{ currentStep.message }}</p>
          <div class="tooltip-footer">
            <div class="step-indicators">
              <span *ngFor="let s of pageSteps; let i = index"
                class="step-dot"
                [class.active]="s.id === currentStep.id"
                [class.completed]="state.completedSteps.includes(s.id)"
                (click)="goToStep(s.id)">
              </span>
            </div>
            <div class="tooltip-nav">
              <span class="step-counter">{{ currentPageIndex + 1 }} / {{ pageSteps.length }}</span>
              <span class="global-progress" *ngIf="globalCompletedCount > 0" matTooltip="Progression globale">
                ({{ globalCompletedCount }}/{{ globalTotalCount }} au total)
              </span>
              <button class="tooltip-btn" (click)="onboardingService.prevStep()" [disabled]="currentPageIndex === 0">
                <mat-icon>chevron_left</mat-icon>
              </button>
              <button class="tooltip-btn primary" (click)="onboardingService.nextStep()">
                {{ isLastStepOnPage ? 'Compris !' : 'Suivant' }}
                <mat-icon>{{ isLastStepOnPage ? 'check' : 'chevron_right' }}</mat-icon>
              </button>
              <button class="tooltip-btn dismiss" (click)="onboardingService.stopGuide()" matTooltip="Fermer le guide">
                <mat-icon>close</mat-icon>
              </button>
            </div>
          </div>
        </div>
      </div>
    </ng-container>
  `,
  styles: [`
    /* ── Floating action button ── */
    .onboarding-fab {
      position: fixed;
      bottom: 24px;
      right: 24px;
      z-index: 9999;
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 16px 8px 8px;
      border: none;
      border-radius: 28px;
      background: linear-gradient(135deg, #1976d2, #1565c0);
      color: white;
      cursor: pointer;
      box-shadow: 0 4px 16px rgba(25, 118, 210, 0.4);
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      font-family: 'Roboto', sans-serif;
      font-size: 14px;
      font-weight: 500;
    }
    .onboarding-fab:hover {
      transform: scale(1.05);
      box-shadow: 0 6px 24px rgba(25, 118, 210, 0.5);
    }
    .onboarding-fab.active {
      background: linear-gradient(135deg, #43a047, #388e3c);
      box-shadow: 0 4px 16px rgba(67, 160, 71, 0.4);
      padding: 8px;
    }
    .onboarding-fab.active:hover {
      box-shadow: 0 6px 24px rgba(67, 160, 71, 0.5);
    }
    .onboarding-fab.has-steps {
      animation: fabPulse 3s ease-in-out infinite;
    }
    @keyframes fabPulse {
      0%, 100% { box-shadow: 0 4px 16px rgba(25, 118, 210, 0.4); }
      50% { box-shadow: 0 4px 24px rgba(25, 118, 210, 0.7); }
    }

    .fab-avatar {
      width: 36px; height: 36px;
      border-radius: 50%;
      background: white;
      padding: 2px;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .fab-avatar.waving { animation: fabBounce 2s ease-in-out infinite; }
    .fab-label { white-space: nowrap; }
    .fab-badge {
      position: absolute;
      top: -4px;
      right: -4px;
      background: #ff5722;
      color: white;
      border-radius: 50%;
      width: 20px;
      height: 20px;
      font-size: 11px;
      font-weight: 700;
      display: flex;
      align-items: center;
      justify-content: center;
      border: 2px solid white;
    }

    .avatar-svg, .avatar-svg-small { width: 100%; height: 100%; }

    @keyframes fabBounce {
      0%, 100% { transform: translateY(0); }
      50% { transform: translateY(-4px); }
    }

    .wave-hand {
      animation: waveAnimation 1.5s ease-in-out infinite;
      transform-origin: 46px 46px;
    }
    @keyframes waveAnimation {
      0%, 100% { transform: rotate(0deg); }
      25% { transform: rotate(20deg); }
      50% { transform: rotate(-10deg); }
      75% { transform: rotate(15deg); }
    }

    /* ── First visit modal ── */
    .onboarding-welcome-overlay {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.6);
      z-index: 10001;
      display: flex;
      align-items: center;
      justify-content: center;
      animation: fadeInOverlay 0.3s ease;
    }
    @keyframes fadeInOverlay {
      from { opacity: 0; }
      to { opacity: 1; }
    }

    .onboarding-welcome-modal {
      background: white;
      border-radius: 20px;
      padding: 40px;
      max-width: 460px;
      width: 90%;
      text-align: center;
      animation: modalSlideUp 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
      box-shadow: 0 24px 48px rgba(0, 0, 0, 0.2);
    }
    @keyframes modalSlideUp {
      from { opacity: 0; transform: translateY(40px) scale(0.95); }
      to { opacity: 1; transform: translateY(0) scale(1); }
    }

    .welcome-avatar-large {
      width: 100px; height: 100px;
      margin: 0 auto 20px;
      background: #e3f2fd;
      border-radius: 50%;
      padding: 10px;
      animation: avatarFloat 3s ease-in-out infinite;
    }
    @keyframes avatarFloat {
      0%, 100% { transform: translateY(0); }
      50% { transform: translateY(-8px); }
    }

    .onboarding-welcome-modal h2 {
      color: #1B3A5C;
      font-size: 24px;
      margin: 0 0 12px;
    }
    .onboarding-welcome-modal p {
      color: #555;
      font-size: 15px;
      line-height: 1.6;
      margin: 0 0 8px;
    }
    .welcome-sub {
      color: #1976d2 !important;
      font-weight: 500;
      margin-top: 12px !important;
    }
    .welcome-actions {
      display: flex;
      gap: 12px;
      justify-content: center;
      margin-top: 24px;
    }
    .welcome-btn {
      padding: 12px 28px;
      border-radius: 12px;
      font-size: 15px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s;
      border: none;
      font-family: 'Roboto', sans-serif;
    }
    .welcome-btn.primary {
      background: linear-gradient(135deg, #1976d2, #1565c0);
      color: white;
      box-shadow: 0 4px 12px rgba(25, 118, 210, 0.3);
    }
    .welcome-btn.primary:hover {
      transform: translateY(-2px);
      box-shadow: 0 6px 16px rgba(25, 118, 210, 0.4);
    }
    .welcome-btn.secondary {
      background: #f5f5f5;
      color: #666;
    }
    .welcome-btn.secondary:hover { background: #e0e0e0; }

    /* ── Backdrop & Spotlight ── */
    .onboarding-backdrop {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.45);
      z-index: 10000;
      cursor: pointer;
    }

    .onboarding-spotlight {
      position: fixed;
      z-index: 10001;
      border-radius: 8px;
      box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.45);
      background: transparent;
      pointer-events: none;
      transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    }

    /* ── Tooltip ── */
    .onboarding-tooltip {
      position: fixed;
      z-index: 10002;
      display: flex;
      gap: 12px;
      max-width: 440px;
      width: calc(100vw - 48px);
      animation: tooltipAppear 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
    }
    .onboarding-tooltip.animate-in {
      animation: tooltipAppear 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
    }
    @keyframes tooltipAppear {
      from { opacity: 0; transform: translateY(12px) scale(0.96); }
      to { opacity: 1; transform: translateY(0) scale(1); }
    }

    .tooltip-avatar {
      flex-shrink: 0;
      width: 48px; height: 48px;
      background: #e3f2fd;
      border-radius: 50%;
      padding: 4px;
      animation: avatarFloat 3s ease-in-out infinite;
    }

    .tooltip-content {
      flex: 1;
      background: white;
      border-radius: 16px;
      padding: 20px;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
      border: 2px solid #e3f2fd;
    }

    .tooltip-header {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 8px;
    }
    .tooltip-icon {
      color: #1976d2;
      font-size: 22px;
      width: 22px;
      height: 22px;
    }
    .tooltip-content h3 {
      margin: 0;
      font-size: 16px;
      color: #1B3A5C;
      font-weight: 600;
    }
    .tooltip-content p {
      margin: 0 0 16px;
      font-size: 14px;
      line-height: 1.6;
      color: #555;
    }

    .tooltip-footer {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .step-indicators {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      justify-content: center;
    }
    .step-dot {
      width: 8px; height: 8px;
      border-radius: 50%;
      background: #ddd;
      cursor: pointer;
      transition: all 0.2s;
    }
    .step-dot.active {
      background: #1976d2;
      transform: scale(1.4);
    }
    .step-dot.completed { background: #43a047; }
    .step-dot:hover { transform: scale(1.5); }

    .tooltip-nav {
      display: flex;
      align-items: center;
      gap: 8px;
      justify-content: flex-end;
    }
    .step-counter {
      font-size: 12px;
      color: #999;
      margin-right: auto;
    }
    .global-progress {
      font-size: 11px;
      color: #bbb;
      margin-right: auto;
    }

    .tooltip-btn {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 6px 14px;
      border: 1px solid #ddd;
      border-radius: 8px;
      background: white;
      color: #555;
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s;
      font-family: 'Roboto', sans-serif;
    }
    .tooltip-btn:hover:not(:disabled) { background: #f5f5f5; border-color: #bbb; }
    .tooltip-btn:disabled { opacity: 0.4; cursor: not-allowed; }
    .tooltip-btn mat-icon { font-size: 18px; width: 18px; height: 18px; }

    .tooltip-btn.primary {
      background: linear-gradient(135deg, #1976d2, #1565c0);
      color: white;
      border-color: transparent;
    }
    .tooltip-btn.primary:hover:not(:disabled) {
      background: linear-gradient(135deg, #1e88e5, #1976d2);
      box-shadow: 0 2px 8px rgba(25, 118, 210, 0.3);
    }

    .tooltip-btn.dismiss {
      padding: 6px;
      border-color: transparent;
      color: #999;
    }
    .tooltip-btn.dismiss:hover { color: #d32f2f; background: #ffebee; }
  `],
})
export class OnboardingGuideComponent implements OnInit, OnDestroy {
  state: OnboardingState = { active: false, currentStepId: '', completedSteps: [], dismissed: false };
  currentStep: OnboardingStep | null = null;
  pageSteps: OnboardingStep[] = [];
  showWave = true;
  showFirstVisitModal = false;
  animateTooltip = false;
  pageCompleted = false;

  spotlightStyle: { top: string; left: string; width: string; height: string } | null = null;
  tooltipStyle = { top: '50%', left: '50%' };
  tooltipPosition = 'bottom';

  private subs: Subscription[] = [];
  private positionInterval: ReturnType<typeof setInterval> | null = null;

  constructor(
    public onboardingService: OnboardingService,
    private router: Router,
  ) {}

  ngOnInit(): void {
    // Check first visit
    if (this.onboardingService.isFirstVisit()) {
      setTimeout(() => this.showFirstVisitModal = true, 1500);
    }

    // React to state changes
    this.subs.push(
      this.onboardingService.state$.subscribe((s) => {
        this.state = s;
        this.currentStep = this.onboardingService.currentStep;
        this.pageSteps = this.onboardingService.currentPageSteps;
        this.pageCompleted = this.onboardingService.currentPageCompleted;

        if (s.active && this.currentStep) {
          this.animateTooltip = false;
          setTimeout(() => {
            this.updatePosition();
            this.animateTooltip = true;
          }, 50);
        } else {
          this.spotlightStyle = null;
        }
      }),
    );

    // React to route changes
    this.subs.push(
      this.onboardingService.currentRoute$.subscribe(() => {
        this.pageSteps = this.onboardingService.currentPageSteps;
        this.pageCompleted = this.onboardingService.currentPageCompleted;
        if (this.state.active) {
          setTimeout(() => this.updatePosition(), 400);
        }
      }),
    );

    // Periodically update position in case of layout shifts
    this.positionInterval = setInterval(() => {
      if (this.state.active && this.currentStep) {
        this.updatePosition();
      }
    }, 2000);
  }

  ngOnDestroy(): void {
    this.subs.forEach((s) => s.unsubscribe());
    if (this.positionInterval) clearInterval(this.positionInterval);
  }

  @HostListener('window:resize')
  onResize(): void {
    if (this.state.active) this.updatePosition();
  }

  @HostListener('window:scroll')
  onScroll(): void {
    if (this.state.active) this.updatePosition();
  }

  toggleGuide(): void {
    this.onboardingService.toggleGuide();
  }

  dismissWelcome(): void {
    this.showFirstVisitModal = false;
    this.onboardingService.stopGuide();
  }

  startTour(): void {
    this.showFirstVisitModal = false;
    this.onboardingService.startGuide();
  }

  goToStep(stepId: string): void {
    this.onboardingService.goToStep(stepId);
  }

  get currentPageIndex(): number {
    return this.onboardingService.currentPageStepIndex;
  }

  get isLastStepOnPage(): boolean {
    return this.currentPageIndex >= this.pageSteps.length - 1;
  }

  get globalCompletedCount(): number {
    return this.onboardingService.completedStepCount;
  }

  get globalTotalCount(): number {
    return this.onboardingService.totalStepCount;
  }

  private updatePosition(): void {
    if (!this.currentStep) return;

    const selectors = this.currentStep.selector.split(',').map((s) => s.trim());
    let el: Element | null = null;
    for (const sel of selectors) {
      try {
        el = document.querySelector(sel);
      } catch { /* invalid selector, skip */ }
      if (el) break;
    }

    if (!el) {
      // Element not found - show centered floating tooltip
      this.spotlightStyle = null;
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      this.tooltipStyle = { top: Math.round(vh * 0.35) + 'px', left: Math.max(24, Math.round((vw - 440) / 2)) + 'px' };
      this.tooltipPosition = 'bottom';
      return;
    }

    const rect = el.getBoundingClientRect();
    const pad = 8;

    this.spotlightStyle = {
      top: (rect.top - pad) + 'px',
      left: (rect.left - pad) + 'px',
      width: (rect.width + pad * 2) + 'px',
      height: (rect.height + pad * 2) + 'px',
    };

    const tooltipWidth = 440;
    const tooltipHeight = 220;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    let top: number;
    let left: number;

    const pos = this.currentStep.position;

    if (pos === 'bottom' && rect.bottom + tooltipHeight + 20 < vh) {
      top = rect.bottom + 16;
      left = Math.max(24, Math.min(rect.left, vw - tooltipWidth - 24));
      this.tooltipPosition = 'bottom';
    } else if (pos === 'top' && rect.top - tooltipHeight - 20 > 0) {
      top = rect.top - tooltipHeight - 16;
      left = Math.max(24, Math.min(rect.left, vw - tooltipWidth - 24));
      this.tooltipPosition = 'top';
    } else if (rect.bottom + tooltipHeight + 20 < vh) {
      top = rect.bottom + 16;
      left = Math.max(24, Math.min(rect.left, vw - tooltipWidth - 24));
      this.tooltipPosition = 'bottom';
    } else {
      top = Math.max(24, rect.top - tooltipHeight - 16);
      left = Math.max(24, Math.min(rect.left, vw - tooltipWidth - 24));
      this.tooltipPosition = 'top';
    }

    this.tooltipStyle = { top: top + 'px', left: left + 'px' };

    // Scroll element into view if needed
    if (rect.top < 0 || rect.bottom > vh) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }
}
