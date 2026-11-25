"""Données initiales : plans, pays/niveaux/chapitres, exercices, cours d'exemple, comptes de démo.

⚠ Les programmes et cours ci-dessous sont des EXEMPLES de démonstration (rédigés pour ce projet).
Ils doivent être remplacés/validés par des enseignants locaux avant tout usage réel.
"""
import json
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import (Attempt, Chapter, ClassroomStudent, Classroom, Country, Document, Exercise, Lead, Level,
                     ParentChild, Plan, User, Workspace, now)
from .security import hash_password, make_code
from .services import rag

PLANS = [
    ("free", "Gratuit", 5, 10, {}, 0),
    ("pro", "Pro (tuteur)", 40, 60, {"XOF": 5000, "USD": 9, "EUR": 8, "NGN": 12000}, 1),
    ("school", "École / centre", 500, 100, {"XOF": 25000, "USD": 45, "EUR": 40, "NGN": 60000}, 2),
]

COUNTRIES = [
    ("BJ", "Bénin", "fr", "XOF", 20, "Système éducatif béninois (exemple de démo)"),
    ("FR", "France", "fr", "EUR", 20, "Système éducatif français (exemple de démo)"),
    ("NG", "Nigeria", "en", "NGN", 100, "Nigerian education system (demo example)"),
]

# pays -> [(code, nom, stage, [(titre, description)])]
CURRICULUM = {
    "BJ": [("3e", "3ème", "Collège", [
        ("Équations du premier degré", "Résoudre des équations à une inconnue."),
        ("Théorème de Pythagore", "Calculer des longueurs dans un triangle rectangle."),
        ("Fonctions linéaires et affines", "Calculer des images, lire et construire."),
        ("Systèmes d'équations", "Résoudre un système de deux équations à deux inconnues."),
        ("Statistiques", "Moyenne, médiane, étendue."),
    ])],
    "FR": [("2nde", "Seconde", "Lycée", [
        ("Équations et identités", "Équations du second degré simples, développements."),
        ("Fonctions", "Image, antécédent, variations."),
    ])],
    "NG": [("SS1", "SS1", "Senior Secondary", [
        ("Linear and quadratic equations", "Solving linear and simple quadratic equations."),
    ])],
}

# (pays, niveau) -> chapitre(index) -> [(énoncé, réponse, indice, difficulté)]
EXERCISES = {
    ("BJ", "3e"): {
        0: [("Résous : 2x + 3 = 11", "x=4", "Soustrais 3 des deux côtés, puis divise par 2.", 1),
            ("Résous : 5x - 7 = 3x + 9", "x=8", "Regroupe les x d'un côté et les nombres de l'autre.", 2),
            ("Résous : 3(x - 2) = 2x + 5", "x=11", "Développe d'abord la parenthèse.", 2)],
        1: [("Un triangle rectangle a des côtés de l'angle droit de 3 cm et 4 cm. Quelle est l'hypoténuse (en cm) ?", "5", "c² = a² + b².", 1),
            ("Côtés de l'angle droit : 5 et 12. Hypoténuse ?", "13", "25 + 144 = ?", 1),
            ("Calcule : sqrt(81) + 2^3", "17", "√81 = 9 et 2³ = 8.", 1)],
        2: [("f(x) = 2x + 1. Calcule f(3).", "7", "Remplace x par 3.", 1)],
        3: [("Système : x + y = 5 et x - y = 1. Donne x.", "3", "Additionne les deux équations.", 2)],
        4: [("Calcule la moyenne de 8, 12, 10 et 14.", "11", "Somme divisée par l'effectif.", 1)],
    },
    ("FR", "2nde"): {
        0: [("Résous : x^2 = 16", "x=4 ou x=-4", "Deux solutions : un nombre et son opposé.", 1),
            ("Développe (x + 1)^2", "x^2+2x+1", "(a+b)² = a² + 2ab + b².", 1)],
        1: [("Résous : 2x - 6 = 0", "3", "Isole x.", 1)],
    },
    ("NG", "SS1"): {
        0: [("Solve 3x + 5 = 20", "x=5", "Subtract 5, then divide by 3.", 1),
            ("Solve x^2 - 5x + 6 = 0", "x=2 or x=3", "Factorise: (x-2)(x-3).", 2)],
    },
}

# Cours d'exemple pour le RAG : (pays, niveau, chapitre idx, titre, texte)
DOCS = [
    ("BJ", "3e", 0, "Fiche : équations du premier degré",
     "Une équation du premier degré à une inconnue s'écrit ax + b = c. Pour la résoudre, on applique la même "
     "opération aux deux membres afin d'isoler x.\n\nMéthode : 1) développer et réduire chaque membre ; "
     "2) regrouper les termes en x d'un côté et les nombres de l'autre ; 3) diviser par le coefficient de x ; "
     "4) vérifier en remplaçant x par la solution.\n\nExemple : 2x + 3 = 11 donne 2x = 8 puis x = 4."),
    ("BJ", "3e", 1, "Fiche : théorème de Pythagore",
     "Dans un triangle rectangle, le carré de l'hypoténuse est égal à la somme des carrés des deux autres côtés : "
     "c² = a² + b². L'hypoténuse est le côté opposé à l'angle droit, c'est le plus grand côté.\n\n"
     "Réciproque : si dans un triangle le carré du plus grand côté est égal à la somme des carrés des deux autres, "
     "alors le triangle est rectangle. Exemple : 3, 4, 5 car 9 + 16 = 25."),
    ("BJ", "3e", 2, "Fiche : fonctions linéaires et affines",
     "Une fonction affine est de la forme f(x) = ax + b. Si b = 0, elle est linéaire. Le nombre a est le coefficient "
     "directeur (la pente), b est l'ordonnée à l'origine. Pour calculer l'image de 3, on remplace x par 3."),
    ("BJ", "3e", 3, "Fiche : systèmes de deux équations",
     "Pour résoudre un système de deux équations à deux inconnues, on peut utiliser la substitution ou la "
     "combinaison (addition). Par combinaison : x + y = 5 et x - y = 1, on additionne : 2x = 6 donc x = 3, puis y = 2."),
    ("BJ", "3e", 4, "Fiche : statistiques",
     "La moyenne est la somme des valeurs divisée par leur nombre. La médiane partage la série ordonnée en deux "
     "groupes de même effectif. L'étendue est la différence entre la plus grande et la plus petite valeur."),
    ("FR", "2nde", 0, "Fiche : identités remarquables",
     "(a+b)² = a² + 2ab + b² ; (a−b)² = a² − 2ab + b² ; (a+b)(a−b) = a² − b². Une équation x² = k avec k > 0 "
     "a deux solutions : √k et −√k."),
    ("NG", "SS1", 0, "Note: solving equations",
     "To solve a linear equation, perform the same operation on both sides to isolate x. For a quadratic equation "
     "x^2 + bx + c = 0, factorise into (x - p)(x - q) = 0, then x = p or x = q."),
]


