# NextStep

Plateforme IA de pilotage de candidatures: sourcing d'offres, analyse/matching, génération de CV ciblé, génération/envoi d'emails, suivi de réponses recruteur, préparation d'entretien et coaching.

## Table des matières
1. Vue d'ensemble
2. Fonctionnalités principales
3. Architecture technique
4. Stack technologique
5. Structure du projet
6. Parcours utilisateur (end-to-end)
7. APIs et modules backend
8. Installation et démarrage
9. Variables d'environnement
10. Commandes utiles (dev/test/build)
11. Qualité, observabilité et jobs
12. Troubleshooting

## Vue d'ensemble
NextStep centralise le cycle complet de candidature:
- découverte d'offres (scraping multi-source),
- analyse IA de l'offre vs profil,
- génération de CV personnalisé,
- génération et envoi d'emails de candidature,
- suivi intelligent des réponses recruteur,
- simulation/préparation d'entretien.

Le projet est organisé en architecture modulaire:
- `frontend` Angular (UX + pipeline interactif),
- `backend` ASP.NET Core (API métier + persistance + orchestration),
- `agents` FastAPI/LangGraph (agents IA spécialisés).

## Fonctionnalités principales

### 1) Profil candidat
- onboarding guidé,
- édition sections: informations perso, expériences, projets, compétences, formations, certifications,
- upload/import CV et parsing,
- import LinkedIn.

### 2) Offres & pipeline d'analyse
- soumission d'offre (URL/texte),
- analyse synchrone (titre, compétences, contrat, localisation, scores),
- matching + ATS + recommandations,
- progression pipeline en étapes (`Offre -> Skill Gap -> Template -> CV Final -> Email & Send`),
- restauration d'analyse depuis historique.

### 3) Scraping d'offres
- sources: LinkedIn, Indeed, Glassdoor,
- filtres (mots-clés, localisation, date, type contrat, provider),
- workflow states (`saved`, `shortlisted`, `archived`),
- promotion d'une offre scrapée vers le pipeline d'analyse.

### 4) CV Builder
- templates CV (Modern, Latex, etc.),
- prévisualisation HTML/PDF,
- historique de CV générés,
- téléchargement et suppression,
- stockage objet via MinIO.

### 5) Email & Letter
- génération de drafts d'emails (candidature, follow-up, reply),
- workspace par candidature,
- connexion Gmail OAuth (credentials utilisateur),
- envoi email avec/sans pièce jointe CV,
- suivi statut d'envoi, brouillons et historique.

### 6) Suivi des réponses recruteur
- polling/monitoring des threads Gmail,
- classification de réponses (retenu/refus/entretien/en attente),
- détection follow-up nécessaire,
- jobs automatiques backend (Hangfire).

