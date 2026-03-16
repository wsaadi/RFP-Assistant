# RFP Assistant

Application web collaborative pour la rédaction assistée par IA de réponses aux appels d'offres (RFP — *Request for Proposal*). Elle permet à une équipe d'importer les documents d'un appel d'offres, de structurer la réponse en chapitres, de générer du contenu via LLM, puis d'exporter le tout en Word ou PowerPoint.

## Fonctionnalités principales

- **Import et analyse de documents** — Upload de fichiers PDF, DOCX, DOC, XLSX, XLS et PPTX (jusqu'à 100 Mo). Les documents sont découpés en chunks, indexés dans une base vectorielle (ChromaDB) et les images sont extraites automatiquement.
- **Anonymisation automatique** — Détection d'entités nommées (NER) via Ollama (Qwen 2.5) pour anonymiser les données sensibles des documents sources avant traitement IA.
- **Analyse d'images par Vision IA** — Analyse automatique des images extraites des documents via un modèle de vision (LLaMA 3.2 Vision).
- **Structuration en chapitres** — Éditeur arborescent de chapitres et sous-chapitres avec notes, références aux sources, axes d'amélioration et limite de mots.
- **Génération de contenu IA** — Rédaction, reformulation et complétion de chapitres via LLM (Mistral AI, Scaleway ou Ollama local) avec recherche sémantique dans les documents sources (RAG).
- **Documents de réponse multiples** — Gestion de plusieurs livrables par projet (rédaction ou complétion de formulaires).
- **Analyse de conformité** — Vérification de la couverture des exigences de l'appel d'offres.
- **Gap analysis** — Identification des écarts entre les exigences et la réponse rédigée.
- **Prévisualisation et chat** — Prévisualisation du document final avec chat IA contextuel pour poser des questions sur le contenu.
- **Export Word et PowerPoint** — Génération de documents DOCX formatés et de présentations PPTX (soutenance).
- **Backup / Restore** — Export et import complet d'un projet au format ZIP.
- **Galerie d'images** — Visualisation, catégorisation et sélection des images extraites pour inclusion dans l'export.
- **Statistiques et suivi des coûts** — Tableaux de bord de progression et suivi de la consommation IA (tokens, coûts par modèle).
- **Workspaces collaboratifs** — Espaces de travail partagés avec gestion des membres et des rôles.
- **Administration** — Gestion des utilisateurs, configuration IA par workspace, personnalisation du branding (logo, couleurs, favicon).
- **Sécurité** — Authentification JWT (cookies httpOnly), rate limiting (nginx + SlowAPI), chiffrement des clés API et des PII, headers de sécurité, protection brute-force, quotas d'upload par utilisateur.

## Architecture

```
┌─────────────┐       ┌──────────────────┐       ┌──────────────┐
│   Frontend   │──────▶│     Backend      │──────▶│  PostgreSQL  │
│  Angular 17  │  HTTP │  FastAPI/Python  │       │   16-alpine  │
│  + Material  │◀──────│   + Celery       │──────▶│              │
│  (nginx)     │       │                  │       └──────────────┘
└─────────────┘       │                  │       ┌──────────────┐
     :80              │                  │──────▶│    Redis 7    │
                      │                  │       │  (broker +   │
                      │                  │       │   cache)     │
                      └──────────────────┘       └──────────────┘
                              │
                      ┌───────┴────────┐
                      │  Celery Workers │
                      │                │
                      │  documents (×1) │─── NER, embeddings, images
                      │  default  (×1)  │─── exports, backups
                      │  ai       (×3)  │─── génération LLM (I/O)
                      └────────────────┘
                              │
                      ┌───────┴────────┐
                      │    Ollama      │
                      │  (NER + Vision │
                      │   + génération)│
                      └────────────────┘
```

## Technologies

| Composant | Stack |
|-----------|-------|
| **Frontend** | Angular 17, Angular Material, Chart.js |
| **Backend** | Python 3.11, FastAPI, SQLAlchemy (async), Pydantic |
| **Tâches asynchrones** | Celery (5 workers : documents, default, ai ×3) |
| **Base de données** | PostgreSQL 16 |
| **Cache / Broker** | Redis 7 (AOF, authentifié, mémoire bornée) |
| **Recherche vectorielle** | ChromaDB + intfloat/multilingual-e5-base |
| **IA / LLM** | Mistral AI, Scaleway, ou Ollama (local) |
| **NER / Anonymisation** | Ollama — Qwen 2.5 (14B) |
| **Vision** | Ollama — LLaMA 3.2 Vision (11B) |
| **Reverse proxy** | nginx (rate limiting, CSP, security headers) |
| **Conteneurisation** | Docker + Docker Compose |
| **GPU (optionnel)** | NVIDIA CUDA 12.6 (Dockerfile.gpu pour DGX Spark / Blackwell) |

## Prérequis

- **Docker** et **Docker Compose** (v2+)
- **Ollama** installé et accessible (par défaut sur `host.docker.internal:11434`)
  - Modèles requis : `qwen2.5:14b` (NER), `llama3.2-vision:11b` (vision, optionnel)
  - Modèle de génération optionnel : `mistral:latest` (si provider Ollama)
- Une **clé API Mistral** ou **Scaleway** (configurable dans l'interface admin, sauf si Ollama est utilisé comme provider de génération)

## Installation et démarrage

### 1. Configuration

```bash
# Cloner le dépôt
git clone <repository-url>
cd RFP-Assistant

# Créer le fichier d'environnement
cp .env.example .env
```

Modifiez `.env` avec des valeurs sécurisées :

| Variable | Description | Obligatoire |
|----------|-------------|:-----------:|
| `POSTGRES_DB` | Nom de la base PostgreSQL | oui |
| `POSTGRES_USER` | Utilisateur PostgreSQL | oui |
| `POSTGRES_PASSWORD` | Mot de passe PostgreSQL (**changer impérativement**) | oui |
| `SECRET_KEY` | Clé secrète JWT — générer avec `python -c "import secrets; print(secrets.token_urlsafe(64))"` | oui |
| `ADMIN_EMAIL` | Email du compte admin par défaut | oui |
| `ADMIN_PASSWORD` | Mot de passe admin (**12+ caractères, mixte**) | oui |
| `REDIS_PASSWORD` | Mot de passe Redis (**changer impérativement**) | oui |
| `CORS_ORIGINS` | Origines CORS autorisées (séparées par des virgules) | non |
| `OLLAMA_BASE_URL` | URL du serveur Ollama | non |
| `OLLAMA_NER_MODEL` | Modèle Ollama pour la NER | non |
| `HF_TOKEN` | Token HuggingFace (téléchargement de modèles) | non |
| `DEBUG` | Mode debug — `true` active Swagger UI (`/api/docs`) | non |

### 2. Lancement avec Docker (recommandé)

```bash
# Démarrer tous les services
docker compose up --build -d

# Vérifier que tout fonctionne
docker compose ps
docker compose logs -f backend
```

L'application est accessible sur **http://localhost** (port 80).

### 3. Lancement avec GPU (NVIDIA)

Pour accélérer le calcul des embeddings sur une machine avec GPU NVIDIA :

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build -d
```

Cela utilise `Dockerfile.gpu` (CUDA 12.6) pour le worker de documents.

### 4. Développement local (sans Docker)

#### Backend

```bash
cd backend

# Créer un environnement virtuel
python3.11 -m venv venv
source venv/bin/activate  # Linux/Mac
# ou : .\venv\Scripts\activate  # Windows

# Installer les dépendances
pip install -r requirements.txt

# Lancer le serveur
uvicorn app.main:app --reload --port 8000
```

> Vous aurez besoin d'une instance PostgreSQL, Redis et Ollama accessibles localement.

#### Frontend

```bash
cd frontend

# Installer les dépendances
npm install

# Lancer le serveur de développement
npm start
```

Le frontend est accessible sur **http://localhost:4200** et proxy les appels `/api` vers le backend.

## Structure du projet

```
RFP-Assistant/
├── backend/
│   ├── app/
│   │   ├── api/              # Routes FastAPI
│   │   │   ├── auth.py       #   Authentification (login, register, JWT)
│   │   │   ├── admin.py      #   Administration (utilisateurs, config IA)
│   │   │   ├── workspaces.py #   Espaces de travail collaboratifs
│   │   │   ├── projects.py   #   Projets RFP (CRUD, plan, analyse, AI)
│   │   │   ├── documents.py  #   Upload, traitement et recherche de documents
│   │   │   ├── chapters.py   #   Chapitres (CRUD, génération IA)
│   │   │   ├── export.py     #   Export Word/PPTX, backup/restore, chat
│   │   │   └── branding.py   #   Personnalisation (logo, couleurs)
│   │   ├── models/           # Modèles SQLAlchemy (ORM)
│   │   ├── schemas/          # Schémas Pydantic (validation)
│   │   ├── services/         # Logique métier
│   │   │   ├── ai_service.py           # Orchestration LLM (RAG)
│   │   │   ├── anonymization_service.py # NER + anonymisation via Ollama
│   │   │   ├── document_service.py     # Parsing PDF/DOCX/XLSX
│   │   │   ├── vector_service.py       # ChromaDB (indexation + recherche)
│   │   │   ├── word_service.py         # Génération DOCX
│   │   │   ├── pptx_service.py         # Génération PPTX (soutenance)
│   │   │   ├── export_service.py       # Backup/restore ZIP
│   │   │   ├── image_analysis_service.py # Vision AI (Ollama)
│   │   │   ├── llm_provider.py         # Abstraction multi-provider LLM
│   │   │   ├── moderation_service.py   # Modération des prompts utilisateur
│   │   │   ├── soutenance_service.py   # Génération de soutenances
│   │   │   └── progress_service.py     # Suivi de progression (Redis)
│   │   ├── tasks/            # Tâches Celery
│   │   │   ├── document_tasks.py  # Traitement de documents (async)
│   │   │   ├── chapter_tasks.py   # Génération de contenu (async)
│   │   │   ├── export_tasks.py    # Export Word/backup (async)
│   │   │   └── project_tasks.py   # Analyse de projet (async)
│   │   ├── main.py           # Point d'entrée FastAPI + migrations
│   │   ├── config.py         # Configuration (Settings / .env)
│   │   ├── database.py       # Connexion PostgreSQL (async)
│   │   ├── security.py       # JWT, hashing, chiffrement
│   │   └── celery_app.py     # Configuration Celery
│   ├── Dockerfile            # Image backend (CPU)
│   ├── Dockerfile.gpu        # Image backend (NVIDIA CUDA 12.6)
│   ├── entrypoint.sh         # Entrypoint Docker
│   └── requirements.txt      # Dépendances Python
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── components/   # Composants Angular
│   │   │   │   ├── login/              # Page de connexion
│   │   │   │   ├── layout/             # Layout principal (sidebar, nav)
│   │   │   │   ├── workspace-list/     # Liste des workspaces
│   │   │   │   ├── workspace-detail/   # Détail d'un workspace + projets
│   │   │   │   ├── project-dashboard/  # Dashboard projet (documents, plan)
│   │   │   │   ├── chapter-editor/     # Éditeur de chapitre + IA
│   │   │   │   ├── image-gallery/      # Galerie d'images du projet
│   │   │   │   ├── preview/            # Prévisualisation + chat IA
│   │   │   │   ├── gap-analysis/       # Analyse des écarts
│   │   │   │   ├── compliance/         # Conformité aux exigences
│   │   │   │   ├── statistics/         # Statistiques de progression
│   │   │   │   ├── soutenance/         # Génération de présentation
│   │   │   │   ├── cost-tracking/      # Suivi des coûts IA (admin)
│   │   │   │   ├── admin-users/        # Gestion des utilisateurs (admin)
│   │   │   │   ├── admin-settings/     # Configuration IA (admin)
│   │   │   │   ├── admin-branding/     # Personnalisation (admin)
│   │   │   │   └── onboarding-guide/   # Guide de démarrage
│   │   │   ├── models/       # Interfaces TypeScript
│   │   │   └── services/     # Services Angular (API, auth, branding)
│   │   └── styles.scss
│   ├── Dockerfile            # Build multi-stage (Node 20 → nginx)
│   ├── nginx.conf            # Configuration nginx (proxy, sécurité)
│   ├── angular.json
│   └── package.json
├── documents_test/           # Documents de test pour le load test
├── docker-compose.yml        # Orchestration complète (8 services)
├── docker-compose.gpu.yml    # Override GPU (NVIDIA)
├── .env.example              # Template de configuration
└── README.md
```

## Services Docker

| Service | Image | Rôle | Mémoire |
|---------|-------|------|---------|
| `db` | postgres:16-alpine | Base de données principale | 512 Mo |
| `redis` | redis:7-alpine | Broker Celery + cache de progression | 512 Mo |
| `backend` | custom (Python 3.11 + FastAPI) | API REST | 5 Go |
| `celery-worker-documents` | custom | Traitement de documents, NER, embeddings, images | 16 Go |
| `celery-worker-default` | custom | Exports Word/PPTX, backups | 4 Go |
| `celery-worker-ai-1/2/3` | custom | Génération LLM (I/O-bound) ×3 | 12 Go chacun |
| `frontend` | nginx:alpine | SPA Angular + reverse proxy | 128 Mo |

## API Endpoints

L'API est préfixée par `/api`. En mode debug (`DEBUG=true`), la documentation Swagger est disponible sur `/api/docs`.

### Authentification (`/api/auth`)

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| POST | `/auth/login` | Connexion (retourne JWT en cookie httpOnly) |
| POST | `/auth/register` | Inscription |
| POST | `/auth/logout` | Déconnexion |
| GET | `/auth/me` | Profil utilisateur courant |
| PUT | `/auth/change-password` | Changement de mot de passe |

### Administration (`/api/admin`)

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/admin/users` | Liste des utilisateurs |
| POST | `/admin/users` | Créer un utilisateur |
| PUT | `/admin/users/{id}` | Modifier un utilisateur |
| DELETE | `/admin/users/{id}` | Supprimer un utilisateur |
| GET | `/admin/ai-config/{workspace_id}` | Configuration IA d'un workspace |
| PUT | `/admin/ai-config/{workspace_id}` | Modifier la configuration IA |

### Workspaces (`/api/workspaces`)

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/workspaces` | Liste des workspaces accessibles |
| POST | `/workspaces` | Créer un workspace |
| PUT | `/workspaces/{id}` | Modifier un workspace |
| DELETE | `/workspaces/{id}` | Supprimer un workspace |
| POST | `/workspaces/{id}/members` | Ajouter un membre |
| DELETE | `/workspaces/{id}/members/{user_id}` | Retirer un membre |

### Projets (`/api/projects`)

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/projects/workspace/{workspace_id}` | Liste des projets d'un workspace |
| POST | `/projects` | Créer un projet |
| GET | `/projects/{id}` | Détail d'un projet |
| PUT | `/projects/{id}` | Modifier un projet |
| DELETE | `/projects/{id}` | Supprimer un projet |
| POST | `/projects/{id}/generate-plan` | Générer le plan de réponse (IA) |
| POST | `/projects/{id}/gap-analysis` | Lancer l'analyse des écarts (IA) |
| POST | `/projects/{id}/compliance-check` | Vérifier la conformité (IA) |

### Documents (`/api/documents`)

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| POST | `/documents/upload/{project_id}` | Uploader un document |
| GET | `/documents/project/{project_id}` | Liste des documents d'un projet |
| DELETE | `/documents/{id}` | Supprimer un document |
| POST | `/documents/search/{project_id}` | Recherche sémantique dans les chunks |
| GET | `/documents/progress/{project_id}` | Progression du traitement |
| GET | `/documents/images/{project_id}` | Images consolidées du projet |
| POST | `/documents/images-analyze/{project_id}` | Analyser les images (Vision IA) |

### Chapitres (`/api/chapters`)

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/chapters/project/{project_id}` | Arbre des chapitres |
| POST | `/chapters/project/{project_id}` | Créer un chapitre |
| GET | `/chapters/{id}` | Détail d'un chapitre |
| PUT | `/chapters/{id}` | Modifier un chapitre |
| DELETE | `/chapters/{id}` | Supprimer un chapitre |
| POST | `/chapters/{id}/generate-content` | Générer le contenu (IA, async) |
| GET | `/chapters/{id}/generate-status` | Statut de la génération |
| POST | `/chapters/{id}/note` | Ajouter une note |
| POST | `/chapters/reorder` | Réordonner les chapitres |

### Export (`/api/export`)

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| POST | `/export/word/{project_id}` | Exporter en Word (DOCX) |
| POST | `/export/soutenance/{project_id}` | Générer une présentation PPTX |
| POST | `/export/backup/{project_id}` | Exporter un backup ZIP |
| POST | `/export/import/{workspace_id}` | Importer un backup ZIP |
| POST | `/export/preview-chat/{project_id}` | Chat IA sur le contenu du projet |

### Branding (`/api/branding`)

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/branding/settings` | Paramètres de branding (public) |
| PUT | `/branding/settings` | Modifier le branding (admin) |
| POST | `/branding/logo` | Uploader un logo (admin) |
| POST | `/branding/favicon` | Uploader un favicon (admin) |

### Santé

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/` | Version de l'API |
| GET | `/api/health` | Health check (détails étendus pour les admins) |

## Sécurité

- **Authentification** : JWT stocké en cookie httpOnly (pas de localStorage)
- **Rate limiting** : nginx (30 req/min sur login) + SlowAPI (60 req/min global)
- **Brute-force** : Verrouillage après 10 tentatives échouées (15 min)
- **Headers** : HSTS, X-Frame-Options DENY, CSP, X-Content-Type-Options, Referrer-Policy
- **Chiffrement** : Clés API chiffrées en base, PII chiffrées (Fernet)
- **Validation fichiers** : Vérification des magic bytes (anti-spoofing d'extension)
- **Quotas** : Limite de stockage par utilisateur (5 Go par défaut)
- **Réseau** : PostgreSQL et Redis non exposés sur l'hôte (réseau Docker interne uniquement)
- **Non-root** : Le backend tourne sous un utilisateur `appuser` dédié
- **Swagger désactivé en production** : `/api/docs` uniquement en mode `DEBUG=true`

## Licence

Usage interne.
