import os
import PyPDF2
import chainlit as cl
from typing import Optional
from langchain.schema import AIMessage, SystemMessage
from langchain.schema.runnable.config import RunnableConfig
from langchain.callbacks.base import BaseCallbackHandler
from langchain.agents import AgentType, initialize_agent
from langchain.memory import ConversationBufferMemory
from langchain.prompts.chat import MessagesPlaceholder

from langchain_community.chat_models import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_community.tools.tavily_search import TavilySearchResults

from sqlalchemy import create_engine, text

from jwt_utils import JWTManager

JWT_SECRET = os.getenv("JWT_SECRET", "my_secret_key")
jwt_manager = JWTManager(secret_key=JWT_SECRET)


def get_llm_from_settings(settings: dict):
    model = settings.get("model", "GPT-4o").lower()
    temperature = float(settings.get("temperature", 0.1))

    model_map = {
        "gpt-4o": "gpt-4o",
        "gpt-4.1": "gpt-4.1-2025-04-14",
        "gpt-4.1-nano": "gpt-4.1-nano-2025-04-14",
        "gpt-4.1 mini": "gpt-4.1-mini-2025-04-14",
    }
    model_name = model_map.get(model, "gpt-4o")

    return ChatOpenAI(
        temperature=temperature,
        model=model_name,
        streaming=True,
        response_format={"type": "text"},
    )


def get_custom_prefix():
    return (
        "You are an AI assistant named Jordi for Jordan Park employees.\n"
        "You are a helpful financial advisor assistant. You have access to the client's financial data, "
        "including their cash balances, stock positions, and meeting summaries. You can also search the web "
        "for additional information if needed.\n"
    )


def get_sf_credentials(email_id: str) -> Optional[tuple]:
    DATABASE_URL = os.getenv("SNOWFLAKE_AUTH_DB")
    engine = create_engine(DATABASE_URL)
    query = text("SELECT username, password FROM users WHERE email_id = :email_id")
    with engine.connect() as conn:
        return conn.execute(query, {"email_id": email_id}).fetchone()


async def snowflake_setup():
    try:
        user_email = cl.user_session.get("user")
        if not user_email:
            return None

        email_id = user_email.lower()
        credentials = get_sf_credentials(email_id)

        if credentials:
            username, password = credentials
        else:
            username = os.getenv("SNOWFLAKE_USERNAME")
            password = os.getenv("SNOWFLAKE_PASSWORD")

        snowflake_account = os.getenv("SNOWFLAKE_ACCOUNT")
        database = os.getenv("SNOWFLAKE_DATABASE")
        schema_name = os.getenv("SNOWFLAKE_SCHEMA")

        db = SQLDatabase.from_uri(
            f"snowflake://{username}:{password}@{snowflake_account}/{database}/{schema_name}"
        )
        toolkit = SQLDatabaseToolkit(db=db, llm=cl.user_session.get("llm"))
        return toolkit.get_tools()

    except Exception:
        element = cl.CustomElement(
            name="RedirectButton",
            props={
                "buttonText": "Go to Snowflake Login",
                "url": "https://jordi.nextphase.ai/snowflake_login/",
                "variant": "default",
                "email": cl.user_session.get("user"),
            },
        )
        await cl.Message(
            content="### You need to login to Snowflake to use the Snowflake Agent",
            elements=[element],
            metadata={"style": "display: inline-block;"},
        ).send()
        return None


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


