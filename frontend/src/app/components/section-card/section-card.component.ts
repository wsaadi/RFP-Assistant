import { Component, Input, Output, EventEmitter, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatRippleModule } from '@angular/material/core';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ReportSection, SectionStatus } from '../../models/report.model';

@Component({
  selector: 'app-section-card',
  standalone: true,
  imports: [CommonModule, MatIconModule, MatRippleModule, MatTooltipModule],
  template: `
    <div
      class="section-card"
      [class.selected]="isSelected || isSubsectionSelected()"
      [class.has-subsections]="section.subsections?.length"
      [class.expanded]="isExpanded()"
    >
      <div class="section-main" matRipple (click)="onSelect()">
        <div class="section-status">
          @switch (section.status) {
            @case ('not_started') {
              <mat-icon class="status-icon not-started">radio_button_unchecked</mat-icon>
            }
            @case ('in_progress') {
              <mat-icon class="status-icon in-progress">pending</mat-icon>
            }
            @case ('completed') {
              <mat-icon class="status-icon completed">check_circle</mat-icon>
            }
            @case ('needs_review') {
              <mat-icon class="status-icon needs-review">error</mat-icon>
            }
          }
        </div>

        <div class="section-info">
          <span class="section-title">{{ section.title }}</span>
          <div class="section-meta">
            @if (section.min_pages || section.max_pages) {
              <span class="section-pages">
                {{ section.min_pages || 0 }}-{{ section.max_pages || '?' }} pages
              </span>
            }
            @if (section.notes?.length) {
              <span class="notes-badge">
                <mat-icon>note</mat-icon>
                {{ section.notes.length }}
              </span>
            }
            @if (section.subsections?.length) {
              <span class="subsections-count">
                {{ getCompletedSubsections() }}/{{ section.subsections.length }}
              </span>
            }
          </div>
        </div>

        @if (section.required) {
          <span class="required-badge">Requis</span>
        }
      </div>

      @if (section.subsections?.length) {
        <button
          class="expand-btn"
          (click)="toggleExpand($event)"
          [matTooltip]="isExpanded() ? 'Réduire' : 'Développer'"
        >
          <mat-icon>{{ isExpanded() ? 'expand_less' : 'expand_more' }}</mat-icon>
        </button>
      }
    </div>

    @if (section.subsections?.length && isExpanded()) {
      <div class="subsections" [@expandCollapse]>
        @for (subsection of section.subsections; track subsection.id) {
          <div
            class="subsection-card"
            [class.selected]="selectedSubsectionId === subsection.id"
            matRipple
            (click)="selectSubsection($event, subsection)"
          >
            <div class="section-status">
              @switch (subsection.status) {
                @case ('not_started') {
                  <mat-icon class="status-icon small not-started">radio_button_unchecked</mat-icon>
                }
                @case ('in_progress') {
                  <mat-icon class="status-icon small in-progress">pending</mat-icon>
                }
                @case ('completed') {
                  <mat-icon class="status-icon small completed">check_circle</mat-icon>
                }
                @case ('needs_review') {
                  <mat-icon class="status-icon small needs-review">error</mat-icon>
                }
              }
            </div>
            <span class="subsection-title">{{ subsection.title }}</span>
            @if (subsection.notes?.length) {
              <span class="notes-badge small">
                {{ subsection.notes.length }}
              </span>
            }
          </div>
        }
      </div>
    }
  `,
  styles: [`
    .section-card {
      display: flex;
      align-items: center;
      margin-bottom: 8px;
      background: white;
      border-radius: 10px;
      border: 2px solid transparent;
      transition: all 0.2s ease;
      overflow: hidden;

      &:hover {
        border-color: #e3f2fd;
        background: #fafafa;
      }

      &.selected {
        border-color: #1976d2;
        background: #e3f2fd;
      }

      &.expanded {
        border-color: #e3f2fd;
      }
    }

    .section-main {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 14px 16px;
      flex: 1;
      cursor: pointer;
      min-width: 0;
    }

    .expand-btn {
      background: transparent;
      border: none;
      padding: 8px 12px;
      cursor: pointer;
      color: #78909c;
      display: flex;
      align-items: center;
      justify-content: center;
      border-left: 1px solid #e0e0e0;
      transition: all 0.2s;

      &:hover {
        background: #e3f2fd;
        color: #1976d2;
      }

      mat-icon {
        font-size: 24px;
        width: 24px;
        height: 24px;
      }
    }

    .section-status {
      flex-shrink: 0;
    }

    .status-icon {
      font-size: 22px;
      width: 22px;
      height: 22px;

      &.small {
        font-size: 18px;
        width: 18px;
        height: 18px;
      }

      &.not-started { color: #bdbdbd; }
      &.in-progress { color: #ff9800; }
      &.completed { color: #43a047; }
      &.needs-review { color: #e91e63; }
    }

    .section-info {
      flex: 1;
      min-width: 0;

      .section-title {
        display: block;
        font-size: 14px;
        font-weight: 500;
        color: #37474f;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .section-meta {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-top: 4px;
      }

      .section-pages {
        font-size: 11px;
        color: #9e9e9e;
      }

      .notes-badge {
        display: inline-flex;
        align-items: center;
        gap: 3px;
        font-size: 11px;
        color: #78909c;
        background: #e3f2fd;
        padding: 2px 6px;
        border-radius: 4px;

        mat-icon {
          font-size: 12px;
          width: 12px;
          height: 12px;
        }
      }

      .subsections-count {
        font-size: 11px;
        color: #43a047;
        background: #e8f5e9;
        padding: 2px 6px;
        border-radius: 4px;
        font-weight: 500;
      }
    }

    .required-badge {
      flex-shrink: 0;
      font-size: 10px;
      padding: 3px 8px;
      background: #fff3e0;
      color: #f57c00;
      border-radius: 4px;
      font-weight: 500;
    }

    .subsections {
      margin-left: 20px;
      margin-bottom: 8px;
      padding-left: 16px;
      border-left: 2px solid #1976d2;
      animation: slideDown 0.2s ease-out;
    }

    @keyframes slideDown {
      from {
        opacity: 0;
        transform: translateY(-10px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }

    .subsection-card {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 12px;
      margin-bottom: 4px;
      background: #fafafa;
      border-radius: 8px;
      cursor: pointer;
      transition: all 0.2s ease;
      border: 2px solid transparent;

      &:hover {
        background: #f0f0f0;
        border-color: #e3f2fd;
      }

      &.selected {
        background: #e3f2fd;
        border-color: #1976d2;
      }

      .subsection-title {
        flex: 1;
        font-size: 13px;
        color: #546e7a;
      }

      .notes-badge {
        font-size: 11px;
        color: #78909c;
        background: #e0e0e0;
        padding: 2px 6px;
        border-radius: 4px;

        &.small {
          font-size: 10px;
        }
      }
    }
  `],
})
export class SectionCardComponent {
  @Input() section!: ReportSection;
  @Input() isSelected = false;
  @Input() selectedSubsectionId: string | null = null;
  @Output() select = new EventEmitter<ReportSection>();

  expanded = signal(false);

  isExpanded(): boolean {
    return this.expanded() || this.isSelected || this.isSubsectionSelected();
  }

  isSubsectionSelected(): boolean {
    if (!this.selectedSubsectionId || !this.section.subsections) return false;
    return this.section.subsections.some(s => s.id === this.selectedSubsectionId);
  }

  getCompletedSubsections(): number {
    if (!this.section.subsections) return 0;
    return this.section.subsections.filter(s => s.status === 'completed').length;
  }

  toggleExpand(event: Event): void {
    event.stopPropagation();
    this.expanded.set(!this.expanded());
  }

  onSelect(): void {
    this.select.emit(this.section);
    // Auto expand when selecting
    if (this.section.subsections?.length && !this.expanded()) {
      this.expanded.set(true);
    }
  }

  selectSubsection(event: Event, subsection: ReportSection): void {
    event.stopPropagation();
    this.select.emit(subsection);
  }
}
