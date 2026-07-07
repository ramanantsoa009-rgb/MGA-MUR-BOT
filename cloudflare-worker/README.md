# Déclenchement manuel depuis Telegram (Cloudflare Worker)

Ce Worker permet de lancer une vérification du taux MGA/MUR **depuis Telegram**,
via la commande `/verifier` ou le bouton **« Vérifier maintenant »**. Il reçoit
l'événement Telegram (webhook) et déclenche le workflow GitHub Actions.

```
Telegram ── webhook ──► Cloudflare Worker ── API workflow_dispatch ──► GitHub Actions ──► check_rate.py
```

## Prérequis

- Un compte Cloudflare (gratuit).
- Node.js installé (pour la CLI `wrangler`).
- Le token de ton bot Telegram.

## 1. Créer un token GitHub (fine-grained)

Le Worker doit pouvoir déclencher le workflow.

1. GitHub → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**
2. **Repository access** : *Only select repositories* → `MGA-MUR-BOT`
3. **Permissions → Repository permissions → Actions** : *Read and write*
4. Génère le token et **copie-le** (il ne sera plus affiché).

## 2. Déployer le Worker

Depuis ce dossier `cloudflare-worker/` :

```bash
npm install -g wrangler        # si pas déjà installé
wrangler login                 # ouvre le navigateur pour connecter ton compte

# Enregistre les 3 secrets (ils seront demandés de façon interactive) :
wrangler secret put TELEGRAM_TOKEN     # le token du bot Telegram
wrangler secret put GITHUB_TOKEN       # le token GitHub de l'étape 1
wrangler secret put WEBHOOK_SECRET     # invente une chaîne aléatoire (garde-la)

wrangler deploy
```

`wrangler deploy` affiche l'URL du Worker, par ex. :
`https://mga-mur-telegram-trigger.<ton-sous-domaine>.workers.dev`

> Vérifie que `AUTHORIZED_CHAT_ID` dans `wrangler.toml` correspond bien à ton
> chat (déjà réglé sur `7004757178`). Laisse vide pour autoriser tout le monde.

## 3. Connecter le webhook Telegram

Remplace `<TOKEN>`, `<WORKER_URL>` et `<WEBHOOK_SECRET>` par tes valeurs :

```bash
curl "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  --data-urlencode "url=<WORKER_URL>" \
  --data-urlencode "secret_token=<WEBHOOK_SECRET>" \
  --data-urlencode "allowed_updates=[\"message\",\"callback_query\"]"
```

Le `secret_token` doit être **identique** à `WEBHOOK_SECRET`. Telegram le
renvoie dans l'en-tête `X-Telegram-Bot-Api-Secret-Token`, que le Worker vérifie.

## 4. (Optionnel) Ajouter la commande au menu du bot

Pour faire apparaître `/verifier` dans le menu Telegram du bot :

```bash
curl "https://api.telegram.org/bot<TOKEN>/setMyCommands" \
  -H "Content-Type: application/json" \
  -d '{"commands":[{"command":"verifier","description":"Vérifier le taux MGA/MUR maintenant"}]}'
```

## Utilisation

- Envoie `/verifier` au bot, **ou**
- Clique sur **« Vérifier maintenant »** sous n'importe quelle notification, ou
  envoie `/start` pour afficher le bouton.

Le Worker déclenche le workflow ; `check_rate.py` s'exécute et t'envoie le taux
comme d'habitude (quelques secondes à ~1 min selon la file GitHub Actions).

## Dépannage

- **Rien ne se passe** : vérifie le webhook avec
  `curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"` (regarde
  `last_error_message`).
- **401 dans les logs** : `WEBHOOK_SECRET` (Worker) ≠ `secret_token` (setWebhook).
- **Échec du déclenchement** : le `GITHUB_TOKEN` n'a pas la permission *Actions:
  write*, ou `WORKFLOW_FILE`/`GITHUB_REPO` sont incorrects dans `wrangler.toml`.
- **Logs en direct** : `wrangler tail`.

## Sécurité

- Les 3 secrets vivent uniquement dans Cloudflare (jamais dans le dépôt).
- `AUTHORIZED_CHAT_ID` empêche quelqu'un d'autre de déclencher ton workflow.
- Le `WEBHOOK_SECRET` garantit que seules les requêtes de Telegram sont acceptées.
