# jordi-sso
Jordi SSO with Snowflake &amp; Azure AD

### 1. Microsoft Azure Integration & Authentication
- Set up OAuth callback scaffolding for Chainlit with Microsoft Entra ID (Azure AD) as identity provider.
- Planned user session handling and token management with placeholders for secure OAuth environment variables.
- Handled user session initialization with user email extraction for contextual personalization.
- Addressed and temporarily commented out OAuth due to missing environment configs for smoother local dev.

### 2. Snowflake Authentication via ExternalBrowser (SSO)
- Designed Snowflake connection leveraging the externalbrowser authenticator for seamless SSO experience.
- Developed a secure pattern to fetch Snowflake credentials per user from a PostgreSQL-backed credential store.
- Created a Streamlit-based Snowflake login UI to collect and validate Snowflake user credentials, then securely store them in PostgreSQL.
- Configured Chainlit backend to conditionally enable Snowflake SQL tools based on user toggle and credential presence.
- Handled Snowflake setup failures gracefully by showing a redirect button to the Snowflake login UI in Chainlit.

### 3. Chainlit Code Improvements
- Modularized user session lifecycle with event handlers:
- @cl.on_chat_start to initialize models, tools, and memory.
- @cl.on_chat_resume for restoring conversation history and state.
- @cl.on_settings_update to dynamically update LLM models and toggle Snowflake tools.

### 4. Integrated TavilySearchResults as a default search tool.
- Added multi-model support with GPT-4o, GPT-4.1, GPT-4.1-nano, and GPT-4.1-mini selections.
- Enhanced chat input to handle multi-file PDF uploads, extracting content and injecting into conversation memory.
- Introduced streaming response handling with a custom LangChain callback to provide token-by-token feedback.
- Improved error handling and logging for Snowflake setup and credential retrieval.