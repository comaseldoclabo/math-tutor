"""Parcours complet : démo seedée, trois rôles, exercices, chat (mode sans IA), CRM, RAG, facturation, droits."""
import os
import re
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/t.db"
os.environ["SEED_DEMO"] = "1"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["DEMO_BILLING"] = "1"

import pytest
from fastapi.testclient import TestClient

from app.main import app


def csrf_of(client, path="/login"):
    html = client.get(path).text
    return re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)


def login(client, email, pw="demo1234"):
    tok = csrf_of(client, "/login")
    r = client.post("/login", data={"email": email, "password": pw, "csrf": tok}, follow_redirects=False)
    assert r.status_code == 303, r.text[:300]
    return csrf_of(client, "/dashboard")


@pytest.fixture(scope="module")
def web():
    with TestClient(app) as c:
        yield c


def fresh(web):
    c = TestClient(app)
    return c


def test_landing_and_health(web):
    assert web.get("/").status_code == 200
    assert web.get("/healthz").json() == {"ok": True}
    assert web.get("/manifest.webmanifest").status_code == 200
    assert web.get("/sw.js").status_code == 200
    assert web.get("/register").status_code == 200


def test_csrf_blocks_post_without_token(web):
    r = web.post("/login", data={"email": "a@b.c", "password": "x"}, follow_redirects=False)
    assert r.status_code == 403


def test_protected_pages_redirect(web):
    r = TestClient(app).get("/student", follow_redirects=False)
    assert r.status_code == 303 and "/login" in r.headers["location"]
    r = TestClient(app).post("/api/chat", json={"message": "x"})
    assert r.status_code in (401, 403)


def test_student_flow_attempts_and_alerts(web):
    st = TestClient(app)
    tok = login(st, "student@demo.test")
    assert st.get("/student").status_code == 200
    page = st.get("/curriculum")
    assert page.status_code == 200 and "Équations" in page.text
    # chapitre 1 (Équations) : exercice 1 = 2x+3=11
    ch = re.search(r'href="/chapters/(\d+)"', page.text).group(1)
    html = st.get(f"/chapters/{ch}").text
    ex_ids = [int(x) for x in re.findall(r'data-ex="(\d+)"', html)]
    assert ex_ids
    H = {"X-CSRF-Token": tok}
    r = st.post("/api/attempts", json={"exercise_id": ex_ids[0], "answer": "x = 4"}, headers=H)
    assert r.status_code == 200 and r.json()["correct"] is True
    r = st.post("/api/attempts", json={"exercise_id": ex_ids[1], "answer": "999"}, headers=H)
    assert r.json()["correct"] is False and r.json()["hint"]
    r = st.post("/api/attempts", json={"exercise_id": ex_ids[1], "answer": "__import__('os')"}, headers=H)
    assert r.status_code == 422
    for _ in range(3):  # 3 échecs d'affilée → alerte
        st.post("/api/attempts", json={"exercise_id": ex_ids[2], "answer": "0"}, headers=H)
    assert st.post("/api/attempts", json={"exercise_id": 99999, "answer": "1"}, headers=H).status_code == 404

    tu = TestClient(app)
    login(tu, "tutor@demo.test")
    notes = tu.get("/notifications").text
    assert "est en difficulté" in notes
    assert tu.get("/tutor").status_code == 200

    pa = TestClient(app)
    login(pa, "parent@demo.test")
    assert "est en difficulté" in pa.get("/notifications").text
    assert "Koffi" in pa.get("/parent").text


def test_chat_offline_mode_with_verified_math_and_rag(web):
    st = TestClient(app)
    tok = login(st, "student@demo.test")
    r = st.post("/api/chat", json={"message": "Aide-moi à résoudre 5x - 7 = 3x + 9"}, headers={"X-CSRF-Token": tok})
    j = r.json()
    assert r.status_code == 200, j
    assert j["verified"]["solutions"] == ["x = 8"]
    assert j["mode"] == "offline"
    r = st.post("/api/chat", json={"message": "Explique le théorème de Pythagore et l'hypoténuse"}, headers={"X-CSRF-Token": tok})
    assert any("Pythagore" in s["title"] for s in r.json()["sources"])
    assert st.get("/chat").status_code == 200


def test_authorization_boundaries(web):
    st = TestClient(app)
    login(st, "student@demo.test")
    assert st.get("/tutor").status_code == 403
    assert st.get("/admin").status_code == 403
    assert st.get("/parent").status_code == 403

    # un autre parent ne voit pas l'élève
    other = TestClient(app)
    tok = csrf_of(other, "/register")
    r = other.post("/register", data={"csrf": tok, "role": "parent", "name": "Autre", "email": "autre@x.test",
                                      "password": "motdepasse1"}, follow_redirects=False)
    assert r.status_code == 303
    sid = re.search(r"/students/(\d+)", TestClient(app).__class__ and login_and_get_student_link()).group(1)
    assert other.get(f"/students/{sid}").status_code == 404


def login_and_get_student_link():
    tu = TestClient(app)
    login(tu, "tutor@demo.test")
    return tu.get("/tutor/students").text


