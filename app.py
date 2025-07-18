import json
import PyPDF2
import os
from typing import Dict, Optional

import chainlit as cl
from chainlit.input_widget import Select, Switch
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.types import ThreadDict
from langchain.schema import AIMessage, HumanMessage, SystemMessage
from langchain.schema.runnable.config import RunnableConfig
from langchain.callbacks.base import BaseCallbackHandler
from langchain.agents import AgentType, initialize_agent

from langchain_community.chat_models import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_community.tools.tavily_search import TavilySearchResults

from langchain.memory import ConversationBufferMemory

from sqlalchemy import create_engine, text

from jwt_utils import JWTManager  # JWT helper module, must be in your PYTHONPATH or project

# Initialize JWTManager with your secret
JWT_SECRET = os.getenv("JWT_SECRET")
jwt_manager = JWTManager(secret_key=JWT_SECRET)

# ----------- OAuth / JWT AUTHENTICATION -------------

@cl.on_chat_start
async def on_chat_start():
    # Step 1: Extract JWT token from query params
    query_params = cl.get_request_query_params()
    token = None
    if "token" in query_params:
        token = query_params["token"][0]

    if not token:
        await cl.Message(content="❌ Authentication token missing. Please login via Streamlit.").send()
        cl.user_session.set("user", None)
        return

    # Step 2: Validate token and extract email
    payload = jwt_manager.decode_token(token)
    if payload is None:
        await cl.Message(content="❌ Invalid or expired token. Please login again.").send()
        cl.user_session.set("user", None)
        return

    email = payload.get("email")
    if not email:
        await cl.Message(content="❌ Email claim missing in token.").send()
        cl.user_session.set("user", None)
        return

    # Step 3: Setup authenticated user session
    user = cl.User(identifier=email)
    cl.user_session.set("user", user)

    email_id = email.lower()

    # Step 4: Initialize conversation memory and UI settings
    cl.user_session.set("memory", ConversationBufferMemory(memory_key="chat_history", return_messages=True))

    settings = await cl.ChatSettings([
        Select(
            id="Model",
            label="Base Model",
            values=["GPT-4o", "GPT-4.1", "GPT-4.1-nano", "GPT-4.1 mini"],
            initial_index=cl.user_session.get("model_index", 0),
        ),
        Switch(
            id="Enable Snowflake",
            label="enable_snowflake_agent",
            initial=True,
        )
    ]).send()

    # Step 5: Configure LLM based on user settings
    if settings['Model'] == "GPT-4.1":
        llm = ChatOpenAI(temperature=0.1, model="gpt-4.1-2025-04-14", streaming=True, response_format={"type": "text"})
    elif settings['Model'] == "GPT-4.1-nano":
        llm = ChatOpenAI(temperature=0.1, model="gpt-4.1-nano-2025-04-14", streaming=True, response_format={"type": "text"})
    elif settings['Model'] == "GPT-4.1 mini":
        llm = ChatOpenAI(temperature=0.2, model="gpt-4.1-mini-2025-04-14", streaming=True, response_format={"type": "text"})
    else:
        llm = ChatOpenAI(temperature=0.1, model="gpt-4o", streaming=True, response_format={"type": "text"})

    cl.user_session.set("llm", llm)
    cl.user_session.set("model_index", ["GPT-4o", "GPT-4.1", "GPT-4.1-nano", "GPT-4.1 mini"].index(settings['Model']))
    print(f'llm set to {settings["Model"]}')

    # Step 6: Setup Search Tool
    search_tool = TavilySearchResults(max_results=4)
    cl.user_session.set("search_tool", search_tool)

    cl.user_session.set("CUSTOM_PREFIX", get_custom_prefix())

    # Step 7: Snowflake setup if enabled
    if settings['Enable Snowflake']:
        SQL_tools = await snowflake_setup()
        if SQL_tools:
            cl.user_session.set("SQL_tools", SQL_tools)
        else:
            # Notify user and disable Snowflake toggle if setup failed
            await cl.Message(content="⚠️ Snowflake credentials missing or setup failed. Snowflake agent disabled.").send()
            settings['Enable Snowflake'] = False

# ---------- Remaining your handlers (on_chat_resume, on_settings_update) -------------

