"""Extract user-visible text from a Strands ``AgentResult``."""

from __future__ import annotations

from strands.agent.agent_result import AgentResult


def text_from_agent_result(result: AgentResult) -> str:
    """Return assistant text for HTTP ``response``.

    ``AgentResult.__str__`` only concatenates ``{"text": ...}`` blocks. Some providers
    (Ollama / Qwen via LiteLLM) may leave that empty while still populating other
    content shapes, so we fall back to a structured walk of ``message["content"]``.
    """
    primary = str(result).strip()
    if primary:
        return primary

    message = result.message
    if not isinstance(message, dict):
        return ""

    content = message.get("content")
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if "text" in block and block["text"]:
            parts.append(str(block["text"]))
            continue
        rc = block.get("reasoningContent")
        if isinstance(rc, dict):
            rt = rc.get("reasoningText")
            if isinstance(rt, dict) and rt.get("text"):
                parts.append(str(rt["text"]))
            continue
        cc = block.get("citationsContent")
        if isinstance(cc, dict):
            for item in cc.get("content") or []:
                if isinstance(item, dict) and item.get("text"):
                    parts.append(str(item["text"]))

    return "\n".join(parts).strip()