def test_registration_roles_and_codes(web):
    # élève avec le code du centre démo
    c = TestClient(app)
    tok = csrf_of(c, "/register")
    r = c.post("/register", data={"csrf": tok, "role": "student", "name": "Nadia", "email": "nadia@x.test",
                                  "password": "motdepasse1", "country_code": "BJ", "code": "DEMO-ELEVE"}, follow_redirects=False)
    assert r.status_code == 303
    assert c.get("/student").status_code == 200
    # mauvais code
    c2 = TestClient(app)
    tok = csrf_of(c2, "/register")
    r = c2.post("/register", data={"csrf": tok, "role": "student", "name": "X", "email": "x2@x.test",
                                   "password": "motdepasse1", "code": "NOPE"})
    assert r.status_code == 400
    # mot de passe trop court / email dupliqué
    r = c2.post("/register", data={"csrf": tok, "role": "student", "name": "X", "email": "nadia@x.test", "password": "motdepasse1"})
    assert r.status_code == 400
    # tuteur indépendant → crée son espace
    t = TestClient(app)
    tok = csrf_of(t, "/register")
    r = t.post("/register", data={"csrf": tok, "role": "tutor", "name": "Tuteur Neuf", "email": "neuf@x.test",
                                  "password": "motdepasse1", "country_code": "FR", "workspace_name": "Maths Express"}, follow_redirects=False)
    assert r.status_code == 303
    assert "Maths Express" in t.get("/tutor").text
    assert t.get("/admin").status_code == 200


def test_tutor_tools_docs_exercises_crm_billing(web):
    tu = TestClient(app)
    tok = login(tu, "tutor@demo.test")
    # RAG : import d'un cours privé puis recherche côté élève
    r = tu.post("/tutor/docs", data={"csrf": tok, "title": "Mon cours de proportionnalité", "country_code": "BJ"},
                files={"file": ("p.txt", "La proportionnalité : le coefficient de proportionnalité relie deux grandeurs. "
                                        "Un tableau est proportionnel si on passe d'une ligne à l'autre par une même multiplication.".encode())},
                follow_redirects=False)
    assert r.status_code == 303
    st = TestClient(app)
    stok = login(st, "student@demo.test")
    j = st.post("/api/chat", json={"message": "Qu'est-ce que le coefficient de proportionnalité ?"}, headers={"X-CSRF-Token": stok}).json()
    assert any("proportionnalité" in s["title"] for s in j["sources"])
    # un élève d'un autre espace ne voit pas ce document privé
    lone = TestClient(app)
    ltok = csrf_of(lone, "/register")
    lone.post("/register", data={"csrf": ltok, "role": "student", "name": "Solo", "email": "solo@x.test",
                                 "password": "motdepasse1", "country_code": "BJ"})
    lcsrf = csrf_of(lone, "/dashboard")
    j = lone.post("/api/chat", json={"message": "coefficient de proportionnalité"}, headers={"X-CSRF-Token": lcsrf}).json()
    assert not any("Mon cours" in s["title"] for s in j["sources"])

    # exercice du tuteur : réponse attendue valide / invalide
    chap = re.search(r'<option value="(\d+)"', tu.get("/tutor/exercises").text).group(1)
    r = tu.post("/tutor/exercises", data={"csrf": tok, "chapter_id": chap, "statement": "Calcule 1/2 + 1/4", "answer": "3/4"}, follow_redirects=False)
    assert r.status_code == 303 and "1/2 + 1/4" in tu.get("/tutor/exercises").text
    tu.post("/tutor/exercises", data={"csrf": tok, "chapter_id": chap, "statement": "pirate", "answer": "__import__('os')"})
    assert "pirate" not in tu.get("/tutor/exercises").text

    # CRM
    tu.post("/tutor/crm", data={"csrf": tok, "name": "Parent Test", "contact": "+229 99", "child_level": "3e"})
    page = tu.get("/tutor/crm").text
    lead_id = re.search(r'/tutor/crm/(\d+)"', page).group(1)
    tu.post(f"/tutor/crm/{lead_id}", data={"csrf": tok, "status": "enrolled"})
    assert "Parent Test" in tu.get("/tutor/crm").text

    # message aux parents + classes
    sid = re.search(r"/students/(\d+)", tu.get("/tutor/students").text).group(1)
    assert tu.post(f"/students/{sid}/note", data={"csrf": tok, "message": "Bravo cette semaine"}, follow_redirects=False).status_code == 303
    assert tu.post("/tutor/classes", data={"csrf": tok, "name": "Groupe B"}, follow_redirects=False).status_code == 303
    assert "Groupe B" in tu.get("/tutor/classes").text

    # facturation (mode démo)
    assert "Pro" in tu.get("/admin").text
    r = tu.post("/admin/checkout", data={"csrf": tok, "plan_code": "school"}, follow_redirects=False)
    assert r.status_code == 303
    assert "École / centre" in tu.get("/admin").text


def test_rag_unit():
    from app.services import rag
    chunks = rag.chunk_text("A\n\n" + "mot " * 400)
    assert len(chunks) >= 2
    assert rag.tokens("Les équations du premier degré")[:1] == ["equation"]


def test_webhook_rejects_bad_signature(web):
    r = web.post("/webhooks/flutterwave", json={"data": {"tx_ref": "x"}})
    assert r.status_code == 400


def test_language_switch(web):
    c = TestClient(app)
    c.get("/lang/en")
    assert "Sign up" in c.get("/register").text
