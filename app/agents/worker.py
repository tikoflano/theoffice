from langchain_core.messages import SystemMessage
from app.llm import get_llm
from app.prompts import BASE_SYSTEM_PROMPT


def worker_chat(
    history: list,
    system_prompt: str,
    personality_prompt: str,
    is_first_reply: bool,
) -> dict:
    """Run one turn of direct conversation with any worker. Returns {"message": str}."""
    llm = get_llm()
    system_sections = [
        BASE_SYSTEM_PROMPT,
        system_prompt,
        personality_prompt
        or (
            "You are friendly, clear, and professional. "
            "On your first reply in a new conversation, start with a brief greeting that "
            "matches this tone, then move straight into helping the user."
        ),
    ]
    if is_first_reply:
        system_sections.append(
            "This is your first reply in this conversation; follow your greeting rule."
        )
    system = "\n\n".join(s for s in system_sections if s)
    messages = [SystemMessage(content=system)] + list(history)
    response = llm.invoke(messages)
    return {"message": response.content}
