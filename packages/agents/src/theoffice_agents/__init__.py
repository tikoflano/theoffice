"""Agent definitions and model providers (Bedrock, AgentCore, Ollama)."""

from theoffice_agents.agent_runtime import create_app, run
from theoffice_agents.strands_setup import build_ollama_model

__all__ = ["build_ollama_model", "create_app", "run"]
