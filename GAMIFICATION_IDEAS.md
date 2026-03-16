# TheOffice — Gamified UX Ideas

Office metaphors mapped to LLM/agent interactions. Each entry describes the UX trigger,
what it does under the hood, and rough implementation notes.

---

## Collaboration & Meetings

### 📅 Call a Meeting
**Trigger:** "Call a meeting" button — all hired agents animate walking to the meeting room.
**UX:** You type the meeting goal. Each agent responds in turn (round-robin LLM calls), building on the previous response. A chairperson (the Manager) synthesises the outputs into a final summary.
**Under the hood:** Sequential LLM calls with shared context; each agent sees the previous agents' contributions before responding.
**Output:** A "meeting minutes" block rendered in the chat.

---

### 🧠 Whiteboard Session
**Trigger:** "Open the whiteboard" — a shared canvas appears beside the chat.
**UX:** You pose a problem. Agents take turns adding bullet points or diagram nodes to the whiteboard. You can point at any item and ask an agent to expand it.
**Under the hood:** Accumulating structured state (a list of nodes/bullets) passed in each agent's system prompt alongside the original goal.
**Output:** An exportable markdown/mermaid diagram.

---

### ☕ Standup
**Trigger:** "Run standup" button, available once per session.
**UX:** Each agent is asked "What are you working on? Any blockers?" They summarise their recent activity from conversation history. Rendered as a compact card per agent, Scrum-style.
**Under the hood:** Per-agent LLM call with their message history as context, prompt constrained to two sentences.

---

### 🔁 Brainstorm Session
**Trigger:** "Brainstorm" — agents sit in a circle animation.
**UX:** You give a topic. Agents contribute ideas in random order. You can thumbs-up ideas (starred) or ask any agent to drill into one of their ideas.
**Under the hood:** Parallel LLM calls (or rapid sequential), results merged into a deduplicated idea list. Starred items carry forward as context if you continue.

---

### 🗳️ Vote on It
**Trigger:** After a brainstorm or meeting, "Put it to a vote."
**UX:** You propose a decision. Each agent votes Yes / No / Abstain with a one-sentence rationale. Manager casts the deciding vote if tied.
**Under the hood:** Each agent receives the proposal + their role system prompt + instruction to respond with a structured vote object.

---

### 🔄 Devil's Advocate
**Trigger:** "Play devil's advocate" toggle during any meeting.
**UX:** One randomly selected agent is secretly prompted to challenge every consensus point. Others don't know who it is. Revealed at the end.
**Under the hood:** That agent's system prompt is prepended with a devil's advocate instruction for the duration of the meeting.

---

## 1:1 & Direct Interactions

### 🪑 Drop by Their Desk
**Trigger:** Click directly on an agent's desk in the office scene (bypasses the supervisor).
**UX:** Opens a direct chat channel with that agent only. The routing step is skipped entirely.
**Under the hood:** Graph starts at `worker_node` directly with the clicked worker pre-populated in state.

---

### 📨 Send a Memo
**Trigger:** "Send memo" form — recipient(s), subject, body.
**UX:** Async task. Agents "read" it and respond with a brief acknowledgement or follow-up question. Replies appear in an inbox panel.
**Under the hood:** Queued background tasks, one LLM call per recipient. Responses stored and surfaced as inbox notifications.

---

### 🎤 One-on-One Review
**Trigger:** Right-click an agent card → "1:1 meeting."
**UX:** Manager mode: you review the agent's last N responses. The LLM (as Manager) suggests improvements to the agent's system prompt. You can accept, edit, or reject each suggestion before it's applied.
**Under the hood:** LLM is given the agent's system prompt + recent responses and asked to output a diff. Accepted diffs are written back to the DB.

---

### 🏖️ Mark Out of Office
**Trigger:** Toggle on an agent's card.
**UX:** Agent's desk shows an "OOO" flag. Supervisor is informed they're unavailable and routes around them. Their pending memos accumulate and deliver when they return.
**Under the hood:** `active` flag variant — agent still exists but is excluded from supervisor's worker list.

---

### 📞 Cold Call
**Trigger:** "Cold call" — picks a random agent without telling you which one.
**UX:** You chat without knowing who you're talking to. Guess at the end. Their name is revealed with a confetti pop.
**Under the hood:** Supervisor forced to a random worker; responder label hidden in the UI until reveal.

---

## Task & Project Management

### 📋 Start a Project
**Trigger:** "New project" — name it, assign agents to it.
**UX:** Creates a named workspace. All messages sent inside it are prefixed with project context. Agents assigned to the project see each other's contributions.
**Under the hood:** A project record in SQLite; a shared context string injected into every agent's system prompt for that project.

