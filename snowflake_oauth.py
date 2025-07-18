import streamlit as st
import snowflake.connector
from langchain_community.agent_toolkits.gmail.toolkit import SCOPES
from sqlalchemy import create_engine
from sqlalchemy.sql import text
import msal
import os
import time
from dotenv import load_dotenv

load_dotenv()

# ===================================
# MSAL Configuration
# ===================================
CLIENT_ID     = os.getenv("AZURE_CLIENT_ID")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")
AUTHORITY     = os.getenv("AZURE_AUTHORITY")
REDIRECT_URI  = os.getenv("AZURE_REDIRECT_URI")
SCOPE = ["User.Read"]

msal_app = msal.ConfidentialClientApplication(
    CLIENT_ID,
    client_credential=CLIENT_SECRET,
    authority=AUTHORITY
)

# ===================================
# Handle OAuth Callback
# ===================================
query_params = st.experimental_get_query_params()
if "code" in query_params:
    code = query_params["code"][0]
    result = msal_app.acquire_token_by_authorization_code(
        scopes=SCOPE,
        redirect_uri=REDIRECT_URI,
        code=code
    )
    if "id_token_claims" in result:
        # ✅ CHANGE: Store user email from Azure ID token into session state
        st.session_state["user_email"] = result["id_token_claims"]["email"]
    else:
        st.error("Azure login failed: " + result.get("error_description", "Unknown error"))
        auth_url = msal_app.get_authorization_request_url(scopes=SCOPE, redirect_uri=REDIRECT_URI)
        st.markdown(f"<a href='{auth_url}'>Retry Login</a>", unsafe_allow_html=True)
        st.stop()

# ===================================
# Trigger Login if Session Missing
# ===================================
if "user_email" not in st.session_state:
    auth_url = msal_app.get_authorization_request_url(scopes=SCOPE, redirect_uri=REDIRECT_URI)
    st.markdown(f"Please login to Snowflake using your Azure account. <a href='{auth_url}'>Login</a>")
    st.stop()

# ✅ CHANGE: Enforce session-based identity only (no fallback input)
email_id = st.session_state.get("user_email")

# 🛡️ ADDITION: Guard if email missing after supposed login
if not email_id:
    st.error("Session expired or invalid. Please login again.")
    auth_url = msal_app.get_authorization_request_url(scopes=SCOPE, redirect_uri=REDIRECT_URI)
    st.markdown(f"<a href='{auth_url}'>Login Again</a>", unsafe_allow_html=True)
    st.stop()

# ===================================
# Streamlit UI Setup
# ===================================
st.set_page_config(page_title="Snowflake Login", layout="wide", page_icon="public/favicon.png")

# Custom CSS
st.markdown("""...""", unsafe_allow_html=True)  # Keep unchanged

# Layout
left_col, right_col = st.columns([1, 1])
with left_col:
    st.markdown('<div class="left-column">', unsafe_allow_html=True)

    img_col, _ = st.columns([0.25, 0.25])
    with img_col:
        st.image("public/jordi.png", use_container_width=True)

    _, form_col, _ = st.columns([0.25, 0.5, 0.25])
    with form_col:
        st.markdown('<div style="margin-top: 4rem;"></div>', unsafe_allow_html=True)
        st.markdown(f'<h2 class="login-title">❄️ Snowflake Login</h2>', unsafe_allow_html=True)

        if email_id:
            st.markdown(f'<p style="text-align: center; color: #666; margin-bottom: 1.5rem;">{email_id}</p>',
                        unsafe_allow_html=True)

        # Snowflake login form
        username = st.text_input("Username", placeholder="Enter your username", label_visibility="collapsed")
        password = st.text_input("Password", type="password", placeholder="Enter your password",
                                 label_visibility="collapsed")

        if st.button("Login with Snowflake", type="tertiary", icon=':material/mode_cool:'):
            snowflake_account = os.getenv("SNOWFLAKE_ACCOUNT", "KNYNISV-SJA93363")
            database = os.getenv("SNOWFLAKE_DB", "NEO")
            schema_name = os.getenv("SNOWFLAKE_SCHEMA", "PUBLIC")

            try:
                # Snowflake Connection
                conn = snowflake.connector.connect(
                    user=username,
                    password=password,
                    account=snowflake_account,
                    database=database,
                    schema=schema_name
                )

                # PostgreSQL Insertion
                pg_engine = create_engine(os.getenv("POSTGRES_URL", "postgresql+psycopg2://postgres:nextphaseai!!!@localhost:5432/snowflake_auth"))
                with pg_engine.connect() as pg_conn:
                    pg_conn.execute(text("DELETE FROM users WHERE email_id = :email_id"), {"email_id": email_id})
                    pg_conn.execute(
                        text("INSERT INTO users (email_id, username, password) VALUES (:email_id, :username, :password)"),
                        {"email_id": email_id, "username": username, "password": password}
                    )
                    pg_conn.commit()

                st.success("Login successful and credentials stored!")

                # Redirect
                st.info("Redirecting to Jordi...")
                time.sleep(1.5)
                redirect_url = "https://jordi.nextphase.ai/"
                st.markdown(f"""
                    <meta http-equiv="refresh" content="0; url={redirect_url}" />
                """, unsafe_allow_html=True)

            except snowflake.connector.Error as e:
                st.error(f"Snowflake login failed: {e}")
            except Exception as e:
                st.error(f"Error: {e}")

        st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ===================================
# Branding Right Panel
# ===================================
with right_col:
    st.markdown("""
    <div class="right-column">
        <div class="brand-text">
            JORDAN <br> PARK <br> TRUST <br> COMPANY
        </div>
    </div>
    """, unsafe_allow_html=True)

# ===================================
# Optional Debug Panel (for dev only)
# ===================================
with st.expander("🔍 Debug Info"):
    st.write("User Email:", email_id)
    st.write("Query Params:", query_params)
    st.write("Session State:", st.session_state)

# ===================================
# Schema (for reference)
# ===================================
'''
CREATE TABLE users (
    email_id VARCHAR(255) PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    password VARCHAR(255) NOT NULL
);
'''