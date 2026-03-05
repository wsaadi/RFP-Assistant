import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, tap } from 'rxjs';
import { Router } from '@angular/router';
import { LoginRequest, TokenResponse, UserInfo } from '../models/report.model';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private baseUrl = '/api/auth';
  private userKey = 'rfp_user';

  private currentUserSubject = new BehaviorSubject<UserInfo | null>(this.getStoredUser());
  currentUser$ = this.currentUserSubject.asObservable();

  constructor(private http: HttpClient, private router: Router) {}

  login(request: LoginRequest): Observable<TokenResponse> {
    return this.http.post<TokenResponse>(`${this.baseUrl}/login`, request, {
      withCredentials: true,
    }).pipe(
      tap((response) => {
        const user: UserInfo = {
          id: response.user_id,
          email: '',
          username: response.username,
          full_name: '',
          role: response.role,
          is_active: true,
        };
        sessionStorage.setItem(this.userKey, JSON.stringify(user));
        this.currentUserSubject.next(user);
      })
    );
  }

  logout(): void {
    this.http.post(`${this.baseUrl}/logout`, {}, { withCredentials: true }).subscribe();
    sessionStorage.removeItem(this.userKey);
    this.currentUserSubject.next(null);
    this.router.navigate(['/login']);
  }

  getToken(): string | null {
    // Token is now in httpOnly cookie — not accessible via JS.
    // This method returns null; auth is handled via cookie automatically.
    return null;
  }

  isLoggedIn(): boolean {
    // With httpOnly cookies, we check user presence in session
    return !!this.currentUserSubject.value;
  }

  isAdmin(): boolean {
    const user = this.currentUserSubject.value;
    return user?.role === 'admin';
  }

  getCurrentUser(): UserInfo | null {
    return this.currentUserSubject.value;
  }

  fetchCurrentUser(): Observable<UserInfo> {
    return this.http.get<UserInfo>(`${this.baseUrl}/me`, { withCredentials: true }).pipe(
      tap((user) => {
        sessionStorage.setItem(this.userKey, JSON.stringify(user));
        this.currentUserSubject.next(user);
      })
    );
  }

  private getStoredUser(): UserInfo | null {
    const stored = sessionStorage.getItem(this.userKey);
    if (!stored) {
      // Migration: check localStorage for old key and move to sessionStorage
      const legacy = localStorage.getItem(this.userKey) || localStorage.getItem('rfp_token');
      if (legacy) {
        localStorage.removeItem(this.userKey);
        localStorage.removeItem('rfp_token');
      }
      return null;
    }
    return JSON.parse(stored);
  }
}