---

### 🎯 Sprint Planning
**Trigger:** "Plan a sprint" — you describe the goal.
**UX:** Agents collectively break the goal into tasks and self-assign based on their roles. Tasks appear on a Kanban-style board. You can drag-reassign.
**Under the hood:** Single LLM call to decompose goal into tasks (structured JSON), then each agent claims tasks matching their role description.

---

### ✅ Sign-off Chain
**Trigger:** An agent marks work "ready for review."
**UX:** It lands in the next agent's inbox (or Manager's) for approval. They can approve, reject with comments, or escalate. Work moves through a defined pipeline.
**Under the hood:** A `review_state` field on task records; each approval triggers the next agent's LLM call with the previous agent's output as context.

---

### 📁 File a Report
**Trigger:** "Generate report" button at end of a session or project.
**UX:** The Manager synthesises all activity into a structured report: summary, decisions made, open questions, next steps. Rendered as a printable document.
**Under the hood:** Full message history + activity log fed to LLM with a report-formatting prompt. Output as markdown.

---

### 🚨 Escalate
**Trigger:** "This isn't working" button mid-conversation.
**UX:** The current worker is bypassed. Manager takes over and explicitly acknowledges the escalation before responding.
**Under the hood:** Injects an escalation note into the system prompt; forces routing to Manager regardless of supervisor decision.

---

## Office Culture & Fun

### 🥳 Call a Party
**Trigger:** "It's Friday" button (or triggered on actual Fridays).
**UX:** All agents switch to casual/fun mode. The office scene gets confetti and music notes. Responses are playful and off-topic chit-chat is encouraged.
**Under the hood:** A `party_mode` flag that prepends "It's the end of the week, be relaxed and fun" to every system prompt for the session.

---

### 🏆 Employee of the Month
**Trigger:** Auto-computed at session end, or manually awarded.
**UX:** The agent with the most messages handled (or highest user rating) gets a trophy on their desk. They give a short acceptance speech.
**Under the hood:** Message count from session history; LLM generates the speech given the agent's persona.

---

### 💬 Office Gossip
**Trigger:** "Rumour mill" button — whispers between agents.
**UX:** Two randomly selected agents have a brief conversation about a third (or about the Manager). Shown as a chat bubble exchange. Harmlessly silly.
**Under the hood:** Two-turn LLM dialogue with each agent playing off the other's last line.

---

### 🎂 Work Anniversary
**Trigger:** Auto-triggered when an agent has been in the DB for 7 / 30 / 365 days.
**UX:** A cake appears on their desk. Other agents send short congratulatory messages. Manager gives a speech.
**Under the hood:** `created_at` comparison on startup; brief parallel LLM calls for congratulations.

---

### 💡 Suggestion Box
**Trigger:** Anonymous "suggestion" form — you submit feedback without attribution.
**UX:** The suggestion is anonymously surfaced to the Manager, who decides whether to act on it. If accepted, it modifies an agent's system prompt or the office rules.
**Under the hood:** Suggestion stored in DB; Manager LLM call decides accept/reject/defer; accepted suggestions write to system prompts.

---

### 🎲 Random Assignment
**Trigger:** "Spin the wheel" — ignores roles entirely.
**UX:** A wheel spins and picks a random agent to handle the next message, regardless of their role. Good for creative tasks or when you want a fresh perspective.
**Under the hood:** Supervisor bypassed; random agent selected from worker list.

---

## Performance & Agent Management

### 📊 Performance Review
**Trigger:** "Review quarter" — Manager reviews all agents.
**UX:** Each agent is scored on response quality, task completion, and consistency. Presented as a report card. You can give each agent a raise (enhanced system prompt) or a PIP (corrective instruction appended to prompt).
**Under the hood:** LLM evaluates recent message samples per agent against their stated role. Scoring is structured JSON. Prompt changes written to DB.

---

### 🎓 Training Day
**Trigger:** "Send to training" on an agent card.
**UX:** You upload examples of good responses. The agent's system prompt is automatically expanded with few-shot examples derived from them.
**Under the hood:** LLM summarises the examples into reusable behavioural guidelines and appends them to the system prompt.

---

### 🧬 Clone
**Trigger:** Right-click agent → "Clone."
**UX:** Creates a copy of the agent with the same role and system prompt but a new name. Useful for parallel workstreams needing the same expertise.
**Under the hood:** `INSERT` with new UUID, same fields, name suffixed with "II" or a number.

---