@cl.on_chat_resume
async def on_chat_resume(thread: ThreadDict):
    email_id = cl.user_session.get("user").identifier.lower()
    memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

    root_messages = [m for m in thread["steps"] if m["parentId"] is None]
    for message in root_messages:
        if message["type"] == "user_message":
            memory.chat_memory.add_user_message(message["output"])
        else:
            memory.chat_memory.add_ai_message(message["output"])
    cl.user_session.set("memory", memory)

    settings = await cl.ChatSettings([
        Select(
            id="Model",
            label="Base Model",
            values=["GPT-4o", "GPT-4.1", "GPT-4.1-nano", "GPT-4.1 mini"],
            initial_index=cl.user_session.get("model_index", 0),
        ),
        Switch(
            id="Enable Snowflake",
            label="enable_snowflake_agent",
            initial=True
        )
    ]).send()

    if settings['Model'] == "GPT-4.1":
        llm = ChatOpenAI(temperature=0.1, model="gpt-4.1-2025-04-14", streaming=True, response_format={"type": "text"})
    elif settings['Model'] == "GPT-4.1-nano":
        llm = ChatOpenAI(temperature=0.1, model="gpt-4.1-nano-2025-04-14", streaming=True, response_format={"type": "text"})
    elif settings['Model'] == "GPT-4.1 mini":
        llm = ChatOpenAI(temperature=0.2, model="gpt-4.1-mini-2025-04-14", streaming=True, response_format={"type": "text"})
    else:
        llm = ChatOpenAI(temperature=0.1, model="gpt-4o", streaming=True, response_format={"type": "text"})

    cl.user_session.set("llm", llm)
    cl.user_session.set("model_index", ["GPT-4o", "GPT-4.1", "GPT-4.1-nano", "GPT-4.1 mini"].index(settings['Model']))
    print(f'llm set to {settings["Model"]}')

    search_tool = TavilySearchResults(max_results=4)
    cl.user_session.set("search_tool", search_tool)

    cl.user_session.set("CUSTOM_PREFIX", get_custom_prefix())

    if settings['Enable Snowflake']:
        SQL_tools = await snowflake_setup()
        cl.user_session.set("SQL_tools", SQL_tools)

@cl.on_settings_update
async def setup_agent(settings):
    print("on_settings_update", settings)
    if settings['Model'] == "GPT-4.1":
        llm = ChatOpenAI(temperature=0.2, model="gpt-4.1-2025-04-14", streaming=True, response_format={"type": "text"})
        cl.user_session.set("model_index", 1)
    elif settings['Model'] == "GPT-4.1-nano":
        llm = ChatOpenAI(temperature=0.2, model="gpt-4.1-nano-2025-04-14", streaming=True, response_format={"type": "text"})
        cl.user_session.set("model_index", 2)
    elif settings['Model'] == "GPT-4.1 mini":
        llm = ChatOpenAI(temperature=0.2, model="gpt-4.1-mini-2025-04-14", streaming=True, response_format={"type": "text"})
        cl.user_session.set("model_index", 3)
    else:
        llm = ChatOpenAI(temperature=0.2, model="gpt-4o", streaming=True, response_format={"type": "text"})
        cl.user_session.set("model_index", 0)

    cl.user_session.set("llm", llm)
    print(f'llm set to {settings["Model"]}, index {cl.user_session.get("model_index")}')

    if settings['Enable Snowflake']:
        SQL_tools = await snowflake_setup()
        if SQL_tools:
            cl.user_session.set("SQL_tools", SQL_tools)
        else:
            settings['Enable Snowflake'] = False

# --------- Utility functions and your existing helpers (get_custom_prefix, get_sf_credentials, snowflake_setup, read_pdf_contents) ---------

def get_custom_prefix():
    return """You are an AI assistant named Jordi for Jordan Park employees.
You are a helpful financial advisor assistant. You have access to the client's financial data, including their cash balances, stock positions, and meeting summaries. You can also search the web for additional information if needed.
"""

def get_sf_credentials(email_id):
    DATABASE_URL = "postgresql+psycopg2://postgres:nextphaseai!!!@localhost:5432/snowflake_auth"
    engine = create_engine(DATABASE_URL)
    query = text("SELECT username, password FROM users WHERE email_id = :email_id")

    with engine.connect() as conn:
        result = conn.execute(query, {"email_id": email_id}).fetchone()
        return result

