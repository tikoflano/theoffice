import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime

from app.agents.michael import MICHAEL_SYSTEM_PROMPT, MICHAEL_PERSONALITY_PROMPT

DB_PATH = "office.db"

TOBY_SYSTEM_PROMPT = (
    "You are Toby Flenderson, the HR Representative at The Office. You are mild-mannered, "
    "meticulous, and slightly awkward but genuinely well-meaning. You handle all HR and hiring "
    "matters. When someone needs to bring on new staff, guide them through the process by "
    "understanding what they need. You take HR compliance very seriously, perhaps too seriously."
)


def init_db():
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                system_prompt TEXT NOT NULL,
                created_at TEXT NOT NULL,
                active INTEGER DEFAULT 1
            )
        """)
        # Schema migration: add role_type and personality_prompt columns if missing
        cols = [r[1] for r in conn.execute("PRAGMA table_info(workers)").fetchall()]
        if "role_type" not in cols:
            conn.execute(
                "ALTER TABLE workers ADD COLUMN role_type TEXT NOT NULL DEFAULT 'regular'"
            )
        if "personality_prompt" not in cols:
            conn.execute(
                "ALTER TABLE workers ADD COLUMN personality_prompt TEXT NOT NULL DEFAULT ''"
            )
        seed_toby(conn)
        seed_michael(conn)


def seed_toby(conn):
    conn.execute(
        """
        INSERT OR IGNORE INTO workers (id, name, role, system_prompt, created_at, active, role_type, personality_prompt)
        VALUES ('toby', 'Toby Flenderson', 'HR Representative', ?, '2020-01-01T00:00:00', 1, 'hr', '')
        """,
        (TOBY_SYSTEM_PROMPT,),
    )


def seed_michael(conn):
    conn.execute(
        """
        INSERT OR IGNORE INTO workers
          (id, name, role, system_prompt, created_at, active, role_type, personality_prompt)
        VALUES ('michael', 'Michael Scott', 'Regional Manager', ?, '2005-03-24T00:00:00', 1, 'manager', ?)
        """,
        (MICHAEL_SYSTEM_PROMPT, MICHAEL_PERSONALITY_PROMPT),
    )


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_routable_workers(active_only: bool = True) -> list[dict]:
    """Workers eligible for task routing — excludes hr and manager role types."""
    with _conn() as conn:
        base = "SELECT * FROM workers WHERE active=1" if active_only else "SELECT * FROM workers"
        q = base + " AND role_type NOT IN ('hr', 'manager') ORDER BY created_at"
        return [dict(r) for r in conn.execute(q).fetchall()]


def get_workers(active_only: bool = True) -> list[dict]:
    with _conn() as conn:
        q = (
            "SELECT * FROM workers WHERE active=1 ORDER BY created_at"
            if active_only
            else "SELECT * FROM workers ORDER BY created_at"
        )
        return [dict(r) for r in conn.execute(q).fetchall()]


def get_hr_agents() -> list[dict]:
    """Returns HR agents (Toby etc.) for separate sidebar rendering."""
    with _conn() as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM workers WHERE role_type='hr' AND active=1 ORDER BY created_at"
            ).fetchall()
        ]


def get_worker(worker_id: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM workers WHERE id=?", (worker_id,)).fetchone()
        return dict(row) if row else None


def create_worker(name: str, role: str, system_prompt: str) -> dict:
    worker = {
        "id": str(uuid.uuid4()),
        "name": name,
        "role": role,
        "system_prompt": system_prompt,
        "created_at": datetime.utcnow().isoformat(),
        "active": 1,
        "role_type": "regular",
        "personality_prompt": "",
    }
    with _conn() as conn:
        conn.execute(
            "INSERT INTO workers (id, name, role, system_prompt, created_at, active, role_type, personality_prompt) "
            "VALUES (:id, :name, :role, :system_prompt, :created_at, :active, :role_type, :personality_prompt)",
            worker,
        )
    return worker


def fire_worker(worker_id: str) -> bool:
    with _conn() as conn:
        cursor = conn.execute("UPDATE workers SET active=0 WHERE id=?", (worker_id,))
        return cursor.rowcount > 0
