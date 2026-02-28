import { Component, OnInit, OnDestroy, ViewEncapsulation, ElementRef, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatInputModule } from '@angular/material/input';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { Subscription, timer } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { ApiService } from '../../services/api.service';
import { renderMarkdown } from '../../services/markdown.service';
import { DocumentPreview, PreviewChapter } from '../../models/report.model';

interface ChatMessage {
  role: 'user' | 'assistant' | 'error';
  content: string;
  changedChapters?: string[];
  timestamp: Date;
}

@Component({
  selector: 'app-preview',
  standalone: true,
  imports: [
    CommonModule, FormsModule, RouterLink, MatCardModule, MatButtonModule, MatIconModule,
    MatProgressSpinnerModule, MatProgressBarModule, MatButtonToggleModule, MatTooltipModule,
    MatInputModule, MatSnackBarModule,
  ],
  encapsulation: ViewEncapsulation.None,
  template: `
    <div class="preview-layout" *ngIf="preview">
      <div class="preview-main" [class.chat-open]="chatOpen">
        <div class="preview-header no-print">
          <button mat-icon-button [routerLink]="['/project', projectId]"><mat-icon>arrow_back</mat-icon></button>
          <h1>Apercu du document</h1>

          <mat-button-toggle-group [(value)]="viewMode" (change)="onViewModeChange($event.value)" class="view-mode-toggle">
            <mat-button-toggle value="final" matTooltip="Contenu final avec les vraies valeurs">
              <mat-icon>visibility</mat-icon> Final
            </mat-button-toggle>
            <mat-button-toggle value="anonymized" matTooltip="Ce que l'IA Mistral voit (donnees sensibles masquees)">
              <mat-icon>security</mat-icon> Vue IA
            </mat-button-toggle>
          </mat-button-toggle-group>

          <button mat-raised-button color="primary" (click)="printPreview()">
            <mat-icon>print</mat-icon> Imprimer
          </button>
          <button mat-raised-button [color]="chatOpen ? 'accent' : ''" (click)="toggleChat()" class="chat-toggle-btn" matTooltip="Chat IA - Modifier le document">
            <mat-icon>chat</mat-icon> IA
          </button>
        </div>

        <div *ngIf="viewMode === 'anonymized'" class="anon-banner no-print">
          <mat-icon>security</mat-icon>
          <span>Vue anonymisee — C'est ce que l'IA Mistral voit. Les donnees sensibles sont remplacees par des placeholders.</span>
        </div>

        <div class="document-preview" [class.anon-mode]="viewMode === 'anonymized'">
          <!-- Cover page -->
          <div class="page cover-page">
            <h1 class="doc-title">REPONSE A L'APPEL D'OFFRES</h1>
            <h2 *ngIf="currentPreview.rfp_reference">Reference: {{ currentPreview.rfp_reference }}</h2>
            <h2 class="project-name">{{ currentPreview.project_name }}</h2>
            <div class="separator"></div>
            <p *ngIf="currentPreview.client_name">Client: {{ currentPreview.client_name }}</p>
            <p class="confidential">DOCUMENT CONFIDENTIEL</p>
          </div>

          <!-- TOC -->
          <div class="page toc-page">
            <h2>SOMMAIRE</h2>
            <div *ngFor="let ch of currentPreview.chapters" class="toc-entry" [class.toc-sub]="ch.level > 1">
              <span>{{ ch.numbering }} {{ ch.title }}</span>
              <ng-container *ngIf="ch.children?.length">
                <div *ngFor="let sub of ch.children" class="toc-entry toc-sub">
                  <span>{{ sub.numbering }} {{ sub.title }}</span>
                </div>
              </ng-container>
            </div>
          </div>

          <!-- Chapters -->
          <ng-container *ngFor="let ch of currentPreview.chapters">
            <div class="page">
              <h2 class="chapter-title">{{ ch.numbering }} {{ ch.title }}</h2>
              <div class="chapter-content" *ngIf="ch.content" [innerHTML]="renderMarkdown(ch.content)"></div>
              <p *ngIf="!ch.content" class="empty-content">[Section a completer]</p>

              <ng-container *ngFor="let sub of ch.children">
                <h3 class="sub-title">{{ sub.numbering }} {{ sub.title }}</h3>
                <div class="chapter-content" *ngIf="sub.content" [innerHTML]="renderMarkdown(sub.content)"></div>
                <p *ngIf="!sub.content" class="empty-content">[Section a completer]</p>
              </ng-container>
            </div>
          </ng-container>
        </div>
      </div>

      <!-- Chat panel -->
      <div class="chat-panel no-print" *ngIf="chatOpen">
        <div class="chat-header">
          <mat-icon>auto_awesome</mat-icon>
          <h3>Chat IA</h3>
          <span style="flex:1"></span>
          <button mat-icon-button (click)="toggleChat()" matTooltip="Fermer"><mat-icon>close</mat-icon></button>
        </div>

        <div class="chat-messages" #chatMessages>
          <div *ngIf="messages.length === 0" class="chat-empty">
            <mat-icon>auto_awesome</mat-icon>
            <p>Decrivez ce que vous voulez modifier dans le document.</p>
            <span class="chat-hint">L'IA identifiera les chapitres concernes et appliquera les changements.</span>
          </div>

          <div *ngFor="let msg of messages" class="chat-msg" [class.chat-msg-user]="msg.role === 'user'" [class.chat-msg-ai]="msg.role === 'assistant'" [class.chat-msg-error]="msg.role === 'error'">
            <div class="chat-msg-icon">
              <mat-icon *ngIf="msg.role === 'user'">person</mat-icon>
              <mat-icon *ngIf="msg.role === 'assistant'">auto_awesome</mat-icon>
              <mat-icon *ngIf="msg.role === 'error'">error</mat-icon>
            </div>
            <div class="chat-msg-body">
              <p>{{ msg.content }}</p>
              <div *ngIf="msg.changedChapters?.length" class="chat-changed">
                <span>Chapitres modifies :</span>
                <span class="chat-chip" *ngFor="let ch of msg.changedChapters">{{ ch }}</span>
              </div>
              <span class="chat-msg-time">{{ msg.timestamp | date:'HH:mm' }}</span>
            </div>
          </div>

          <!-- Progress indicator -->
          <div *ngIf="chatProcessing" class="chat-msg chat-msg-ai chat-msg-loading">
            <div class="chat-msg-icon"><mat-icon>auto_awesome</mat-icon></div>
            <div class="chat-msg-body">
              <mat-progress-bar mode="determinate" [value]="chatProgress?.progress || 0"></mat-progress-bar>
              <p class="chat-progress-msg">{{ chatProgress?.message || 'Traitement...' }}</p>
              <button mat-button color="warn" (click)="cancelChat()" class="chat-cancel-btn">
                <mat-icon>close</mat-icon> Annuler
              </button>
            </div>
          </div>
        </div>

        <div class="chat-input-area">
          <textarea
            class="chat-input"
            [(ngModel)]="chatInput"
            (keydown.enter)="onChatKeydown($event)"
            placeholder="Ex: Corrige la reference ISO dans tout le document..."
            [disabled]="chatProcessing"
            rows="2"
          ></textarea>
          <button mat-icon-button color="primary" (click)="sendMessage()" [disabled]="!chatInput.trim() || chatProcessing" matTooltip="Envoyer">
            <mat-icon>send</mat-icon>
          </button>
        </div>
      </div>
    </div>

    <div *ngIf="loading" class="loading-container"><mat-spinner diameter="40"></mat-spinner></div>
  `,
  styles: [`
    .preview-layout { display: flex; gap: 0; max-width: 1400px; margin: 0 auto; }
    .preview-main { flex: 1; min-width: 0; max-width: 900px; margin: 0 auto; transition: max-width 0.3s; }
    .preview-main.chat-open { max-width: 100%; margin: 0; }
    .preview-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
    .preview-header h1 { flex: 1; margin: 0; color: #1B3A5C; }
    .view-mode-toggle .mat-button-toggle-label-content { display: flex; align-items: center; gap: 4px; font-size: 13px; }
    .view-mode-toggle mat-icon { font-size: 18px; width: 18px; height: 18px; }
    .chat-toggle-btn mat-icon { margin-right: 4px; }
    .anon-banner { display: flex; align-items: center; gap: 8px; padding: 10px 16px; margin-bottom: 12px; background: #e8f5e9; border: 1px solid #a5d6a7; border-radius: 8px; color: #2e7d32; font-size: 13px; }
    .anon-banner mat-icon { color: #2e7d32; }
    .document-preview { background: white; box-shadow: 0 2px 8px rgba(0,0,0,0.1); border-radius: 4px; overflow: hidden; }
    .document-preview.anon-mode { border: 2px solid #a5d6a7; }
    .page { padding: 48px 56px; min-height: 600px; border-bottom: 1px solid #e0e0e0; }
    .cover-page { text-align: center; display: flex; flex-direction: column; justify-content: center; align-items: center; min-height: 700px; background: linear-gradient(180deg, #f8fafd 0%, #ffffff 100%); }
    .doc-title { font-size: 28px; color: #1B3A5C; letter-spacing: 0.5px; }
    .project-name { font-size: 22px; color: #2C5F8A; }
    .separator { width: 200px; height: 2px; background: #2C5F8A; margin: 24px 0; }
    .confidential { color: #990000; font-weight: bold; font-size: 12px; margin-top: 48px; }
    .toc-page h2 { color: #1B3A5C; margin-bottom: 24px; border-bottom: 2px solid #2C5F8A; padding-bottom: 8px; }
    .toc-entry { padding: 8px 0; border-bottom: 1px dotted #ddd; font-size: 15px; color: #333; }
    .toc-sub { padding-left: 28px; font-size: 14px; color: #555; }
    .chapter-title { color: #1B3A5C; font-size: 20px; border-bottom: 2px solid #2C5F8A; padding-bottom: 8px; margin-bottom: 16px; }
    .sub-title { color: #2C5F8A; font-size: 17px; margin-top: 28px; margin-bottom: 12px; padding-bottom: 4px; border-bottom: 1px solid #e0e0e0; }
    .chapter-content { line-height: 1.7; font-size: 14px; color: #333; }
    .chapter-content p { margin: 0 0 12px 0; line-height: 1.7; text-align: justify; }
    .chapter-content h2, .chapter-content h3 { font-size: 17px; font-weight: 700; color: #1B3A5C; margin: 24px 0 10px 0; padding-bottom: 4px; border-bottom: 1px solid #e0e0e0; }
    .chapter-content h2:first-child, .chapter-content h3:first-child { margin-top: 0; }
    .chapter-content h4 { font-size: 15px; font-weight: 600; color: #2C5F8A; margin: 18px 0 8px 0; }
    .chapter-content h5 { font-size: 14px; font-weight: 600; color: #37474f; margin: 14px 0 6px 0; }
    .chapter-content ul, .chapter-content ol { margin: 6px 0 12px 0; padding-left: 28px; }
    .chapter-content ul { list-style-type: disc; }
    .chapter-content ul ul { list-style-type: circle; margin: 2px 0; }
    .chapter-content ol { list-style-type: decimal; }
    .chapter-content li { margin-bottom: 4px; line-height: 1.6; }
    .chapter-content strong { color: #1B3A5C; }
    .chapter-content em { color: #555; }
    .chapter-content hr { border: none; border-top: 1px solid #ccc; margin: 20px 0; }
    .chapter-content code { background: #e8eaf6; padding: 1px 5px; border-radius: 3px; font-size: 13px; }
    .chapter-content .table-wrap { overflow-x: auto; margin: 16px 0; }
    .chapter-content table { border-collapse: collapse; width: 100%; font-size: 14px; }
    .chapter-content th, .chapter-content td { border: 1px solid #ccc; padding: 10px 12px; text-align: left; }
    .chapter-content th { background: #e3f2fd; color: #1B3A5C; font-weight: 600; }
    .chapter-content tr:nth-child(even) td { background: #fafafa; }
    .empty-content { color: #999; font-style: italic; }
    .loading-container { display: flex; justify-content: center; padding: 48px; }

    /* Chat panel */
    .chat-panel { width: 380px; min-width: 380px; border-left: 1px solid #e0e0e0; background: #fafafa; display: flex; flex-direction: column; height: calc(100vh - 32px); position: sticky; top: 16px; border-radius: 8px 0 0 8px; overflow: hidden; }
    .chat-header { display: flex; align-items: center; gap: 8px; padding: 12px 16px; background: #1B3A5C; color: white; }
    .chat-header h3 { margin: 0; font-size: 15px; }
    .chat-header mat-icon { font-size: 20px; width: 20px; height: 20px; }
    .chat-header button { color: white; }
    .chat-messages { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 12px; }
    .chat-empty { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 24px 12px; text-align: center; color: #888; }
    .chat-empty mat-icon { font-size: 40px; width: 40px; height: 40px; color: #1B3A5C; opacity: 0.5; }
    .chat-empty p { margin: 0; font-size: 14px; }
    .chat-hint { font-size: 12px; color: #aaa; margin-top: 8px; }

    .chat-msg { display: flex; gap: 8px; }
    .chat-msg-icon { padding-top: 2px; }
    .chat-msg-icon mat-icon { font-size: 18px; width: 18px; height: 18px; }
    .chat-msg-user .chat-msg-icon mat-icon { color: #1B3A5C; }
    .chat-msg-ai .chat-msg-icon mat-icon { color: #7b1fa2; }
    .chat-msg-error .chat-msg-icon mat-icon { color: #c62828; }
    .chat-msg-body { flex: 1; min-width: 0; }
    .chat-msg-user .chat-msg-body { background: #e3f2fd; border-radius: 8px; padding: 8px 12px; }
    .chat-msg-ai .chat-msg-body { background: #f3e5f5; border-radius: 8px; padding: 8px 12px; }
    .chat-msg-error .chat-msg-body { background: #ffebee; border-radius: 8px; padding: 8px 12px; }
    .chat-msg-body p { margin: 0; font-size: 13px; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }
    .chat-msg-time { font-size: 11px; color: #aaa; }
    .chat-changed { margin-top: 6px; display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
    .chat-changed > span:first-child { font-size: 11px; color: #7b1fa2; font-weight: 500; }
    .chat-chip { font-size: 11px; background: #ce93d8; color: white; padding: 2px 8px; border-radius: 10px; }
    .chat-msg-loading .chat-msg-body { background: #fff3e0; border-radius: 8px; padding: 10px 12px; }
    .chat-progress-msg { font-size: 12px; color: #e65100; margin-top: 6px; }
    .chat-cancel-btn { font-size: 12px; margin-top: 4px; }
    .chat-input-area { display: flex; gap: 4px; padding: 10px 12px; border-top: 1px solid #e0e0e0; background: white; align-items: flex-end; }
    .chat-input { flex: 1; border: 1px solid #ccc; border-radius: 8px; padding: 8px 12px; font-size: 13px; resize: none; font-family: inherit; outline: none; transition: border-color 0.2s; }
    .chat-input:focus { border-color: #1B3A5C; }
    .chat-input:disabled { background: #f5f5f5; }

    @media print { .no-print { display: none !important; } .page { border: none; page-break-after: always; } .preview-layout { display: block; } }
  `],
})
export class PreviewComponent implements OnInit, OnDestroy {
  @ViewChild('chatMessages') chatMessagesEl!: ElementRef;

