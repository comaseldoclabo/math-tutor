"""RAG : découpage des cours, indexation, recherche BM25 filtrée par pays / niveau / espace de travail.

BM25 en Python pur = zéro dépendance, bon pour démarrer (quelques milliers de passages).
Pour passer à l'échelle : remplacer `retrieve()` par une recherche vectorielle (pgvector, Qdrant...)
en gardant la même signature.
"""
import math
import re
import unicodedata
from collections import Counter
from io import BytesIO

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from ..models import Chunk, Document, User

STOP = set("""le la les de des du un une et en au aux ce ces que qui quoi dans pour par sur est sont a ai as
the of and to in is are for on with as at by an be this that it ou ne pas se sa son ses mais plus""".split())


def tokens(text: str) -> list[str]:
    t = unicodedata.normalize("NFD", text.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    out = []
    for w in re.findall(r"[a-z0-9]+", t):
        if w in STOP:
            continue
        if len(w) > 3 and w.endswith("s"):
            w = w[:-1]
        out.append(w)
    return out


def chunk_text(text: str, size: int = 700, overlap: int = 120) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) + 1 <= size:
            cur = f"{cur}\n{p}".strip()
            continue
        if cur:
            chunks.append(cur)
        while len(p) > size:
            chunks.append(p[:size])
            p = p[size - overlap:]
        cur = p
    if cur:
        chunks.append(cur)
    return chunks


def index_document(db: Session, doc: Document) -> int:
    db.execute(delete(Chunk).where(Chunk.document_id == doc.id))
    pieces = chunk_text(doc.text)
    for i, piece in enumerate(pieces):
        db.add(Chunk(document_id=doc.id, idx=i, text=piece))
    db.commit()
    return len(pieces)


def extract_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(data))
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
        if len(text.strip()) < 20:
            raise ValueError("PDF sans texte (scan ?). Utilisez un PDF avec texte ou faites un OCR avant.")
        return text
    if name.endswith((".txt", ".md", ".csv")):
        for enc in ("utf-8", "latin-1"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
    raise ValueError("Format non pris en charge (PDF, TXT, MD).")


def retrieve(db: Session, query: str, user: User, k: int = 4, max_chunks: int = 5000) -> list[dict]:
    q_tokens = tokens(query)
    if not q_tokens:
        return []
    stmt = (
        select(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .where(or_(Document.workspace_id.is_(None), Document.workspace_id == user.workspace_id))
    )
    if user.country_code:
        stmt = stmt.where(or_(Document.country_code.is_(None), Document.country_code == user.country_code))
    if user.level_id:
        stmt = stmt.where(or_(Document.level_id.is_(None), Document.level_id == user.level_id))
    rows = db.execute(stmt.limit(max_chunks)).all()
    if not rows:
        return []

    docs_tokens = [Counter(tokens(c.text + " " + d.title)) for c, d in rows]
    n = len(rows)
    avgdl = sum(sum(t.values()) for t in docs_tokens) / n or 1
    df = Counter()
    for t in docs_tokens:
        df.update(set(t))
    k1, b = 1.5, 0.75
    scored = []
    for (chunk, doc), tf in zip(rows, docs_tokens):
        dl = sum(tf.values())
        score = 0.0
        for w in set(q_tokens):
            if w not in tf:
                continue
            idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
            score += idf * tf[w] * (k1 + 1) / (tf[w] + k1 * (1 - b + b * dl / avgdl))
        if score > 0:
            scored.append((score, chunk, doc))
    scored.sort(key=lambda x: -x[0])
    return [{"text": c.text, "title": d.title, "doc_id": d.id, "source": d.source, "score": round(s, 3)}
            for s, c, d in scored[:k]]
