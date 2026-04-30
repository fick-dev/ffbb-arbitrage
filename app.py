"""
FFBB FBI Scraper — Backend Flask
Récupère les convocations d'arbitrage depuis extranet.ffbb.com/fbi
"""

import os
import json
import logging
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, jsonify, request
from flask_cors import CORS
from scraper import FBIScraper
from cache import ConvocationCache

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins=os.getenv("ALLOWED_ORIGINS", "*").split(","))

cache = ConvocationCache()

# ── Auth simple par token ────────────────────────────────────────────────────

API_TOKEN = os.getenv("API_TOKEN", "changez-moi-en-production")

def require_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("X-API-Token") or request.args.get("token")
        if token != API_TOKEN:
            return jsonify({"error": "Token invalide"}), 401
        return f(*args, **kwargs)
    return decorated


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})


@app.route("/api/convocations")
@require_token
def get_convocations():
    """
    Retourne les convocations. Utilise le cache (TTL configurable).
    Query params:
      - force_refresh=1  : ignore le cache et rescrape
      - statut=upcoming|done|all (défaut: all)
    """
    force = request.args.get("force_refresh") == "1"
    statut = request.args.get("statut", "all")

    # Vérifier le cache
    if not force:
        cached = cache.get()
        if cached:
            logger.info("Réponse depuis le cache")
            return jsonify(_filter(cached, statut))

    # Scraper les données fraîches
    logger.info("Scraping FBI...")
    scraper = FBIScraper(
        username=os.getenv("FBI_USERNAME"),
        password=os.getenv("FBI_PASSWORD"),
    )

    try:
        convocations = scraper.fetch_convocations()
        cache.set(convocations)
        logger.info(f"{len(convocations)} convocations récupérées")
        return jsonify(_filter(convocations, statut))
    except Exception as e:
        logger.error(f"Erreur scraping: {e}")
        # Retourner le cache périmé si disponible plutôt que rien
        stale = cache.get(ignore_ttl=True)
        if stale:
            logger.info("Retour du cache périmé après erreur")
            return jsonify({**_filter(stale, statut), "stale": True, "error": str(e)})
        return jsonify({"error": str(e)}), 500


@app.route("/api/stats")
@require_token
def get_stats():
    """Statistiques globales de la saison."""
    cached = cache.get(ignore_ttl=True)
    if not cached:
        return jsonify({"error": "Aucune donnée disponible — lancez /api/convocations d'abord"}), 404

    convocations = cached.get("convocations", [])
    now = datetime.now()

    upcoming = [c for c in convocations if _parse_date(c) and _parse_date(c) >= now]
    done     = [c for c in convocations if _parse_date(c) and _parse_date(c) < now]
    week     = [c for c in upcoming if _parse_date(c) <= now + timedelta(days=7)]

    return jsonify({
        "total":    len(convocations),
        "upcoming": len(upcoming),
        "done":     len(done),
        "this_week": len(week),
        "last_update": cached.get("fetched_at"),
    })


# ── Helpers ──────────────────────────────────────────────────────────────────

def _filter(data: dict, statut: str) -> dict:
    if statut == "all":
        return data
    convocations = data.get("convocations", [])
    now = datetime.now()
    if statut == "upcoming":
        filtered = [c for c in convocations if _parse_date(c) and _parse_date(c) >= now]
    elif statut == "done":
        filtered = [c for c in convocations if _parse_date(c) and _parse_date(c) < now]
    else:
        filtered = convocations
    return {**data, "convocations": filtered}


def _parse_date(conv: dict):
    try:
        return datetime.strptime(conv.get("date_iso", ""), "%Y-%m-%d")
    except Exception:
        return None


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("DEBUG", "false").lower() == "true")
