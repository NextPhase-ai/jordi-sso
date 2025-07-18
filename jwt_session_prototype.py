import streamlit as st
import jwt
import datetime
from urllib.parse import urlencode, urlparse, parse_qs

# ==============================
# 🔐 JWT Configuration
# ==============================
JWT_SECRET = "super-secret-key"  # In prod, store in environment variable
JWT_ALGORITHM = "HS256"
JWT_EXP_MINUTES = 15  # Token valid for 15 minutes

# ==============================
# 🔁 Helper Functions
# ==============================
def generate_jwt(user_email: str) -> str:
    payload = {
        "email": user_email,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=JWT_EXP_MINUTES),
        "iat": datetime.datetime.utcnow()
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token

def decode_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        st.warning("Token has expired. Please login again.")
    except jwt.InvalidTokenError:
        st.error("Invalid token. Please login again.")
    return None

def update_query_params(token: str):
    st.experimental_set_query_params(token=token)

# ==============================
# 🌐 Extract Token from URL
# ==============================
query_params = st.experimental_get_query_params()
token = query_params.get("token", [None])[0]

# ==============================
# 🧪 Streamlit UI
# ==============================
st.set_page_config(page_title="JWT Session Prototype", layout="centered")

st.title("🔐 JWT Session Prototype")

if not token:
    st.info("🔓 Simulate login to generate a JWT token.")
    if st.button("🔐 Simulate Login"):
        test_email = "user@nextphase.ai"
        new_token = generate_jwt(test_email)
        update_query_params(new_token)
        st.rerun()
else:
    decoded = decode_jwt(token)
    if decoded:
        st.success("✅ Token is valid!")
        st.write("**Decoded Email:**", decoded["email"])
        st.write("**Token Expires At:**", datetime.datetime.fromtimestamp(decoded["exp"]))
        if st.button("🚪 Logout"):
            st.experimental_set_query_params()  # Clear token from URL
            st.rerun()
    else:
        st.error("⚠️ Invalid or expired session.")
        if st.button("🔁 Try Login Again"):
            st.experimental_set_query_params()
            st.rerun()

# ==============================
# 🔍 Debug Panel (Optional)
# ==============================
with st.expander("🛠 Debug Info"):
    st.write("Query Params:", query_params)
    st.write("Raw Token:", token)
