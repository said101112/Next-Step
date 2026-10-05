import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { TestBed } from '@angular/core/testing';
import Keycloak from 'keycloak-js';
import { AuthService } from './auth.service';

describe('AuthService', () => {
  let service: AuthService;
  
  // Mock Keycloak
  const mockKeycloak = {
    authenticated: true,
    token: 'fake-jwt-token',
    login: vi.fn().mockResolvedValue(undefined),
    logout: vi.fn().mockResolvedValue(undefined),
    loadUserProfile: vi.fn().mockResolvedValue({
      firstName: 'Jane',
      lastName: 'Doe',
      email: 'jane@example.com'
    })
  };

  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [
        AuthService,
        { provide: Keycloak, useValue: mockKeycloak }
      ]
    });
    
    // Le constructeur de AuthService appelle init() qui est asynchrone,
    // On l'injecte donc après la conf
    service = TestBed.inject(AuthService);
    
    // Attendre que la promesse du constructeur (loadUserProfile) se résolve
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('devrait être créé', () => {
    expect(service).toBeTruthy();
  });

  it('devrait initialiser le signal utilisateur si authentifié', () => {
    // Le constructor appelle loadUserProfile car on a mocké authenticated = true
    expect(mockKeycloak.loadUserProfile).toHaveBeenCalled();
    const user = service.user();
    expect(user).toEqual({
      firstName: 'Jane',
      lastName: 'Doe',
      email: 'jane@example.com'
    });
  });

  it('devrait appeler login() de keycloak sur login()', () => {
    service.login();
    expect(mockKeycloak.login).toHaveBeenCalledWith();
  });

  it('devrait appeler login() avec idpHint=google pour Google Auth', () => {
    service.loginWithGoogle();
    expect(mockKeycloak.login).toHaveBeenCalledWith({ idpHint: 'google' });
  });

  it('devrait appeler login() avec idpHint=github pour Github Auth', () => {
    service.loginWithGithub();
    expect(mockKeycloak.login).toHaveBeenCalledWith({ idpHint: 'github' });
  });

  it('devrait appeler logout() de keycloak avec redirectUri', () => {
    service.logout();
    expect(mockKeycloak.logout).toHaveBeenCalledWith({ redirectUri: globalThis.location.origin });
  });

  it('devrait retourner l\'état d\'authentification et le token', () => {
    expect(service.isAuthenticated()).toBe(true);
    expect(service.getToken()).toBe('fake-jwt-token');
  });
});