  projectId = '';
  preview: DocumentPreview | null = null;
  anonPreview: DocumentPreview | null = null;
  loading = true;
  viewMode: 'final' | 'anonymized' = 'final';

  // Chat state
  chatOpen = false;
  chatInput = '';
  messages: ChatMessage[] = [];
  chatProcessing = false;
  chatProgress: { status: string; step: string; progress: number; message: string } | null = null;
  private chatPollSub: Subscription | null = null;

  constructor(
    private route: ActivatedRoute,
    private api: ApiService,
    private snackBar: MatSnackBar,
  ) {}

  get currentPreview(): DocumentPreview {
    return (this.viewMode === 'anonymized' && this.anonPreview) ? this.anonPreview : this.preview!;
  }

  ngOnInit(): void {
    this.projectId = this.route.snapshot.paramMap.get('projectId') || '';
    this.api.getPreview(this.projectId).subscribe({
      next: (p) => { this.preview = p; this.loading = false; },
      error: () => { this.loading = false; },
    });
  }

  ngOnDestroy(): void {
    this.stopChatPolling();
  }

  onViewModeChange(mode: 'final' | 'anonymized'): void {
    this.viewMode = mode;
    if (mode === 'anonymized' && !this.anonPreview) {
      this.loading = true;
      this.api.getPreview(this.projectId, true).subscribe({
        next: (p) => { this.anonPreview = p; this.loading = false; },
        error: () => { this.loading = false; },
      });
    }
  }

