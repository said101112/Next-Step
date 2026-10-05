import { describe, it, expect } from 'vitest';
import { HttpErrorResponse } from '@angular/common/http';
import { extractApiError } from './extract-api-error';

describe('extractApiError', () => {
  it('extrait le contrat backend { error, type, details }', () => {
    const err = new HttpErrorResponse({
      status: 400,
      error: {
        error: 'Validation failed',
        type: 'ValidationError',
        details: { titre: ['Le titre est requis'] }
      }
    });
    const result = extractApiError(err);
    expect(result.status).toBe(400);
    expect(result.message).toBe('Validation failed');
    expect(result.type).toBe('ValidationError');
    expect(result.details).toEqual({ titre: ['Le titre est requis'] });
  });

  it('extrait le format FastAPI { detail } string', () => {
    const err = new HttpErrorResponse({
      status: 502,
      error: { detail: 'Service IA indisponible' }
    });
    expect(extractApiError(err).message).toBe('Service IA indisponible');
  });

  it('concatène un tableau FastAPI detail de validation', () => {
    const err = new HttpErrorResponse({
      status: 422,
      error: {
        detail: [{ msg: 'champ obligatoire' }, { msg: 'format invalide' }]
      }
    });
    expect(extractApiError(err).message).toBe('champ obligatoire, format invalide');
  });

  it('retourne le corps texte brut', () => {
    const err = new HttpErrorResponse({
      status: 500,
      error: 'Internal Server Error'
    });
    expect(extractApiError(err).message).toBe('Internal Server Error');
  });

  it('gère une erreur réseau (status 0)', () => {
    const err = new HttpErrorResponse({ status: 0, statusText: 'Unknown Error' });
    const result = extractApiError(err);
    expect(result.status).toBe(0);
    expect(result.message).toContain('server');
  });

  it('utilise un message générique pour une erreur inconnue', () => {
    expect(extractApiError(null).message).toBe('An unexpected error occurred.');
  });

  it('gère une exception native (hors HTTP)', () => {
    const result = extractApiError(new Error('boom'));
    expect(result.status).toBeNull();
    expect(result.message).toBe('boom');
  });
});