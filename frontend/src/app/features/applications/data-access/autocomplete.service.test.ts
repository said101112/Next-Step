import { describe, it, expect, beforeEach } from 'vitest';
import { of, throwError } from 'rxjs';
import { AutocompleteService, CompanySuggestion, JobTitleSuggestion } from './autocomplete.service';

describe('AutocompleteService', () => {
  let service: AutocompleteService;
  let mockHttpClient: any;

  beforeEach(() => {
    mockHttpClient = {
      get: () => of([]),
    };

    service = new AutocompleteService(mockHttpClient);
  });

  describe('searchCompanies', () => {
    it('returns empty array if query length < 2', async () => {
      const results = await new Promise<CompanySuggestion[]>((resolve) => {
        service.searchCompanies('a').subscribe(resolve);
      });
      expect(results).toEqual([]);
    });

    it('returns local catalog results matching query (e.g. Doctolib)', async () => {
      mockHttpClient.get = () => of([]);

      const results = await new Promise<CompanySuggestion[]>((resolve) => {
        service.searchCompanies('docto').subscribe(resolve);
      });

      expect(results.length).toBeGreaterThan(0);
      const doctolib = results.find((r) => r.name.toLowerCase().includes('doctolib'));
      expect(doctolib).toBeDefined();
      expect(doctolib?.domain).toBe('doctolib.fr');
      expect(doctolib?.source).toBe('catalog');
    });

    it('prioritizes historical companies and sets alreadyApplied flag', async () => {
      mockHttpClient.get = () => of([]);

      const results = await new Promise<CompanySuggestion[]>((resolve) => {
        service.searchCompanies('goog', ['Google France', 'Autre Boîte']).subscribe(resolve);
      });

      expect(results.length).toBeGreaterThan(0);
      const historyItem = results.find((r) => r.name === 'Google France');
      expect(historyItem).toBeDefined();
      expect(historyItem?.alreadyApplied).toBe(true);
      expect(historyItem?.source).toBe('history');
    });

    it('integrates Clearbit API results and avoids duplicates', async () => {
      mockHttpClient.get = () =>
        of([
          { name: 'CustomTech Inc', domain: 'customtech.io', logo: 'https://logo.clearbit.com/customtech.io' },
        ]);

      const results = await new Promise<CompanySuggestion[]>((resolve) => {
        service.searchCompanies('customtech').subscribe(resolve);
      });

      expect(results.length).toBe(1);
      expect(results[0].name).toBe('CustomTech Inc');
      expect(results[0].domain).toBe('customtech.io');
      expect(results[0].source).toBe('clearbit');
    });

    it('falls back gracefully to local catalog if Clearbit fails or times out', async () => {
      mockHttpClient.get = () => throwError(() => new Error('Network error'));

      const results = await new Promise<CompanySuggestion[]>((resolve) => {
        service.searchCompanies('microsoft').subscribe(resolve);
      });

      expect(results.length).toBeGreaterThan(0);
      const ms = results.find((r) => r.name === 'Microsoft');
      expect(ms).toBeDefined();
      expect(ms?.domain).toBe('microsoft.com');
    });
  });

  describe('searchJobTitles', () => {
    it('returns empty array if query length < 2', () => {
      const results = service.searchJobTitles('d');
      expect(results).toEqual([]);
    });

    it('finds job titles matching alias "fs"', () => {
      const results = service.searchJobTitles('fs');
      expect(results.length).toBeGreaterThan(0);
      const fullstack = results.find((r) => r.title === 'Full Stack Developer');
      expect(fullstack).toBeDefined();
      expect(fullstack?.category).toBe('Engineering & Dev');
    });

    it('handles accent-insensitive queries like "developpeur"', () => {
      const results = service.searchJobTitles('developpeur');
      expect(results.length).toBeGreaterThan(0);
      expect(results.some((r) => r.title.includes('Developer'))).toBe(true);
    });

    it('matches "data" roles with category Data & AI', () => {
      const results = service.searchJobTitles('data');
      expect(results.length).toBeGreaterThan(0);
      const ds = results.find((r) => r.title === 'Data Scientist');
      expect(ds).toBeDefined();
      expect(ds?.category).toBe('Data & AI');
    });

    it('prioritizes historical roles with alreadyApplied flag', () => {
      const results = service.searchJobTitles('dev', ['Senior .NET Developer']);
      expect(results.length).toBeGreaterThan(0);
      const histRole = results.find((r) => r.title === 'Senior .NET Developer');
      expect(histRole).toBeDefined();
      expect(histRole?.alreadyApplied).toBe(true);
    });
  });
});