### 7) Company Intelligence
- analyse entreprise (culture, signaux, questions d'entretien),
- écran dédié de restitution.

### 8) Chatbot carrière
- mode entretien (session question/réponse),
- salary coach,
- assistant conversationnel orienté candidature.

### 9) Dashboard
- KPIs (candidatures, statuts, succès, CV générés),
- offres récentes scrapées,
- activités et candidatures récentes.

## Architecture technique

### Frontend
- Angular 19 standalone components,
- Tailwind + SCSS,
- routing lazy-loaded,
- SignalR client pour progression pipeline,
- Keycloak Angular pour auth.

### Backend
- ASP.NET Core (`net10.0`),
- architecture modulaire par domaines (`Modules/*`),
- Entity Framework Core + PostgreSQL,
- SignalR Hub (`/hubs/pipeline`),
- Hangfire pour jobs récurrents,
- génération PDF via QuestPDF/Puppeteer,
- intégrations: Keycloak, MinIO.

### Agents IA
- FastAPI + LangGraph,
- domaines IA: `offer_analyzer`, `profile_retriever`, `skill_gap`, `cv_optimizer`, `cv_engine`, `company`, `email_composer`, `chatbot`,
- appels LLM multi-provider (Groq/Gemini/OpenAI selon configuration).

## Stack technologique
- Frontend: Angular 19, TypeScript, TailwindCSS, RxJS, SignalR, Vitest
- Backend: ASP.NET Core, EF Core, Npgsql, Hangfire, QuestPDF, PuppeteerSharp
- IA: FastAPI, LangChain, LangGraph, Groq/Gemini/OpenAI
- Data/Infra: PostgreSQL (+pgvector), MinIO, Keycloak, Docker Compose
- Qualité: SonarQube

## Structure du projet
```text
NextStep/
├─ frontend/                 # UI Angular
├─ backend/                  # API .NET + modules métier
├─ agents/                   # API FastAPI + agents IA
├─ init_config/
│  ├─ postgres/              # scripts init DB + seeds
│  ├─ keycloak/              # realm import + thèmes custom
│  └─ nginx/                 # reverse proxy (prod)
├─ infra/aws/                # Terraform AWS (voir infra/aws/README.md)
│  ├─ enterprise-fargate/    # production: ECS Fargate, ALB, RDS Multi-AZ, KMS
│  └─ ec2-quickstart/        # démo live: 1 EC2 + docker-compose.prod.yml + HTTPS
├─ scripts/                  # dev.ps1 (stack local sans Docker)
├─ docs/                     # diagrammes et documentation
├─ docker-compose.yml        # base commune (services, healthchecks, volumes)
├─ docker-compose.dev.yml    # surcharge dev (ports, hot reload)
├─ docker-compose.prod.yml   # surcharge prod (reverse proxy, restart, limites)
└─ NextStep.sln
```

## Parcours utilisateur (end-to-end)
1. L'utilisateur complète son profil.
2. Il source une offre (scraping) ou colle une offre manuellement.
3. Le pipeline IA analyse l'offre et calcule le matching/ATS.
4. Il choisit un template et génère un CV ciblé.
5. Il génère un email de candidature.
6. Il envoie via Gmail connecté.
7. NextStep suit les réponses recruteur et met à jour le statut candidature.

## APIs et modules backend

### Principaux contrôleurs .NET
- `api/profile` (`ProfileController`)
- `api/offers` (`OfferController`)
- `api/cv` (`CvController`)
- `api/emails` (`EmailController`)
- `api/email-connections` (`EmailConnectionsController`)
- `api/candidatures` (`CandidatureController`)
- `api/sourced-offers` (`SourcedOffersController`)
- `api/arena` (`ArenaController`)
- `api/identity` (`IdentityController`)

### Routes agents FastAPI (exemples)
- `/offer/*` (pipeline, analyze-offer, match)
- `/cv-optimizer/*`
- `/cv-engine/*`
- `/company/*`
- `/email/*` (generate, follow-up, classify, reply)
- `/linkedin-jobs/*`, `/indeed-jobs/*`, `/glassdoor-jobs/*`
- `/resume/parse`, `/resume/parse-linkedin`
- `/chatbot/*`

## Installation et démarrage

## Option A - Docker Compose (recommandé)
Prérequis:
- Docker + Docker Compose

Étapes:
1. Copier l'environnement:
```bash
cp .env.example .env
```
2. Renseigner les clés/API secrets dans `.env`.
3. Lancer la stack **dev** (hot reload, tous les ports ouverts):
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```
Le premier build est long (téléchargement des images de base et des dépendances). Ensuite, lancer simplement `up` : le code du backend, des agents et du frontend est monté et rechargé à chaud. `--build` n'est utile qu'après une modification d'un `Dockerfile`, de `requirements.txt`, `package.json` ou `NextStep.csproj`.

Services (dev):
- Frontend: `http://localhost:4200`
- Backend API: `http://localhost:5000` (Swagger: `/swagger`, Hangfire: `/hangfire`)
- Agents FastAPI: `http://localhost:8000/docs`
- Keycloak: `http://localhost:8080`
- PostgreSQL: `localhost:5433`

**Production** (seul le reverse proxy nginx est exposé, port `HTTP_PORT`, défaut 80):
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```
Renseigner `PUBLIC_URL` dans `.env`. Routes: `/api`, `/hubs`, `/uploads` → backend, `/api/agents/*` → agents (proxy backend, service interne), `/auth` → Keycloak, `/` → frontend.

Stockage des fichiers: disque local (volume Docker) par défaut (`STORAGE_MODE=Local`). MinIO est optionnel via `--profile minio` (voir `docker-compose.yml`).

## Option B - Démarrage manuel (dev)
### Frontend
```bash
cd frontend
npm install
npm run start
```

### Backend
```bash
cd backend
dotnet restore
dotnet run
```

### Agents
```bash
cd agents
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Variables d'environnement
Référence: `.env.example`

Variables critiques:
- DB: `POSTGRES_*`, `ConnectionStrings__DefaultConnection`, `DATABASE_URL`
- Auth: `KEYCLOAK_*`, `Keycloak__ClientSecret`
- LLM: `GROQ_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`, priorités `LLM_PROVIDER_PRIORITY`
- Email OAuth: credentials Google OAuth + callback URL
- Storage: `MINIO_*`
- Search: `TAVILY_API_KEY`

## Commandes utiles (dev/test/build)

### Frontend
```bash
npm run start
npm run build
npm run test
```

### Backend
```bash
dotnet build
dotnet test backend/tests/NextStep.Tests.csproj
```

### Agents
```bash
pytest
```

## Qualité, observabilité et jobs
- Analyse SonarQube dans la CI GitHub Actions
- Logs backend centralisés (`Console` + `Debug`)
- SignalR pour état live du pipeline
- Jobs Hangfire:
  - `check-email-replies`
  - `detect-follow-up-needed`

## Troubleshooting

### 1) Gmail OAuth échoue (redirect mismatch / access denied)
- Vérifier `redirect_uri` exact dans Google Cloud Console.
- Ajouter les test users si app en mode test.
- Vérifier que credentials sont bien enregistrés côté `api/email-connections`.

### 2) Email envoyé sans pièce jointe
- Vérifier que le CV final est bien sauvegardé (`api/cv/save` / historique CV).
- Vérifier que l'ID CV utilisé pour l'envoi correspond au dernier CV généré.

### 3) Pipeline bloqué sur "Saving..."
- Vérifier logs backend (PDF renderer, SignalR, endpoints `/offers/*`).
- Vérifier le stockage des fichiers (volume `backend_storage` ou MinIO) et la persistance DB.
- Vérifier timeouts API ou erreurs `500` dans l'onglet réseau frontend.

### 4) Scraping ne lance pas le bon écran
- Le flux attendu est `offers-recent -> /offers/analyze?offerId=...`.
- Vérifier que l'offre est bien promue (`/api/sourced-offers/{id}/promote`) avant analyse.

---

Si tu veux, je peux aussi te générer un `README-ARCHITECTURE.md` séparé avec diagrammes de flux (pipeline offre, pipeline email, classification réponse recruteur) et mapping complet des endpoints par module.
