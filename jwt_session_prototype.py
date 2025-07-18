# jwt_session_prototype.py

import streamlit as st
import jwt
import time
import os
from urllib.parse import quote_plus
from dotenv import load_dotenv

# 🔐 Load secret from .env or fallback
load_dotenv()
SECRET_KEY = os.getenv("JWT_SECRET", "my_secret_key")

# 🧭 App layout
st.set_page_config(page_title="JWT Token Generator", layout="centered")
st.title("🔐 Generate JWT Token for Chainlit")

# 📩 Email input
email = st.text_input("Enter your email")

# 🕒 Time-to-live selector
ttl_minutes = st.slider("Token TTL (in minutes)", 5, 120, 30)

# 🚀 Generate token
if st.button("Generate Token"):
    iat = int(time.time())
    exp = iat + ttl_minutes * 60
    payload = {
        "email": email,
        "iat": iat,
        "exp": exp
    }

    try:
        token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
        token_str = token if isinstance(token, str) else token.decode("utf-8")
        url_token = quote_plus(token_str)

        st.success("✅ JWT Token Generated Successfully!")
        st.code(token_str, language="text")

        chainlit_url = f"http://localhost:8000/?token={url_token}"
        st.markdown(f"🔗 [Open Chainlit with Token]({chainlit_url})")
        st.text("Paste this token in Chainlit if not redirected automatically.")
    except Exception as e:
        st.error(f"Error generating JWT: {str(e)}")
