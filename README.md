# FFBB Arbitrage — Dashboard de convocations

Récupère automatiquement vos convocations d'arbitrage depuis le portail FBI
(extranet.ffbb.com) et les affiche dans un dashboard web.

---

## Architecture

```
ffbb-arbitrage/
├── backend/          ← API Python (Flask) + scraper FBI
│   ├── app.py        ← Serveur Flask, routes /api/convocations et /api/stats
│   ├── scraper.py    ← Connexion + parsing FBI
│   ├── cache.py      ← Cache en mémoire (TTL 6h)
│   ├── requirements.txt
│   ├── Procfile      ← Pour Render/Railway (gunicorn)
│   └── .env.example  ← Variables d'environnement à configurer
└── frontend/
    └── index.html    ← Dashboard HTML/CSS/JS (fichier unique, hébergeable partout)
```

---

## Déploiement en 4 étapes

### 1. Préparer le dépôt Git

```bash
git init ffbb-arbitrage
cd ffbb-arbitrage
cp -r /chemin/vers/backend .
cp -r /chemin/vers/frontend .
echo ".env" >> .gitignore
git add .
git commit -m "Initial commit"
# Poussez sur GitHub / GitLab
```

---

### 2. Déployer le backend sur Render (gratuit)

1. Créez un compte sur **render.com**
2. **New → Web Service** → connectez votre dépôt GitHub
3. Paramètres :
   - **Root directory** : `backend`
   - **Runtime** : Python 3
   - **Build command** : `pip install -r requirements.txt`
   - **Start command** : `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 60`
4. Dans **Environment Variables**, ajoutez :

   | Clé | Valeur |
   |-----|--------|
   | `FBI_USERNAME` | votre identifiant FBI |
   | `FBI_PASSWORD` | votre mot de passe FBI |
   | `API_TOKEN` | un token aléatoire (voir ci-dessous) |
   | `CACHE_TTL_SECONDS` | `21600` |
   | `ALLOWED_ORIGINS` | `*` (ou l'URL de votre frontend) |

5. **Générer un token sécurisé** (à faire en local) :
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

6. Cliquez **Deploy** — notez l'URL, ex : `https://ffbb-arbitrage.onrender.com`

> ⚠️ Sur le plan gratuit Render, le service se met en veille après 15 min d'inactivité.
> Le premier appel après la veille prend ~30 secondes. Pour éviter ça, utilisez
> un service de ping gratuit (UptimeRobot) sur `/health` toutes les 10 minutes.

---

### 3. Déployer le backend sur Railway (alternative)

1. Créez un compte sur **railway.app**
2. **New Project → Deploy from GitHub repo**
3. Sélectionnez votre dépôt, root directory = `backend`
4. Ajoutez les mêmes variables d'environnement
5. Railway détecte automatiquement le `Procfile`

---

### 4. Configurer et héberger le frontend

Ouvrez `frontend/index.html` et modifiez les deux lignes en haut du script :

```javascript
const API_BASE  = "https://ffbb-arbitrage.onrender.com"; // ← Votre URL Render/Railway
const API_TOKEN = "votre-token-genere-plus-haut";        // ← Même que dans .env
```

**Héberger le frontend (choisissez une option) :**

- **GitHub Pages** : Pushez `index.html` dans un repo → Settings → Pages
- **Netlify Drop** : Glissez-déposez le fichier sur app.netlify.com/drop
- **Vercel** : `vercel deploy --prod frontend/`
- **Local** : Ouvrez simplement `index.html` dans votre navigateur

---

## Routes API disponibles

| Route | Description |
|-------|-------------|
| `GET /health` | Vérification que le serveur tourne |
| `GET /api/convocations` | Liste toutes les convocations (cachées 6h) |
| `GET /api/convocations?statut=upcoming` | Filtre : à venir |
| `GET /api/convocations?statut=done` | Filtre : effectuées |
| `GET /api/convocations?force_refresh=1` | Force un nouveau scraping |
| `GET /api/stats` | Statistiques globales de la saison |

Toutes les routes protégées nécessitent le header `X-API-Token: votre-token`.

---

## Adapter le scraper si nécessaire

Le site FBI peut changer sa structure HTML. Si les convocations n'apparaissent pas :

1. Connectez-vous manuellement sur extranet.ffbb.com/fbi
2. Naviguez vers votre page de convocations
3. Clic droit → **Inspecter** pour voir le HTML
4. Identifiez les sélecteurs CSS des lignes/colonnes
5. Mettez à jour `scraper.py` → méthodes `_parse_convocations()`,
   `_parse_row()` ou `_parse_card()`

Les logs gunicorn afficheront les éventuelles erreurs de parsing.

---

## Fréquence de mise à jour

Le cache est configuré à **6 heures** (`CACHE_TTL_SECONDS=21600`).
Vous pouvez baisser à `3600` (1h) ou forcer manuellement via le bouton
"Actualiser" du dashboard (qui appelle `?force_refresh=1`).

---

## Sécurité

- Ne commitez jamais `.env` dans Git (il est dans `.gitignore`)
- Utilisez un `API_TOKEN` fort (32 caractères hex minimum)
- En production, limitez `ALLOWED_ORIGINS` à l'URL exacte de votre frontend
- Vos identifiants FBI sont stockés uniquement dans les variables d'environnement
  de Render/Railway, jamais dans le code
