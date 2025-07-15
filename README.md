# Jordi – SSO with Azure AD & Snowflake OAuth

This repo is a **minimal, self‑contained prototype** that adds Azure Active Directory Single Sign‑On to the Jordi (Chainlit + LangChain) agent and uses the resulting Access Token to log into **Snowflake** via an **external OAuth security integration**.

> **Why a separate repo?**  
> Keeps sensitive auth logic isolated, simplifies code review, and provides a reusable blueprint for future projects.

---

## 📋 Feature Roadmap
| Step | Description |
|---|-------------|
| 1 | Azure App Registration |
| 2 | Chainlit OAuth callback with MSAL |
| 3 | Token storage in user session |
| 4 | Snowflake connection via Access Token |
| 5 | Refresh‑token flow |
| 6 | Snowflake security integration docs |
| 7 | Remove plaintext creds |

---

## 🚀 Quick‑start

```bash
# 0. Clone & cd
git clone https://github.com/<org>/jordi-sso.git
cd jordi-sso

# 1. Create a virtual env
python -m venv .venv && source .venv/bin/activate

# 2. Install deps
pip install -r requirements.txt

# 3. Copy env template and fill in secrets
cp .env.example .env
nano .env   # or your favorite editor

# 4. Run the Chainlit app
chainlit run app.py
