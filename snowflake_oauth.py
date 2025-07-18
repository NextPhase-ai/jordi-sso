import streamlit as st
import snowflake.connector
from sqlalchemy import create_engine, text
import msal
import os
import time
from urllib.parse import quote
from dotenv import load_dotenv

from jwt_utils import JWTManager

# ==========================
# Load environment variables
# ==========================
load_dotenv()

CLIENT_ID     = os.getenv("AZURE_CLIENT_ID")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")
AUTHORITY     = os.getenv("AZURE_AUTHORITY")
REDIRECT_URI  = os.getenv("AZURE_REDIRECT_URI")
SCOPE         = ["User.Read"]  # For POC: no admin consent needed

# Once admin consent and full SSO approved
# SCOPE = [
#     "openid",          # for ID token
#     "offline_access",  # for refresh tokens (not applicable in Streamlit POC)
#     "User.Read",       # basic profile info from Microsoft Graph
# ]

JWT_SECRET = os.getenv("JWT_SECRET")
jwt_manager = JWTManager(secret_key=JWT_SECRET)

def get_msal_app():
    return msal.ConfidentialClientApplication(
        CLIENT_ID,
        client_credential=CLIENT_SECRET,
        authority=AUTHORITY
    )

# ==========================
# OAuth Callback Handling
# ==========================
query_params = st.experimental_get_query_params()
if "code" in query_params:
    code = query_params["code"][0]
    msal_app = get_msal_app()

    result = msal_app.acquire_token_by_authorization_code(
        scopes=SCOPE,
        redirect_uri=REDIRECT_URI,
        code=code
    )
    if "id_token_claims" in result:
        user_email = result["id_token_claims"].get("email")
        if user_email:
            token = jwt_manager.create_token(email=user_email)
            st.session_state["jwt_token"] = token
            st.session_state["email_id"] = user_email
            st.experimental_rerun()
        else:
            st.error("Azure login failed: Email claim missing.")
            st.stop()
    else:
        st.error("Azure login failed: " + result.get("error_description", "Unknown error"))
        st.stop()

# ==========================
# JWT Session Check
# ==========================
token = st.session_state.get("jwt_token")
if not token:
    msal_app = msal.ConfidentialClientApplication(
        CLIENT_ID,
        client_credential=CLIENT_SECRET,
        authority=AUTHORITY
    )
    auth_url = msal_app.get_authorization_request_url(scopes=SCOPE, redirect_uri=REDIRECT_URI)
    st.markdown(f"<a href='{auth_url}'>Please login using Microsoft Entra ID</a>", unsafe_allow_html=True)
    st.stop()

payload = jwt_manager.decode_token(token)
if payload is None:
    st.session_state.pop("jwt_token", None)
    msal_app = msal.ConfidentialClientApplication(
        CLIENT_ID,
        client_credential=CLIENT_SECRET,
        authority=AUTHORITY
    )
    auth_url = msal_app.get_authorization_request_url(scopes=SCOPE, redirect_uri=REDIRECT_URI)
    st.error("Session expired or invalid. Please login again.")
    st.markdown(f"<a href='{auth_url}'>Login Again</a>", unsafe_allow_html=True)
    st.stop()

email_id = payload.get("email")
if not email_id:
    st.error("Email claim missing in token payload.")
    st.stop()

st.session_state["email_id"] = email_id

# ==========================
# UI Layout
# ==========================
st.set_page_config(page_title="Snowflake Login", layout="wide", page_icon="public/favicon.png")

left_col, right_col = st.columns([1, 1])

with left_col:
    st.markdown(f'<p style="text-align: center; color: #666; margin-bottom: 1.5rem;">{email_id}</p>', unsafe_allow_html=True)

    username = st.text_input("Username", placeholder="Enter your username", label_visibility="collapsed")
    password = st.text_input("Password", type="password", placeholder="Enter your password", label_visibility="collapsed")

    if st.button("Login with Snowflake", type="tertiary", icon=":material/mode_cool:"):
        snowflake_account = os.getenv("SNOWFLAKE_ACCOUNT", "KNYNISV-SJA93363")
        database = os.getenv("SNOWFLAKE_DB", "NEO")
        schema_name = os.getenv("SNOWFLAKE_SCHEMA", "PUBLIC")

        try:
            # Validate Snowflake credentials
            conn = snowflake.connector.connect(
                user=username,
                password=password,
                account=snowflake_account,
                database=database,
                schema=schema_name
            )

            # Save credentials to PostgreSQL
            pg_engine = create_engine(os.getenv("POSTGRES_URL", "postgresql+psycopg2://postgres:nextphaseai!!!@localhost:5432/snowflake_auth"))
            with pg_engine.connect() as pg_conn:
                pg_conn.execute(text("DELETE FROM users WHERE email_id = :email_id"), {"email_id": email_id})
                pg_conn.execute(
                    text("INSERT INTO users (email_id, username, password) VALUES (:email_id, :username, :password)"),
                    {"email_id": email_id, "username": username, "password": password}
                )
                pg_conn.commit()

            # Redirect to Chainlit with encoded JWT
            st.success("Login successful! Redirecting to Jordi Assistant...")
            time.sleep(1.5)
            encoded_token = quote(token)
            redirect_url = f"https://jordi.nextphase.ai/?token={encoded_token}"
            st.markdown(f'<meta http-equiv="refresh" content="0; url={redirect_url}" />', unsafe_allow_html=True)

        except snowflake.connector.Error as e:
            st.error(f"Snowflake login failed: {e}")
        except Exception as e:
            st.error(f"Unexpected error: {e}")

with right_col:
    st.markdown("""
    <div class="right-column">
        <div class="brand-text">
            JORDAN <br> PARK <br> TRUST <br> COMPANY
        </div>
    </div>
    """, unsafe_allow_html=True)

# ==========================
# Optional: Logout
# ==========================
with st.sidebar:
    if st.button("Logout"):
        st.session_state.pop("jwt_token", None)
        st.experimental_rerun()

# ==========================
# Dev Debug Panel
# ==========================
with st.expander("Debug Info"):
    st.write("User Email:", email_id)
    st.write("Token Payload:", payload)
    st.write("Raw Query Params:", query_params)
    st.write("Session State:", st.session_state)

# ==========================
# PostgreSQL Reference
# ==========================
'''
CREATE TABLE users (
    email_id VARCHAR(255) PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    password VARCHAR(255) NOT NULL
);
'''