"""Internationalisation « gettext simplifié » : la clé est le texte français, les autres langues
fournissent une traduction. Texte manquant = le français s'affiche (rien ne casse).

Ajouter une langue : créer un dictionnaire (ex. PT), l'enregistrer dans TRANSLATIONS et dans
settings.SUPPORTED_LANGS. Pour une langue écrite de droite à gauche (ar), ajouter son code à RTL_LANGS.
"""
from fastapi import Request

from .config import settings

EN = {
    "Tableau de bord": "Dashboard", "Mes élèves": "My students", "Élèves": "Students", "Classes": "Classes",
    "Cours (RAG)": "Course files (RAG)", "Exercices": "Exercises", "Prospects (CRM)": "Leads (CRM)",
    "Administration": "Administration", "Programmes": "Curriculum", "Tuteur IA": "AI tutor",
    "Notifications": "Notifications", "Déconnexion": "Log out", "Connexion": "Log in",
    "Créer un compte": "Sign up", "Mot de passe": "Password", "Nom complet": "Full name", "Email": "Email",
    "Je suis": "I am", "Élève": "Student", "Parent": "Parent", "Tuteur / répétiteur": "Tutor",
    "École / centre": "School / centre", "Pays": "Country", "Niveau": "Level", "Choisir": "Choose",
    "Code d'invitation (facultatif)": "Invite code (optional)",
    "Code de l'enfant (facultatif)": "Child's code (optional)",
    "Nom de l'espace de travail": "Workspace name", "Téléphone / WhatsApp": "Phone / WhatsApp",
    "Recevoir les alertes sur WhatsApp": "Get alerts on WhatsApp",
    "Bienvenue": "Welcome", "Progression par chapitre": "Progress by chapter",
    "Exercices réussis": "Exercises solved", "Précision": "Accuracy", "Statut": "Status",
    "Non commencé": "Not started", "En cours": "In progress", "En difficulté": "Struggling", "Maîtrisé": "Mastered",
    "Activité des 14 derniers jours": "Last 14 days activity",
    "Mon code de liaison (à donner à mon parent)": "My link code (give it to my parent)",
    "Rejoindre un tuteur / centre": "Join a tutor / centre", "Rejoindre": "Join",
    "Questions IA aujourd'hui": "AI questions today", "Valider": "Submit", "Réponse": "Answer",
    "Indice": "Hint", "Correct !": "Correct!", "Pas encore. Réessaie.": "Not yet. Try again.",
    "Enregistré hors ligne, envoi dès le retour du réseau.": "Saved offline, will sync when back online.",
    "Écris ta question de maths…": "Ask your maths question…", "Envoyer": "Send",
    "Vérifié par le moteur de calcul": "Checked by the calculation engine", "Sources": "Sources",
    "Mes enfants": "My children", "Lier un enfant": "Link a child", "Code de l'enfant": "Child's code",
    "Lier": "Link", "Dernières questions posées au tuteur IA": "Latest questions to the AI tutor",
    "Dernières tentatives": "Latest attempts", "Aucun enfant lié pour le moment.": "No linked child yet.",
    "Élèves à surveiller": "Students needing attention", "Activité en direct": "Live activity",
    "Code élèves": "Student code", "Code tuteurs": "Tutor code", "Nom": "Name", "Dernière activité": "Last activity",
    "Moyenne": "Average", "Créer": "Create", "Ajouter": "Add", "Supprimer": "Delete", "Enregistrer": "Save",
    "Envoyer un message aux parents": "Send a message to parents", "Message": "Message",
    "Assigner à une classe": "Assign to a class", "Importer un cours (PDF, TXT, MD)": "Upload a course file (PDF, TXT, MD)",
    "Titre": "Title", "Fichier": "File", "Importer": "Upload", "Énoncé": "Statement",
    "Réponse attendue": "Expected answer", "Chapitre": "Chapter", "Contact": "Contact", "Notes": "Notes",
    "Source": "Source", "Nouveau": "New", "Contacté": "Contacted", "Essai": "Trial", "Inscrit": "Enrolled",
    "Perdu": "Lost", "Plan actuel": "Current plan", "Valable jusqu'au": "Valid until",
    "Choisir ce plan": "Choose this plan", "Équipe": "Team", "Paiements": "Payments",
    "Aucune notification.": "No notifications.", "Tout marquer comme lu": "Mark all as read",
    "Hors ligne": "Offline", "Vous êtes hors ligne": "You are offline",
    "Suivi instantané des élèves, pour les tuteurs et les parents":
        "Instant progress tracking for tutors and parents",
    "Un tuteur de maths IA qui s'appuie sur VOS cours, vérifie chaque calcul et prévient les parents et les tuteurs en temps réel.":
        "An AI maths tutor grounded in YOUR course material, that verifies every calculation and alerts parents and tutors in real time.",
    "Programme local": "Local curriculum", "Calcul vérifié": "Verified maths", "Suivi en temps réel": "Real-time tracking",
    "Léger et hors ligne": "Light and offline-ready", "Langue": "Language",
}

TRANSLATIONS = {"en": EN}


def get_lang(request: Request, user=None) -> str:
    lang = request.session.get("lang")
    if lang in settings.SUPPORTED_LANGS:
        return lang
    if user is not None and user.lang in settings.SUPPORTED_LANGS:
        return user.lang
    accept = request.headers.get("accept-language", "")
    for part in accept.split(","):
        code = part.split(";")[0].strip()[:2].lower()
        if code in settings.SUPPORTED_LANGS:
            return code
    return settings.DEFAULT_LANG


def make_t(lang: str):
    table = TRANSLATIONS.get(lang, {})

    def t(text: str) -> str:
        return table.get(text, text)

    return t
