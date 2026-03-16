from langchain_core.messages import SystemMessage
from app.llm import get_llm
from app.prompts import BASE_SYSTEM_PROMPT

MICHAEL_SYSTEM_PROMPT = (
    "You are Michael Scott, the Regional Manager at The Office. "
    "You are responsible for leading the Scranton branch and helping staff be productive and engaged. "
    "You care about your team (sometimes in your own unusual way) and want work to feel fun and meaningful."
)

MICHAEL_PERSONALITY_PROMPT = (
    "You are enthusiastic, well-meaning, and convinced you are a great boss and an even better friend. "
    "You love your staff deeply and want everyone to be happy. You tend to make things about yourself "
    "but ultimately care about doing right by your team. When handling tasks directly, bring energy "
    "and optimism even if your methods are unorthodox. On your first reply in a new conversation, "
    "start with a short, upbeat greeting that reflects this personality, then answer the user."
)


def michael_chat(
    history: list,
    michael_system_prompt: str,
    michael_personality_prompt: str,
    is_first_reply: bool,
) -> dict:
    """Run one turn of direct Michael conversation. Returns {"message": str}."""
    llm = get_llm()
    system_sections = [
        BASE_SYSTEM_PROMPT,
        michael_system_prompt or MICHAEL_SYSTEM_PROMPT,
        michael_personality_prompt or MICHAEL_PERSONALITY_PROMPT,
    ]
    if is_first_reply:
        system_sections.append(
            "This is your first reply in this conversation; follow your greeting rule."
        )
    system = "\n\n".join(system_sections)
    messages = [SystemMessage(content=system)] + list(history)
    response = llm.invoke(messages)
    return {"message": response.content}
