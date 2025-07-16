import json
import PyPDF2
import os
from typing import Dict, Optional

import chainlit as cl
from chainlit.input_widget import Select, Switch, Slider
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.data.storage_clients.azure import AzureStorageClient
from chainlit.types import ThreadDict

from langchain.schema import AIMessage, HumanMessage, SystemMessage
from langchain.schema.runnable.config import RunnableConfig
from langchain.callbacks.base import BaseCallbackHandler
from langchain.agents import AgentType, initialize_agent

# Use langchain_community imports as per deprecation warnings:
from langchain_community.chat_models import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_community.tools.tavily_search import TavilySearchResults

from langchain.memory import ConversationBufferMemory
from langchain_core.prompts import MessagesPlaceholder

from O365 import Account, FileSystemTokenBackend
from sqlalchemy import create_engine, text

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
import logging

import os
import logging
import chainlit as cl
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit



#
# @cl.oauth_callback
# def oauth_callback(
#         provider_id: str,
#         token: str,
#         raw_user_data: Dict[str, str],
#         default_user: cl.User,
# ) -> Optional[cl.User]:
#     return default_user


@cl.data_layer
def get_data_layer():
    return SQLAlchemyDataLayer(conninfo="postgresql+asyncpg://postgres:nextphaseai!!!@localhost:5432/chat_history")



@cl.on_chat_start
async def on_chat_start():
    """
    Initializes a fresh user session:
      • Loads chat settings UI (model selector + Snowflake toggle)
      • Sets up LLM, search tool, and optional Snowflake tools
      • Creates conversation memory buffer
    """
    email_id = cl.user_session.get("user").identifier.lower()
    print(f"[CHAT_START] New session for {email_id}")

    #Conversation memory
    cl.user_session.set(
        "memory",
        ConversationBufferMemory(memory_key="chat_history", return_messages=True),
    )

    #Render settings UI (model + Snowflake toggle)
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
            initial=False if get_sf_credentials(email_id) is None else True,
        ),
    ]).send()

    #Load the chosen LLM
    if settings["Model"] == "GPT-4.1":
        llm = ChatOpenAI(temperature=0.1, model="gpt-4.1-2025-04-14", streaming=True, response_format={"type": "text"})
        cl.user_session.set("model_index", 1)
    elif settings["Model"] == "GPT-4.1-nano":
        llm = ChatOpenAI(temperature=0.1, model="gpt-4.1-nano-2025-04-14", streaming=True, response_format={"type": "text"})
        cl.user_session.set("model_index", 2)
    elif settings["Model"] == "GPT-4.1 mini":
        llm = ChatOpenAI(temperature=0.2, model="gpt-4.1-mini-2025-04-14", streaming=True, response_format={"type": "text"})
        cl.user_session.set("model_index", 3)
    else:
        llm = ChatOpenAI(temperature=0.1, model="gpt-4o", streaming=True, response_format={"type": "text"})
        cl.user_session.set("model_index", 0)

    cl.user_session.set("llm", llm)
    print(f"[CHAT_START] LLM set to {settings['Model']} (index {cl.user_session.get('model_index')})")

    #Load always‑on tools
    search_tool = TavilySearchResults(max_results=4)
    cl.user_session.set("search_tool", search_tool)

    #System prompt
    cl.user_session.set("CUSTOM_PREFIX", get_custom_prefix())

    #Optional Snowflake SQL toolkit
    if settings["Enable Snowflake"]:
        sql_tools = await snowflake_setup()
        cl.user_session.set("SQL_tools", sql_tools)
        print("[CHAT_START] Snowflake tools initialized.")



@cl.on_chat_resume
async def on_chat_resume(thread: ThreadDict):
    """
    Consistent session memory restoration
    model_index is updated back to session for continuity
    Clean Snowflake conditional logic
    Log prints for better observability
    Robust handling of chat model and settings
    """
    email_id = cl.user_session.get("user").identifier.lower()

    # Restore conversation memory from saved thread
    memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
    root_messages = [m for m in thread["steps"] if m["parentId"] is None]
    for message in root_messages:
        if message["type"] == "user_message":
            memory.chat_memory.add_user_message(message["output"])
        elif message["type"] == "ai_message":
            memory.chat_memory.add_ai_message(message["output"])
    cl.user_session.set("memory", memory)

    # Render settings UI again (model selector & Snowflake toggle)
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
            initial=False if get_sf_credentials(email_id) is None else True,
        )
    ]).send()

    # Assign selected LLM model based on user input
    if settings['Model'] == "GPT-4.1":
        llm = ChatOpenAI(temperature=0.1, model="gpt-4.1-2025-04-14", streaming=True, response_format={"type": "text"})
        cl.user_session.set("model_index", 1)
    elif settings['Model'] == "GPT-4.1-nano":
        llm = ChatOpenAI(temperature=0.1, model="gpt-4.1-nano-2025-04-14", streaming=True, response_format={"type": "text"})
        cl.user_session.set("model_index", 2)
    elif settings['Model'] == "GPT-4.1 mini":
        llm = ChatOpenAI(temperature=0.2, model="gpt-4.1-mini-2025-04-14", streaming=True, response_format={"type": "text"})
        cl.user_session.set("model_index", 3)
    else:
        llm = ChatOpenAI(temperature=0.1, model="gpt-4o", streaming=True, response_format={"type": "text"})
        cl.user_session.set("model_index", 0)

    cl.user_session.set("llm", llm)
    print(f"[RESUME] LLM resumed as {settings['Model']} for user: {email_id}")

    # Load Tavily Search tool
    search_tool = TavilySearchResults(max_results=4)
    cl.user_session.set("search_tool", search_tool)

    # Load Custom System Prompt
    cl.user_session.set("CUSTOM_PREFIX", get_custom_prefix())

    # Conditionally enable Snowflake SQL agent tools
    if settings['Enable Snowflake']:
        SQL_tools = await snowflake_setup()
        cl.user_session.set("SQL_tools", SQL_tools)