  printPreview(): void {
    window.print();
  }

  toggleChat(): void {
    this.chatOpen = !this.chatOpen;
  }

  sendMessage(): void {
    const msg = this.chatInput.trim();
    if (!msg || this.chatProcessing) return;

    this.messages.push({ role: 'user', content: msg, timestamp: new Date() });
    this.chatInput = '';
    this.chatProcessing = true;
    this.chatProgress = { status: 'running', step: 'starting', progress: 0, message: 'Envoi...' };
    this.scrollToBottom();

    this.api.sendPreviewChat(this.projectId, msg).subscribe({
      next: () => {
        this.startChatPolling();
      },
      error: (err) => {
        if (err.status === 409) {
          // Stale progress in Redis — cancel then retry once
          this.api.cancelPreviewChat(this.projectId).subscribe({
            next: () => {
              this.api.sendPreviewChat(this.projectId, msg).subscribe({
                next: () => this.startChatPolling(),
                error: (err2) => {
                  this.chatProcessing = false;
                  this.chatProgress = null;
                  this.messages.push({ role: 'error', content: err2.error?.detail || 'Erreur', timestamp: new Date() });
                  this.scrollToBottom();
                },
              });
            },
          });
          return;
        }
        this.chatProcessing = false;
        this.chatProgress = null;
        this.messages.push({
          role: 'error',
          content: err.error?.detail || 'Erreur lors de l\'envoi',
          timestamp: new Date(),
        });
        this.scrollToBottom();
      },
    });
  }

