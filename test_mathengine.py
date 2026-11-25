import pytest

from app.services import mathengine as m


def test_check_basic():
    assert m.check_answer("x=4", "4")
    assert m.check_answer("4", "x=4")
    assert m.check_answer("4,0", "x=4")
    assert not m.check_answer("5", "x=4")


def test_check_expressions_and_sets():
    assert m.check_answer("(x+1)^2", "x^2+2x+1")
    assert m.check_answer("x²+2x+1", "x^2+2*x+1")
    assert m.check_answer("x=-2 ou x=2", "x=2 ou x=-2")
    assert not m.check_answer("x=2", "x=2 ou x=-2")
    assert m.check_answer("sqrt(81)+2^3", "17")
    assert m.check_answer("√81+2³", "17")


def test_decimal_tolerance():
    assert m.check_answer("3.33", "10/3")
    assert m.check_answer("3,33", "10/3")
    assert not m.check_answer("3.5", "10/3")
    assert not m.check_answer("5.1", "5")  # entier attendu : exact


@pytest.mark.parametrize("bad", [
    "__import__('os').system('ls')", "().__class__", "9^9^9^9", "10^1000", "open('x')",
    "lambda: 1", "x" * 300, "eval(1)", "a;b;c;import os",
])
def test_rejects_malicious(bad):
    with pytest.raises(m.MathError):
        m.check_answer(bad, "1")


def test_analyze_equation_in_sentence():
    r = m.analyze_message("Peux-tu m'aider à résoudre 2x + 3 = 11 s'il te plaît ?")
    assert r and r["kind"] == "equation" and r["solutions"] == ["x = 4"]


def test_analyze_quadratic_and_compact():
    r = m.analyze_message("résous x^2-5x+6=0")
    assert sorted(r["solutions"]) == ["x = 2", "x = 3"]


def test_analyze_arithmetic():
    r = m.analyze_message("Combien font (3+4)*12 ?")
    assert r and r["kind"] == "value" and r["value"] == "84"


def test_analyze_ignores_plain_text():
    assert m.analyze_message("Explique-moi le théorème de Pythagore") is None


def test_false_statement():
    r = m.analyze_message("est-ce que 2+2=5 ?")
    assert r and r["kind"] == "statement" and r["truth"] is False
