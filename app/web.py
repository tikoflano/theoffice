from dotenv import load_dotenv
load_dotenv()

import asyncio
import collections
import logging
import uuid
from typing import Annotated

from fastapi import FastAPI, Form, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage, AIMessage
from pydantic import BaseModel

from app.db import init_db, get_workers, get_worker, create_worker, get_hr_agents
from app.db import fire_worker as db_fire_worker
from app.agents.michael import michael_chat
from app.agents.toby import toby_chat, generate_candidates
from app.agents.worker import worker_chat

web = FastAPI()
web.mount("/static", StaticFiles(directory="static"), name="static")


@web.exception_handler(RequestValidationError)
async def _log_validation_error(request: Request, exc: RequestValidationError):
    logger.error("422 %s %s errors=%s", request.method, request.url.path, exc.errors())
    return await request_validation_exception_handler(request, exc)

# hire_session_id -> list of BaseMessage (Toby interview history)
toby_sessions: dict[str, list] = {}

# michael_session_id -> list of BaseMessage (Michael chat history)
michael_sessions: dict[str, list] = {}

# "{worker_id}:{session_id}" -> list of BaseMessage (direct worker chat history)
worker_sessions: dict[str, list] = {}

# generic chat session_id -> list of BaseMessage (future unified /chat history)
chat_sessions: dict[str, list] = {}


class ChatRequest(BaseModel):
    session_id: str
    participants: list[str]
    from_id: str
    action: str
    message: str


class ChatTurn(BaseModel):
    agent: str
    content: str


class ChatResponse(BaseModel):
    session_id: str
    turns: list[ChatTurn]

_log_buffer: collections.deque[str] = collections.deque(maxlen=200)


class _BufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            _log_buffer.append(self.format(record))
        except Exception:
            self.handleError(record)


