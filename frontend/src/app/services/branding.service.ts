import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable } from 'rxjs';
import { tap } from 'rxjs/operators';

export interface BrandingSettings {
  app_name: string;
  has_logo: boolean;
  has_favicon: boolean;
  primary_color: string;
  logo_url: string;
  favicon_url: string;
}

@Injectable({ providedIn: 'root' })
export class BrandingService {
  private baseUrl = '/api/branding';

  private brandingSubject = new BehaviorSubject<BrandingSettings>({
    app_name: 'RFP Assistant',
    has_logo: false,
    has_favicon: false,
    primary_color: '#1B3A5C',
    logo_url: '',
    favicon_url: '',
  });

  branding$ = this.brandingSubject.asObservable();

  constructor(private http: HttpClient) {
    this.loadBranding();
  }

  get current(): BrandingSettings {
    return this.brandingSubject.value;
  }

  loadBranding(): void {
    this.http.get<BrandingSettings>(`${this.baseUrl}/settings`).subscribe({
      next: (b) => {
        this.brandingSubject.next(b);
        this.applyFavicon(b);
        this.applyTitle(b);
      },
      error: () => {
        // Keep defaults
      },
    });
  }

  updateSettings(appName: string, primaryColor: string): Observable<BrandingSettings> {
    return this.http.put<BrandingSettings>(
      `${this.baseUrl}/settings`,
      null,
      { params: { app_name: appName, primary_color: primaryColor } }
    ).pipe(
      tap((b) => {
        this.brandingSubject.next(b);
        this.applyTitle(b);
      })
    );
  }

  uploadLogo(file: File): Observable<any> {
    const formData = new FormData();
    formData.append('file', file);
    return this.http.post(`${this.baseUrl}/logo`, formData).pipe(
      tap(() => this.loadBranding())
    );
  }

  uploadFavicon(file: File): Observable<any> {
    const formData = new FormData();
    formData.append('file', file);
    return this.http.post(`${this.baseUrl}/favicon`, formData).pipe(
      tap(() => this.loadBranding())
    );
  }

  deleteLogo(): Observable<any> {
    return this.http.delete(`${this.baseUrl}/logo`).pipe(
      tap(() => this.loadBranding())
    );
  }

  deleteFavicon(): Observable<any> {
    return this.http.delete(`${this.baseUrl}/favicon`).pipe(
      tap(() => this.loadBranding())
    );
  }

  private applyFavicon(b: BrandingSettings): void {
    if (b.has_favicon && b.favicon_url) {
      const link: HTMLLinkElement =
        document.querySelector("link[rel~='icon']") || document.createElement('link');
      link.rel = 'icon';
      link.href = b.favicon_url + '?v=' + Date.now();
      if (!link.parentNode) {
        document.head.appendChild(link);
      }
    }
  }

  private applyTitle(b: BrandingSettings): void {
    if (b.app_name) {
      document.title = b.app_name;
    }
  }
}
