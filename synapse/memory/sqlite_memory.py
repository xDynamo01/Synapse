from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from synapse.config.models import DB_PATH


class MemoryStore:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                create table if not exists sessions (
                    id text primary key,
                    title text,
                    created_at text not null,
                    updated_at text not null
                );
                create table if not exists messages (
                    id integer primary key autoincrement,
                    session_id text not null,
                    agent_name text not null,
                    role text not null,
                    content text not null,
                    created_at text not null
                );
                create table if not exists long_memory (
                    scope text primary key,
                    user_name text default 'Usuario',
                    profile text default '',
                    summary text default '',
                    updated_at text not null
                );
                create table if not exists agent_memory (
                    agent_name text primary key,
                    summary text default '',
                    updated_at text not null
                );
                """
            )

    def ensure_session(self, session_id: str) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as db:
            db.execute(
                "insert or ignore into sessions(id,title,created_at,updated_at) values(?,?,?,?)",
                (session_id, "Synapse session", now, now),
            )

    def add_message(self, session_id: str, agent_name: str, role: str, content: str) -> None:
        self.ensure_session(session_id)
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as db:
            db.execute(
                "insert into messages(session_id,agent_name,role,content,created_at) values(?,?,?,?,?)",
                (session_id, agent_name, role, content, now),
            )
            db.execute("update sessions set updated_at=? where id=?", (now, session_id))

    def history(self, session_id: str, limit: int = 12, agent_name: str | None = None) -> list[dict[str, str]]:
        sql = "select role, content from messages where session_id=?"
        params: list[object] = [session_id]
        if agent_name:
            sql += " and agent_name=?"
            params.append(agent_name)
        sql += " order by id desc limit ?"
        params.append(limit)
        with self._connect() as db:
            rows = db.execute(sql, params).fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]

    def all_history_text(self, session_id: str, limit: int = 50) -> str:
        with self._connect() as db:
            rows = db.execute(
                "select role, content from messages where session_id=? order by id desc limit ?",
                (session_id, limit),
            ).fetchall()
        return "\n".join(f"{row['role'].upper()}: {row['content']}" for row in reversed(rows))

    def get_long_memory(self, scope: str = "global") -> dict[str, str]:
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as db:
            db.execute(
                "insert or ignore into long_memory(scope,user_name,profile,summary,updated_at) values(?,?,?,?,?)",
                (scope, "Usuario", "", "", now),
            )
            row = db.execute("select * from long_memory where scope=?", (scope,)).fetchone()
        return dict(row)

    def update_long_memory(self, summary: str, scope: str = "global", profile: str | None = None) -> None:
        current = self.get_long_memory(scope)
        with self._connect() as db:
            db.execute(
                "update long_memory set summary=?, profile=?, updated_at=? where scope=?",
                (summary, current["profile"] if profile is None else profile, datetime.now().isoformat(timespec="seconds"), scope),
            )

    def forget(self, scope: str = "global") -> None:
        with self._connect() as db:
            db.execute(
                "update long_memory set summary='', profile='', updated_at=? where scope=?",
                (datetime.now().isoformat(timespec="seconds"), scope),
            )

    def reset_session(self, session_id: str) -> None:
        with self._connect() as db:
            db.execute("delete from messages where session_id=?", (session_id,))
