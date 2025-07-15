import json
import chainlit as cl
from typing import Dict, Optional

import sys
import os
sys.path.append(os.path.abspath(os.path.dirname(__file__) + "/.."))


# Import the helpers you just created
#from .azure_auth import ConfidentialClientApplication, _build_app, _augment_with_expiry

from snowflake_oauth.azure_auth import ConfidentialClientApplication, _build_app, _augment_with_expiry


# ----------------------------------------------------------------------
# OAuth callback – called automatically when Azure AD redirects here
# ----------------------------------------------------------------------
@cl.oauth_callback
def oauth_callback(
    provider_id: str,             # "azure-ad" if using Chainlit's built‑in provider router
    token: str,                   # Raw JWT or opaque token sent by IdP
    raw_user_data: Dict[str, str],
    default_user: cl.User,
) -> Optional[cl.User]:
    """
    1. Parse the `raw_user_data` that Chainlit receives from Azure AD.
    2. Capture email / object ID for session identity.
    3. Persist the full token bundle (access + refresh + id) in cl.user_session
       so other hooks (e.g., snowflake_setup) can grab it.
    4. Gracefully handle failures.
    """
    try:
        # ------------------------------------------------------------------
        # 1️⃣  Identify the user
        # ------------------------------------------------------------------
        # Azure AD often returns both 'email' and 'preferred_username'
        email = (
            raw_user_data.get("email")
            or raw_user_data.get("preferred_username")
            or raw_user_data.get("upn")                # fallback
        )
        if not email:
            raise ValueError("Email claim missing from Azure AD response")

        email = email.lower()  # normalize

        # ------------------------------------------------------------------
        # 2️⃣  Parse the token string Chainlit gives us
        # ------------------------------------------------------------------
        # Chainlit v0.7+ forwards `token` as a JSON string when using OAuth2
        # flows.  We'll try to decode; if it fails, assume it's an access token
        try:
            token_dict = json.loads(token)
            # Expect keys: access_token, id_token, refresh_token, expires_in
        except json.JSONDecodeError:
            token_dict = {"access_token": token}

        # Ensure expiry metadata exists (for later silent refresh)
        if "expires_at" not in token_dict:
            token_dict = _augment_with_expiry(token_dict)

        # ------------------------------------------------------------------
        # 3️⃣  Store in Chainlit session for downstream use
        # ------------------------------------------------------------------
        cl.user_session.set("azure_token", token_dict)
        cl.user_session.set("user_email", email)

        # ------------------------------------------------------------------
        # 4️⃣  Return a custom cl.User (optional; default_user is fine too)
        # ------------------------------------------------------------------
        # Populate display_name so Chainlit’s UI shows the user’s address
        return cl.User(identifier=email, metadata={"email": email})

    except Exception as err:
        # ------------------------------------------------------------------
        # 🔥 Graceful fallback – show login button if anything breaks
        # ------------------------------------------------------------------
        print("[OAuthCallback] Azure SSO error:", err)

        login_element = cl.CustomElement(
            name="RedirectButton",
            props={
                "buttonText": "Sign in with Microsoft",
                "url": "/login/azure-ad",  # Chainlit’s login endpoint
                "variant": "default",
            },
        )
        # Inform user in the UI
        cl.run_sync(
            cl.Message(
                content="### Microsoft sign‑in failed. Please click below to try again.",
                elements=[login_element],
            ).send()
        )
        # Returning None keeps the anonymous user state
        return None
