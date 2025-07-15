from __future__ import annotations

import os
import time
from typing import Dict, Tuple, Optional

from msal import ConfidentialClientApplication

from dotenv import load_dotenv
load_dotenv()

# Load env vars (raise if missing to fail fast)
TENANT_ID          = os.getenv("AZURE_TENANT_ID")
CLIENT_ID          = os.getenv("AZURE_CLIENT_ID")
CLIENT_SECRET      = os.getenv("AZURE_CLIENT_SECRET")
REDIRECT_URI       = os.getenv("REDIRECT_URI", "http://localhost:8000/oauth/callback")
DEFAULT_SCOPES     = os.getenv("AZURE_SCOPES", "openid profile email offline_access").split()

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"

# Simple in‑memory cache.
# @TO-DO: Replace it with persistent cache for production.
_token_cache: Dict[str, Dict] = {}  # key = user_id/email, value = token dict


def _build_app() -> ConfidentialClientApplication:
    return ConfidentialClientApplication(
        client_id=CLIENT_ID,
        client_credential=CLIENT_SECRET,
        authority=AUTHORITY,
    )


# Public helpers
def acquire_token_interactive(user_identifier: str) -> Dict:
    """
    *Development‑only* helper. Launches the system browser so the user can sign in.
    Stores token in the module cache keyed by user email.
    """
    app = _build_app()
    flow = app.initiate_auth_code_flow(scopes=DEFAULT_SCOPES, redirect_uri=REDIRECT_URI)

    auth_url = flow["auth_uri"]
    print(f"[AzureAuth] Opening browser for user login: {auth_url}")

    # In Chainlit, you might instead present this URL as a link element
    import webbrowser
    webbrowser.open(auth_url)

    # Wait for redirect… In production, Chainlit's /oauth/callback will POST back the code.
    auth_code = input("Paste the 'code' query param from the redirected URL: ").strip()

    result = app.acquire_token_by_auth_code_flow(flow, { "code": auth_code, "redirect_uri": REDIRECT_URI })
    if "access_token" not in result:
        raise RuntimeError(f"Azure token acquisition failed: {result.get('error_description')}")

    _token_cache[user_identifier] = _augment_with_expiry(result)
    return result


def get_access_token(user_identifier: str, scopes: Optional[list[str]] = None) -> Tuple[str, Dict]:
    """
    Silent flow. Returns (access_token, full_token_dict).

    * If cached token is valid → return it.
    * If expired but refresh_token present → refresh.
    * Else → raise so caller can trigger interactive/login UI.
    """
    scopes = scopes or DEFAULT_SCOPES
    cached = _token_cache.get(user_identifier)
    if cached and cached["expires_at"] > time.time() + 60:
        return cached["access_token"], cached

    app = _build_app()
    if cached and "refresh_token" in cached:
        result = app.acquire_token_by_refresh_token(cached["refresh_token"], scopes=scopes)
        if "access_token" in result:
            _token_cache[user_identifier] = _augment_with_expiry(result)
            return result["access_token"], result

    raise RuntimeError("No valid Azure token; user must sign in.")


# Internals
def _augment_with_expiry(token_dict: Dict) -> Dict:
    """
    MSAL returns `expires_in` (seconds). Convert to absolute epoch for quick check.
    """
    token_dict["expires_at"] = int(time.time()) + int(token_dict.get("expires_in", 3600))
    return token_dict
