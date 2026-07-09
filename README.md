# Assistant Agent 🤖

Projet perso pour apprendre à construire des agents IA avec LangChain.
C'est un assistant personnel qui peut gérer mon Google Calendar et envoyer des emails via Gmail, juste en lui parlant en langage naturel.

## Ce que ça fait

- Créer un événement dans Google Calendar (avec lien Google Meet si besoin)
- Vérifier les créneaux libres sur une journée
- Envoyer un email via Gmail
- Enchaîner les deux : "crée un rdv mardi à 14h et envoie les détails par mail à X"

Avant chaque action réelle (créer un event, envoyer un mail), le programme demande une confirmation dans le terminal, pour éviter que l'IA fasse une bêtise toute seule.

## Comment c'est organisé

- `personal_assistant.py` : tout le code principal (agents, prompts, outils)
- `src/google_auth.py` : gère la connexion OAuth avec Google

### Architecture

Un agent "superviseur" reçoit la demande de l'utilisateur et la redirige vers le bon sous-agent :

```
Utilisateur
   │
   ▼
Agent superviseur
   │
   ├── Agent calendrier ── Google Calendar API
   └── Agent email ── Gmail API
```

## Stack technique

- Python
- LangChain (`create_agent`) + OpenAI (gpt-4o-mini)
- Google Calendar API / Gmail API (OAuth2)

## Installation

```bash
pip install langchain langchain-openai google-api-python-client google-auth-oauthlib python-dotenv
```

Il faut aussi :
1. Un fichier `credentials.json` (OAuth Google Cloud Console)
2. Un fichier `.env` avec `OPENAI_API_KEY=...`

Ces fichiers ne sont pas sur le repo car ce sont des secrets.

## Lancer le projet

```bash
python personal_assistant.py
```

Ça ouvre une conversation dans le terminal. Tape `exit` pour quitter.

## Exemple

```
Toi > Crée un événement mardi prochain à 14h avec Léo sur Google Meet
Assistant > [demande confirmation, puis crée l'event et donne le lien]
```

## Ce que j'ai appris en le faisant

- Comment structurer plusieurs agents IA qui collaborent (pattern superviseur / sous-agents)
- Comment brancher un LLM sur de vraies API (Google Calendar, Gmail) avec OAuth2
- L'importance de valider les entrées (dates, formats) avant d'appeler une API externe
- Pourquoi il faut toujours une confirmation humaine avant qu'un agent fasse une action irréversible
