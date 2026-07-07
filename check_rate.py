"""Surveille le taux de change MGA -> MUR et notifie via Telegram.

Le taux est récupéré via l'API fawazahmed0 (mise à jour quotidienne).
À chaque exécution, on compare avec le dernier taux enregistré et on
envoie une notification Telegram si la variation dépasse le seuil configuré.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Maurice : UTC+4, sans changement d'heure saisonnier.
MAURITIUS_TZ = timezone(timedelta(hours=4))

# Noms des mois en français (indice 1 = janvier) — évite de dépendre de la
# locale système, absente sur GitHub Actions.
MOIS_FR = (
    "", "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)


def date_fr(d: datetime) -> str:
    """Formate une date en français, ex. '07 juillet 2026'."""
    return f"{d.day:02d} {MOIS_FR[d.month]} {d.year}"


def format_date_iso(date_iso: str) -> str:
    """Convertit une date ISO 'AAAA-MM-JJ' au format '07 juillet 2026'."""
    return date_fr(datetime.strptime(date_iso, "%Y-%m-%d"))


def heure_maurice() -> str:
    """Date et heure locales de Maurice, ex. '07 juillet 2026 12:30' (UTC+4)."""
    now = datetime.now(MAURITIUS_TZ)
    return f"{date_fr(now)} {now:%H:%M}"

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("check_rate")

# --- Constantes ---
LAST_RATE_FILE = Path("last_rate.json")
ENV_FILE = Path(".env")
HTTP_TIMEOUT = 20  # secondes


def load_dotenv(path: Path = ENV_FILE) -> None:
    """Charge un fichier .env local dans os.environ (usage local, sans dépendance).

    Les variables déjà définies dans l'environnement (ex. GitHub Actions) ne
    sont pas écrasées. Sans .env, la fonction ne fait rien.
    """
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())

# API principale + fallback recommandé par le projet fawazahmed0.
RATE_URLS = (
    "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/mga.json",
    "https://latest.currency-api.pages.dev/v1/currencies/mga.json",
)


@dataclass(frozen=True)
class Config:
    """Configuration lue depuis les variables d'environnement."""

    telegram_token: str
    telegram_chat_id: str
    seuil_pct: float  # variation minimale (%) pour notifier ; 0 = tout changement
    force: bool  # déclenchement manuel : notifier même sans changement

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            telegram_token=os.environ["TELEGRAM_TOKEN"],
            telegram_chat_id=os.environ["TELEGRAM_CHAT_ID"],
            seuil_pct=float(os.environ.get("SEUIL_PCT", "0")),
            force=os.environ.get("FORCE_REPORT", "").strip().lower()
            in ("1", "true", "yes", "oui"),
        )


@dataclass(frozen=True)
class Rate:
    """Un taux MGA -> MUR à une date donnée."""

    date: str
    value: float

    def to_dict(self) -> dict:
        return {"date": self.date, "rate": self.value}


# --- Récupération du taux ---
def fetch_rate() -> Rate:
    """Récupère le taux MGA -> MUR, avec fallback si le CDN échoue."""
    last_error: Exception | None = None
    for url in RATE_URLS:
        try:
            with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT) as resp:
                data = json.load(resp)
            return Rate(date=data["date"], value=data["mga"]["mur"])
        except Exception as error:  # réseau, JSON ou clé manquante -> on tente le fallback
            logger.warning("Échec de %s : %s", url, error)
            last_error = error
    raise RuntimeError(f"Impossible de récupérer le taux : {last_error}")


# --- Persistance du dernier taux ---
def load_last_rate() -> Rate | None:
    if not LAST_RATE_FILE.exists():
        return None
    data = json.loads(LAST_RATE_FILE.read_text())
    return Rate(date=data["date"], value=data["rate"])


def save_rate(rate: Rate) -> None:
    LAST_RATE_FILE.write_text(json.dumps(rate.to_dict(), indent=2))


# --- Notification Telegram ---
# Bouton inline « Vérifier maintenant » sous chaque message. Le clic est
# traité par le Cloudflare Worker (voir cloudflare-worker/), qui relance le
# workflow GitHub. Sans Worker déployé, le bouton reste inerte (sans erreur).
VERIFIER_KEYBOARD = {
    "inline_keyboard": [
        [{"text": "Vérifier maintenant", "callback_data": "trigger_check"}]
    ]
}


