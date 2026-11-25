"""Moteur de calcul (SymPy) : vérifie les réponses des élèves et calcule les "résultats de référence"
que le tuteur IA doit respecter.

SÉCURITÉ : les expressions viennent d'utilisateurs. On n'appelle jamais eval() sur du texte brut :
liste blanche de caractères et de noms, builtins Python supprimés, limites de taille / d'exposants.
"""
import random
import re

import sympy as sp
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

TRANSFORMS = standard_transformations + (implicit_multiplication_application, convert_xor)
FUNCS = {
    "sqrt": sp.sqrt, "sin": sp.sin, "cos": sp.cos, "tan": sp.tan,
    "asin": sp.asin, "acos": sp.acos, "atan": sp.atan,
    "ln": sp.log, "log": lambda x: sp.log(x, 10), "exp": sp.exp, "abs": sp.Abs,
}
CONSTS = {"pi": sp.pi, "e": sp.E}
_GLOBALS = {
    "__builtins__": {}, "Integer": sp.Integer, "Float": sp.Float, "Rational": sp.Rational,
    "Symbol": sp.Symbol, "Function": sp.Function, "Mul": sp.Mul, "Add": sp.Add, "Pow": sp.Pow,
}
_ALLOWED = re.compile(r"[0-9A-Za-z+\-*/^().=\s]*")


class MathError(ValueError):
    """Expression illisible, interdite ou trop lourde."""


def _clean(s: str) -> str:
    s = s.strip()
    s = re.sub(r"√\s*(\d+(?:[.,]\d+)?|[a-zA-Z])", r"sqrt(\1)", s)
    for a, b in (("²", "^2"), ("³", "^3"), ("×", "*"), ("·", "*"), ("÷", "/"), ("−", "-"),
                 ("–", "-"), ("√", "sqrt"), ("π", "pi"), (",", "."), (" ", " ")):
        s = s.replace(a, b)
    return s


def _validate(s: str) -> None:
    if not s:
        raise MathError("expression vide")
    if len(s) > 200:
        raise MathError("expression trop longue")
    if not _ALLOWED.fullmatch(s):
        raise MathError("caractères non autorisés")
    if re.search(r"\d{9,}", s) or len(re.findall(r"\^|\*\*", s)) > 3 or re.search(r"(\^|\*\*)\s*\(?\s*-?\d{3,}", s):
        raise MathError("expression trop lourde")
    # puissances empilées (9^9^9, 9^(9^9)) : explosion de calcul → interdites
    if re.search(r"(\^|\*\*)\s*[\w.\s]*(\^|\*\*)", s) or re.search(r"(\^|\*\*)\s*\([^)]*(\^|\*\*)", s):
        raise MathError("puissances imbriquées non autorisées")
    for tok in re.findall(r"[A-Za-z]+", s):
        if tok in FUNCS or tok in CONSTS or len(tok) <= 3:
            continue
        raise MathError(f"mot non reconnu : {tok}")


def parse(text: str) -> sp.Expr:
    s = _clean(text)
    _validate(s)
    if "=" in s:
        raise MathError("signe = inattendu")
    try:
        expr = parse_expr(s, local_dict={**FUNCS, **CONSTS}, global_dict=dict(_GLOBALS),
                          transformations=TRANSFORMS, evaluate=True)
    except Exception as exc:  # noqa: BLE001 - toute erreur de parsing = expression illisible
        raise MathError("expression illisible") from exc
    if not isinstance(expr, sp.Expr):
        raise MathError("expression illisible")
    return expr


def equivalent(a: sp.Expr, b: sp.Expr) -> bool:
    diff = a - b
    try:
        if sp.simplify(diff) == 0:
            return True
        syms = sorted(diff.free_symbols, key=str)
        if not syms:
            val = abs(complex(sp.N(diff)))
            ev = sp.N(b)
            if ev.is_number and sp.nsimplify(b).is_Rational and sp.nsimplify(b).q == 1:
                return val < 1e-9  # réponse entière attendue : exacte
            return val <= 0.01 * max(1.0, abs(complex(ev)))  # arrondi toléré sur les décimaux
        rnd = random.Random(7)
        ok = 0
        for _ in range(10):
            sub = {s: sp.Rational(rnd.randint(-20, 20), rnd.randint(1, 5)) + sp.Rational(1, 7) for s in syms}
            v = complex(sp.N(diff.subs(sub)))
            if v != v:  # NaN
                continue
            if abs(v) > 1e-8:
                return False
            ok += 1
        return ok >= 3
    except Exception:  # noqa: BLE001
        return False


def _split_set(s: str) -> list[str]:
    parts = re.split(r";|\bou\b|\bor\b", s.strip())
    return [p.strip() for p in parts if p.strip()]


