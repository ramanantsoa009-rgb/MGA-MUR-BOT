# Politique de sécurité

Ce projet appartient personnellement à **ramanantsoa009-rgb**. Tous droits réservés.

## Signaler une vulnérabilité

Toute vulnérabilité ou incident de sécurité doit être signalé de façon privée au
propriétaire du dépôt, **[@ramanantsoa009-rgb](https://github.com/ramanantsoa009-rgb)**
(via un message privé GitHub). N'ouvrez pas d'issue publique pour un problème de sécurité.

Merci d'inclure :

- une description du problème et de son impact ;
- les étapes pour le reproduire ;
- la version / le commit concerné.

## Gestion des secrets

- Les identifiants (`TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`) ne doivent **jamais**
  être commités dans le dépôt.
- En local, ils sont stockés dans `.env`, ignoré par Git (voir `.gitignore`).
- En production (GitHub Actions), ils sont fournis via les **GitHub Secrets**
  (*Settings → Secrets and variables → Actions*).
- Si un token est exposé, révoquez-le immédiatement via [@BotFather](https://t.me/BotFather)
  et générez-en un nouveau.

## Bonnes pratiques

- Le dossier `.claude/` (configuration locale) est exclu du versionnement.
- Le script n'utilise que la bibliothèque standard Python, ce qui réduit la
  surface d'attaque liée aux dépendances tierces.
- Les appels réseau sont limités aux domaines de l'API de taux et de l'API
  Telegram, avec un délai d'expiration (`HTTP_TIMEOUT`).

## Périmètre

Cette politique couvre le code de ce dépôt uniquement. Les services externes
(Telegram, API de taux de change) relèvent de leurs propres politiques de
sécurité.