def send_telegram(config: Config, message: str) -> None:
    url = f"https://api.telegram.org/bot{config.telegram_token}/sendMessage"
    payload = json.dumps(
        {
            "chat_id": config.telegram_chat_id,
            "text": message,
            "parse_mode": "HTML",
            "reply_markup": VERIFIER_KEYBOARD,
        }
    ).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        result = json.load(resp)
    if not result.get("ok"):
        raise RuntimeError(f"Erreur Telegram : {result}")


# --- Formatage des messages ---
def format_initial_message(rate: Rate) -> str:
    return (
        f"<b>SUIVI DU TAUX MGA/MUR</b>\n"
        f"Surveillance activée.\n"
        f"\n"
        f"<b>Taux actuel :</b> 1 MGA = {rate.value:.6f} MUR\n"
        f"<b>Équivalence :</b> 1 MUR = {1 / rate.value:,.2f} MGA\n"
        f"<b>Date de référence :</b> {format_date_iso(rate.date)}\n"
        f"<b>Heure de Maurice :</b> {heure_maurice()}"
    )


def format_change_message(rate: Rate, previous: Rate, variation_pct: float) -> str:
    tendance = "Hausse" if rate.value > previous.value else "Baisse"
    return (
        f"<b>VARIATION DU TAUX MGA/MUR</b>\n"
        f"\n"
        f"<b>Nouveau taux :</b> 1 MGA = {rate.value:.6f} MUR\n"
        f"<b>Taux précédent :</b> 1 MGA = {previous.value:.6f} MUR\n"
        f"<b>Variation :</b> {variation_pct:+.3f} % ({tendance})\n"
        f"<b>Équivalence :</b> 1 MUR = {1 / rate.value:,.2f} MGA\n"
        f"<b>Date :</b> {format_date_iso(rate.date)}\n"
        f"<b>Heure de Maurice :</b> {heure_maurice()}"
    )


def format_current_message(rate: Rate, previous: Rate, variation_pct: float) -> str:
    """Message de confirmation pour un déclenchement manuel (taux courant)."""
    if rate.value == previous.value:
        etat = "Aucune variation depuis la dernière vérification."
        variation_line = ""
    else:
        tendance = "Hausse" if rate.value > previous.value else "Baisse"
        etat = "Variation sous le seuil de notification."
        variation_line = (
            f"<b>Variation :</b> {variation_pct:+.3f} % ({tendance})\n"
        )
    return (
        f"<b>TAUX ACTUEL MGA/MUR</b>\n"
        f"{etat}\n"
        f"\n"
        f"<b>Taux actuel :</b> 1 MGA = {rate.value:.6f} MUR\n"
        f"{variation_line}"
        f"<b>Équivalence :</b> 1 MUR = {1 / rate.value:,.2f} MGA\n"
        f"<b>Date de référence :</b> {format_date_iso(rate.date)}\n"
        f"<b>Heure de Maurice :</b> {heure_maurice()}"
    )


# --- Logique principale ---
def run(config: Config) -> None:
    rate = fetch_rate()
    previous = load_last_rate()

    # Premier lancement : on enregistre et on envoie un message initial.
    if previous is None:
        save_rate(rate)
        send_telegram(config, format_initial_message(rate))
        logger.info("Premier taux enregistré : %s", rate.value)
        return

    changed = rate.value != previous.value
    variation_pct = (
        (rate.value - previous.value) / previous.value * 100 if changed else 0.0
    )
    notable = changed and abs(variation_pct) >= config.seuil_pct

    if notable:
        # Variation significative : notification standard.
        send_telegram(config, format_change_message(rate, previous, variation_pct))
        logger.info("Notification envoyée : %s -> %s", previous.value, rate.value)
    elif config.force:
        # Déclenchement manuel : on confirme toujours le taux courant.
        send_telegram(config, format_current_message(rate, previous, variation_pct))
        logger.info("Déclenchement manuel : taux courant %s.", rate.value)
    else:
        logger.info("Pas de notification (variation %+.3f%%).", variation_pct)

    # On met à jour le dernier taux connu dès qu'il a bougé.
    if changed:
        save_rate(rate)


def main() -> int:
    try:
        load_dotenv()
        run(Config.from_env())
    except Exception as error:
        logger.error("Erreur : %s", error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
