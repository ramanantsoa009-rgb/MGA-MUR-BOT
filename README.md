# mga-mur-bot

Bot de surveillance du taux de change **MGA → MUR** (ariary malgache → roupie mauricienne). À chaque exécution, il récupère le taux du jour, le compare au dernier taux enregistré et envoie une notification **Telegram** en cas de variation.

> **Propriété** — Ce projet appartient personnellement à **ramanantsoa009-rgb**. Tous droits réservés. Voir [LICENSE](LICENSE).

## Fonctionnement

1. Récupération du taux via l'API [fawazahmed0 / currency-api](https://github.com/fawazahmed0/exchange-api) (mise à jour quotidienne), avec une URL de secours.
2. Comparaison avec le dernier taux stocké dans `last_rate.json`.
3. Notification Telegram si la variation atteint le seuil configuré (`SEUIL_PCT`).
4. Mise à jour de `last_rate.json`.

Au tout premier lancement, un message d'activation est envoyé et le taux initial est enregistré.

## Format des notifications

```
VARIATION DU TAUX MGA/MUR

Nouveau taux : 1 MGA = 0.011098 MUR
Taux précédent : 1 MGA = 0.011050 MUR
Variation : +0.438 % (Hausse)
Équivalence : 1 MUR = 90.10 MGA
Date : 07 juillet 2026
Heure de Maurice : 07 juillet 2026 12:31
```

## Configuration

Variables d'environnement (voir [.env.example](.env.example)) :

| Variable | Requis | Description |
|----------|--------|-------------|
| `TELEGRAM_TOKEN` | oui | Token du bot Telegram (via [@BotFather](https://t.me/BotFather)) |
| `TELEGRAM_CHAT_ID` | oui | Identifiant du chat/canal destinataire |
| `SEUIL_PCT` | non | Variation minimale (%) pour notifier. `0` (défaut) = notifier à chaque changement |

En local, copiez le modèle puis renseignez vos valeurs :

```bash
cp .env.example .env
# éditez .env
```

Le fichier `.env` est ignoré par Git et n'est **jamais** versionné.

## Exécution

### En local

```bash
python3 check_rate.py
```

Le script charge automatiquement `.env`. Aucune dépendance externe (Python 3.12+, bibliothèque standard uniquement).

> Sur macOS, si vous obtenez une erreur `SSL: CERTIFICATE_VERIFY_FAILED`, installez les certificats Python une fois :
> `/Applications/Python\ 3.12/Install\ Certificates.command`

### Automatique (GitHub Actions)

Le workflow [`.github/workflows/check-rate.yml`](.github/workflows/check-rate.yml) s'exécute :

- **chaque jour à 06:00 UTC** (cron) ;
- **manuellement** via l'onglet *Actions → Suivi taux MGA/MUR → Run workflow*.

Il faut d'abord définir les secrets `TELEGRAM_TOKEN` et `TELEGRAM_CHAT_ID` dans
*Settings → Secrets and variables → Actions* du dépôt.

## Sécurité

Aucun secret ne doit être commité. Voir [SECURITY.md](SECURITY.md) pour la politique complète.

## Licence

Logiciel propriétaire — © 2026 ramanantsoa009-rgb. Tous droits réservés. Voir [LICENSE](LICENSE).