def _configure_logging() -> None:
    fmt = logging.Formatter(
        fmt="%(asctime)s.%(msecs)03d  %(levelname)-8s  %(name)-14s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    stream_h = logging.StreamHandler()
    stream_h.setFormatter(fmt)
    buffer_h = _BufferHandler()
    buffer_h.setFormatter(fmt)
    root = logging.getLogger("office")
    root.setLevel(logging.DEBUG)
    root.addHandler(stream_h)
    root.addHandler(buffer_h)
    root.propagate = False  # don't double-print through uvicorn's root handler

    # Mirror uvicorn access log into the buffer so HTTP status codes are visible
    access = logging.getLogger("uvicorn.access")
    access.addHandler(buffer_h)


logger = logging.getLogger("office.web")


@web.on_event("startup")
async def startup():
    _configure_logging()
    init_db()


def _worker_card(worker: dict) -> str:
    return (
        f'<div id="worker-{worker["id"]}" class="bg-white rounded-lg border p-3 flex items-center justify-between gap-2">'
        "<div>"
        f'<p class="font-medium text-sm text-gray-800">{worker["name"]}</p>'
        f'<p class="text-xs text-gray-500">{worker["role"]}</p>'
        "</div>"
        f'<button hx-post="/workers/{worker["id"]}/fire" hx-target="#staff-list" hx-swap="innerHTML" '
        f'hx-confirm="Fire {worker["name"]}?" '
        'hx-on::after-request="window.officeScene && window.officeScene.syncWorkers()" '
        'class="text-xs text-red-400 hover:text-red-600 font-medium shrink-0">Fire</button>'
        "</div>"
    )


def _staff_list_html() -> str:
    all_workers = get_workers()
    regular = [w for w in all_workers if w.get("role_type", "regular") not in ("hr", "manager")]
    hr_agents = [w for w in all_workers if w.get("role_type", "regular") == "hr"]

    parts = []
    if regular:
        parts.append("".join(_worker_card(w) for w in regular))
    else:
        parts.append('<p class="text-xs text-gray-400 text-center py-4">No staff hired yet</p>')

    if hr_agents:
        parts.append('<div class="border-t mt-2 pt-2">')
        parts.append('<p class="text-xs text-gray-500 font-medium px-1 mb-2 uppercase tracking-wide">HR</p>')
        parts.append("".join(_worker_card(w) for w in hr_agents))
        parts.append("</div>")

    return "".join(parts)


def _worker_card(worker: dict) -> str:
    return (
        f'<div id="worker-{worker["id"]}" class="bg-white rounded-lg border p-3 flex items-center justify-between gap-2">'
        "<div>"
        f'<p class="font-medium text-sm text-gray-800">{worker["name"]}</p>'
        f'<p class="text-xs text-gray-500">{worker["role"]}</p>'
        "</div>"
        f'<button hx-post="/workers/{worker["id"]}/fire" hx-target="#staff-list" hx-swap="innerHTML" '
        f'hx-confirm="Fire {worker["name"]}?" '
        'hx-on::after-request="window.officeScene && window.officeScene.syncWorkers()" '
        'class="text-xs text-red-400 hover:text-red-600 font-medium shrink-0">Fire</button>'
        "</div>"
    )


def _staff_list_html() -> str:
    all_workers = get_workers()
    regular = [w for w in all_workers if w.get("role_type", "regular") not in ("hr", "manager")]
    hr_agents = [w for w in all_workers if w.get("role_type", "regular") == "hr"]

    parts = []
    if regular:
        parts.append("".join(_worker_card(w) for w in regular))
    else:
        parts.append('<p class="text-xs text-gray-400 text-center py-4">No staff hired yet</p>')

    if hr_agents:
        parts.append('<div class="border-t mt-2 pt-2">')
        parts.append('<p class="text-xs text-gray-500 font-medium px-1 mb-2 uppercase tracking-wide">HR</p>')
        parts.append("".join(_worker_card(w) for w in hr_agents))
        parts.append("</div>")

    return "".join(parts)


# --- Routes ---

@web.get("/", response_class=FileResponse)
async def index():
    return FileResponse("static/index.html")


@web.get("/health")
async def health():
    return {"status": "ok"}


@web.get("/workers/partial", response_class=HTMLResponse)
async def workers_partial():
    return HTMLResponse(_staff_list_html())


@web.get("/workers/positions")
async def workers_positions():
    all_workers = get_workers()
    # Exclude HR agents from the slot grid (Toby has a fixed desk position)
    regular = [w for w in all_workers if w.get("role_type", "regular") not in ("hr", "manager")]
    return [
        {"id": w["id"], "name": w["name"], "role": w["role"], "slot": i}
        for i, w in enumerate(regular)
    ]


@web.post("/workers", response_class=HTMLResponse)
async def hire_worker(
    name: Annotated[str, Form()],
    role: Annotated[str, Form()],
    system_prompt: Annotated[str, Form()],
):
    logger.info("hire name=%r role=%r", name.strip(), role.strip())
    create_worker(name.strip(), role.strip(), system_prompt.strip())
    return HTMLResponse(_staff_list_html())


@web.post("/workers/{worker_id}/fire", response_class=HTMLResponse)
async def fire_worker_route(worker_id: str):
    logger.info("fire worker_id=%s", worker_id)
    db_fire_worker(worker_id)
    return HTMLResponse(_staff_list_html())


@web.get("/logs", response_class=HTMLResponse)
async def logs_page():
    lines = list(_log_buffer)
    escaped = "\n".join(
        line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        for line in lines
    ) or "(no log entries yet)"
    html = (
        "<!DOCTYPE html><html><head>"
        "<meta charset='utf-8'>"
        "<meta http-equiv='refresh' content='3'>"
        "<title>Office Logs</title>"
        "<style>"
        "body{margin:0;background:#0f172a;color:#e2e8f0;font-family:monospace;font-size:13px;}"
        "pre{padding:16px;white-space:pre-wrap;word-break:break-all;}"
        "</style></head><body>"
        f"<pre>{escaped}</pre>"
        "</body></html>"
    )
    return HTMLResponse(html)


# --- Unified chat endpoint (stubbed) ---


@web.post("/chat", response_model=ChatResponse)
async def chat_endpoint(body: ChatRequest):
    """
    Generic chat endpoint that will eventually route to LangGraph-based graphs.
    For now this is a stub that simply echoes a single turn from the first participant.
    """
    # Basic validation: must have at least one participant
    if not body.participants:
        return JSONResponse(
            status_code=400, content={"error": "participants list must not be empty"}
        )

    # Initialize or update generic chat history for this session
    history = chat_sessions.setdefault(body.session_id, [])
    history.append(
        HumanMessage(
            content=body.message,
            additional_kwargs={
                "from_id": body.from_id,
                "action": body.action,
                "participants": body.participants,
            },
        )
    )

    # TODO: replace this with a call into LangGraph once graphs are implemented.
    # For now, just return a single stubbed turn "from" the first participant.
    first_agent = body.participants[0]
    reply_text = (
        f"[stub] {first_agent} received: {body.message} "
        f"(action={body.action}, from={body.from_id})"
    )

    history.append(
        AIMessage(
            content=reply_text,
            additional_kwargs={"agent": first_agent},
        )
    )

    logger.info(
        "chat/session=%s participants=%s action=%s from=%s",
        body.session_id,
        body.participants,
        body.action,
        body.from_id,
    )

    return ChatResponse(
        session_id=body.session_id,
        turns=[ChatTurn(agent=first_agent, content=reply_text)],
    )


# --- Michael endpoints ---

class _MichaelChatReq(BaseModel):
    michael_session_id: str
    message: str


@web.post("/michael/chat")
async def michael_chat_endpoint(body: _MichaelChatReq):
    history = michael_sessions.setdefault(body.michael_session_id, [])
    history.append(HumanMessage(content=body.message))
    michael = get_worker("michael")
    michael_system = michael["system_prompt"] if michael else ""
    michael_personality = (michael or {}).get("personality_prompt", "")
    # First reply is defined as the first turn before any AIMessage exists in history
    is_first_reply = not any(isinstance(m, AIMessage) for m in history)
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: michael_chat(
            history,
            michael_system,
            michael_personality,
            is_first_reply,
        ),
    )
    history.append(AIMessage(content=result["message"]))
    logger.info("michael/chat sid=%s", body.michael_session_id)
    return result


