from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _default_hermes_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "hermes" / "hermes-agent"
    return Path.home() / "AppData" / "Local" / "hermes" / "hermes-agent"


def _default_state_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "hermes" / "cache" / "xai-oauth-manual-state.json"
    return Path.home() / "AppData" / "Local" / "hermes" / "cache" / "xai-oauth-manual-state.json"


HERMES_ROOT = Path(os.environ.get("HERMES_ROOT") or _default_hermes_root())
STATE_PATH = Path(os.environ.get("HERMES_XAI_OAUTH_STATE") or _default_state_path())

sys.path.insert(0, str(HERMES_ROOT))

import hermes_cli.auth as auth_mod  # noqa: E402
from agent.credential_pool import (  # noqa: E402
    AUTH_TYPE_OAUTH,
    SOURCE_MANUAL,
    PooledCredential,
    label_from_token,
    load_pool,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def init() -> None:
    discovery = auth_mod._xai_oauth_discovery(20.0)
    redirect_uri = (
        f"http://{auth_mod.XAI_OAUTH_REDIRECT_HOST}:"
        f"{auth_mod.XAI_OAUTH_REDIRECT_PORT}"
        f"{auth_mod.XAI_OAUTH_REDIRECT_PATH}"
    )
    auth_mod._xai_validate_loopback_redirect_uri(redirect_uri)
    code_verifier = auth_mod._oauth_pkce_code_verifier()
    code_challenge = auth_mod._oauth_pkce_code_challenge(code_verifier)
    state = uuid.uuid4().hex
    nonce = uuid.uuid4().hex
    authorize_url = auth_mod._xai_oauth_build_authorize_url(
        authorization_endpoint=discovery["authorization_endpoint"],
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        state=state,
        nonce=nonce,
    )
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(
            {
                "created_at": _now(),
                "discovery": discovery,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
                "code_challenge": code_challenge,
                "state": state,
                "nonce": nonce,
                "authorize_url": authorize_url,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(authorize_url)


def exchange(callback_or_code: str) -> None:
    if not STATE_PATH.exists():
        raise SystemExit(f"State file not found: {STATE_PATH}")
    data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    callback = auth_mod._parse_pasted_callback(callback_or_code)
    if callback.get("error"):
        detail = callback.get("error_description") or callback.get("error")
        raise SystemExit(f"xAI authorization failed: {detail}")
    callback_state = callback.get("state")
    if callback_state is None:
        callback_state = data["state"]
    if callback_state != data["state"]:
        raise SystemExit("xAI authorization failed: state mismatch")
    code = str(callback.get("code") or "").strip()
    if not code:
        raise SystemExit("xAI authorization failed: missing code")

    payload = auth_mod._xai_oauth_exchange_code_for_tokens(
        token_endpoint=data["discovery"]["token_endpoint"],
        code=code,
        redirect_uri=data["redirect_uri"],
        code_verifier=data["code_verifier"],
        code_challenge=data["code_challenge"],
        timeout_seconds=30.0,
    )
    access_token = str(payload.get("access_token", "") or "").strip()
    refresh_token = str(payload.get("refresh_token", "") or "").strip()
    if not access_token or not refresh_token:
        raise SystemExit("xAI token exchange did not return expected tokens")

    base_url = auth_mod._xai_validate_inference_base_url(
        os.getenv("HERMES_XAI_BASE_URL", "").strip().rstrip("/")
        or os.getenv("XAI_BASE_URL", "").strip().rstrip("/"),
        fallback=auth_mod.DEFAULT_XAI_OAUTH_BASE_URL,
    )
    last_refresh = _now()
    tokens = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "id_token": str(payload.get("id_token", "") or "").strip(),
        "expires_in": payload.get("expires_in"),
        "token_type": str(payload.get("token_type") or "Bearer").strip() or "Bearer",
    }
    auth_mod._save_xai_oauth_tokens(
        tokens,
        discovery=data["discovery"],
        redirect_uri=data["redirect_uri"],
        last_refresh=last_refresh,
    )

    pool = load_pool("xai-oauth")
    label = label_from_token(access_token, f"xai-oauth-{len(pool.entries()) + 1}")
    entry = PooledCredential(
        provider="xai-oauth",
        id=uuid.uuid4().hex[:6],
        label=label,
        auth_type=AUTH_TYPE_OAUTH,
        priority=0,
        source=f"{SOURCE_MANUAL}:xai_pkce",
        access_token=access_token,
        refresh_token=refresh_token,
        base_url=base_url,
        last_refresh=last_refresh,
    )
    pool.add_entry(entry)
    try:
        STATE_PATH.unlink()
    except OSError:
        pass
    print(f"saved: {entry.label}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate and exchange an xAI OAuth callback URL for Hermes."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="Print an xAI authorization URL.")
    exchange_parser = sub.add_parser("exchange", help="Exchange callback URL or code and save credentials.")
    exchange_parser.add_argument("callback_or_code")
    args = parser.parse_args()
    if args.cmd == "init":
        init()
    elif args.cmd == "exchange":
        exchange(args.callback_or_code)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
