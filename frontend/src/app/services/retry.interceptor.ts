import { HttpInterceptorFn, HttpErrorResponse } from '@angular/common/http';
import { timer, throwError } from 'rxjs';
import { retry } from 'rxjs/operators';

const MAX_RETRIES = 3;

export const retryInterceptor: HttpInterceptorFn = (req, next) => {
  return next(req).pipe(
    retry({
      count: MAX_RETRIES,
      delay: (error: HttpErrorResponse, retryCount: number) => {
        if (error.status === 429) {
          const retryAfter = error.headers.get('Retry-After');
          const delayMs = retryAfter
            ? parseInt(retryAfter, 10) * 1000
            : Math.pow(2, retryCount) * 1000; // 2s, 4s, 8s
          return timer(delayMs);
        }
        return throwError(() => error);
      },
    })
  );
};
