import { describe, it, expect, beforeEach, vi } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { HttpErrorResponse } from '@angular/common/http';
import { ToastService } from './toast.service';
import { toast } from 'ngx-sonner';

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

describe('ToastService', () => {
  let service: ToastService;

  beforeEach(() => {
    vi.clearAllMocks();
    TestBed.configureTestingModule({ providers: [ToastService] });
    service = TestBed.inject(ToastService);
  });

  it('devrait être créé', () => {
    expect(service).toBeTruthy();
  });

  it('success appelle toast.success avec le message', () => {
    service.success('OK');
    expect(toast.success).toHaveBeenCalledWith('OK', expect.objectContaining({ duration: 3000 }));
  });

  it('error appelle toast.error avec le message', () => {
    service.error('Problème');
    expect(toast.error).toHaveBeenCalledWith('Problème', expect.objectContaining({ duration: 5000 }));
  });

  it('info appelle toast.message avec le message', () => {
    service.info('Note');
    expect(toast.message).toHaveBeenCalledWith('Note', expect.objectContaining({ duration: 3000 }));
  });

  it('apiError extrait le message du contrat d erreur normalisé', () => {
    service.apiError(new HttpErrorResponse({ error: { error: 'Erreur serveur' }, status: 502 }));
    expect(toast.error).toHaveBeenCalledWith('Erreur serveur', expect.objectContaining({ duration: 5000 }));
  });

  it('apiError retombe sur un message générique pour un objet sans message exploitable', () => {
    service.apiError({ foo: 'bar' });
    expect(toast.error).toHaveBeenCalledWith('An unexpected error occurred.', expect.objectContaining({ duration: 5000 }));
  });

  it('dismiss appelle toast.dismiss', () => {
    service.dismiss();
    expect(toast.dismiss).toHaveBeenCalledTimes(1);
  });
});