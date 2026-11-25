# MathTutor — SaaS de tutorat de maths avec IA (RAG), pour tuteurs, élèves et parents

Un seul projet Python (FastAPI) : site web + API + base de données + tuteur IA + moteur de calcul.
Pages légères (aucune librairie externe, ~15 Ko de CSS/JS), installable sur téléphone (PWA), français + anglais.

## Démarrage rapide (5 minutes)

```bash
python -m venv .venv && source .venv/bin/activate      # Windows : .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                     # puis éditez-le (voir plus bas)
uvicorn app.main:app --reload
```
Ouvrez http://localhost:8000. Au premier lancement, la base SQLite est créée et remplie
(plans, programmes d'exemple, exercices, cours d'exemple, comptes de démo).

**Comptes de démo** (mot de passe `demo1234`) :
| Rôle | Email |
|---|---|
| Tuteur (propriétaire du « Centre Démo ») | `tutor@demo.test` |
| Élève (3ème, Bénin) | `student@demo.test` |
| Parent (lié à l'élève) | `parent@demo.test` |

Codes du centre démo : élèves `DEMO-ELEVE`, tuteurs `DEMO-TUTEUR` ; code de liaison de l'élève : `E-DEMO22`.
⚠ En production : `SEED_DEMO=0` et `ENV=production`.

## Activer l'IA
Sans clé, le tuteur fonctionne en « mode sans IA » : il renvoie le calcul vérifié et les extraits de cours trouvés.
Pour activer le modèle : mettez `ANTHROPIC_API_KEY=...` dans `.env` (modèle réglable avec `ANTHROPIC_MODEL`).

## Ce que contient le projet

| Besoin | Où c'est |
|---|---|
| Comptes + rôles (élève, parent, tuteur, admin d'école), espaces de travail multi-tenant | `app/models.py`, `app/security.py`, `app/routers/auth.py` |
| Dashboard élève / parent / tuteur / admin | `app/routers/{student,parent,tutor,admin}.py` + `app/templates/` |
| Suivi instantané (activité en direct, alertes de difficulté, messages tuteur → parents) | `app/services/{progress,notifier,events}.py` (SSE) |
| Programmes par pays → niveau → chapitres (en base de données) | `app/models.py` (Country/Level/Chapter), `app/seed.py` |
| RAG : import PDF/TXT/MD, découpage, indexation, recherche BM25 filtrée (pays, niveau, espace) | `app/services/rag.py` |
| Tuteur IA socratique + citations + quota par plan | `app/services/tutor.py`, `app/services/llm.py` |
| Moteur de calcul SymPy (vérifie les réponses, calcule le « résultat de référence » donné à l'IA) | `app/services/mathengine.py` |
| CRM des prospects (pipeline Nouveau → Inscrit) | `app/routers/tutor.py`, `templates/crm.html` |
| SaaS : plans, quotas, paiements (Flutterwave : cartes + mobile money) | `app/services/payments.py`, `app/routers/admin.py` |
| Notifications in-app + WhatsApp (optionnel) | `app/services/notifier.py` |
| Multilingue (fr/en), RTL prévu | `app/i18n.py` |
| PWA : installable, page hors ligne, réponses d'exercices mises en file hors connexion | `static/sw.js`, `static/app.js` |

## Comment fonctionne le tuteur IA
1. Le message de l'élève passe dans le **moteur de calcul** : s'il contient une équation ou un calcul, SymPy le résout.
2. Le **RAG** cherche les passages pertinents dans les cours visibles par l'élève (cours officiels du pays/niveau + cours privés de son tuteur).
3. Le modèle reçoit : consignes pédagogiques (guider pas à pas, ne pas donner la solution trop vite), pays/niveau, **résultat vérifié** (vérité à ne pas contredire) et extraits de cours (traités comme données, pas comme instructions).
4. La réponse est affichée avec le badge « vérifié par le moteur de calcul » et ses sources. Tuteurs et parents voient les questions posées.

## Ajouter un pays ou une langue
- **Pays** : ajoutez les lignes `Country`, `Level`, `Chapter`, `Exercise` (voir `app/seed.py`), ou créez une page d'admin. Les tuteurs peuvent ajouter leurs propres exercices et cours.
- **Langue** : ajoutez un dictionnaire dans `app/i18n.py` (la clé est le texte français ; ce qui manque reste en français) et le code dans `SUPPORTED_LANGS`.

## Tests
```bash
pip install pytest && pytest -q        # 28 tests : moteur de calcul, sécurité, parcours des 3 rôles, RAG, CRM, facturation démo
```
Un test réel du temps réel (SSE) a aussi été fait : une réponse d'élève apparaît immédiatement dans le flux du tuteur.

## Déploiement
- **Docker** : `docker compose up --build` (PostgreSQL + app). *Non testé ici : vérifiez-le sur votre machine.*
- Variables importantes : `ENV=production`, `SECRET_KEY` (longue chaîne aléatoire), `DATABASE_URL`, `BASE_URL`, `SEED_DEMO=0`.
- Mettez un proxy HTTPS devant (Caddy, Nginx…). Un seul processus (`--workers 1`) tant que `services/events.py` est en mémoire.

## ⚠ Ce qui n'est PAS fait / PAS testé (à lire avant de lancer en vrai)
- **L'appel au modèle d'IA n'a pas été testé avec une vraie clé** (pas de clé ici). Le code suit l'API Messages d'Anthropic ; testez avec votre clé.
- **Paiements Flutterwave** et **WhatsApp** : code écrit d'après leur documentation, **jamais testé avec de vraies clés**. Utilisez d'abord leurs modes « test ». Sans clés, `DEMO_BILLING=1` active le plan sans débit (à désactiver en production).
- **Les programmes, exercices et cours fournis sont des exemples de démonstration**, pas les vrais programmes officiels. Ils doivent être remplacés/validés par des enseignants locaux.
- **Prix des plans** (`app/seed.py`) : valeurs d'exemple à ajuster à votre marché.
- **Avant la mise en production réelle** il manque : vérification d'email et réinitialisation du mot de passe, export/suppression des données (RGPD et lois locales de protection des données, consentement parental pour les mineurs), migrations de base (Alembic), limitation de débit partagée (Redis), sauvegardes, journalisation/monitoring, CGU et politique de confidentialité.
- **RAG** : recherche par mots-clés (BM25), suffisante pour démarrer ; passez à une recherche vectorielle (pgvector) quand les cours deviennent nombreux ou que les questions sont très reformulées. Les PDF scannés demandent un OCR préalable.
- **Moteur de calcul** : équations, calculs, expressions. Pas (encore) d'inéquations, de géométrie, de démonstrations ni de lecture de formules manuscrites. L'IA peut toujours se tromper dans ses explications : le résultat vérifié la cadre, mais ne remplace pas la relecture d'un tuteur.
- **Hors ligne** : les réponses d'exercices sont envoyées au retour du réseau, mais la correction a lieu côté serveur (pas de correction sans connexion) et un envoi interrompu peut être compté deux fois.
