import json
import re
from typing import TypedDict

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END

from app.llm import get_llm

TOBY_INTERVIEW_SYSTEM = """You are currently conducting a staff intake interview. Ask ONE question at a time across these four areas:
1. Domain/function: what kind of work? (coding, writing, research, analysis, etc.)
2. Personality/communication style: formal, casual, terse, verbose, encouraging?
3. Autonomy level: asks clarifying questions, decides independently, strictly follows instructions?
4. Specific skills or knowledge areas?

Acknowledge each answer before moving on. After covering at least areas 1 and 2 (typically 3–4 exchanges), set "ready" to true and tell the user you have enough to go search for candidates.

Respond with valid JSON only. No markdown. No extra text.
{"message": "...", "ready": false}"""

TOBY_GENERATE_SYSTEM = """You are a talent acquisition specialist. Given a hiring interview transcript, generate exactly 3 distinct AI staff member profiles. Each must differ meaningfully in personality, style, and specialization — not just name.

- name: realistic first + last name
- role: specific job title (2-4 words)
- tagline: punchy, under 12 words
- system_prompt: 3-5 sentences in second person ("You are...") covering who they are, their expertise, communication style, and how they approach tasks

Respond with valid JSON only. No markdown.
{"candidates": [{name, role, tagline, system_prompt}, ...]}"""

TOBY_CRITIQUE_SYSTEM = """You are reviewing 3 AI staff member candidate profiles. Evaluate whether:
1. The 3 candidates are meaningfully distinct (personality, style, specialization)
2. System prompts are specific and actionable (3-5 sentences, second person)
3. Each has a clear unique value proposition

Respond with valid JSON only. No markdown.
{"ok": true, "feedback": "brief feedback or empty string if ok"}"""


def _parse_json(text: str) -> dict:
    """Parse JSON from LLM response, stripping markdown fences if present."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text.strip())


def toby_chat(history: list, toby_base_prompt: str) -> dict:
    """Run one turn of Toby's interview. Returns {"message": str, "ready": bool}."""
    llm = get_llm()
    system = toby_base_prompt + "\n\n" + TOBY_INTERVIEW_SYSTEM
    messages = [SystemMessage(content=system)] + list(history)
    response = llm.invoke(messages)
    try:
        result = _parse_json(response.content)
        return {
            "message": str(result.get("message", "")),
            "ready": bool(result.get("ready", False)),
        }
    except Exception:
        return {"message": response.content, "ready": False}


class _GenState(TypedDict):
    transcript: str
    draft: list
    feedback: str
    passes: int
    ok: bool


def generate_candidates(history: list) -> list[dict]:
    """Generate 3 candidate profiles via a LangGraph draft→critique→refine loop."""
    transcript = "\n".join(
        f"{'User' if isinstance(m, HumanMessage) else 'Toby'}: {m.content}"
        for m in history
    )
    llm = get_llm()

    def draft_candidates(state: _GenState) -> dict:
        prompt = f"Hiring interview transcript:\n\n{state['transcript']}\n\nGenerate 3 distinct candidate profiles."
        if state.get("feedback"):
            prompt += f"\n\nPrevious feedback to address: {state['feedback']}"
        messages = [
            SystemMessage(content=TOBY_GENERATE_SYSTEM),
            HumanMessage(content=prompt),
        ]
        response = llm.invoke(messages)
        try:
            data = _parse_json(response.content)
            candidates = data.get("candidates", [])
        except Exception:
            candidates = []
        return {"draft": candidates}

    def critique(state: _GenState) -> dict:
        draft_str = json.dumps(state["draft"], indent=2)
        messages = [
            SystemMessage(content=TOBY_CRITIQUE_SYSTEM),
            HumanMessage(content=f"Candidates to review:\n{draft_str}"),
        ]
        response = llm.invoke(messages)
        try:
            result = _parse_json(response.content)
            ok = bool(result.get("ok", True))
            feedback = str(result.get("feedback", ""))
        except Exception:
            ok = True
            feedback = ""
        return {"ok": ok, "feedback": feedback}

    def refine(state: _GenState) -> dict:
        return {"passes": state["passes"] + 1}

    def should_refine(state: _GenState) -> str:
        if not state.get("ok", True) and state["passes"] < 2:
            return "refine"
        return END

    graph = StateGraph(_GenState)
    graph.add_node("draft_candidates", draft_candidates)
    graph.add_node("critique", critique)
    graph.add_node("refine", refine)
    graph.set_entry_point("draft_candidates")
    graph.add_edge("draft_candidates", "critique")
    graph.add_conditional_edges(
        "critique", should_refine, {"refine": "refine", END: END}
    )
    graph.add_edge("refine", "draft_candidates")
    app = graph.compile()

    result = app.invoke(
        {"transcript": transcript, "draft": [], "feedback": "", "passes": 0, "ok": True}
    )
    return result.get("draft", [])
