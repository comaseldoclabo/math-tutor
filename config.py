"""Configuration centralisée, lue depuis les variables d'environnement."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _bool(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


class Settings:
    ENV = os.getenv("ENV", "development")  # "production" active les protections strictes
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./tuteur.db")
    APP_NAME = os.getenv("APP_NAME", "MathTutor")
    BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

    DEFAULT_LANG = "fr"
    SUPPORTED_LANGS = ["fr", "en"]
    RTL_LANGS = {"ar", "he", "fa", "ur"}

    # IA (Anthropic). Sans clé, l'app fonctionne en "mode hors IA" : sources du cours + calcul vérifié.
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")

    # Paiement (Flutterwave : cartes + mobile money). Sans clé : DEMO_BILLING active le plan directement.
    FLW_SECRET_KEY = os.getenv("FLW_SECRET_KEY", "")
    FLW_SECRET_HASH = os.getenv("FLW_SECRET_HASH", "")  # valeur du "secret hash" des webhooks
    DEMO_BILLING = _bool("DEMO_BILLING", "1")

    # Notifications WhatsApp (API Cloud Meta) - optionnel
    WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
    WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "")

    SEED_DEMO = _bool("SEED_DEMO", "1")
    UPLOAD_MAX_BYTES = int(os.getenv("UPLOAD_MAX_BYTES", str(5 * 1024 * 1024)))


settings = Settings()

if settings.ENV == "production" and settings.SECRET_KEY == "dev-only-change-me":
    raise RuntimeError("SECRET_KEY doit être défini en production.")