@cl.on_settings_update
async def on_settings_update(settings):
    """
    Reacts to user UI setting changes (model switch, Snowflake toggle).
    Updates LLM, model index, and reinitialises Snowflake tools if requested.
    """
    print("[SETTINGS_UPDATE] New settings:", settings)

    # ---- LLM selection ----------------------------------------------------
    if settings["Model"] == "GPT-4.1":
        llm = ChatOpenAI(temperature=0.2, model="gpt-4.1-2025-04-14", streaming=True, response_format={"type": "text"})
        cl.user_session.set("model_index", 1)
    elif settings["Model"] == "GPT-4.1-nano":
        llm = ChatOpenAI(temperature=0.2, model="gpt-4.1-nano-2025-04-14", streaming=True, response_format={"type": "text"})
        cl.user_session.set("model_index", 2)
    elif settings["Model"] == "GPT-4.1 mini":
        llm = ChatOpenAI(temperature=0.2, model="gpt-4.1-mini-2025-04-14", streaming=True, response_format={"type": "text"})
        cl.user_session.set("model_index", 3)
    else:  # default GPT‑4o
        llm = ChatOpenAI(temperature=0.2, model="gpt-4o", streaming=True, response_format={"type": "text"})
        cl.user_session.set("model_index", 0)

    cl.user_session.set("llm", llm)
    print(f"[SETTINGS_UPDATE] LLM switched to {settings['Model']} (index {cl.user_session.get('model_index')})")

    # ---- Snowflake toggle --------------------------------------------------
    if settings["Enable Snowflake"]:
        sql_tools = await snowflake_setup()
        if sql_tools:
            cl.user_session.set("SQL_tools", sql_tools)
            print("[SETTINGS_UPDATE] Snowflake tools enabled.")
        else:
            # Setup failed → disable the toggle so UI reflects reality
            settings["Enable Snowflake"] = False
            print("[SETTINGS_UPDATE] Snowflake setup failed; toggle disabled.")
    else:
        # User turned Snowflake off – clear tools from session
        cl.user_session.pop("SQL_tools", None)
        print("[SETTINGS_UPDATE] Snowflake tools disabled.")




@cl.set_starters
async def set_starters():
    return [
        cl.Starter(
            label="Client Summary",
            message="Can you provide me with a client summary of the Doe Household?",
            icon="/public/client.png",
        ),

        cl.Starter(
            label="Latest meeting summary",
            message="Can you provide a summary of the last meeting with the Doe Household?",
            icon="/public/call.png",
        ),
        cl.Starter(
            label="Client Quarterly Report",
            message="Can you provide me the latest quarterly report of the Doe Household?",
            icon="/public/summary.png",
        ),
        cl.Starter(
            label="Client's concentrated stock positions",
            message="Tell me about the Doe Household's concentrated stock positions.",
            icon="/public/stocks.png",
        ),
        cl.Starter(
            label="Client's cash balance",
            message="What are the cash balances for these client accounts and any recommended actions?",
            icon="/public/cash.png",
        ),
    ]



def get_custom_prefix():
    return """You are an AI assistant named Jordi for Jordan Park employees.
    You are a helpful financial advisor assistant. You have access to the client's financial data, including their cash balances, stock positions, and meeting summaries. You can also search the web for additional information if needed.
    """




def get_sf_credentials(email_id: str):
    """
    Securely fetches Snowflake credentials (username, password) for the given email_id.
    Returns:
        tuple(str, str): (username, password) if found,
        None: if no credentials found or error occurs.
    """
    try:
        if not email_id:
            logging.warning("Email ID not provided to get_sf_credentials().")
            return None

        # Preferably use environment variables for production DB connection
        DATABASE_URL = os.getenv("AUTH_DB_URL", "postgresql+psycopg2://postgres:nextphaseai!!!@localhost:5432/snowflake_auth")

        engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        query = text("SELECT username, password FROM users WHERE email_id = :email_id")

        with engine.connect() as conn:
            result = conn.execute(query, {"email_id": email_id}).fetchone()

        if result:
            logging.info(f"Fetched Snowflake credentials for {email_id}")
            return result  # (username, password)
        else:
            logging.warning(f"No credentials found for {email_id}")
            return None

    except SQLAlchemyError as e:
        logging.error(f"Database error in get_sf_credentials: {e}", exc_info=True)
        return None
    except Exception as e:
        logging.error(f"Unexpected error in get_sf_credentials: {e}", exc_info=True)
        return None