  cancelChat(): void {
    this.stopChatPolling();
    this.api.cancelPreviewChat(this.projectId).subscribe();
    this.chatProcessing = false;
    this.chatProgress = null;
    this.messages.push({ role: 'error', content: 'Instruction annulee.', timestamp: new Date() });
    this.scrollToBottom();
  }

  private startChatPolling(): void {
    this.stopChatPolling();
    this.chatPollSub = timer(500, 1500).pipe(
      switchMap(() => this.api.getPreviewChatStatus(this.projectId))
    ).subscribe({
      next: (status) => {
        if (status.status === 'completed') {
          this.stopChatPolling();
          this.chatProcessing = false;
          this.chatProgress = null;
          this.messages.push({
            role: 'assistant',
            content: status.message || 'Modifications appliquees.',
            changedChapters: status.changed_chapters || [],
            timestamp: new Date(),
          });
          this.scrollToBottom();
          // Refresh the preview to show updated content
          this.refreshPreview();
        } else if (status.status === 'error') {
          this.stopChatPolling();
          this.chatProcessing = false;
          this.chatProgress = null;
          this.messages.push({
            role: 'error',
            content: status.message || 'Erreur lors du traitement',
            timestamp: new Date(),
          });
          this.scrollToBottom();
        } else if (status.status === 'running') {
          this.chatProgress = status;
        }
      },
    });
  }

  private stopChatPolling(): void {
    this.chatPollSub?.unsubscribe();
    this.chatPollSub = null;
  }

  private refreshPreview(): void {
    this.api.getPreview(this.projectId).subscribe({
      next: (p) => {
        this.preview = p;
        this.anonPreview = null;
        this.snackBar.open('Apercu mis a jour', 'OK', { duration: 3000 });
      },
    });
  }

  private scrollToBottom(): void {
    setTimeout(() => {
      if (this.chatMessagesEl?.nativeElement) {
        this.chatMessagesEl.nativeElement.scrollTop = this.chatMessagesEl.nativeElement.scrollHeight;
      }
    }, 100);
  }

  onChatKeydown(event: Event): void {
    const ke = event as KeyboardEvent;
    if (!ke.shiftKey) {
      ke.preventDefault();
      this.sendMessage();
    }
  }

  renderMarkdown = renderMarkdown;
}
