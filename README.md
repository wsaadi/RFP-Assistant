# UTC TN05 - Assistant Rapport de Stage

Application web intelligente pour aider les étudiants de l'UTC à rédiger leur rapport de stage TN05 (stage ouvrier/exécutant).

## Fonctionnalités

- **Plan détaillé automatique** : Génération d'un plan conforme aux exigences UTC TN05
- **Éditeur graphique** : Interface intuitive pour organiser notes et contenu
- **Questions suggérées** : L'IA génère des questions pertinentes à poser pendant le stage
- **Recommandations personnalisées** : Conseils adaptés à l'avancement de chaque section
- **Export Word** : Génération d'un document Word formaté selon les normes UTC
- **Rédaction assistée** : Transformation des notes en texte professionnel sans fautes

## Technologies

- **Backend** : Python 3.11 + FastAPI
- **Frontend** : Angular 17 + Angular Material
- **IA** : OpenAI (GPT-4o) ou Mistral AI (Mistral Large)
- **Déploiement** : Docker + Docker Compose

## Prérequis

- Docker et Docker Compose installés
- Une clé API OpenAI ou Mistral AI

## Installation et démarrage

### Avec Docker (recommandé)

```bash
# Cloner le dépôt
git clone <repository-url>
cd fab-utc

# Lancer l'application
docker-compose up --build

# L'application sera accessible sur http://localhost
```

### Développement local

#### Backend

```bash
cd backend

# Créer un environnement virtuel
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
.\venv\Scripts\activate  # Windows

# Installer les dépendances
pip install -r requirements.txt

# Lancer le serveur
uvicorn app.main:app --reload --port 8000
```

#### Frontend

```bash
cd frontend

# Installer les dépendances
npm install

# Lancer le serveur de développement
npm start

# L'application sera accessible sur http://localhost:4200
```

## Configuration

L'application ne nécessite pas de fichier de configuration. La clé API est saisie directement dans l'interface lors de la première utilisation et stockée localement dans le navigateur.

## Structure du projet

```
fab-utc/
├── backend/
│   ├── app/
│   │   ├── api/           # Routes FastAPI
│   │   ├── models/        # Modèles Pydantic
│   │   ├── services/      # Services métier
│   │   └── main.py        # Point d'entrée
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── components/  # Composants Angular
│   │   │   ├── models/      # Interfaces TypeScript
│   │   │   └── services/    # Services Angular
│   │   └── styles.scss
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml
└── README.md
```

## Utilisation

1. **Configuration IA** : Sélectionnez OpenAI ou Mistral et entrez votre clé API
2. **Informations** : Renseignez vos informations personnelles et celles du stage
3. **Rédaction** : Utilisez l'éditeur pour :
   - Ajouter des notes pour chaque section
   - Générer des questions à poser pendant le stage
   - Obtenir des recommandations personnalisées
   - Rédiger et améliorer le contenu avec l'IA
4. **Export** : Générez votre rapport au format Word

## Conformité UTC TN05

L'application respecte intégralement les consignes de rédaction UTC :

- Structure du rapport (10-20 pages hors annexes)
- Page de garde conforme
- Sections obligatoires (présentation entreprise, tâches, bilan, analyse...)
- Mise en forme professionnelle
- Style de rédaction adapté

## API Endpoints

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/api/health` | Vérification de l'état du service |
| GET | `/api/guidelines` | Récupérer les consignes UTC |
| GET | `/api/plan/default` | Obtenir le plan par défaut |
| POST | `/api/reports` | Créer un nouveau rapport |
| POST | `/api/ai/test` | Tester la connexion IA |
| POST | `/api/ai/questions` | Générer des questions |
| POST | `/api/ai/recommendations` | Obtenir des recommandations |
| POST | `/api/ai/generate-content` | Générer du contenu |
| POST | `/api/generate-word` | Exporter en Word |

## Licence

Ce projet est destiné à un usage éducatif pour les étudiants de l'UTC.