async def snowflake_setup():
    """
    Setup Snowflake SQL toolkit with externalbrowser (SSO) authentication.
    Returns a list of LangChain SQL tools if successful, otherwise None.
    """
    logging.info("Starting Snowflake setup...")
    try:
        email_id = cl.user_session.get("user").identifier.lower()
        if not email_id:
            logging.warning("User email not found in session.")
            return None

        credentials = get_sf_credentials(email_id)
        if not credentials:
            logging.warning(f"No Snowflake credentials found for user {email_id}")
            return None

        username, password = credentials

        snowflake_account = os.getenv("SNOWFLAKE_ACCOUNT")
        database = os.getenv("SNOWFLAKE_DATABASE")
        schema_name = os.getenv("SNOWFLAKE_SCHEMA")

        if not all([snowflake_account, database, schema_name]):
            logging.error("Missing one or more Snowflake environment variables.")
            return None

        # Construct URI with externalbrowser authenticator to enable SSO browser pop-up login
        snowflake_uri = (
            f"snowflake://{username}:{password}@{snowflake_account}/{database}/{schema_name}"
            "?authenticator=externalbrowser"
        )

        logging.info(f"Connecting to Snowflake with URI: {snowflake_uri}")

        # Initialize LangChain SQLDatabase and toolkit
        db = SQLDatabase.from_uri(snowflake_uri)

        llm = cl.user_session.get("llm")
        if llm is None:
            logging.warning("LLM instance missing in user session.")
            return None

        toolkit = SQLDatabaseToolkit(db=db, llm=llm)

        logging.info("Snowflake setup completed successfully.")
        return toolkit.get_tools()

    except Exception as e:
        logging.error(f"Snowflake setup error: {e}", exc_info=True)

        email_id = cl.user_session.get("user").identifier.lower()
        # Show a Chainlit UI button to redirect users to Snowflake login page
        login_button = cl.CustomElement(
            name="RedirectButton",
            props={
                "buttonText": "Go to Snowflake Login",
                "url": "https://jordi.nextphase.ai/snowflake_login/",
                "variant": "default",
                "email": email_id,
            },
        )
        await cl.Message(
            content="### You need to login to Snowflake to use the Snowflake Agent",
            elements=[login_button],
            metadata={"style": "display: inline-block;"},
        ).send()

        return None


# Helper function for on_message
def read_pdf_contents(file_path):
    try:
        # Open the PDF file
        with open(file_path, "rb") as uploaded_file:
            reader = PyPDF2.PdfReader(uploaded_file)
            text = []
            # Iterate through each page and extract text
            for page in reader.pages:
                text.append(page.extract_text())
            # Join all text from all pages into a single string
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
    print(f"Settings={cl.user_session.get('chat_settings')}")
    memory = cl.user_session.get("memory")  # Retrieve conversation memory

    attachment_context = ''
    # Context file upload for multiple files
    if message.elements:
        uploaded_files_content = []
        for element in message.elements:
            if element.type == "file":
                # Use the file path to read the PDF contents
                context = read_pdf_contents(element.path)
                if "Error reading PDF file" not in context:  # Check if reading was successful
                    file_info = f"File: {element.name}\nContent: {context}\n{'=' * 50}\n"
                    uploaded_files_content.append(file_info)
                else:
                    uploaded_files_content.append(f"Error processing {element.name}: {context}\n{'=' * 50}\n")

        if uploaded_files_content:
            attachment_context = "Retrieved context from uploaded files:\n\n" + "".join(uploaded_files_content)
            memory.chat_memory.add_message(SystemMessage(content=attachment_context))

    res = cl.Message(content="")
    await res.send()
    stream_handler = StreamHandler(res)

    settings = cl.user_session.get("chat_settings")
    # Load LangChain tools
    search_tool = cl.user_session.get("search_tool")
    SQL_tools = cl.user_session.get("SQL_tools")

    tools = [search_tool]

    if settings['Enable Snowflake']:
        tools.extend(SQL_tools)

    chat_history = MessagesPlaceholder(variable_name="chat_history")

    print(f"Tools loaded: {[tool.name for tool in tools]}")

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
    # Stream response from the agent
    response = await agent.ainvoke(
        {"input": message.content + attachment_context},
        config=RunnableConfig(callbacks=[callback, stream_handler]),
    )

    # If successful, break the retry loop
    final_content = stream_handler.get_content()
    # final_content = escape_markdown(final_content)

    # If no content was streamed, extract it from the response
    if not final_content and 'response' in locals():
        if isinstance(response, dict) and "output" in response:
            final_content = response["output"]
        elif isinstance(response, AIMessage):
            final_content = response.content
        else:
            final_content = str(response)

    # Set the content directly on the message object
    res.content = final_content

    # Update the UI
    await res.update()

    # Save messages to memory
    memory.chat_memory.add_user_message(message.content)
    memory.chat_memory.add_ai_message(final_content)


if __name__ == "__main__":
    cl.run()