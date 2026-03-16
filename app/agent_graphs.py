from typing import Any, Dict, List

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

from app.agents.michael import michael_chat
from app.agents.worker import worker_chat
from app.db import get_worker


ChatState = Dict[str, Any]


def _ensure_outputs(state: ChatState) -> None:
    if "outputs" not in state or state["outputs"] is None:
        state["outputs"] = []


def run_graph(action: str, state: ChatState) -> ChatState:
    """
    Entry point for running a chat interaction.

    For now, this only implements a very simple direct-chat behavior and ignores
    multi-agent / delegation logic. It exists so that the unified /chat endpoint
    can call into a stable API while we evolve the graphs.
    """
    participants: List[str] = state.get("participants") or []
    if action == "message" and len(participants) == 1:
        return _direct_chat_graph(state)

    # Fallback: echo-style behavior from the first participant
    _ensure_outputs(state)
    participants = participants or ["unknown"]
    first_agent = participants[0]
    message: str = state.get("last_message", "")
    reply_text = (
        f"[stub graph] {first_agent} received: {message} "
        f"(action={action}, from={state.get('from_id')})"
    )
    state["history"].append(
        AIMessage(content=reply_text, additional_kwargs={"agent": first_agent})
    )
    state["outputs"].append({"agent": first_agent, "content": reply_text})
    return state


def _direct_chat_graph(state: ChatState) -> ChatState:
    """
    Very simple direct chat: one participant, no delegation.
    - If the participant is 'michael', call michael_chat.
    - Otherwise, treat the participant as a worker id and call worker_chat.
    """
    _ensure_outputs(state)
    participants: List[str] = state.get("participants") or []
    agent_id = participants[0]
    history: List[BaseMessage] = state.get("history", [])

    if agent_id == "michael":
        worker = get_worker("michael")
        michael_system = worker["system_prompt"] if worker else ""
        michael_personality = (worker or {}).get("personality_prompt", "")
        is_first_reply = not any(isinstance(m, AIMessage) for m in history)
        result = michael_chat(
            history,
            michael_system,
            michael_personality,
            is_first_reply,
        )
        reply_text = result["message"]
    else:
        worker = get_worker(agent_id)
        if not worker:
            reply_text = f"[error] Worker {agent_id!r} not found."
        else:
            is_first_reply = not any(isinstance(m, AIMessage) for m in history)
            result = worker_chat(
                history,
                worker["system_prompt"],
                worker.get("personality_prompt", ""),
                is_first_reply,
            )
            reply_text = result["message"]

    history.append(AIMessage(content=reply_text, additional_kwargs={"agent": agent_id}))
    state["history"] = history
    state["outputs"].append({"agent": agent_id, "content": reply_text})
    return state

