import streamlit as st
import snowflake.connector
from sqlalchemy import create_engine
from sqlalchemy.sql import text
import msal
import os
import time
from dotenv import load_dotenv

from jwt_utils import JWTManager

# ===================================
# Load environment variables
# ===================================
load_dotenv()

# ===================================
# MSAL Configuration
# ===================================
CLIENT_ID     = os.getenv("AZURE_CLIENT_ID")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")
AUTHORITY     = os.getenv("AZURE_AUTHORITY")
REDIRECT_URI  = os.getenv("AZURE_REDIRECT_URI")
SCOPE = ["User.Read"]

# Once admin consent and full SSO approved
# SCOPE = [
#     "openid",          # for ID token
#     "offline_access",  # for refresh tokens (not applicable in Streamlit POC)
#     "User.Read",       # basic profile info from Microsoft Graph
# ]

# ===================================
# JWT Setup
# ===================================
JWT_SECRET = os.getenv("JWT_SECRET")
jwt_manager = JWTManager(secret_key=JWT_SECRET)

# ===================================
# Handle OAuth Callback and JWT creation
# ===================================
query_params = st.experimental_get_query_params()
if "code" in query_params:
    code = query_params["code"][0]
    msal_app = msal.ConfidentialClientApplication(
        CLIENT_ID,
        client_credential=CLIENT_SECRET,
        authority=AUTHORITY
    )
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
            st.experimental_rerun()
        else:
            st.error("Azure login failed: Email claim missing.")
            st.stop()
    else:
        st.error("Azure login failed: " + result.get("error_description", "Unknown error"))
        st.stop()

# ===================================
# Validate JWT token in session state
# ===================================
token = st.session_state.get("jwt_token")
if not token:
    msal_app = msal.ConfidentialClientApplication(
        CLIENT_ID,
        client_credential=CLIENT_SECRET,
        authority=AUTHORITY
    )
    auth_url = msal_app.get_authorization_request_url(scopes=SCOPE, redirect_uri=REDIRECT_URI)
    st.markdown(f"🔐 <a href='{auth_url}'>Please login using Microsoft Entra ID</a>", unsafe_allow_html=True)
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

# ===================================
# Streamlit UI Setup
# ===================================
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
            # Attempt Snowflake login
            conn = snowflake.connector.connect(
                user=username,
                password=password,
                account=snowflake_account,
                database=database,
                schema=schema_name
            )

            # Store user creds in PostgreSQL
            pg_engine = create_engine(os.getenv("POSTGRES_URL", "postgresql+psycopg2://postgres:nextphaseai!!!@localhost:5432/snowflake_auth"))
            with pg_engine.connect() as pg_conn:
                pg_conn.execute(text("DELETE FROM users WHERE email_id = :email_id"), {"email_id": email_id})
                pg_conn.execute(
                    text("INSERT INTO users (email_id, username, password) VALUES (:email_id, :username, :password)"),
                    {"email_id": email_id, "username": username, "password": password}
                )
                pg_conn.commit()

            st.success("Login successful! Redirecting to Jordi Assistant...")
            time.sleep(1.5)

            # Final Chainlit redirect with JWT
            redirect_url = f"https://jordi.nextphase.ai/?token={token}"
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

# ===================================
# Debug Panel (Dev-Only)
# ===================================
with st.expander("🛠 Debug Info"):
    st.write("User Email:", email_id)
    st.write("Session Token Payload:", payload)
    st.write("Raw Query Params:", query_params)
    st.write("Session State:", st.session_state)

# ===================================
# Reference: PostgreSQL Table Schema
# ===================================
'''
CREATE TABLE users (
    email_id VARCHAR(255) PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    password VARCHAR(255) NOT NULL
);
'''