# --- Worker direct-chat endpoints ---

class _WorkerChatReq(BaseModel):
    session_id: str
    message: str


class _WorkerGreetReq(BaseModel):
    session_id: str


@web.post("/worker/{worker_id}/chat")
async def worker_chat_endpoint(worker_id: str, body: _WorkerChatReq):
    worker = get_worker(worker_id)
    if not worker:
        return JSONResponse(status_code=404, content={"error": "Worker not found"})
    key = f"{worker_id}:{body.session_id}"
    history = worker_sessions.setdefault(key, [])
    if body.message:
        history.append(HumanMessage(content=body.message))
    # First reply is defined as the first turn before any AIMessage exists in history
    is_first_reply = not any(isinstance(m, AIMessage) for m in history)
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: worker_chat(
            history,
            worker["system_prompt"],
            worker.get("personality_prompt", ""),
            is_first_reply,
        ),
    )
    history.append(AIMessage(content=result["message"]))
    logger.info("worker/chat worker_id=%s sid=%s", worker_id, body.session_id)
    return result


@web.post("/worker/{worker_id}/greet")
async def worker_greet_endpoint(worker_id: str, body: _WorkerGreetReq):
    worker = get_worker(worker_id)
    if not worker:
        return JSONResponse(status_code=404, content={"error": "Worker not found"})
    key = f"{worker_id}:{body.session_id}"
    history = worker_sessions.setdefault(key, [])
    # First reply is defined as the first turn before any AIMessage exists in history
    is_first_reply = not any(isinstance(m, AIMessage) for m in history)
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: worker_chat(
            history,
            worker["system_prompt"],
            worker.get("personality_prompt", ""),
            is_first_reply,
        ),
    )
    history.append(AIMessage(content=result["message"]))
    logger.info("worker/greet worker_id=%s sid=%s", worker_id, body.session_id)
    return result


# --- Toby / Hire endpoints ---

class _TobyChatReq(BaseModel):
    hire_session_id: str
    message: str


class _TobyCandidatesReq(BaseModel):
    hire_session_id: str


class _TobyHireReq(BaseModel):
    name: str
    role: str
    system_prompt: str
    hire_session_id: str


@web.post("/toby/chat")
async def toby_chat_endpoint(body: _TobyChatReq):
    history = toby_sessions.setdefault(body.hire_session_id, [])
    history.append(HumanMessage(content=body.message))
    toby = get_worker("toby")
    toby_prompt = toby["system_prompt"] if toby else ""
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, lambda: toby_chat(history, toby_prompt)
    )
    history.append(AIMessage(content=result["message"]))
    logger.info("toby/chat sid=%s ready=%s", body.hire_session_id, result["ready"])
    return result


@web.post("/toby/candidates")
async def toby_candidates(body: _TobyCandidatesReq):
    history = toby_sessions.get(body.hire_session_id, [])
    loop = asyncio.get_running_loop()
    candidates = await loop.run_in_executor(
        None, lambda: generate_candidates(history)
    )
    logger.info("toby/candidates sid=%s count=%d", body.hire_session_id, len(candidates))
    return {"candidates": candidates}


@web.post("/toby/hire")
async def toby_hire(body: _TobyHireReq):
    logger.info("toby/hire name=%r role=%r", body.name, body.role)
    worker = create_worker(body.name.strip(), body.role.strip(), body.system_prompt.strip())
    toby_sessions.pop(body.hire_session_id, None)
    return worker


@web.delete("/toby/session/{session_id}")
async def toby_delete_session(session_id: str):
    toby_sessions.pop(session_id, None)
    return {"ok": True}
