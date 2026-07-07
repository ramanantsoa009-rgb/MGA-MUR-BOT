/**
 * Cloudflare Worker — déclenchement manuel du bot MGA/MUR depuis Telegram.
 *
 * Reçoit les mises à jour Telegram (webhook), et sur la commande /verifier
 * ou le bouton « Vérifier maintenant », déclenche le workflow GitHub Actions
 * via l'API workflow_dispatch.
 *
 * Secrets attendus (wrangler secret put ...) :
 *   TELEGRAM_TOKEN   — token du bot Telegram
 *   GITHUB_TOKEN     — token GitHub (fine-grained) avec Actions: write
 *   WEBHOOK_SECRET   — secret partagé, vérifié à chaque requête entrante
 *
 * Variables (wrangler.toml [vars]) :
 *   GITHUB_OWNER, GITHUB_REPO, WORKFLOW_FILE, GIT_REF, AUTHORIZED_CHAT_ID
 */

const TELEGRAM_API = "https://api.telegram.org";

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("OK", { status: 200 });
    }

    // Vérifie le secret partagé envoyé par Telegram dans l'en-tête.
    const secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token");
    if (secret !== env.WEBHOOK_SECRET) {
      return new Response("Unauthorized", { status: 401 });
    }

    let update;
    try {
      update = await request.json();
    } catch {
      return new Response("Bad Request", { status: 400 });
    }

    // On répond toujours 200 à Telegram ; le traitement est géré au-dessus.
    await handleUpdate(update, env).catch((e) => console.error("handleUpdate:", e));
    return new Response("OK", { status: 200 });
  },
};

async function handleUpdate(update, env) {
  // Bouton inline pressé
  if (update.callback_query) {
    const cq = update.callback_query;
    const chatId = cq.message?.chat?.id;
    if (!isAuthorized(chatId, env)) {
      return answerCallback(env, cq.id, "Non autorisé.");
    }
    if (cq.data === "trigger_check") {
      const ok = await triggerWorkflow(env);
      await answerCallback(
        env,
        cq.id,
        ok ? "Vérification lancée." : "Échec du déclenchement."
      );
      await sendMessage(
        env,
        chatId,
        ok
          ? "Vérification du taux MGA/MUR lancée. Résultat dans quelques instants."
          : "Impossible de lancer la vérification. Réessaie plus tard."
      );
    }
    return;
  }

  // Message texte / commande
  const msg = update.message;
  if (!msg || !msg.text) return;
  const chatId = msg.chat?.id;
  if (!isAuthorized(chatId, env)) {
    return sendMessage(env, chatId, "Non autorisé.");
  }

  const text = msg.text.trim().toLowerCase();

  if (text.startsWith("/start")) {
    return sendMessage(
      env,
      chatId,
      "Bot de suivi du taux MGA/MUR.\n" +
        "Utilise /verifier ou le bouton ci-dessous pour lancer une vérification manuelle.",
      triggerKeyboard()
    );
  }

  if (text.startsWith("/verifier") || text.startsWith("/check")) {
    const ok = await triggerWorkflow(env);
    return sendMessage(
      env,
      chatId,
      ok
        ? "Vérification du taux MGA/MUR lancée. Résultat dans quelques instants."
        : "Impossible de lancer la vérification. Réessaie plus tard."
    );
  }
}

function isAuthorized(chatId, env) {
  if (!env.AUTHORIZED_CHAT_ID) return true; // pas de restriction si non défini
  return String(chatId) === String(env.AUTHORIZED_CHAT_ID);
}

function triggerKeyboard() {
  return {
    inline_keyboard: [
      [{ text: "Vérifier maintenant", callback_data: "trigger_check" }],
    ],
  };
}

async function triggerWorkflow(env) {
  const url =
    `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}` +
    `/actions/workflows/${env.WORKFLOW_FILE}/dispatches`;
  const resp = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "mga-mur-telegram-trigger",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      ref: env.GIT_REF || "main",
      inputs: { force: "true" }, // déclenchement manuel : toujours notifier
    }),
  });
  if (resp.status !== 204) {
    console.error("workflow_dispatch:", resp.status, await resp.text());
    return false;
  }
  return true;
}

async function sendMessage(env, chatId, text, replyMarkup) {
  const body = { chat_id: chatId, text };
  if (replyMarkup) body.reply_markup = replyMarkup;
  await fetch(`${TELEGRAM_API}/bot${env.TELEGRAM_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function answerCallback(env, callbackQueryId, text) {
  await fetch(`${TELEGRAM_API}/bot${env.TELEGRAM_TOKEN}/answerCallbackQuery`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ callback_query_id: callbackQueryId, text }),
  });
}