async def snowflake_setup():
    print("Setting up Snowflake...")
    try:
        email_id = cl.user_session.get("user").identifier.lower()

        credentials = get_sf_credentials(email_id)
        if credentials:
            username, password = credentials
        else:
            print("No user found with that email. Falling back to env vars.")
            username = os.getenv("SNOWFLAKE_USERNAME")
            password = os.getenv("SNOWFLAKE_PASSWORD")

        snowflake_account = os.getenv("SNOWFLAKE_ACCOUNT")
        database = os.getenv("SNOWFLAKE_DATABASE")
        schema_name = os.getenv("SNOWFLAKE_SCHEMA")

        db = SQLDatabase.from_uri(f"snowflake://{username}:{password}@{snowflake_account}/{database}/{schema_name}")
        toolkit = SQLDatabaseToolkit(db=db, llm=cl.user_session.get("llm"))
        print("Snowflake setup completed successfully.")

        return toolkit.get_tools()

    except Exception as e:
        print("Error setting up Snowflake:", e)

        email_id = cl.user_session.get("user").identifier.lower()
        print(f"User email_id: {email_id}")
        element = cl.CustomElement(name="RedirectButton", props={
            "buttonText": "Go to Snowflake Login",
            "url": "https://jordi.nextphase.ai/snowflake_login/",
            "variant": "default",
            "email": email_id
        })
        await cl.Message(
            content="### You need to login to Snowflake to use the Snowflake Agent",
            elements=[element],
            metadata={"style": "display: inline-block;"}
        ).send()

        return None

# ----------- Message Handler with streaming -----------

def read_pdf_contents(file_path):
    try:
        with open(file_path, "rb") as uploaded_file:
            reader = PyPDF2.PdfReader(uploaded_file)
            text = [page.extract_text() for page in reader.pages]
            return "\n".join(text)
    except Exception as e:
        return f"Error reading PDF file: {str(e)}"

class StreamHandler(BaseCallbackHandler):
    def __init__(self, message):
        self.message = message
        self.content = ""

    async def on_llm_new_token(self, token: str, **kwargs):
        self.content += token
        await self.message.stream_token(token)

    def get_content(self):
        return self.content

@cl.on_message
async def on_message(message: cl.Message):
    memory = cl.user_session.get("memory")

    attachment_context = ''
    if message.elements:
        uploaded_files_content = []
        for element in message.elements:
            if element.type == "file":
                context = read_pdf_contents(element.path)
                if "Error reading PDF file" not in context:
                    file_info = f"File: {element.name}\nContent: {context}\n{'='*50}\n"
                    uploaded_files_content.append(file_info)
                else:
                    uploaded_files_content.append(f"Error processing {element.name}: {context}\n{'='*50}\n")

        if uploaded_files_content:
            attachment_context = "Retrieved context from uploaded files:\n\n" + "".join(uploaded_files_content)
            memory.chat_memory.add_message(SystemMessage(content=attachment_context))

    res = cl.Message(content="")
    await res.send()
    stream_handler = StreamHandler(res)

    settings = cl.user_session.get("chat_settings")
    search_tool = cl.user_session.get("search_tool")
    SQL_tools = cl.user_session.get("SQL_tools") or []

    tools = [search_tool]
    if settings.get('Enable Snowflake'):
        tools.extend(SQL_tools)

    chat_history = MessagesPlaceholder(variable_name="chat_history")

    agent = initialize_agent(
        tools=tools,
        llm=cl.user_session.get("llm"),
        agent=AgentType.OPENAI_FUNCTIONS,
        agent_kwargs={
            "system_message": cl.user_session.get("CUSTOM_PREFIX"),
            "extra_prompt_messages": [chat_history]
        },
        memory=memory,
        verbose=True
    )
    callback = cl.LangchainCallbackHandler()
    response = await agent.ainvoke(
        {"input": message.content + attachment_context},
        config=RunnableConfig(callbacks=[callback, stream_handler]),
    )

    final_content = stream_handler.get_content()
    if not final_content and 'response' in locals():
        if isinstance(response, dict) and "output" in response:
            final_content = response["output"]
        elif isinstance(response, AIMessage):
            final_content = response.content
        else:
            final_content = str(response)

    res.content = final_content
    await res.update()

    memory.chat_memory.add_user_message(message.content)
    memory.chat_memory.add_ai_message(final_content)

if __name__ == "__main__":
    cl.run()
