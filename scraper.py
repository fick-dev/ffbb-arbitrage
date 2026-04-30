"""
FBIScraper — Connexion et extraction des convocations d'arbitrage
depuis extranet.ffbb.com/fbi
"""

import re
import logging
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL   = "https://extranet.ffbb.com/fbi"
LOGIN_URL  = f"{BASE_URL}/connexion.fbi"
# URL de la page convocations arbitre — à ajuster selon votre profil FBI
CONVOC_URL = f"{BASE_URL}/arbitre/mesConvocations.fbi"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9",
}

# Correspondance mois français → numéro
MOIS_FR = {
    "janvier": 1, "février": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "août": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
}


class FBIAuthError(Exception):
    pass

class FBIParseError(Exception):
    pass


class FBIScraper:
    def __init__(self, username: str, password: str):
        if not username or not password:
            raise ValueError(
                "FBI_USERNAME et FBI_PASSWORD doivent être définis "
                "dans les variables d'environnement."
            )
        self.username = username
        self.password = password
        self.session  = requests.Session()
        self.session.headers.update(HEADERS)

    # ── Authentification ────────────────────────────────────────────────────

    def login(self) -> None:
        """Se connecte au portail FBI et maintient la session."""
        logger.info("Connexion à FBI...")

        # 1. GET la page de login pour récupérer les tokens CSRF / champs cachés
        resp = self.session.get(LOGIN_URL, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Récupérer tous les champs cachés du formulaire
        form = soup.find("form")
        if not form:
            raise FBIAuthError("Formulaire de connexion introuvable sur la page FBI.")

        payload = {}
        for inp in form.find_all("input"):
            name  = inp.get("name", "")
            value = inp.get("value", "")
            if name:
                payload[name] = value

        # Surcharger avec les identifiants
        # Les noms exacts peuvent varier — adaptez si besoin
        payload["username"] = self.username
        payload["password"] = self.password
        # Champ commun FBI (Spring Security)
        if "j_username" in payload or not payload.get("username"):
            payload["j_username"] = self.username
            payload["j_password"] = self.password

        # 2. POST le formulaire
        action = form.get("action", LOGIN_URL)
        if not action.startswith("http"):
            action = f"{BASE_URL}/{action.lstrip('/')}"

        resp2 = self.session.post(action, data=payload, timeout=20, allow_redirects=True)
        resp2.raise_for_status()

        # 3. Vérifier qu'on est bien connecté
        if "connexion.fbi" in resp2.url or "Identifiant ou e-mail" in resp2.text:
            raise FBIAuthError(
                "Échec de connexion FBI. Vérifiez FBI_USERNAME et FBI_PASSWORD."
            )

        logger.info("Connexion réussie.")

    # ── Récupération des convocations ────────────────────────────────────────

    def fetch_convocations(self) -> dict:
        """Connexion + scraping. Retourne un dict prêt pour l'API."""
        self.login()

        logger.info(f"Récupération des convocations depuis {CONVOC_URL}")
        resp = self.session.get(CONVOC_URL, timeout=20)
        resp.raise_for_status()

        convocations = self._parse_convocations(resp.text)
        return {
            "convocations": convocations,
            "fetched_at":   datetime.now().isoformat(),
            "count":        len(convocations),
        }

    # ── Parsing HTML ─────────────────────────────────────────────────────────

    def _parse_convocations(self, html: str) -> list[dict]:
        """
        Parse la page HTML des convocations.
        ⚠️  Les sélecteurs CSS ci-dessous sont des estimations basées sur
        les conventions FBI. Adaptez-les en inspectant le HTML réel de votre page.
        """
        soup = BeautifulSoup(html, "html.parser")
        results = []

        # FBI utilise généralement un tableau ou une liste de cartes.
        # Tentative 1 : lignes de tableau
        rows = soup.select("table.liste-convocations tr, table tr.convocation")
        if rows:
            for row in rows:
                cols = row.find_all("td")
                if len(cols) < 3:
                    continue
                conv = self._parse_row(cols)
                if conv:
                    results.append(conv)
            logger.info(f"Mode tableau : {len(results)} convocations parsées")
            return results

        # Tentative 2 : blocs / cartes
        cards = soup.select(".convocation-item, .convoc-card, .ligne-convoc, article")
        if cards:
            for card in cards:
                conv = self._parse_card(card)
                if conv:
                    results.append(conv)
            logger.info(f"Mode cartes : {len(results)} convocations parsées")
            return results

        # Tentative 3 : toutes les lignes du premier grand tableau
        all_rows = soup.select("table tr")
        for row in all_rows:
            cols = row.find_all("td")
            if len(cols) >= 3:
                conv = self._parse_row(cols)
                if conv:
                    results.append(conv)

        if not results:
            logger.warning(
                "Aucune convocation trouvée. Le HTML FBI a peut-être changé. "
                "Inspectez la page et adaptez les sélecteurs dans scraper.py."
            )

        return results

    def _parse_row(self, cols: list) -> Optional[dict]:
        """Parse une ligne de tableau en dict convocation."""
        try:
            texts = [c.get_text(strip=True) for c in cols]
            # Heuristique : chercher une colonne qui ressemble à une date
            date_str, date_iso = None, None
            for t in texts:
                parsed = self._try_parse_date(t)
                if parsed:
                    date_str = t
                    date_iso = parsed
                    break

            return {
                "date_affichage": date_str or texts[0] if texts else "",
                "date_iso":       date_iso or "",
                "competition":    texts[1] if len(texts) > 1 else "",
                "lieu":           texts[2] if len(texts) > 2 else "",
                "horaire":        texts[3] if len(texts) > 3 else "",
                "role":           texts[4] if len(texts) > 4 else "",
                "statut":         self._infer_statut(date_iso),
                "raw":            texts,  # conservé pour debug
            }
        except Exception as e:
            logger.debug(f"Erreur parse row: {e}")
            return None

    def _parse_card(self, card) -> Optional[dict]:
        """Parse un bloc HTML de type carte en dict convocation."""
        try:
            text = card.get_text(" ", strip=True)
            date_iso = None
            for word in text.split():
                parsed = self._try_parse_date(word)
                if parsed:
                    date_iso = parsed
                    break

            return {
                "date_affichage": card.select_one(".date, .convoc-date, time"),
                "date_iso":       date_iso or "",
                "competition":    self._text(card, ".competition, .match, .libelle"),
                "lieu":           self._text(card, ".lieu, .salle, .adresse"),
                "horaire":        self._text(card, ".horaire, .heure, time"),
                "role":           self._text(card, ".role, .fonction"),
                "statut":         self._infer_statut(date_iso),
                "raw_text":       text[:200],
            }
        except Exception as e:
            logger.debug(f"Erreur parse card: {e}")
            return None

    # ── Utilitaires ──────────────────────────────────────────────────────────

    @staticmethod
    def _text(el, selector: str) -> str:
        found = el.select_one(selector)
        return found.get_text(strip=True) if found else ""

    @staticmethod
    def _try_parse_date(text: str) -> Optional[str]:
        """
        Tente de parser une date en français et retourne ISO 8601 (YYYY-MM-DD).
        Formats tentés : DD/MM/YYYY, DD-MM-YYYY, 'DD mois YYYY'.
        """
        text = text.strip().lower()

        # DD/MM/YYYY ou DD-MM-YYYY
        m = re.match(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", text)
        if m:
            d, mo, y = m.groups()
            try:
                dt = datetime(int(y), int(mo), int(d))
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                pass

        # DD mois YYYY  (ex: "12 avril 2026")
        m = re.match(r"(\d{1,2})\s+(\w+)\s+(\d{4})", text)
        if m:
            d, mois, y = m.groups()
            mo = MOIS_FR.get(mois.lower())
            if mo:
                try:
                    dt = datetime(int(y), mo, int(d))
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    pass

        return None

    @staticmethod
    def _infer_statut(date_iso: Optional[str]) -> str:
        if not date_iso:
            return "inconnu"
        try:
            dt = datetime.strptime(date_iso, "%Y-%m-%d")
            now = datetime.now()
            if dt < now:
                return "done"
            if (dt - now).days <= 7:
                return "urgent"
            return "upcoming"
        except ValueError:
            return "inconnu"
