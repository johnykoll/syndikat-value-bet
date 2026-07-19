"""
Databázová vrstva - lokálna SQLite databáza (simulácia multi-user backendu pre MVP).
Súbor sa vytvorí automaticky pri prvom spustení: synbet.db
"""

import sqlite3
import os
import datetime
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "synbet.db")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                bankroll REAL DEFAULT 1000,
                kelly_frakcia REAL DEFAULT 0.25,
                max_bet_limit REAL DEFAULT 0.05,
                global_marza REAL DEFAULT 0.04,
                pyramid_level INTEGER DEFAULT 0,
                pyramid_profit REAL DEFAULT 0,
                created_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                sport TEXT,
                liga TEXT,
                timy TEXT,
                soft_bookmaker TEXT,
                typ_marketu TEXT,
                tip TEXT,
                sharp_k REAL,
                sharp_l REAL,
                soft_kurz REAL,
                fair_kurz REAL,
                edge REAL,
                kelly_pct REAL,
                priebezna_hodnota_tiketu REAL,
                odporucany_vklad REAL,
                neposistena_cast REAL,
                proti_kurz REAL,
                proti_vklad REAL,
                skore TEXT,
                status TEXT DEFAULT 'Otvorený',
                pnl REAL,
                pyramid_level INTEGER,
                shared INTEGER DEFAULT 0,
                ai_filled INTEGER DEFAULT 0,
                is_live INTEGER DEFAULT 0,
                created_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        # Migrácia pre existujúce DB súbory vytvorené pred pridaním is_live stĺpca.
        existing_cols = [row["name"] for row in c.execute("PRAGMA table_info(tickets)").fetchall()]
        if "is_live" not in existing_cols:
            c.execute("ALTER TABLE tickets ADD COLUMN is_live INTEGER DEFAULT 0")
        c.execute("""
            CREATE TABLE IF NOT EXISTS feed_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT,
                FOREIGN KEY (ticket_id) REFERENCES tickets (id),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS feed_reactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                emoji TEXT NOT NULL,
                created_at TEXT,
                FOREIGN KEY (ticket_id) REFERENCES tickets (id),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        conn.commit()


def now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


# ---------- USERS ----------

def get_or_create_user(username: str) -> sqlite3.Row:
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = c.fetchone()
        if row:
            return row
        c.execute(
            "INSERT INTO users (username, created_at) VALUES (?, ?)",
            (username, now()),
        )
        conn.commit()
        c.execute("SELECT * FROM users WHERE username = ?", (username,))
        return c.fetchone()


def list_users():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users ORDER BY pyramid_profit DESC").fetchall()


def update_user_settings(user_id: int, bankroll: float, kelly_frakcia: float,
                          max_bet_limit: float, global_marza: float):
    with get_conn() as conn:
        conn.execute(
            """UPDATE users SET bankroll = ?, kelly_frakcia = ?, max_bet_limit = ?,
               global_marza = ? WHERE id = ?""",
            (bankroll, kelly_frakcia, max_bet_limit, global_marza, user_id),
        )


def adjust_user_bankroll(user_id: int, delta: float):
    with get_conn() as conn:
        conn.execute("UPDATE users SET bankroll = bankroll + ? WHERE id = ?", (delta, user_id))


def update_pyramid_progress(user_id: int, level: int, profit_delta: float):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET pyramid_level = ?, pyramid_profit = pyramid_profit + ? WHERE id = ?",
            (level, profit_delta, user_id),
        )


def get_user(user_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


# ---------- TICKETS ----------

def create_ticket(user_id: int, data: dict) -> int:
    fields = list(data.keys())
    placeholders = ", ".join(["?"] * len(fields))
    columns = ", ".join(fields)
    values = [data[f] for f in fields]
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            f"INSERT INTO tickets (user_id, created_at, {columns}) VALUES (?, ?, {placeholders})",
            [user_id, now()] + values,
        )
        conn.commit()
        return c.lastrowid


def update_ticket(ticket_id: int, data: dict):
    if not data:
        return
    set_clause = ", ".join([f"{k} = ?" for k in data.keys()])
    values = list(data.values()) + [ticket_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE tickets SET {set_clause} WHERE id = ?", values)


def share_ticket(ticket_id: int):
    update_ticket(ticket_id, {"shared": 1})


def get_my_tickets(user_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM tickets WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
        ).fetchall()


def get_feed_tickets():
    """Všetky zdieľané tikety zoradené od najnovšieho, spolu s menom autora."""
    with get_conn() as conn:
        return conn.execute("""
            SELECT tickets.*, users.username AS author
            FROM tickets
            JOIN users ON tickets.user_id = users.id
            WHERE tickets.shared = 1
            ORDER BY tickets.created_at DESC
        """).fetchall()


def get_ticket(ticket_id: int):
    with get_conn() as conn:
        return conn.execute("""
            SELECT tickets.*, users.username AS author
            FROM tickets JOIN users ON tickets.user_id = users.id
            WHERE tickets.id = ?
        """, (ticket_id,)).fetchone()


def get_pyramid_tickets(user_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM tickets WHERE user_id = ? AND pyramid_level IS NOT NULL ORDER BY pyramid_level",
            (user_id,),
        ).fetchall()


# ---------- FEED: COMMENTS & REACTIONS ----------

def add_comment(ticket_id: int, user_id: int, message: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO feed_comments (ticket_id, user_id, message, created_at) VALUES (?, ?, ?, ?)",
            (ticket_id, user_id, message, now()),
        )


def get_comments(ticket_id: int):
    with get_conn() as conn:
        return conn.execute("""
            SELECT feed_comments.*, users.username AS author
            FROM feed_comments JOIN users ON feed_comments.user_id = users.id
            WHERE ticket_id = ? ORDER BY feed_comments.created_at ASC
        """, (ticket_id,)).fetchall()


def add_reaction(ticket_id: int, user_id: int, emoji: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO feed_reactions (ticket_id, user_id, emoji, created_at) VALUES (?, ?, ?, ?)",
            (ticket_id, user_id, emoji, now()),
        )


def get_reaction_counts(ticket_id: int):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT emoji, COUNT(*) as cnt FROM feed_reactions WHERE ticket_id = ? GROUP BY emoji",
            (ticket_id,),
        ).fetchall()
        return {r["emoji"]: r["cnt"] for r in rows}
