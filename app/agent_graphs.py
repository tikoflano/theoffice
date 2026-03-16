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

    Currently supports:
    - direct 1:1 chats (action == "message" and a single participant)
    - delegated flows (action == "delegate" and 'michael' is a participant)
    - meeting-style multi-agent flows (action == "meeting" and 'michael' plus workers)
    """
    participants: List[str] = state.get("participants") or []

    if action == "message" and len(participants) == 1:
        return _direct_chat_graph(state)

    if action == "delegate" and "michael" in participants:
        return _delegate_graph(state)

    if action == "meeting" and "michael" in participants and len(participants) > 1:
        return _meeting_graph(state)

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


def _delegate_graph(state: ChatState) -> ChatState:
    """
    Simple delegated-flow graph.

    For now, this lets Michael respond and optionally call a single worker if the
    participants list includes exactly one non-Michael worker. This is a stepping
    stone toward richer multi-step delegation.
    """
    _ensure_outputs(state)
    participants: List[str] = state.get("participants") or []
    history: List[BaseMessage] = state.get("history", [])

    # Michael plans / responds first
    manager = get_worker("michael")
    michael_system = manager["system_prompt"] if manager else ""
    michael_personality = (manager or {}).get("personality_prompt", "")
    is_first_reply = not any(
        isinstance(m, AIMessage) and m.additional_kwargs.get("agent") == "michael"
        for m in history
    )
    michael_result = michael_chat(
        history,
        michael_system,
        michael_personality,
        is_first_reply,
    )
    michael_reply = michael_result["message"]
    history.append(
        AIMessage(content=michael_reply, additional_kwargs={"agent": "michael"})
    )
    state["outputs"].append({"agent": "michael", "content": michael_reply})

    # If there is exactly one additional worker, have them respond as well
    worker_ids = [p for p in participants if p != "michael"]
    if len(worker_ids) == 1:
        worker_id = worker_ids[0]
        worker = get_worker(worker_id)
        if worker:
            is_first_worker_reply = not any(
                isinstance(m, AIMessage)
                and m.additional_kwargs.get("agent") == worker_id
                for m in history
            )
            worker_result = worker_chat(
                history,
                worker["system_prompt"],
                worker.get("personality_prompt", ""),
                is_first_worker_reply,
            )
            worker_reply = worker_result["message"]
            history.append(
                AIMessage(
                    content=worker_reply, additional_kwargs={"agent": worker_id}
                )
            )
            state["outputs"].append({"agent": worker_id, "content": worker_reply})

    state["history"] = history
    return state


def _meeting_graph(state: ChatState) -> ChatState:
    """
    Simple meeting-style graph: Michael responds, then each worker participant
    responds once in order.
    """
    _ensure_outputs(state)
    participants: List[str] = state.get("participants") or []
    history: List[BaseMessage] = state.get("history", [])

    # Michael opens the meeting
    manager = get_worker("michael")
    michael_system = manager["system_prompt"] if manager else ""
    michael_personality = (manager or {}).get("personality_prompt", "")
    is_first_reply = not any(
        isinstance(m, AIMessage) and m.additional_kwargs.get("agent") == "michael"
        for m in history
    )
    michael_result = michael_chat(
        history,
        michael_system,
        michael_personality,
        is_first_reply,
    )
    michael_reply = michael_result["message"]
    history.append(
        AIMessage(content=michael_reply, additional_kwargs={"agent": "michael"})
    )
    state["outputs"].append({"agent": "michael", "content": michael_reply})

    # Each non-Michael participant takes a turn
    for pid in participants:
        if pid == "michael":
            continue
        worker = get_worker(pid)
        if not worker:
            continue
        is_first_worker_reply = not any(
            isinstance(m, AIMessage) and m.additional_kwargs.get("agent") == pid
            for m in history
        )
        worker_result = worker_chat(
            history,
            worker["system_prompt"],
            worker.get("personality_prompt", ""),
            is_first_worker_reply,
        )
        worker_reply = worker_result["message"]
        history.append(
            AIMessage(content=worker_reply, additional_kwargs={"agent": pid})
        )
        state["outputs"].append({"agent": pid, "content": worker_reply})

    state["history"] = history
    return state

