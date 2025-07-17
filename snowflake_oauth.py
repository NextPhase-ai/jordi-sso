import streamlit as st
import snowflake.connector
from sqlalchemy import create_engine
from sqlalchemy.sql import text
import msal
import os
from dotenv import load_dotenv
load_dotenv()

# MSAL Configuration
CLIENT_ID     = os.getenv("AZURE_CLIENT_ID")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")
AUTHORITY     = os.getenv("AZURE_AUTHORITY")
REDIRECT_URI  = os.getenv("AZURE_REDIRECT_URI")
SCOPE         = ["openid", "profile", "email"]

msal_app = msal.ConfidentialClientApplication(
    CLIENT_ID,
    client_credential=CLIENT_SECRET,
    authority=AUTHORITY
)

# Set page config for wide layout
st.set_page_config(page_title="Snowflake Login", layout="wide", page_icon="public/favicon.png")

# Custom CSS for styling
st.markdown("""
<style>
    /* Import Google Font */
    @import url('https://fonts.googleapis.com/css2?family=Questrial&display=swap');

    /* Hide Streamlit default elements */
    #MainMenu {visibility: hidden;}
    .stDeployButton {display:none;}
    footer {visibility: hidden;}
    .stApp > header {visibility: hidden;}

    /* Remove default padding and margins */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        padding-left: 1rem;
        padding-right: 1rem;
        max-width: 100%;
    }

    /* Style for the right column background */
    .right-column {
        background-color: #a2c2ce;
        padding: 14rem 12rem;
        border-radius: 0;
        text-align: left;
        min-height: 100vh;
        margin: -4rem -1rem -2rem 0;
        display: flex;
        align-items: center;
        justify-content: flex-start;
    }

    .brand-text {
        font-size: 5rem;
        font-weight: bold;
        color: #586b71;
        letter-spacing: 2px;
        line-height: 1.4;
        font-family: 'Questrial', sans-serif;
        text-align: left;
    }

    .login-form {
        background-color: #f8f9fa;
        padding: 2rem;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        margin-top: 2rem;
        max-width: 400px;
        margin-left: auto;
        margin-right: auto;
    }

    .login-title {
        text-align: center;
        color: #333;
        margin-bottom: 1rem;
        font-size: 2rem;
        font-weight: 600;
    }

    .stTextInput > div > div > input {
        border-radius: 5px;
        border: 2px solid #ddd;
        padding: 0.75rem;
        font-size: 1rem;
    }

    .stButton > button {
        width: 100%;
        background-color: #81a5b3;
        color: white;
        border: none;
        padding: 0.75rem;
        font-size: 1rem;
        font-weight: 600;
        border-radius: 5px;
        margin-top: 1rem;
    }

    .stButton > button:hover {
        background-color: #8db4c2;
    }

    /* Add some spacing to columns */
    .left-column {
        padding: 2rem 1rem;
    }
</style>
""", unsafe_allow_html=True)

# Extract email_id from query parameters
query_params = st.query_params
email_id = query_params.get("email", "harshil_gandhi@nextphase.ai")

# Create two columns for split layout
left_col, right_col = st.columns([1, 1])

with left_col:
    st.markdown('<div class="left-column">', unsafe_allow_html=True)
    img_col, _, = st.columns([0.25, 0.25])
    with img_col:
        st.image("public/jordi.png", use_container_width=True)  # Display the logo image

    # Login form container
    _, form_col, _, = st.columns([0.25, 0.5, 0.25])
    with form_col:
        # Add some top spacing
        st.markdown('<div style="margin-top: 4rem;"></div>', unsafe_allow_html=True)

        st.markdown(f'<h2 class="login-title">❄️ Snowflake Login</h2>', unsafe_allow_html=True)
        if email_id != '':
            st.markdown(f'<p style="text-align: center; color: #666; margin-bottom: 1.5rem;"> {email_id}</p>',
                        unsafe_allow_html=True)

        username = st.text_input("Username", placeholder="Enter your username", label_visibility="collapsed")
        password = st.text_input("Password", type="password", placeholder="Enter your password",
                                 label_visibility="collapsed")

        if st.button("Login with Snowflake", type="tertiary", icon=':material/mode_cool:'):
            # Snowflake connection parameters
            snowflake_account = "KNYNISV-SJA93363"
            database = "NEO"
            schema_name = "PUBLIC"

            try:
                # Connect to Snowflake
                conn = snowflake.connector.connect(
                    user=username,
                    password=password,
                    account=snowflake_account,
                    database=database,
                    schema=schema_name
                )

                # Connect to PostgreSQL and store credentials
                pg_engine = create_engine("postgresql+psycopg2://postgres:nextphaseai!!!@localhost:5432/snowflake_auth")
                with pg_engine.connect() as pg_conn:
                    # Delete existing entry with the same email_id
                    pg_conn.execute(
                        text("DELETE FROM users WHERE email_id = :email_id"),
                        {"email_id": email_id}
                    )
                    # Insert new entry
                    pg_conn.execute(
                        text(
                            "INSERT INTO users (email_id, username, password) VALUES (:email_id, :username, :password)"),
                        {"email_id": email_id, "username": username, "password": password}
                    )
                    pg_conn.commit()  # Commit both operations

                # Display success message
                st.success("Login successful and data stored!")

                # Close Snowflake connection
                conn.close()

                # Redirect back to the main application
                redirect_url = "https://jordi.nextphase.ai/"
                st.markdown(f"""
                    <meta http-equiv="refresh" content="0; url={redirect_url}" />
                """, unsafe_allow_html=True)

            except snowflake.connector.Error as e:
                # Handle Snowflake authentication errors
                st.error(f"Login failed: {e}")
            except Exception as e:
                # Handle other exceptions (e.g., PostgreSQL issues)
                st.error(f"An error occurred: {e}")

        # Login form container - end
        st.markdown('</div>', unsafe_allow_html=True)  # Close login-form
        st.markdown('</div>', unsafe_allow_html=True)  # Close left-column

with right_col:
    st.markdown("""
    <div class="right-column">
        <div class="brand-text">
            JORDAN <br> PARK <br> TRUST <br> COMPANY
        </div>
    </div>
    """, unsafe_allow_html=True)

'''
CREATE TABLE users (
    email_id VARCHAR(255) PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    password VARCHAR(255) NOT NULL
);
'''