def seed_reference(db: Session) -> None:
    if db.scalar(select(Plan.code).limit(1)):
        return
    for code, name, max_s, quota, prices, pos in PLANS:
        db.add(Plan(code=code, name=name, max_students=max_s, ai_daily_quota=quota,
                    prices=json.dumps(prices), position=pos))
    for c in COUNTRIES:
        db.add(Country(code=c[0], name=c[1], lang=c[2], currency=c[3], grading_max=c[4], system_name=c[5]))
    db.commit()

    level_ids: dict[tuple[str, str], int] = {}
    chapter_ids: dict[tuple[str, str, int], int] = {}
    for cc, levels in CURRICULUM.items():
        for pos, (code, name, stage, chapters) in enumerate(levels):
            lv = Level(country_code=cc, code=code, name=name, stage=stage, position=pos)
            db.add(lv)
            db.flush()
            level_ids[(cc, code)] = lv.id
            for i, (title, desc) in enumerate(chapters):
                ch = Chapter(level_id=lv.id, position=i, title=title, description=desc)
                db.add(ch)
                db.flush()
                chapter_ids[(cc, code, i)] = ch.id
    db.commit()

    for (cc, lv), chapters in EXERCISES.items():
        for idx, items in chapters.items():
            for statement, answer, hint, diff in items:
                db.add(Exercise(chapter_id=chapter_ids[(cc, lv, idx)], statement=statement,
                                answer=answer, hint=hint, difficulty=diff))
    for cc, lv, idx, title, text in DOCS:
        doc = Document(title=title, source="Exemple de démonstration", country_code=cc,
                       level_id=level_ids[(cc, lv)], chapter_id=chapter_ids[(cc, lv, idx)], text=text)
        db.add(doc)
        db.flush()
        rag.index_document(db, doc)
    db.commit()


def seed_demo(db: Session) -> None:
    if db.scalar(select(User.id).where(User.email == "tutor@demo.test")):
        return
    bj = db.scalar(select(Level).where(Level.country_code == "BJ", Level.code == "3e"))
    ws = Workspace(name="Centre Démo", kind="tutor", join_code="DEMO-ELEVE", tutor_code="DEMO-TUTEUR",
                   plan_code="pro", plan_until=now() + timedelta(days=30), country_code="BJ")
    db.add(ws)
    db.flush()
    pw = hash_password("demo1234")
    tutor = User(email="tutor@demo.test", name="Mme Adjovi (tuteur démo)", pw_hash=pw, role="tutor", is_owner=True,
                 workspace_id=ws.id, country_code="BJ")
    student = User(email="student@demo.test", name="Koffi (élève démo)", pw_hash=pw, role="student",
                   workspace_id=ws.id, country_code="BJ", level_id=bj.id, link_code="E-DEMO22")
    parent = User(email="parent@demo.test", name="M. Dossou (parent démo)", pw_hash=pw, role="parent", country_code="BJ")
    db.add_all([tutor, student, parent])
    db.flush()
    db.add(ParentChild(parent_id=parent.id, child_id=student.id))
    room = Classroom(workspace_id=ws.id, name="3ème - Groupe A", level_id=bj.id)
    db.add(room)
    db.flush()
    db.add(ClassroomStudent(classroom_id=room.id, student_id=student.id))

    exs = db.scalars(select(Exercise).join(Chapter, Exercise.chapter_id == Chapter.id)
                     .where(Chapter.level_id == bj.id).order_by(Exercise.id)).all()
    pattern = [(0, True, 5), (1, False, 4), (1, False, 3), (1, True, 2), (3, True, 1), (4, True, 1)]
    for k, ok, days_ago in pattern:
        db.add(Attempt(student_id=student.id, exercise_id=exs[k].id, answer="démo", correct=ok,
                       created_at=now() - timedelta(days=days_ago, hours=k)))
    db.add(Lead(workspace_id=ws.id, name="Mme Gnonlonfoun", contact="+229 01 00 00 00 00", child_level="4ème",
                source="Bouche à oreille", status="contacted", notes="Veut des cours de maths le mercredi."))
    db.add(Lead(workspace_id=ws.id, name="M. Houngbo", contact="houngbo@example.com", child_level="Tle",
                source="Facebook", status="new"))
    db.commit()


def run(db: Session) -> None:
    seed_reference(db)
    if settings.SEED_DEMO:
        seed_demo(db)