### 🤝 Pair Programming
**Trigger:** Select two agents → "Pair them."
**UX:** Both agents tackle the next message together. They produce a joint response — one drafts, the other reviews and amends, output is their merged answer.
**Under the hood:** Two sequential LLM calls; second agent receives first agent's draft with instruction to improve it.

---

### 🔀 Job Swap
**Trigger:** "Swap roles" between two agents for a session.
**UX:** Agent A temporarily takes Agent B's system prompt and vice versa. Revealed to the user after they notice something is off (or never — chaos mode).
**Under the hood:** Roles swapped in-memory for the session, not persisted to DB.

---

## Chaos & Edge Cases

### 🔥 Fire Drill
**Trigger:** "Fire drill!" — everyone evacuates.
**UX:** All agent avatars run to the emergency exit. All pending work is paused. A timer counts down. When it ends, everyone files back in and resumes.
**Under the hood:** A session pause; queued messages are held and delivered after the timer.

---

### 📴 Server's Down (Chaos Mode)
**Trigger:** "Chaos mode" toggle.
**UX:** 20% of messages are randomly routed to the wrong agent. Responses occasionally include a "(sorry, wrong desk)" disclaimer. Mimics the chaos of a real office.
**Under the hood:** Supervisor's routing decision is randomly overridden with a different worker.

---

### 🕵️ Undercover Boss
**Trigger:** "Go undercover" — Manager disguises themselves as a new hire.
**UX:** Manager joins as a regular worker with a fake name and bland role. Agents respond to them normally. At any point you can "reveal" the boss and see if the agents change their tone.
**Under the hood:** Manager is added to the worker list temporarily with a generic system prompt; reveal compares the before/after responses.

---

### 📣 All-Hands
**Trigger:** "Call all-hands" — everyone gathers.
**UX:** You broadcast a single message. Every active agent responds with their take on it in parallel. Responses are displayed side-by-side in a grid.
**Under the hood:** Parallel LLM calls, one per worker + Manager, all with the same message and their individual system prompts.

---

### ⏰ After Hours
**Trigger:** Automatic after a configurable time (e.g. 6 pm), or manual toggle.
**UX:** The office lights dim. Only the on-call agent (randomly chosen or designated) is available. Others show "gone home" status. The on-call agent is slightly grumpier.
**Under the hood:** Worker list filtered to on-call agent only; system prompt appended with "you're the only one here, keep it brief."

---

## Meta / Self-Referential

### 🪞 Ask the Office About Itself
**Trigger:** "How are we doing?" prompt surfaced by the Manager unprompted.
**UX:** The Manager reflects on the session so far: what went well, what was confusing, what could be delegated better.
**Under the hood:** Full activity log + message history fed to LLM with a retrospective prompt.

---

### 📰 Office Newsletter
**Trigger:** "Publish newsletter" at end of week.
**UX:** Auto-generated internal newsletter summarising the week's conversations, decisions, and highlights. Written in an over-the-top corporate tone.
**Under the hood:** Session history summarised by LLM with a newsletter-style prompt. Output as styled HTML.

---

### 🤖 New Hire Wizard
**Trigger:** "Post a job listing" instead of manually filling the hire form.
**UX:** You describe the kind of help you need in plain English ("I need someone good at writing SQL and explaining database schemas"). The LLM proposes a name, role, and system prompt. You approve or edit before hiring.
**Under the hood:** LLM generates a structured `{name, role, system_prompt}` JSON from your description. Form is pre-filled for review.

---

### 🗂️ Org Chart View
**Trigger:** "View org chart" button.
**UX:** Visual hierarchy showing Manager at top, workers below, with their roles. Clicking a node opens their system prompt for editing.
**Under the hood:** Workers queried from DB, rendered as an SVG or CSS tree. Edit saves back to DB.

---

## Implementation Priority (rough)

| Priority | Feature | Complexity |
|---|---|---|
| High | Drop by Their Desk | Low — skip supervisor |
| High | New Hire Wizard | Low — one LLM call |
| High | All-Hands | Medium — parallel calls |
| High | Call a Meeting | Medium — sequential calls |
| Medium | Standup | Medium — per-agent calls |
| Medium | Performance Review | Medium — evaluation prompt |
| Medium | File a Report | Low — summarisation prompt |
| Medium | Pair Programming | Low — two sequential calls |
| Medium | Org Chart View | Low — UI only |
| Low | Sprint Planning + Kanban | High — new data model |
| Low | Start a Project | High — new data model |
| Low | Sign-off Chain | High — new workflow state |
| Low | Office Newsletter | Low — fun/polish |
| Low | Undercover Boss | Medium — session-scoped state |
| Low | Chaos Mode | Low — routing randomisation |
