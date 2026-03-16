import logging
import os
from langchain_core.language_models.chat_models import BaseChatModel

_DEFAULTS = {
    "groq": "llama-3.3-70b-versatile",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5-20251001",
    "ollama": "llama3.2",
}


_logger = logging.getLogger("office.llm")


def get_llm() -> BaseChatModel:
    # Explicit provider > auto-detect from available API keys
    provider = os.getenv("LLM_PROVIDER", "").lower()

    if not provider:
        if os.getenv("GROQ_API_KEY"):
            provider = "groq"
        elif os.getenv("OPENAI_API_KEY"):
            provider = "openai"
        elif os.getenv("ANTHROPIC_API_KEY"):
            provider = "anthropic"
        else:
            provider = "ollama"

    model = os.getenv("LLM_MODEL", _DEFAULTS.get(provider, ""))
    _logger.info("llm model=%s", model)

    if provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(model=model, api_key=os.getenv("GROQ_API_KEY"))

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model, api_key=os.getenv("OPENAI_API_KEY"))

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model, api_key=os.getenv("ANTHROPIC_API_KEY"))

    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(model=model)

    raise ValueError(f"Unknown LLM_PROVIDER: {provider!r}. Choose: groq, openai, anthropic, ollama")
