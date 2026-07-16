"""Surcouche IA (Phase 3) — abstraction fournisseur : OpenAI, Azure OpenAI, ou clé universelle Emergent.
Les identifiants sont fournis au runtime (stockés en DB) ; aucune clé n'est exposée au client.
Dégradation gracieuse : si non configuré, lève AINotConfigured (jamais de plantage)."""
import os
import time
import httpx

DEFAULT_MODEL = "gpt-4o"
_RATE = {}
RATE_MAX = 20        # appels
RATE_WINDOW = 60     # secondes


class AINotConfigured(Exception):
    pass


class AIError(Exception):
    pass


def _rate_ok(email: str) -> bool:
    now = time.time()
    arr = [t for t in _RATE.get(email or "anon", []) if now - t < RATE_WINDOW]
    if len(arr) >= RATE_MAX:
        return False
    arr.append(now)
    _RATE[email or "anon"] = arr
    return True


def ai_status(cfg: dict) -> dict:
    """Retourne l'état de configuration sans divulguer les secrets."""
    if not cfg or not cfg.get("enabled"):
        return {"configured": False, "provider": cfg.get("provider") if cfg else None}
    p = cfg.get("provider")
    ok = False
    if p == "emergent":
        ok = bool(os.environ.get("EMERGENT_LLM_KEY"))
    elif p == "openai":
        ok = bool(cfg.get("openai_api_key"))
    elif p == "azure":
        ok = bool(cfg.get("azure_api_key") and cfg.get("azure_endpoint") and cfg.get("azure_deployment"))
    return {"configured": ok, "provider": p}


async def ai_complete(cfg: dict, system: str, user: str, email: str = "", max_tokens: int = 800, temperature: float = 0.2) -> str:
    st = ai_status(cfg)
    if not st["configured"]:
        raise AINotConfigured("Fonctionnalité IA non configurée.")
    if not _rate_ok(email):
        raise AIError("Limite de fréquence atteinte. Réessayez dans une minute.")
    provider = cfg["provider"]
    model = cfg.get("model") or DEFAULT_MODEL

    if provider == "emergent":
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(api_key=os.environ["EMERGENT_LLM_KEY"], session_id="acct-ai", system_message=system).with_model("openai", model)
        resp = await chat.send_message(UserMessage(text=user))
        return resp if isinstance(resp, str) else str(resp)

    async with httpx.AsyncClient(timeout=90) as client:
        if provider == "openai":
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {cfg['openai_api_key']}"},
                json={"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "temperature": temperature},
            )
        else:  # azure
            ver = cfg.get("azure_api_version") or "2024-08-01-preview"
            base = cfg["azure_endpoint"].rstrip("/")
            url = f"{base}/openai/deployments/{cfg['azure_deployment']}/chat/completions?api-version={ver}"
            r = await client.post(
                url,
                headers={"api-key": cfg["azure_api_key"]},
                json={"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "temperature": temperature},
            )
        if r.status_code == 401 or r.status_code == 403:
            raise AINotConfigured("Clé API IA invalide ou non autorisée.")
        if r.status_code >= 400:
            raise AIError(f"Erreur du fournisseur IA ({r.status_code}).")
        data = r.json()
        return data["choices"][0]["message"]["content"]