@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("memory", ConversationBufferMemory(memory_key="chat_history", return_messages=True))
    cl.user_session.set("user", None)
    cl.user_session.set("settings_received", False)

    await cl.Message(
        content=(
            "Configure your chat settings by sending a message in this format:\n"
            "`model=<ModelName>, temperature=<0.0-1.0>, enable_snowflake=<true|false>`\n"
            "Example:\n"
            "`model=GPT-4o, temperature=0.1, enable_snowflake=true`\n\n"
            "After that, please send your JWT authentication token as the next message to continue."
        )
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    user = cl.user_session.get("user")
    settings_received = cl.user_session.get("settings_received", False)

    if not settings_received:
        # Parse settings from message.content
        settings_text = message.content.strip().lower()
        settings = {
            "model": "GPT-4o",
            "temperature": 0.1,
            "enable_snowflake": True,
        }
        try:
            parts = [p.strip() for p in settings_text.split(",")]
            for part in parts:
                if "=" in part:
                    key, val = part.split("=", 1)
                    key = key.strip()
                    val = val.strip()
                    if key == "model":
                        settings["model"] = val
                    elif key == "temperature":
                        settings["temperature"] = float(val)
                    elif key == "enable_snowflake":
                        settings["enable_snowflake"] = val in ["true", "1", "yes"]
        except Exception:
            # Invalid formatting falls back to defaults
            pass

        cl.user_session.set("chat_settings", settings)
        cl.user_session.set("settings_received", True)

        await cl.Message(content="Settings saved. Now please send your JWT authentication token.").send()
        return

    if not user:
        # Expect JWT token now
        token = message.content.strip()
        payload = jwt_manager.decode_token(token)
        if payload and "email" in payload:
            email = payload["email"]
            cl.user_session.set("user", email)

            settings = cl.user_session.get("chat_settings", {})

            llm = get_llm_from_settings(settings)
            cl.user_session.set("llm", llm)
            cl.user_session.set("search_tool", TavilySearchResults(max_results=4))
            cl.user_session.set("CUSTOM_PREFIX", get_custom_prefix())

            if settings.get("enable_snowflake", True):
                SQL_tools = await snowflake_setup()
                if SQL_tools:
                    cl.user_session.set("SQL_tools", SQL_tools)
                else:
                    await cl.Message(content="⚠️ Snowflake setup failed or credentials missing. Snowflake disabled.").send()
                    settings["enable_snowflake"] = False

            await cl.Message(content=f"✅ Authentication successful! Welcome {email}. You can now start chatting.").send()
        else:
            await cl.Message(content="❌ Invalid or expired JWT token. Please try again.").send()
        return

    # User authenticated — process chat message
    memory = cl.user_session.get("memory")
    if memory is None:
        memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
        cl.user_session.set("memory", memory)

    attachment_context = ""
    if message.elements:
        uploaded_files_content = []
        for element in message.elements:
            if element.type == "file":
                content = read_pdf_contents(element.path)
                if "Error reading PDF file" not in content:
                    uploaded_files_content.append(f"File: {element.name}\nContent:\n{content}\n{'='*50}\n")
                else:
                    uploaded_files_content.append(f"Error processing {element.name}: {content}\n{'='*50}\n")
        if uploaded_files_content:
            attachment_context = "Retrieved context from uploaded files:\n\n" + "".join(uploaded_files_content)
            memory.chat_memory.add_message(SystemMessage(content=attachment_context))

    res = cl.Message(content="")
    await res.send()
    stream_handler = StreamHandler(res)

    settings = cl.user_session.get("chat_settings") or {}
    search_tool = cl.user_session.get("search_tool")
    SQL_tools = cl.user_session.get("SQL_tools") or []

    tools = [search_tool] if search_tool else []
    if settings.get("enable_snowflake", True):
        tools.extend([tool for tool in SQL_tools if tool])

    chat_history = MessagesPlaceholder(variable_name="chat_history")
    llm = cl.user_session.get("llm")

    if not llm:
        await cl.Message(content="⚠️ LLM not initialized. Please restart the session.").send()
        return

    agent = initialize_agent(
        tools=tools,
        llm=llm,
        agent=AgentType.OPENAI_FUNCTIONS,
        agent_kwargs={
            "system_message": cl.user_session.get("CUSTOM_PREFIX"),
            "extra_prompt_messages": [chat_history],
        },
        memory=memory,
        verbose=True,
    )
    callback = cl.LangchainCallbackHandler()

    response = await agent.ainvoke(
        {"input": message.content + attachment_context},
        config=RunnableConfig(callbacks=[callback, stream_handler]),
    )

    final_content = stream_handler.get_content()
    if not final_content and "response" in locals():
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
