# mga-mur-bot

Bot qui surveille le **taux de change MGA → MUR** (ariary malgache → roupie mauricienne) et envoie une **notification Telegram** à chaque variation. Il tourne automatiquement chaque jour, et peut aussi être déclenché à la demande depuis Telegram.

> **Propriété** — Ce projet appartient personnellement à **ramanantsoa009-rgb**. Tous droits réservés. Voir [LICENSE](LICENSE).

---

## Table des matières

1. [En bref](#en-bref)
2. [Technologies utilisées](#technologies-utilisées)
3. [Architecture générale](#architecture-générale)
4. [Structure du dépôt](#structure-du-dépôt)
5. [Comment ça marche — en détail](#comment-ça-marche--en-détail)
6. [Configuration (variables & secrets)](#configuration-variables--secrets)
7. [Installation depuis zéro](#installation-depuis-zéro)
8. [Utilisation au quotidien](#utilisation-au-quotidien)
9. [Maintenance & opérations](#maintenance--opérations)
10. [Dépannage](#dépannage)
11. [Sécurité](#sécurité)

---

## En bref

- **Source du taux** : API publique gratuite [fawazahmed0 / currency-api](https://github.com/fawazahmed0/exchange-api) (mise à jour ~1×/jour), avec une URL de secours.
- **Exécution automatique** : GitHub Actions, tous les jours à **06:00 UTC** (10:00 à Maurice).
- **Déclenchement manuel** : commande `/verifier` ou bouton **« Vérifier maintenant »** dans Telegram → passe par un **Cloudflare Worker** → relance le workflow GitHub.
- **État persistant** : le dernier taux connu est stocké dans `last_rate.json`, commité automatiquement dans le dépôt par le workflow.
- **Aucune dépendance Python** : uniquement la bibliothèque standard (Python 3.12+).

---

## Technologies utilisées

| Composant | Techno | Rôle |
|-----------|--------|------|
| Script principal | **Python 3.12** (stdlib seule : `urllib`, `json`, `datetime`, `dataclasses`) | Récupère le taux, compare, formate et envoie la notification |
| Ordonnancement + exécution | **GitHub Actions** (cron + `workflow_dispatch`) | Fait tourner le script chaque jour et à la demande ; commite `last_rate.json` |
| Notifications | **API Bot Telegram** (`sendMessage`, boutons inline) | Envoie les messages à l'utilisateur |
| Déclenchement manuel | **Cloudflare Workers** (JavaScript, `wrangler`) | Reçoit les événements Telegram (webhook) et déclenche le workflow via l'API GitHub |
| Persistance de l'état | **Fichier `last_rate.json`** versionné dans Git | Mémorise le dernier taux entre deux exécutions |

**Pourquoi cette architecture ?** GitHub Actions ne peut pas *écouter* Telegram (il est déclenché par cron ou API). Le Cloudflare Worker sert donc de **pont toujours disponible** : il reçoit le clic/commande Telegram et appelle l'API GitHub `workflow_dispatch`. Tout reste **gratuit** et **sans serveur à maintenir**.

---

## Architecture générale

```
                        ┌──────────────────────────────────────┐
                        │              DÉCLENCHEURS              │
                        └──────────────────────────────────────┘

  (1) AUTOMATIQUE                         (2) MANUEL DEPUIS TELEGRAM
  ┌─────────────────┐                     ┌──────────────────────────┐
  │ GitHub Actions  │                     │ Utilisateur : /verifier  │
  │ cron 06:00 UTC  │                     │ ou bouton "Vérifier..."  │
  └────────┬────────┘                     └────────────┬─────────────┘
           │                                           │ webhook HTTPS
           │                                           ▼
           │                              ┌────────────────────────────┐
           │                              │  Cloudflare Worker          │
           │                              │  (vérifie secret + chat id) │
           │                              │  → API workflow_dispatch    │
           │                              │    avec inputs.force=true   │
           │                              └────────────┬───────────────┘
           │                                           │ (token GitHub)
           ▼                                           ▼
        ┌──────────────────────────────────────────────────────┐
        │              GitHub Actions : run check_rate.py         │
        │  1. fetch_rate()  → API fawazahmed0 (+ fallback)        │
        │  2. compare au last_rate.json                           │
        │  3. envoie un message Telegram si nécessaire            │
        │  4. commite last_rate.json si le taux a changé          │
        └───────────────────────────┬────────────────────────────┘
                                     │ sendMessage (API Telegram)
                                     ▼
                              ┌────────────┐
                              │  Telegram  │  ← l'utilisateur reçoit la notif
                              └────────────┘
```

---

## Structure du dépôt

```
mga-mur-bot/
├── check_rate.py                     # Script principal (toute la logique)
├── last_rate.json                    # État : dernier taux connu (auto-commité)
├── .github/workflows/check-rate.yml  # Workflow GitHub Actions (cron + manuel)
├── cloudflare-worker/
│   ├── worker.js                     # Code du Worker (réception Telegram → GitHub)
│   ├── wrangler.toml                 # Config du Worker (variables non-secrètes)
│   └── README.md                     # Guide d'installation du Worker
├── .env                              # Secrets LOCAUX (ignoré par Git)
├── .env.example                      # Modèle de configuration
├── .gitignore
├── README.md                         # Ce fichier
├── SECURITY.md                       # Politique de sécurité
└── LICENSE                           # Licence propriétaire
```

---

## Comment ça marche — en détail

### 1. Récupération du taux (`fetch_rate`)

Le script interroge, dans l'ordre, deux URL de l'API fawazahmed0 (la 2ᵉ sert de secours si la 1ʳᵉ échoue) :

```
https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/mga.json
https://latest.currency-api.pages.dev/v1/currencies/mga.json
```

La réponse JSON contient la date et le taux (`data["mga"]["mur"]`).

### 2. Comparaison et décision de notifier (`run`)

Le dernier taux connu est lu depuis `last_rate.json`. La logique est la suivante :

| Situation | Message envoyé | `last_rate.json` mis à jour |
|-----------|----------------|------------------------------|
| **Premier lancement** (pas de `last_rate.json`) | `SUIVI DU TAUX MGA/MUR` (activation) | oui |
| **Variation ≥ seuil** (`SEUIL_PCT`) | `VARIATION DU TAUX MGA/MUR` | oui |
| **Variation < seuil**, sans force | *(aucun)* | oui |
| **Taux inchangé**, sans force | *(aucun)* | non |
| **Déclenchement manuel forcé** (`FORCE_REPORT=true`) et pas de variation notable | `TAUX ACTUEL MGA/MUR` | oui si changé |

> **Le mode « force »** est la clé du déclenchement manuel : sans lui, demander une vérification quand le taux n'a pas bougé ne renverrait *aucun* message. Le Worker envoie donc toujours `inputs.force=true`, ce qui garantit une réponse.

### 3. Notification Telegram (`send_telegram`)

Appel POST à `https://api.telegram.org/bot<token>/sendMessage` en `parse_mode=HTML`. Chaque message porte un **bouton inline « Vérifier maintenant »** (`callback_data: "trigger_check"`), géré par le Worker.

Les dates sont affichées en français (ex. `07 juillet 2026`) sans dépendre de la locale système, et chaque message inclut l'**heure de Maurice** (UTC+4, calculée à l'envoi).

### 4. Persistance (`save_rate` / `last_rate.json`)

Après une exécution où le taux a changé, `last_rate.json` est réécrit. Le workflow GitHub le **commite et le pousse** dans le dépôt (étape « Sauvegarder le dernier taux »), ce qui sert de mémoire entre deux runs.

### 5. Le workflow GitHub Actions (`.github/workflows/check-rate.yml`)

- **Déclencheurs** : `schedule` (cron `0 6 * * *`) et `workflow_dispatch` (avec un input booléen `force`).
- **Étapes** : checkout → installe Python 3.12 → exécute `check_rate.py` (avec les secrets en variables d'env) → commite `last_rate.json` s'il a changé.
- **Permissions** : `contents: write` (pour pouvoir committer le fichier d'état).

### 6. Le Cloudflare Worker (`cloudflare-worker/worker.js`)

Reçoit les mises à jour Telegram (webhook). Pour chaque requête :

1. Vérifie l'en-tête `X-Telegram-Bot-Api-Secret-Token` == `WEBHOOK_SECRET` (sinon `401`).
2. Vérifie que le `chat_id` correspond à `AUTHORIZED_CHAT_ID` (sinon action refusée).
3. Sur `/verifier`, `/check` ou le bouton, appelle l'API GitHub `workflow_dispatch` (avec `inputs.force=true`) puis répond « Vérification lancée ».
4. Sur `/start`, affiche un message avec le bouton.

---

## Configuration (variables & secrets)

> ⚠️ **Les valeurs réelles ne figurent PAS dans ce dépôt.** Elles vivent dans `.env` (local, ignoré par Git), dans les **GitHub Secrets**, et dans les **secrets Cloudflare**. Ne jamais committer de token.

### Variables du script Python

| Variable | Où | Description |
|----------|-----|-------------|
| `TELEGRAM_TOKEN` | secret | Token du bot Telegram (via [@BotFather](https://t.me/BotFather)) |
| `TELEGRAM_CHAT_ID` | secret | Identifiant du chat destinataire |
| `SEUIL_PCT` | variable (défaut `0`) | Variation minimale (%) pour notifier ; `0` = tout changement |
| `FORCE_REPORT` | variable | `true` = notifier même sans changement (injecté par le workflow lors d'un déclenchement manuel) |

### Où vit chaque secret

| Secret | GitHub Actions | Cloudflare Worker | Local (`.env`) |
|--------|:--------------:|:-----------------:|:--------------:|
| `TELEGRAM_TOKEN` | ✅ (Repository secret) | ✅ (`wrangler secret`) | ✅ |
| `TELEGRAM_CHAT_ID` | ✅ (Repository secret) | — (dans `wrangler.toml` comme `AUTHORIZED_CHAT_ID`) | ✅ |
| `GITHUB_TOKEN` (PAT fine-grained, *Actions: write*) | — | ✅ (`wrangler secret`) | — |
| `WEBHOOK_SECRET` (chaîne aléatoire) | — | ✅ (`wrangler secret`) | — |

### Variables non-secrètes du Worker (`cloudflare-worker/wrangler.toml`)

`GITHUB_OWNER`, `GITHUB_REPO`, `WORKFLOW_FILE`, `GIT_REF`, `AUTHORIZED_CHAT_ID`.

---

## Installation depuis zéro

Pour reconstruire tout le système (par ex. sur une nouvelle machine ou un nouveau compte).

### A. Bot automatique (indispensable)

1. **Créer un bot Telegram** via [@BotFather](https://t.me/BotFather) → récupérer le `TELEGRAM_TOKEN`.
2. **Trouver son `chat_id`** : écrire au bot, puis ouvrir
   `https://api.telegram.org/bot<TOKEN>/getUpdates` et lire `message.chat.id`.
3. **Pousser le projet sur GitHub.**
4. **Ajouter les secrets** dans *Settings → Secrets and variables → Actions* :
   `TELEGRAM_TOKEN` et `TELEGRAM_CHAT_ID`.
5. **Tester** : onglet *Actions → Suivi taux MGA/MUR → Run workflow*.

Le bot notifie désormais chaque jour à 06:00 UTC.

### B. Déclenchement manuel depuis Telegram (optionnel)

Détails complets dans [`cloudflare-worker/README.md`](cloudflare-worker/README.md). Résumé :

1. **Token GitHub** *fine-grained* avec permission **Actions: Read and write** sur le dépôt (ou token classic avec scopes `repo` + `workflow`).
2. **Déployer le Worker** depuis `cloudflare-worker/` :
   ```bash
   npx wrangler login
   npx wrangler deploy                     # crée le Worker, renvoie son URL
   npx wrangler secret put TELEGRAM_TOKEN
   npx wrangler secret put GITHUB_TOKEN
   npx wrangler secret put WEBHOOK_SECRET  # chaîne aléatoire, à conserver
   ```
   > Nécessite un sous-domaine `workers.dev` enregistré une fois sur le compte
   > (Cloudflare le demande au premier déploiement).
3. **Brancher le webhook Telegram** sur l'URL du Worker (le `secret_token` doit être
   identique à `WEBHOOK_SECRET`) :
   ```bash
   curl "https://api.telegram.org/bot<TOKEN>/setWebhook" \
     --data-urlencode "url=<WORKER_URL>" \
     --data-urlencode "secret_token=<WEBHOOK_SECRET>" \
     --data-urlencode 'allowed_updates=["message","callback_query"]'
   ```
4. **(Optionnel) Ajouter `/verifier` au menu** du bot :
   ```bash
   curl "https://api.telegram.org/bot<TOKEN>/setMyCommands" \
     -H "Content-Type: application/json" \
     -d '{"commands":[{"command":"verifier","description":"Verifier le taux MGA/MUR maintenant"}]}'
   ```

---

## Utilisation au quotidien

- **Automatique** : rien à faire, notification quotidienne si le taux bouge.
- **Manuel** : envoie `/verifier` au bot, ou appuie sur **« Vérifier maintenant »**.
  Tu reçois d'abord « Vérification lancée » (immédiat, depuis le Worker), puis le
  taux (après ~15–30 s, depuis GitHub Actions).
- **Depuis GitHub** : *Actions → Run workflow* (avec l'option « force » cochée pour
  toujours recevoir le taux).

### En local (test manuel du script)

```bash
cp .env.example .env    # puis renseigner les valeurs
python3 check_rate.py
```

> Sur macOS, si erreur `SSL: CERTIFICATE_VERIFY_FAILED`, lancer une fois :
> `/Applications/Python\ 3.12/Install\ Certificates.command`

---

## Maintenance & opérations

| Tâche | Commande / action |
|-------|-------------------|
| Modifier la logique du bot | Éditer `check_rate.py`, commit + push. Le prochain run l'utilise. |
| Modifier le Worker | Éditer `cloudflare-worker/worker.js`, puis `npx wrangler deploy` depuis ce dossier. |
| Changer un secret Cloudflare | `printf '%s' "NOUVELLE_VALEUR" \| npx wrangler secret put NOM_DU_SECRET` |
| Voir les logs du Worker en direct | `npx wrangler tail` (depuis `cloudflare-worker/`) |
| Vérifier l'état du webhook | `curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"` |
| Changer la fréquence auto | Modifier le `cron` dans `.github/workflows/check-rate.yml` |
| Changer le seuil de notif | `SEUIL_PCT` dans le workflow (ex. `"0.5"` pour ±0,5 %) |

---

## Dépannage

| Symptôme | Cause probable / solution |
|----------|---------------------------|
| Le workflow tourne mais **aucun message** | Le taux n'a pas changé. Normal en mode auto. En manuel, `force=true` renvoie quand même le taux (« TAUX ACTUEL »). |
| `/verifier` ne fait **rien** | Webhook mal branché : vérifier `getWebhookInfo` (champ `last_error_message`). |
| Worker renvoie **401** | `WEBHOOK_SECRET` (Worker) ≠ `secret_token` passé à `setWebhook`. |
| Déclenchement **échoue** (Worker log) | Le `GITHUB_TOKEN` n'a pas *Actions: write*, ou `GITHUB_REPO`/`WORKFLOW_FILE` incorrects dans `wrangler.toml`. |
| API GitHub renvoie **422** | L'input `force` doit être déclaré dans le `workflow_dispatch` du YAML (déjà le cas ici). |
| Erreur **SSL** en local (macOS) | Installer les certificats Python (voir plus haut). Sur GitHub Actions, aucun souci. |

---

## Sécurité

Voir [SECURITY.md](SECURITY.md). Points essentiels :

- Aucun secret n'est versionné : `.env` est ignoré par Git ; les tokens vivent dans GitHub Secrets et les secrets Cloudflare.
- Le Worker est protégé par un **secret partagé** (`WEBHOOK_SECRET`) et **restreint à un chat autorisé** (`AUTHORIZED_CHAT_ID`).
- En cas de fuite d'un token : révoquer via [@BotFather](https://t.me/BotFather) (Telegram) ou dans les *Personal access tokens* (GitHub), puis mettre à jour le secret correspondant partout où il est utilisé.

---

## Licence

Logiciel propriétaire — © 2026 ramanantsoa009-rgb. Tous droits réservés. Voir [LICENSE](LICENSE).