def _strip_var(s: str) -> str:
    m = re.fullmatch(r"\s*[A-Za-z]\s*=\s*(.+)", s)
    return m.group(1) if m else s


def check_answer(student: str, expected: str) -> bool:
    """True si la réponse de l'élève est mathématiquement équivalente à l'attendu.
    Lève MathError si la réponse de l'élève est illisible (à ne pas compter comme une erreur)."""
    s_vals = [parse(_strip_var(p)) for p in _split_set(student)]
    e_vals = [parse(_strip_var(p)) for p in _split_set(expected)]
    if not s_vals:
        raise MathError("réponse vide")
    if len(s_vals) != len(e_vals):
        return False
    remaining = list(s_vals)
    for e in e_vals:
        match = next((i for i, s in enumerate(remaining) if equivalent(s, e)), None)
        if match is None:
            return False
        remaining.pop(match)
    return True


def validate_expected(expected: str) -> None:
    """Pour la création d'exercices : l'attendu doit être lisible."""
    for p in _split_set(expected):
        parse(_strip_var(p))


# ------------------------------------------------------------ analyse d'un message libre
_MATHY = re.compile(r"[0-9A-Za-z+\-*/^().²³√π×÷,]+")


def _is_math_token(w: str) -> bool:
    w = w.rstrip(".,;:?!")
    if not w or not _MATHY.fullmatch(w):
        return False
    runs = re.findall(r"[A-Za-z]+", w)
    if runs and re.fullmatch(r"[A-Za-z]+", w):  # mot 100 % lettres : math seulement si 1 lettre ou fonction
        return len(w) == 1 or w in FUNCS or w in CONSTS
    return all(len(r) <= 3 or r in FUNCS for r in runs)


def _grow(words: list[str], i: int) -> list[str]:
    lo = i
    while lo - 1 >= 0 and _is_math_token(words[lo - 1]):
        lo -= 1
    hi = i
    while hi + 1 < len(words) and _is_math_token(words[hi + 1]):
        hi += 1
    return words[lo:hi + 1]


def extract_equation(text: str) -> str | None:
    words = text.replace("=", " = ").split()
    for i, w in enumerate(words):
        if w == "=":
            chunk = _grow(words, i)
            cand = " ".join(x.rstrip(".,;:?!") if k == len(chunk) - 1 else x for k, x in enumerate(chunk))
            if cand.count("=") == 1 and re.search(r"\w", cand.split("=")[0]) and re.search(r"\w", cand.split("=")[1]):
                return cand
    return None


def extract_arithmetic(text: str) -> str | None:
    words = text.split()
    best: list[str] = []
    run: list[str] = []
    for w in words + [""]:
        if w and _is_math_token(w):
            run.append(w.rstrip(".,;:?!") if w == words[-1] else w)
        else:
            if run and len(" ".join(run)) > len(" ".join(best)):
                best = run
            run = []
    cand = " ".join(best)
    if re.search(r"\d", cand) and re.search(r"[+\-*/^×÷√]|sqrt", cand):
        return cand
    return None


def _fmt(v: sp.Basic) -> str:
    s = str(v).replace("**", "^").replace("sqrt", "√")
    try:
        if not v.is_Integer and v.is_real:
            f = float(sp.N(v))
            s += f" ≈ {round(f, 4):g}"
    except Exception:  # noqa: BLE001
        pass
    return s


def solve_equation(text: str) -> dict | None:
    left, right = [p for p in _clean(text).split("=")][:2]
    l_expr, r_expr = parse(left), parse(right)
    syms = sorted((l_expr - r_expr).free_symbols, key=str)
    if not syms:
        return {"kind": "statement", "expression": text.strip(), "truth": bool(sp.simplify(l_expr - r_expr) == 0)}
    var = next((s for s in syms if str(s) == "x"), syms[0])
    sols = sp.solve(sp.Eq(l_expr, r_expr), var)
    return {"kind": "equation", "expression": text.strip(), "variable": str(var),
            "solutions": [f"{var} = {_fmt(s)}" for s in sols]}


def evaluate_arithmetic(text: str) -> dict | None:
    expr = parse(text)
    if expr.free_symbols:
        return None
    return {"kind": "value", "expression": text.strip(), "value": _fmt(sp.nsimplify(sp.simplify(expr)))}


def analyze_message(message: str) -> dict | None:
    """Cherche une équation ou un calcul dans un message libre et renvoie le résultat de référence."""
    try:
        eq = extract_equation(message)
        if eq:
            return solve_equation(eq)
        ar = extract_arithmetic(message)
        if ar:
            return evaluate_arithmetic(ar)
    except (MathError, ValueError, TypeError, NotImplementedError):
        return None
    return None
