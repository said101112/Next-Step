import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { ArenaService } from './arena.service';
import { ArenaConfig, ChatMessage } from './arena.models';

describe('ArenaService (Chatbot Testing)', () => {
  let service: ArenaService;
  let httpMock: HttpTestingController;

  const mockArenaConfig: ArenaConfig = {
    domain: 'software',
    level: 'senior',
    duration_minutes: 20,
    language: 'en',
    focus_areas: ['React', 'Node.js']
  };

  const mockOfferConfig: ArenaConfig = {
    domain: 'software',
    level: 'senior',
    duration_minutes: 30,
    language: 'fr',
    focus_areas: ['Docker', 'Kubernetes'],
    offer_id: 'b1e1e1e1-e1e1-4e1e-b1e1-e1e1e1e1e1e1'
  };

  beforeEach(() => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        ArenaService,
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    service = TestBed.inject(ArenaService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should be created successfully', () => {
    expect(service).toBeTruthy();
  });

  // ───────────────────────────────────────────────────────────
  // 1. TESTS DE GET_QUESTIONS
  // ───────────────────────────────────────────────────────────
  describe('getQuestions()', () => {
    it('should query /questions in Arena Mode (without offerId)', () => {
      const mockResponse = {
        sessionId: 'test-session-id',
        questions: [
          { texteQuestion: 'Explain process vs thread', typeQuestion: 'technical', source: 'generated', companySpecific: false, conseilReponse: 'Use diagrams' }
        ]
      };

      service.getQuestions(mockArenaConfig).subscribe(res => {
        expect(res.status).toBe('success');
        expect(res.total).toBe(1);
        expect(res.session_id).toBe('test-session-id');
        expect(res.questions[0]).toEqual({
          id: expect.any(String),
          question: 'Explain process vs thread',
          type: 'technical',
          source: 'generated',
          company_specific: false,
          tip: 'Use diagrams'
        });
      });

      const req = httpMock.expectOne('http://localhost:5000/api/arena/questions');
      expect(req.request.method).toBe('POST');
      expect(req.request.body.arenaConfig).toEqual({
        domain: 'software',
        level: 'senior',
        durationMinutes: 20,
        language: 'en',
        focusAreas: ['React', 'Node.js'],
        offerId: undefined
      });
      expect(req.request.body.offerId).toBeUndefined();
      req.flush(mockResponse);
    });

    it('should query /questions in Offer Mode (with offerId)', () => {
      const mockResponse = {
        sessionId: 'test-session-id',
        questions: [
          { texteQuestion: 'What is Kubernetes?', typeQuestion: 'technical', source: 'glassdoor', companySpecific: true, conseilReponse: 'Explain pods' }
        ]
      };

      service.getQuestions(mockOfferConfig).subscribe(res => {
        expect(res.status).toBe('success');
        expect(res.total).toBe(1);
        expect(res.session_id).toBe('test-session-id');
        expect(res.questions[0]).toEqual({
          id: expect.any(String),
          question: 'What is Kubernetes?',
          type: 'technical',
          source: 'glassdoor',
          company_specific: true,
          tip: 'Explain pods'
        });
      });

      const req = httpMock.expectOne('http://localhost:5000/api/arena/questions');
      expect(req.request.method).toBe('POST');
      expect(req.request.body.offerId).toBe('b1e1e1e1-e1e1-4e1e-b1e1-e1e1e1e1e1e1');
      expect(req.request.body.arenaConfig).toEqual({
        domain: 'software',
        level: 'senior',
        durationMinutes: 30,
        language: 'fr',
        focusAreas: ['Docker', 'Kubernetes'],
        offerId: 'b1e1e1e1-e1e1-4e1e-b1e1-e1e1e1e1e1e1'
      });
      req.flush(mockResponse);
    });
  });

  // ───────────────────────────────────────────────────────────
  // 2. TESTS DE START_SESSION
  // ───────────────────────────────────────────────────────────
  describe('startSession()', () => {
    it('should query /session/start in Arena Mode', () => {
      const mockResponse = {
        sessionId: 'arena-session-id',
        openingMessage: 'Welcome to your Software Arena!'
      };

      service.startSession(mockArenaConfig, 'arena-session-id', []).subscribe(res => {
        expect(res.status).toBe('success');
        expect(res.session_id).toBe('arena-session-id');
        expect(res.opening_message).toBe('Welcome to your Software Arena!');
      });

      const req = httpMock.expectOne('http://localhost:5000/api/arena/session/start');
      expect(req.request.method).toBe('POST');
      expect(req.request.body.sessionId).toBe('arena-session-id');
      expect(req.request.body.offerId).toBeUndefined();
      req.flush(mockResponse);
    });

    it('should query /session/start in Offer Mode', () => {
      const mockResponse = {
        sessionId: 'offer-session-id',
        openingMessage: 'Welcome to Google! Tell me about Docker.'
      };

      service.startSession(mockOfferConfig, 'offer-session-id', []).subscribe(res => {
        expect(res.status).toBe('success');
        expect(res.session_id).toBe('offer-session-id');
        expect(res.opening_message).toBe('Welcome to Google! Tell me about Docker.');
      });

      const req = httpMock.expectOne('http://localhost:5000/api/arena/session/start');
      expect(req.request.method).toBe('POST');
      expect(req.request.body.sessionId).toBe('offer-session-id');
      expect(req.request.body.offerId).toBe('b1e1e1e1-e1e1-4e1e-b1e1-e1e1e1e1e1e1');
      req.flush(mockResponse);
    });
  });

  // ───────────────────────────────────────────────────────────
  // 3. TESTS DE SEND_MESSAGE
  // ───────────────────────────────────────────────────────────
  describe('sendMessage()', () => {
    const chatHistory: ChatMessage[] = [
      { role: 'ai', content: 'Tell me about yourself.' },
      { role: 'user', content: 'I am a senior full stack developer.' }
    ];

    it('should query /session/message in Arena Mode', () => {
      const mockResponse = {
        sessionId: 'arena-session-id',
        aiResponse: 'Great. Let us move to React questions.'
      };

      service.sendMessage('arena-session-id', 'I love coding.', chatHistory, mockArenaConfig).subscribe(res => {
        expect(res.status).toBe('success');
        expect(res.session_id).toBe('arena-session-id');
        expect(res.ai_response).toBe('Great. Let us move to React questions.');
      });

      const req = httpMock.expectOne('http://localhost:5000/api/arena/session/message');
      expect(req.request.method).toBe('POST');
      expect(req.request.body.userInput).toBe('I love coding.');
      expect(req.request.body.offerId).toBeUndefined();
      expect(req.request.body.history).toEqual([
        { role: 'ai', content: 'Tell me about yourself.' },
        { role: 'user', content: 'I am a senior full stack developer.' }
      ]);
      req.flush(mockResponse);
    });

    it('should query /session/message in Offer Mode', () => {
      const mockResponse = {
        sessionId: 'offer-session-id',
        aiResponse: 'Excellent. Tell me about Kubernetes.'
      };

      service.sendMessage('offer-session-id', 'I have Docker skills.', chatHistory, mockOfferConfig).subscribe(res => {
        expect(res.status).toBe('success');
        expect(res.session_id).toBe('offer-session-id');
        expect(res.ai_response).toBe('Excellent. Tell me about Kubernetes.');
      });

      const req = httpMock.expectOne('http://localhost:5000/api/arena/session/message');
      expect(req.request.method).toBe('POST');
      expect(req.request.body.offerId).toBe('b1e1e1e1-e1e1-4e1e-b1e1-e1e1e1e1e1e1');
      req.flush(mockResponse);
    });
  });

  // ───────────────────────────────────────────────────────────
  // 4. TESTS DE END_SESSION
  // ───────────────────────────────────────────────────────────
  describe('endSession()', () => {
    const chatHistory: ChatMessage[] = [
      { role: 'ai', content: 'First question' },
      { role: 'user', content: 'First answer' }
    ];

    const mockEndResponse = {
      score: 85,
      feedback: {
        globalScore: 85,
        dimensions: [
          { name: 'Technical', score: 9, comment: 'Very deep' }
        ],
        questionEvaluations: [
          { question: 'First question', userAnswer: 'First answer', score: 8, correction: 'Good, but specify Docker details.' }
        ],
        strengths: ['Problem-solving'],
        improvements: ['Explain architecture deeper'],
        bestAnswer: 'First answer',
        worstAnswer: '',
        coachingTips: ['Pace your speech']
      }
    };

    it('should query /session/end in Arena Mode', () => {
      service.endSession('arena-session-id', chatHistory, mockArenaConfig).subscribe(res => {
        expect(res.status).toBe('success');
        expect(res.session_id).toBe('arena-session-id');
        expect(res.score).toBe(85);
        expect(res.feedback.globalScore).toBe(85);
        expect(res.feedback.strengths).toEqual(['Problem-solving']);
        expect(res.feedback.questionEvaluations[0].userAnswer).toBe('First answer');
      });

      const req = httpMock.expectOne('http://localhost:5000/api/arena/session/end');
      expect(req.request.method).toBe('POST');
      expect(req.request.body.offerId).toBeUndefined();
      req.flush({ ...mockEndResponse, sessionId: 'arena-session-id' });
    });

    it('should query /session/end in Offer Mode', () => {
      service.endSession('offer-session-id', chatHistory, mockOfferConfig).subscribe(res => {
        expect(res.status).toBe('success');
        expect(res.session_id).toBe('offer-session-id');
        expect(res.score).toBe(85);
        expect((res.feedback as any).feedback_out).toBeUndefined(); // ensure mapper cleaned up response
      });

      const req = httpMock.expectOne('http://localhost:5000/api/arena/session/end');
      expect(req.request.method).toBe('POST');
      expect(req.request.body.offerId).toBe('b1e1e1e1-e1e1-4e1e-b1e1-e1e1e1e1e1e1');
      req.flush({ ...mockEndResponse, sessionId: 'offer-session-id' });
    });
  });

  // ───────────────────────────────────────────────────────────
  // 5. TESTS DE GET_SALARY
  // ───────────────────────────────────────────────────────────
  describe('getSalary()', () => {
    const mockSalaryResponse = {
      rangeMin: 120000,
      rangeMax: 185000,
      currency: 'USD',
      yourTarget: 155000,
      confidenceLevel: 'high',
      marketSources: ['Glassdoor', 'LinkedIn'],
      negotiationScript: [
        { step: 1, action: 'State your target', phrase: 'I expect 155k USD.', why: 'Align with Google averages' }
      ]
    };

    it('should query /salary in Arena Mode', () => {
      service.getSalary(mockArenaConfig).subscribe(res => {
        expect(res.status).toBe('success');
        expect(res.range_min).toBe(120000);
        expect(res.range_max).toBe(185000);
        expect(res.currency).toBe('USD');
        expect(res.your_target).toBe(155000);
        expect(res.confidence_level).toBe('high');
        expect(res.negotiation_script[0].phrase).toBe('I expect 155k USD.');
      });

      const req = httpMock.expectOne('http://localhost:5000/api/arena/salary');
      expect(req.request.method).toBe('POST');
      expect(req.request.body.offerId).toBeUndefined();
      req.flush(mockSalaryResponse);
    });

    it('should query /salary in Offer Mode', () => {
      service.getSalary(mockOfferConfig).subscribe(res => {
        expect(res.status).toBe('success');
        expect(res.range_min).toBe(120000);
        expect((res as any).offerId).toBeUndefined(); // ensure mapper correctly mapped response
      });

      const req = httpMock.expectOne('http://localhost:5000/api/arena/salary');
      expect(req.request.method).toBe('POST');
      expect(req.request.body.offerId).toBe('b1e1e1e1-e1e1-4e1e-b1e1-e1e1e1e1e1e1');
      req.flush(mockSalaryResponse);
    });
  });

  // ───────────────────────────────────────────────────────────
  // 6. TESTS DU CHAT LIBRE & COACH SALAIRE
  // ───────────────────────────────────────────────────────────
  describe('freeChat() & salaryCoach()', () => {
    it('should query /chat via freeChat()', () => {
      const mockResponse = {
        threadId: 'chat-thread-123',
        response: 'Here is a tip about STAR method.'
      };

      service.freeChat('How to answer Q2?', 'chat-thread-123', []).subscribe(res => {
        expect(res.status).toBe('success');
        expect(res.thread_id).toBe('chat-thread-123');
        expect(res.response).toBe('Here is a tip about STAR method.');
      });

      const req = httpMock.expectOne('http://localhost:5000/api/arena/chat');
      expect(req.request.method).toBe('POST');
      expect(req.request.body.userInput).toBe('How to answer Q2?');
      expect(req.request.body.threadId).toBe('chat-thread-123');
      req.flush(mockResponse);
    });

    it('should query /salary-coach via salaryCoach()', () => {
      const mockResponse = {
        status: 'success',
        threadId: 'salary-thread-456',
        response: 'To negotiate, start with your high range.'
      };

      const salaryCtx = { rangeMin: 120000, rangeMax: 185000, currency: 'USD', yourTarget: 155000 };

      service.salaryCoach('How to counter-offer?', 'salary-thread-456', salaryCtx, [], mockArenaConfig).subscribe(res => {
        expect(res.status).toBe('success');
        expect(res.response).toBe('To negotiate, start with your high range.');
      });

      const req = httpMock.expectOne('http://localhost:5000/api/arena/salary-coach');
      expect(req.request.method).toBe('POST');
      expect(req.request.body.userInput).toBe('How to counter-offer?');
      expect(req.request.body.threadId).toBe('salary-thread-456');
      expect(req.request.body.salaryContext).toEqual(salaryCtx);
      req.flush(mockResponse);
    });
  });

  // ───────────────────────────────────────────────────────────
  // 7. TESTS DE L'HISTORIQUE ET DES OFFRES
  // ───────────────────────────────────────────────────────────
  describe('Session History & Offers list', () => {
    it('should query /sessions via getSessions()', () => {
      const mockList = [
        {
          sessionId: 'session-abc',
          mode: 'arena',
          status: 'completed',
          language: 'fr',
          durationMinutes: 20,
          domain: 'software',
          level: 'senior',
          scoreEntretien: 80,
          dateSession: '2026-05-17'
        }
      ];

      service.getSessions('user-123').subscribe(res => {
        expect(res.length).toBe(1);
        expect(res[0].sessionId).toBe('session-abc');
        expect(res[0].scoreEntretien).toBe(80);
      });

      const req = httpMock.expectOne('http://localhost:5000/api/arena/sessions?userId=user-123');
      expect(req.request.method).toBe('GET');
      req.flush(mockList);
    });

    it('should query /sessions/:id via getSessionDetail()', () => {
      const mockDetail = {
        sessionId: 'session-abc',
        mode: 'arena',
        status: 'completed',
        language: 'fr',
        durationMinutes: 20,
        domain: 'software',
        level: 'senior',
        globalScore: 80,
        dateSession: '2026-05-17',
        dimensions: [{ name: 'Tech', score: 8, comment: 'Nice' }],
        strengths: ['coding'],
        improvements: ['none'],
        coachingTips: ['relax'],
        questionEvaluations: [{ question: 'Q?', userAnswer: 'A', score: 8, correction: 'correct' }],
        bestAnswer: 'A',
        worstAnswer: ''
      };

      service.getSessionDetail('session-abc').subscribe(res => {
        expect(res.sessionId).toBe('session-abc');
        expect(res.globalScore).toBe(80);
        expect(res.dimensions[0].name).toBe('Tech');
      });

      const req = httpMock.expectOne('http://localhost:5000/api/arena/sessions/session-abc');
      expect(req.request.method).toBe('GET');
      req.flush(mockDetail);
    });

    it('should query /sessions/:id/delete via deleteSession()', () => {
      service.deleteSession('session-abc').subscribe(res => {
        expect(res).toBeNull();
      });

      const req = httpMock.expectOne('http://localhost:5000/api/arena/sessions/session-abc/delete');
      expect(req.request.method).toBe('POST');
      req.flush(null);
    });

    it('should query /my-offers via getMyOffers()', () => {
      const mockOffers = [
        {
          offerId: 'offer-123',
          jobTitle: 'Software Engineer',
          company: 'NovaTech',
          location: 'New York',
          contractType: 'Full-time',
          matchingScore: 92,
          yearsExperience: 5,
          requiredSkills: ['Python', 'Docker'],
          dateAnalysed: '2026-05-17'
        }
      ];

      service.getMyOffers().subscribe(res => {
        expect(res.length).toBe(1);
        expect(res[0].offerId).toBe('offer-123');
        expect(res[0].jobTitle).toBe('Software Engineer');
        expect(res[0].company).toBe('NovaTech');
      });

      const req = httpMock.expectOne('http://localhost:5000/api/arena/my-offers');
      expect(req.request.method).toBe('GET');
      req.flush(mockOffers);
    });
  });
});
