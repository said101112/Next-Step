import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { HttpClient, HttpContext, HttpErrorResponse } from '@angular/common/http';
import { SUPPRESS_ERROR_TOAST, apiErrorInterceptor } from './api-error.interceptor';
import { ToastService } from '@core/notifications/toast.service';

vi.mock('ngx-sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
    message: vi.fn(),
    loading: vi.fn(),
    dismiss: vi.fn(),
    promise: vi.fn(),
    custom: vi.fn(),
  },
}));

describe('apiErrorInterceptor', () => {
  let http: HttpClient;
  let httpMock: HttpTestingController;
  let toast: ToastService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([apiErrorInterceptor])),
        provideHttpClientTesting(),
        ToastService,
      ],
    });
    http = TestBed.inject(HttpClient);
    toast = TestBed.inject(ToastService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('affiche un toast global pour les erreurs 5xx', () => {
    const errorSpy = vi.spyOn(toast, 'error');
    http.get('/api/test').subscribe({ error: () => {} });
    httpMock.expectOne('/api/test').flush({ error: 'Backend down' }, { status: 502, statusText: 'Bad Gateway' });
    expect(errorSpy).toHaveBeenCalledWith('Backend down');
  });

  it('affiche un toast global pour les erreurs 4xx', () => {
    const errorSpy = vi.spyOn(toast, 'error');
    http.get('/api/test').subscribe({ error: () => {} });
    httpMock.expectOne('/api/test').flush({ error: 'Bad request' }, { status: 400, statusText: 'Bad Request' });
    expect(errorSpy).toHaveBeenCalledWith('Bad request');
  });

  it('affiche un toast global pour les erreurs réseau', () => {
    const errorSpy = vi.spyOn(toast, 'error');
    http.get('/api/test').subscribe({ error: () => {} });
    httpMock.expectOne('/api/test').error(new ProgressEvent('network'));
    expect(errorSpy).toHaveBeenCalledWith('Unable to reach the server. Please check your connection.');
  });

  it('ré-émet l erreur HTTP telle quelle (pas de transformation)', () => {
    http.get('/api/test').subscribe({
      error: (err: HttpErrorResponse) => {
        expect(err.status).toBe(404);
      },
    });
    httpMock.expectOne('/api/test').flush('Not Found', { status: 404, statusText: 'Not Found' });
  });

  it('ne déclenche pas de toast global avec le contexte SUPPRESS_ERROR_TOAST', () => {
    const errorSpy = vi.spyOn(toast, 'error');
    http.get('/api/test', { context: new HttpContext().set(SUPPRESS_ERROR_TOAST, true) }).subscribe({ error: () => {} });
    httpMock.expectOne('/api/test').flush({ error: 'Bad request' }, { status: 400, statusText: 'Bad Request' });
    expect(errorSpy).not.toHaveBeenCalled();
  });

  it('ne déclenche pas de toast global pour les URL auto-gérées', () => {
    const errorSpy = vi.spyOn(toast, 'error');
    http.get('/api/agents/sn/chat').subscribe({ error: () => {} });
    httpMock.expectOne('/api/agents/sn/chat').flush({ error: 'Down' }, { status: 500, statusText: 'Internal Server Error' });
    expect(errorSpy).not.toHaveBeenCalled();
  });
});