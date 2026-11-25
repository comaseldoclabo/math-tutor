"""Calcul de la progression des élèves et détection des difficultés."""
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models import Attempt, Chapter, ChatMessage, Exercise, Notification, User, now
from . import notifier


def visible_exercises_filter(student: User):
    return or_(Exercise.workspace_id.is_(None), Exercise.workspace_id == student.workspace_id)


def student_progress(db: Session, student: User) -> list[dict]:
    if not student.level_id:
        return []
    chapters = db.scalars(select(Chapter).where(Chapter.level_id == student.level_id).order_by(Chapter.position)).all()
    if not chapters:
        return []
    ch_ids = [c.id for c in chapters]
    ex_rows = db.execute(select(Exercise.id, Exercise.chapter_id).where(
        Exercise.chapter_id.in_(ch_ids), visible_exercises_filter(student))).all()
    ex_chapter = {eid: cid for eid, cid in ex_rows}
    totals: dict[int, int] = defaultdict(int)
    for _, cid in ex_rows:
        totals[cid] += 1

    attempts = db.execute(select(Attempt.exercise_id, Attempt.correct, Attempt.created_at)
                          .where(Attempt.student_id == student.id)).all()
    stats = defaultdict(lambda: {"attempts": 0, "correct": 0, "solved": set(), "last": None})
    for ex_id, ok, ts in attempts:
        cid = ex_chapter.get(ex_id)
        if cid is None:
            continue
        s = stats[cid]
        s["attempts"] += 1
        if ok:
            s["correct"] += 1
            s["solved"].add(ex_id)
        if not s["last"] or ts > s["last"]:
            s["last"] = ts

    out = []
    for c in chapters:
        s = stats[c.id]
        total, solved, n = totals[c.id], len(s["solved"]), s["attempts"]
        acc = (s["correct"] / n) if n else 0.0
        if n == 0:
            status = "new"
        elif n >= 3 and acc < 0.5:
            status = "struggling"
        elif total and solved == total:
            status = "mastered"
        else:
            status = "progress"
        out.append({"chapter": c, "total": total, "solved": solved, "attempts": n,
                    "accuracy": acc, "status": status, "last": s["last"]})
    return out


def overall(progress: list[dict]) -> dict:
    total = sum(p["total"] for p in progress)
    solved = sum(p["solved"] for p in progress)
    attempts = sum(p["attempts"] for p in progress)
    correct = sum(p["accuracy"] * p["attempts"] for p in progress)
    return {
        "solved": solved, "total": total,
        "completion": (solved / total) if total else 0.0,
        "accuracy": (correct / attempts) if attempts else 0.0,
        "struggling": sum(1 for p in progress if p["status"] == "struggling"),
    }


def daily_activity(db: Session, student_id: int, days: int = 14) -> list[int]:
    start = (now() - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = db.execute(select(Attempt.created_at).where(Attempt.student_id == student_id, Attempt.created_at >= start)).all()
    counts = [0] * days
    for (ts,) in rows:
        idx = (ts.date() - start.date()).days
        if 0 <= idx < days:
            counts[idx] += 1
    return counts


def last_activity(db: Session, student_id: int):
    a = db.scalar(select(func.max(Attempt.created_at)).where(Attempt.student_id == student_id))
    c = db.scalar(select(func.max(ChatMessage.created_at)).where(ChatMessage.user_id == student_id))
    return max([x for x in (a, c) if x], default=None)


def check_struggle(db: Session, student: User, exercise: Exercise) -> bool:
    """3 échecs consécutifs dans un même chapitre => alerte (au plus une par jour et par chapitre)."""
    last3 = db.execute(
        select(Attempt.correct).join(Exercise, Attempt.exercise_id == Exercise.id)
        .where(Attempt.student_id == student.id, Exercise.chapter_id == exercise.chapter_id)
        .order_by(Attempt.created_at.desc(), Attempt.id.desc()).limit(3)).all()
    if len(last3) < 3 or any(ok for (ok,) in last3):
        return False
    tutors, parents = notifier.recipients_for_student(db, student)
    url = f"/students/{student.id}?ch={exercise.chapter_id}"
    chapter = db.get(Chapter, exercise.chapter_id)
    recent = db.scalar(select(func.count(Notification.id)).where(
        Notification.kind == "struggle", Notification.url == url, Notification.created_at >= now() - timedelta(hours=24)))
    if recent:
        return False
    notifier.notify(db, tutors + parents, "struggle",
                    f"{student.name} est en difficulté",
                    f"3 erreurs d'affilée : {chapter.title if chapter else 'chapitre'}", url)
    return True
