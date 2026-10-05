import { describe, it, expect } from 'vitest';
import {
  CandidatureCard,
  KANBAN_COLUMNS,
  buildCandidaturesCsv,
  isFollowUpSuggested,
  mapKanbanToStatus,
  mapStatusToKanban,
  resolveContractType,
} from './candidature-board';

const card = (over: Partial<CandidatureCard> = {}): CandidatureCard => ({
  id: '1',
  idOffre: 'o1',
  entreprise: 'Acme',
  role: 'Dev',
  type: 'Stage',
  statut: 'envoye',
  channel: 'EMAIL',
  applicationDate: new Date().toISOString(),
  dateCreation: new Date().toISOString(),
  hasResponse: false,
  responseStatus: '',
  ...over,
});

describe('candidature board rules', () => {
  it('chaque colonne du kanban revient sur elle-même via le statut backend', () => {
    for (const col of KANBAN_COLUMNS) {
      expect(mapStatusToKanban(mapKanbanToStatus(col.key))).toBe(col.key);
    }
  });

  it('regroupe les statuts backend dans les colonnes', () => {
    expect(mapStatusToKanban('ACCUSE_RECEPTION')).toBe('envoye');
    expect(mapStatusToKanban('ENTRETIEN_EFFECTUE')).toBe('entretien');
    expect(mapStatusToKanban('ABANDONNE')).toBe('refuse');
    expect(mapStatusToKanban('INCONNU')).toBe('envoye');
  });

  it('détecte le type de contrat depuis le type, les notes puis le poste', () => {
    expect(resolveContractType('stage pfe')).toBe('Stage PFE');
    expect(resolveContractType('CDI', null, 'Acme\nDev\nAlternance')).toBe('Alternance');
    expect(resolveContractType(null, 'Stagiaire backend')).toBe('Stage');
    expect(resolveContractType(null, null, null)).toBe('Stage PFE');
  });

  it('suggère une relance après 5 jours sans réponse', () => {
    const sixDaysAgo = new Date(Date.now() - 6 * 24 * 3600 * 1000).toISOString();
    expect(isFollowUpSuggested(card({ applicationDate: sixDaysAgo }))).toBe(true);
    expect(isFollowUpSuggested(card({ applicationDate: sixDaysAgo, hasResponse: true }))).toBe(false);
    expect(isFollowUpSuggested(card())).toBe(false);
  });

  it('échappe les guillemets dans le CSV', () => {
    const csv = buildCandidaturesCsv([card({ entreprise: 'Le "Lab"', followUpNeeded: true })]);
    const [header, row] = csv.split('\n');
    expect(header).toBe('Company,Role,Channel,Status,Date,Response,FollowUp');
    expect(row.startsWith('"Le ""Lab""","Dev","EMAIL","envoye"')).toBe(true);
    expect(row.endsWith('"No","Yes"')).toBe(true);
  });
});
