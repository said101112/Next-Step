import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { signal } from '@angular/core';

import { ProfileService } from './profile.service';
import { normalizeImportedPayload } from './profile-import.normalizer';
import { AuthService } from '@core/auth/auth.service';
import { Experience, Education, Skill, Project, Certification, PersonalInfo } from './profile.models';

describe('ProfileFeatureService (State & Signals)', () => {
  let service: ProfileService;
  let httpMock: HttpTestingController;
  
  // Mock AuthService since ProfileService depends on it
  const mockAuthService = {
    user: signal({ firstName: 'Test', lastName: 'User', email: 'test@example.com' })
  };

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        ProfileService,
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: AuthService, useValue: mockAuthService }
      ]
    });
    
    service = TestBed.inject(ProfileService);
    httpMock = TestBed.inject(HttpTestingController);

    const bootstrapRequests = httpMock.match('http://localhost:5000/api/profile');
    bootstrapRequests.forEach((req) => {
      req.flush({
        personalInfo: { prenom: 'Test', nom: 'User', email: 'test@example.com' },
        formations: [],
        experiences: [],
        competences: [],
        projets: [],
        certifications: []
      });
    });
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should be created and initialize Signals', () => {
    expect(service).toBeTruthy();
    expect(service.profile()).toBeDefined();
    expect(service.currentStep()).toBe('coordonnees');
  });

  it('should calculate the correct completion percentage', () => {
    // Empty profile by default
    expect(service.completionPercentage()).toBe(0);

    // Adding personal information (should add 6 points: firstName + lastName + email)
    service.updateProfile({
      personal: {
        ...service.profile().personal,
        firstName: 'John',
        lastName: 'Doe',
        email: 'john@example.com'
      }
    });

    expect(service.completionPercentage()).toBe(6);
  });

  it('should update current step via setStep', () => {
    service.setStep('experience');
    expect(service.currentStep()).toBe('experience');
  });

  it('should check if a section is complete (isSectionComplete)', () => {
    // Incomplete contact details by default
    expect(service.isSectionComplete('coordonnees')).toBe(false);

    service.updateProfile({
      personal: {
        ...service.profile().personal,
        firstName: 'John',
        lastName: 'Doe',
        email: 'john@example.com'
      }
    });
    
    // Becomes complete after adding required fields
    expect(service.isSectionComplete('coordonnees')).toBe(true);
  });

  // --- HTTP CRUD operation tests ---

  it('should load profile from API (loadProfile)', async () => {
    const mockApiData = {
      personalInfo: { prenom: 'John', nom: 'Doe', email: 'john@test.com' },
      formations: [],
      experiences: [],
      competences: [],
      projets: [],
      certifications: []
    };

    const promise = service.loadProfile();
    
    const req = httpMock.expectOne('http://localhost:5000/api/profile');
    expect(req.request.method).toBe('GET');
    req.flush(mockApiData);

    await promise;
    expect(service.profile().personal.firstName).toBe('John');
  });

  it('should generate resume via AI (generateResume)', async () => {
    const mockAiResponse = { resume: 'Dynamic software engineer profile...' };
    
    const promise = service.generateResume({});
    
    const req = httpMock.expectOne('http://localhost:5000/api/profile/generate-resume');
    expect(req.request.method).toBe('POST');
    req.flush(mockAiResponse);

    const result = await promise;
    expect(result).toBe('Dynamic software engineer profile...');
  });

  it('generateResume fails with backend message when nothing is generated', async () => {
    const promise = service.generateResume({});

    httpMock
      .expectOne('http://localhost:5000/api/profile/generate-resume')
      .flush({ resume: '', errors: ['The AI CV generation service is currently unavailable.'] });

    await expect(promise).rejects.toThrow('currently unavailable');
  });

  it('should retrieve keywords (getKeywords)', async () => {
    const mockKeywords = [{ mot: 'Angular', categorie: 'Technique' }];
    const promise = service.getKeywords();
    const req = httpMock.expectOne('http://localhost:5000/api/profile/keywords');
    req.flush(mockKeywords);
    expect(await promise).toEqual(mockKeywords);
  });

  it('should normalize stringified import response without duplicating languages', () => {
    const normalized = normalizeImportedPayload(JSON.stringify({
      personal: {
        prenom: 'Jane',
        nom: 'Doe',
        email: 'jane@test.com',
        telephone: '+212600000000',
        titrePoste: 'Frontend Engineer',
        ville: 'Casablanca',
        pays: 'Morocco',
        summary: 'Angular engineer with product experience.'
      },
      experiences: [
        {
          entreprise: 'NextStep',
          poste: 'Frontend Engineer',
          dateDebut: '2023-02-01',
          dateFin: '2024-05-01',
          missions: 'Built profile flows'
        }
      ],
      formations: [
        {
          etablissement: 'ENSA',
          diplome: 'Engineering Degree',
          annee: '2020-09',
          anneeFin: '2023-06'
        }
      ],
      languages: [{ name: 'English', level: 'C1' }],
      skills: ['English', { name: 'Angular', typeCompetence: 'Technical' }],
      projects: [
        { title: 'Portfolio', technologies: 'Angular, Firebase' }
      ],
      certifications: [
        { title: 'AWS Cloud Practitioner', issuer: 'Amazon' }
      ]
    }));

    expect(normalized.personal.firstName).toBe('Jane');
    expect(normalized.resume).toContain('Angular engineer');
    expect(normalized.experience).toHaveLength(1);
    expect(normalized.education[0].startYear).toBe('2020');
    expect(normalized.languages.map((lang: any) => lang.name)).toEqual(['English']);
    expect(normalized.skills.map((skill: any) => skill.name)).toEqual(['Angular']);
    expect(normalized.projects[0].stack).toEqual(['Angular', 'Firebase']);
    expect(normalized.certifications[0].name).toBe('AWS Cloud Practitioner');
  });

  // --- CRUD Tests --- //

  it('should update personal info (savePersonalInfo)', async () => {
    const info: PersonalInfo = { firstName: 'Jane', lastName: 'Doe', email: 'jane@test.com', phone: '', city: '', country: '', jobTitle: '', linkedinUrl: '', githubUrl: '', portfolioUrl: 'https://portfolio.test', photoUrl: null, useAsHeadline: true, address: '' };
    const promise = service.savePersonalInfo(info);
    const req = httpMock.expectOne('http://localhost:5000/api/profile/personal-info');
    expect(req.request.method).toBe('PUT');
    expect(req.request.body.lienPortfolio).toBe('https://portfolio.test');
    req.flush({});
    await promise;
  });

  it('should add experience and reload profile (addExperience)', async () => {
    const exp: Experience = { id: '', company: 'Tech', title: 'Dev', startDate: '2023-01', endDate: '', description: 'Code', city: 'Paris', type: 'CDI', current: true, taches: ['Built APIs'] };
    const loadSpy = vi.spyOn(service, 'loadProfile').mockResolvedValue(undefined);
    const promise = service.addExperience(exp);
    const req = httpMock.expectOne('http://localhost:5000/api/profile/experiences');
    expect(req.request.method).toBe('POST');
    expect(req.request.body.taches).toEqual(['Built APIs']);
    req.flush({});
    await promise;
    expect(loadSpy).toHaveBeenCalled();
  });

  it('should update experience (updateExperience)', async () => {
    const loadSpy = vi.spyOn(service, 'loadProfile').mockResolvedValue(undefined);
    const exp: Experience = { id: '1', company: 'X', title: 'Y', startDate: '', endDate: '', description: '', city: '', type: 'Stage', current: false, taches: ['Maintained UI'] };
    const promise = service.updateExperience(exp);
    const req = httpMock.expectOne('http://localhost:5000/api/profile/experiences');
    expect(req.request.method).toBe('PUT');
    expect(req.request.body.taches).toEqual(['Maintained UI']);
    req.flush({});
    await promise;
    expect(loadSpy).toHaveBeenCalled();
  });

  it('should delete experience (deleteExperience)', async () => {
    const loadSpy = vi.spyOn(service, 'loadProfile').mockResolvedValue(undefined);
    const promise = service.deleteExperience('1');
    const req = httpMock.expectOne('http://localhost:5000/api/profile/experiences/1');
    expect(req.request.method).toBe('DELETE');
    req.flush({});
    await promise;
    expect(loadSpy).toHaveBeenCalled();
  });

  it('should add education (addEducation)', async () => {
    const loadSpy = vi.spyOn(service, 'loadProfile').mockResolvedValue(undefined);
    const edu: Education = { id: '', institution: 'Z', degree: 'W', startYear: '2020', endYear: '2023', city: '', specialization: '', mention: 'Passable', current: false };
    const promise = service.addEducation(edu);
    const req = httpMock.expectOne('http://localhost:5000/api/profile/formations');
    expect(req.request.method).toBe('POST');
    req.flush({});
    await promise;
    expect(loadSpy).toHaveBeenCalled();
  });

  it('should update education (updateEducation)', async () => {
    const loadSpy = vi.spyOn(service, 'loadProfile').mockResolvedValue(undefined);
    const edu: Education = { id: '2', institution: 'Z', degree: 'W', startYear: '2020', endYear: '2023', city: '', specialization: '', mention: 'Passable', current: false };
    const promise = service.updateEducation(edu);
    const req = httpMock.expectOne('http://localhost:5000/api/profile/formations');
    expect(req.request.method).toBe('PUT');
    req.flush({});
    await promise;
    expect(loadSpy).toHaveBeenCalled();
  });

  it('should add skill (addSkill)', async () => {
    const loadSpy = vi.spyOn(service, 'loadProfile').mockResolvedValue(undefined);
    const skill: Skill = { id: '', name: 'Angular', category: 'Technique' };
    const promise = service.addSkill(skill);
    const req = httpMock.expectOne('http://localhost:5000/api/profile/competences');
    expect(req.request.method).toBe('POST');
    req.flush({});
    await promise;
    expect(loadSpy).toHaveBeenCalled();
  });

  it('should update skill (updateSkill)', async () => {
    const loadSpy = vi.spyOn(service, 'loadProfile').mockResolvedValue(undefined);
    const skill: Skill = { id: '3', name: 'Angular', category: 'Technique' };
    const promise = service.updateSkill(skill);
    const req = httpMock.expectOne('http://localhost:5000/api/profile/competences');
    expect(req.request.method).toBe('PUT');
    req.flush({});
    await promise;
    expect(loadSpy).toHaveBeenCalled();
  });

  it('should delete skill (deleteSkill)', async () => {
    const loadSpy = vi.spyOn(service, 'loadProfile').mockResolvedValue(undefined);
    const promise = service.deleteSkill('3');
    const req = httpMock.expectOne('http://localhost:5000/api/profile/competences/3');
    expect(req.request.method).toBe('DELETE');
    req.flush({});
    await promise;
    expect(loadSpy).toHaveBeenCalled();
  });

  it('should add project (addProject)', async () => {
    const loadSpy = vi.spyOn(service, 'loadProfile').mockResolvedValue(undefined);
    const proj: Project = { id: '', title: 'A', description: 'B', stack: [], githubUrl: '', demoUrl: '', isUniversity: false, taches: ['Designed dashboard'] };
    const promise = service.addProject(proj);
    const req = httpMock.expectOne('http://localhost:5000/api/profile/projets');
    expect(req.request.method).toBe('POST');
    expect(req.request.body.taches).toEqual(['Designed dashboard']);
    req.flush({});
    await promise;
    expect(loadSpy).toHaveBeenCalled();
  });

  it('should update project (updateProject)', async () => {
    const loadSpy = vi.spyOn(service, 'loadProfile').mockResolvedValue(undefined);
    const proj: Project = { id: '4', title: 'A', description: 'B', stack: [], githubUrl: '', demoUrl: '', isUniversity: false, taches: ['Improved CI'] };
    const promise = service.updateProject(proj);
    const req = httpMock.expectOne('http://localhost:5000/api/profile/projets');
    expect(req.request.method).toBe('PUT');
    expect(req.request.body.taches).toEqual(['Improved CI']);
    req.flush({});
    await promise;
    expect(loadSpy).toHaveBeenCalled();
  });

  it('should delete project (deleteProject)', async () => {
    const loadSpy = vi.spyOn(service, 'loadProfile').mockResolvedValue(undefined);
    const promise = service.deleteProject('4');
    const req = httpMock.expectOne('http://localhost:5000/api/profile/projets/4');
    expect(req.request.method).toBe('DELETE');
    req.flush({});
    await promise;
    expect(loadSpy).toHaveBeenCalled();
  });

  it('should add certification (addCertification)', async () => {
    const loadSpy = vi.spyOn(service, 'loadProfile').mockResolvedValue(undefined);
    const cert: Certification = { id: '', name: 'C', issuer: 'D', date: '', verificationUrl: '' };
    const promise = service.addCertification(cert);
    const req = httpMock.expectOne('http://localhost:5000/api/profile/certifications');
    expect(req.request.method).toBe('POST');
    req.flush({});
    await promise;
    expect(loadSpy).toHaveBeenCalled();
  });

  it('should update certification (updateCertification)', async () => {
    const loadSpy = vi.spyOn(service, 'loadProfile').mockResolvedValue(undefined);
    const cert: Certification = { id: '5', name: 'C', issuer: 'D', date: '', verificationUrl: '' };
    const promise = service.updateCertification(cert);
    const req = httpMock.expectOne('http://localhost:5000/api/profile/certifications');
    expect(req.request.method).toBe('PUT');
    req.flush({});
    await promise;
    expect(loadSpy).toHaveBeenCalled();
  });

  it('should delete certification (deleteCertification)', async () => {
    const loadSpy = vi.spyOn(service, 'loadProfile').mockResolvedValue(undefined);
    const promise = service.deleteCertification('5');
    const req = httpMock.expectOne('http://localhost:5000/api/profile/certifications/5');
    expect(req.request.method).toBe('DELETE');
    req.flush({});
    await promise;
    expect(loadSpy).toHaveBeenCalled();
  });

  it('should export profile to JSON format with metadata and sections', () => {
    service.profile.set({
      personal: {
        firstName: 'Jane',
        lastName: 'Doe',
        email: 'jane.doe@example.com',
        phone: '0612345678',
        jobTitle: 'Software Engineer',
        address: 'Paris, France',
        city: 'Paris',
        country: 'France',
        linkedinUrl: 'https://linkedin.com/in/janedoe',
        githubUrl: 'https://github.com/janedoe',
        portfolioUrl: 'https://janedoe.dev',
        photoUrl: null,
        useAsHeadline: true
      },
      education: [
        {
          id: 'edu-1',
          degree: 'Master Computer Science',
          institution: 'Sorbonne',
          city: 'Paris',
          startYear: '2020',
          endYear: '2022',
          current: false,
          specialization: 'Software Engineering',
          mention: 'Très bien'
        }
      ],
      experience: [
        {
          id: 'exp-1',
          title: 'Full Stack Dev',
          company: 'Acme Corp',
          city: 'Paris',
          startDate: '2022-01',
          endDate: '2024-01',
          current: false,
          type: 'CDI',
          description: 'Full stack development',
          taches: ['Feature A', 'Feature B']
        }
      ],
      skills: [
        { id: 'skill-1', name: 'Angular', category: 'Technical' }
      ],
      languages: [
        { id: 'lang-1', name: 'French', level: 'Native' }
      ],
      resume: 'Passionate software engineer with 2 years of experience.',
      projets: [
        {
          id: 'proj-1',
          title: 'Web Platform',
          description: 'Full web application',
          stack: ['Angular', '.NET'],
          githubUrl: 'https://github.com/proj',
          demoUrl: '',
          isUniversity: false,
          taches: []
        }
      ],
      certifications: [
        {
          id: 'cert-1',
          name: 'Azure Fundamentals',
          issuer: 'Microsoft',
          date: '2023-05',
          verificationUrl: ''
        }
      ]
    });

    const exportResult = service.exportProfileJson();
    expect(exportResult).toBeDefined();
    expect(exportResult.filename).toContain('profile_jane_doe_');
    expect(exportResult.filename).toMatch(/\.json$/);

    const parsed = JSON.parse(exportResult.jsonContent);
    expect(parsed.metadata.format).toBe('NextStep-Profile-JSON');
    expect(parsed.profile.personal.firstName).toBe('Jane');
    expect(parsed.profile.personal.lastName).toBe('Doe');
    expect(parsed.profile.education.length).toBe(1);
    expect(parsed.profile.experience.length).toBe(1);
    expect(parsed.profile.skills.length).toBe(1);
    expect(parsed.profile.languages.length).toBe(1);
    expect(parsed.profile.projects.length).toBe(1);
    expect(parsed.profile.certifications.length).toBe(1);
    expect(parsed.profile.summary).toBe('Passionate software engineer with 2 years of experience.');
  });

  it('should trigger JSON file download (downloadProfileJson)', () => {
    const createObjectURLSpy = vi.fn().mockReturnValue('blob:http://localhost/dummy');
    const revokeObjectURLSpy = vi.fn();
    globalThis.URL.createObjectURL = createObjectURLSpy;
    globalThis.URL.revokeObjectURL = revokeObjectURLSpy;

    const mockAnchor = {
      href: '',
      download: '',
      click: vi.fn(),
    } as any;

    const createElementSpy = vi.spyOn(document, 'createElement').mockReturnValue(mockAnchor);
    const appendChildSpy = vi.spyOn(document.body, 'appendChild').mockImplementation(() => mockAnchor);
    const removeChildSpy = vi.spyOn(document.body, 'removeChild').mockImplementation(() => mockAnchor);

    service.downloadProfileJson();

    expect(createObjectURLSpy).toHaveBeenCalled();
    expect(createElementSpy).toHaveBeenCalledWith('a');
    expect(appendChildSpy).toHaveBeenCalledWith(mockAnchor);
    expect(mockAnchor.click).toHaveBeenCalled();
    expect(removeChildSpy).toHaveBeenCalledWith(mockAnchor);
    expect(revokeObjectURLSpy).toHaveBeenCalledWith('blob:http://localhost/dummy');

    createElementSpy.mockRestore();
    appendChildSpy.mockRestore();
    removeChildSpy.mockRestore();
  });
});
