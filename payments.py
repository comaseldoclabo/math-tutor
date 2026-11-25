"""Abonnements : Flutterwave (cartes + mobile money Afrique) via adaptateur, ou mode démo.

⚠ La partie Flutterwave suit leur API v3 documentée mais n'a PAS été testée avec de vraies clés :
testez en mode « test » de Flutterwave avant la mise en production.
"""
import secrets
from datetime import timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Payment, Plan, User, Workspace, now


class PaymentError(RuntimeError):
    pass


def price_for(plan: Plan, currency: str) -> tuple[float, str]:
    prices = plan.price_map()
    if currency in prices:
        return float(prices[currency]), currency
    if "USD" in prices:
        return float(prices["USD"]), "USD"
    raise PaymentError("Plan sans prix.")


def activate_plan(db: Session, ws: Workspace, plan_code: str, days: int = 30) -> None:
    base = ws.plan_until if (ws.plan_until and ws.plan_until > now() and ws.plan_code == plan_code) else now()
    ws.plan_code = plan_code
    ws.plan_until = base + timedelta(days=days)
    db.commit()


def start_checkout(db: Session, user: User, ws: Workspace, plan: Plan, currency: str) -> str | None:
    """Renvoie une URL de paiement, ou None si le plan a été activé directement (mode démo)."""
    if plan.code == "free":
        raise PaymentError("Le plan gratuit ne se paie pas.")
    amount, cur = price_for(plan, currency)
    tx_ref = f"mt-{ws.id}-{secrets.token_hex(6)}"
    if settings.FLW_SECRET_KEY:
        pay = Payment(workspace_id=ws.id, plan_code=plan.code, amount=amount, currency=cur,
                      provider="flutterwave", tx_ref=tx_ref, status="pending")
        db.add(pay)
        db.commit()
        try:
            r = httpx.post(
                "https://api.flutterwave.com/v3/payments",
                headers={"Authorization": f"Bearer {settings.FLW_SECRET_KEY}"},
                json={"tx_ref": tx_ref, "amount": amount, "currency": cur,
                      "redirect_url": f"{settings.BASE_URL}/admin?paid={tx_ref}",
                      "customer": {"email": user.email, "name": user.name, "phonenumber": user.phone or None},
                      "customizations": {"title": settings.APP_NAME, "description": f"Plan {plan.name}"}},
                timeout=20)
            r.raise_for_status()
            return r.json()["data"]["link"]
        except Exception as exc:  # noqa: BLE001
            pay.status = "failed"
            db.commit()
            raise PaymentError(f"Paiement indisponible : {exc}") from exc
    if settings.DEMO_BILLING:
        db.add(Payment(workspace_id=ws.id, plan_code=plan.code, amount=amount, currency=cur,
                       provider="demo", tx_ref=tx_ref, status="paid"))
        activate_plan(db, ws, plan.code)
        return None
    raise PaymentError("Aucun moyen de paiement n'est configuré (FLW_SECRET_KEY).")


def handle_flutterwave_webhook(db: Session, signature: str | None, body: dict) -> bool:
    """Valide la signature, re-vérifie la transaction auprès de Flutterwave, puis active le plan."""
    if not settings.FLW_SECRET_HASH or signature != settings.FLW_SECRET_HASH:
        return False
    data = body.get("data") or {}
    tx_ref = data.get("tx_ref")
    pay = db.scalar(select(Payment).where(Payment.tx_ref == tx_ref)) if tx_ref else None
    if not pay or pay.status == "paid":
        return bool(pay)
    try:
        r = httpx.get("https://api.flutterwave.com/v3/transactions/verify_by_reference",
                      params={"tx_ref": tx_ref}, headers={"Authorization": f"Bearer {settings.FLW_SECRET_KEY}"},
                      timeout=20)
        r.raise_for_status()
        d = r.json().get("data", {})
    except Exception:  # noqa: BLE001
        return False
    if d.get("status") == "successful" and float(d.get("amount", 0)) >= pay.amount and d.get("currency") == pay.currency:
        pay.status = "paid"
        ws = db.get(Workspace, pay.workspace_id)
        db.commit()
        if ws:
            activate_plan(db, ws, pay.plan_code)
        return True
    pay.status = "failed"
    db.commit()
    return False
