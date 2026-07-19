"""
Databázová vrstva - lokálna SQLite databáza (simulácia multi-user backendu pre MVP).
Súbor sa vytvorí automaticky pri prvom spustení: synbet.db

Táto verzia obsahuje GENERICKÝ samo-opravný migračný mechanizmus (_ensure_columns):
pri každom volaní init_db() sa porovná, aké stĺpce tabuľka aktuálne má, a čokoľvek
chýba (napr. po pridaní novej funkcie appky) sa bezpečne dorovná cez ALTER TABLE.
Toto rieši presne situáciu na Streamlit Cloude, kde databázový súbor prežíva
reštarty appky, ale kód sa medzičasom posunul dopredu.
"""

import sqlite3
import os
import datetime
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "synbet.db")

# Kompletný zoznam stĺpcov, ktoré MUSIA existovať v tabuľke `users`.
# Kľúč = názov stĺpca, hodnota = SQL typ + DEFAULT použitý pri ALTER TABLE aj CREATE TABLE.
USERS_COLUMNS = {
    "username": "TEXT UNIQUE NOT NULL",
    "bankroll": "REAL DEFAULT 1000",
    "kelly_frakcia": "REAL DEFAULT 0.25",
    "max_bet_limit": "REAL DEFAULT 0.05",
    "global_marza": "REAL DEFAULT 0.04",
    "pyramid_level": "INTEGER DEFAULT 0",
    "pyramid_profit": "REAL DEFAULT 0",       # historický názov, ponechaný pre spätnú kompatibilitu
    "pyramid_money": "REAL DEFAULT 0.0",      # rovnaká hodnota ako pyramid_profit, udržiavaná synchrónne
    "pyramid_body": "INTEGER DEFAULT 0",      # Nety (vernostné body)
    "pyramid_hlavna_cena": "INTEGER DEFAULT 0",
    "created_at": "TEXT",
}

# Kompletný zoznam stĺpcov, ktoré MUSIA existovať v tabuľke `tickets` (okrem PK a FK).
TICKETS_COLUMNS = {
    "user_id": "INTEGER NOT NULL",
    "sport": "TEXT",
    "liga": "TEXT",
    "timy": "TEXT",
    "soft_bookmaker": "TEXT",
    "typ_marketu": "TEXT",
    "tip": "TEXT",
    "sharp_k": "REAL",
    "sharp_l": "REAL",
    "soft_kurz": "REAL",
    "fair_kurz": "REAL",
    "edge": "REAL",
    "kelly_pct": "REAL",
    "priebezna_hodnota_tiketu": "REAL",
    "odporucany_vklad": "REAL",
    "neposistena_cast": "REAL",
    "proti_kurz": "REAL",
    "proti_vklad": "REAL",
    "skore": "TEXT",
    "status": "TEXT DEFAULT 'Otvorený'",
    "pnl": "REAL",
    "pyramid_level": "INTEGER",
    "shared": "INTEGER DEFAULT 0",
    "ai_filled": "INTEGER DEFAULT 0",
    "is_live": "INTEGER DEFAULT 0",
    "mix_tiket": "INTEGER DEFAULT 0",
    "match_date": "TEXT",   # dátum zápasu, zadaný ručne používateľom (ISO 'YYYY-MM-DD')
    "match_time": "TEXT",   # čas začiatku zápasu, zadaný ručne používateľom (napr. '15:30')
    "placed_at": "TEXT",    # automatický systémový timestamp momentu podania tiketu
    "sharp_provider": "TEXT",  # názov sharp protistrany z arbitráže (napr. Betdaq, Pinnacle)
    "liquidity": "TEXT",       # likvidita protistrany z BetBurger screenshotu (napr. "150€")
    "created_at": "TEXT",
}


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


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict):
    """
    Samo-opravná migrácia: porovná stĺpce, ktoré tabuľka `table` aktuálne má,
    so zoznamom `columns`, a čokoľvek chýba, bezpečne doplní cez ALTER TABLE.
    Bezpečné volať opakovane pri každom štarte appky - už existujúce stĺpce sa preskočia.
    """
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for col_name, col_def in columns.items():
        if col_name in existing:
            continue
        # ALTER TABLE ADD COLUMN nepodporuje UNIQUE/NOT NULL bez DEFAULT na existujúcich riadkoch,
        # takže pre dodatočnú migráciu očistíme definíciu len na typ + prípadný DEFAULT.
        safe_def = col_def.replace("UNIQUE NOT NULL", "TEXT").replace("NOT NULL", "")
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {safe_def}")
        except sqlite3.OperationalError:
            # stĺpec medzitým mohol pribudnúť (napr. súbežný proces) - bezpečné ignorovať
            pass


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
                pyramid_money REAL DEFAULT 0.0,
                pyramid_body INTEGER DEFAULT 0,
                pyramid_hlavna_cena INTEGER DEFAULT 0,
                created_at TEXT
            )
        """)
        _ensure_columns(conn, "users", USERS_COLUMNS)

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
                mix_tiket INTEGER DEFAULT 0,
                match_date TEXT,
                match_time TEXT,
                placed_at TEXT,
                sharp_provider TEXT,
                liquidity TEXT,
                created_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        _ensure_columns(conn, "tickets", TICKETS_COLUMNS)

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


def update_pyramid_progress(user_id: int, level: int, profit_delta: float, reward: dict = None):
    """
    Aktualizuje level a pripisuje odmenu podľa Bodu 2.5.1 oficiálnych pravidiel:
    - reward["type"] == "body"          -> pripočíta sa do pyramid_body (Nety)
    - reward["type"] == "eur"           -> pripočíta sa do pyramid_profit AJ pyramid_money (€)
    - reward["type"] == "hlavna_cena"   -> nastaví sa pyramid_hlavna_cena = 1

    profit_delta zostáva ako doplnkové reálne PnL zápasu (nezávislé od odmeny za level).
    pyramid_profit a pyramid_money sa udržiavajú synchrónne - appka historicky používala
    pyramid_profit, no pyramid_money je udržiavaný ako rovnocenný alias pre prípad, že ho
    niektorá stránka číta priamo.
    """
    with get_conn() as conn:
        conn.execute(
            """UPDATE users
               SET pyramid_level = ?,
                   pyramid_profit = pyramid_profit + ?,
                   pyramid_money = pyramid_money + ?
               WHERE id = ?""",
            (level, profit_delta or 0, profit_delta or 0, user_id),
        )
        if reward:
            if reward["type"] == "body":
                conn.execute(
                    "UPDATE users SET pyramid_body = pyramid_body + ? WHERE id = ?",
                    (reward["amount"], user_id),
                )
            elif reward["type"] == "eur":
                conn.execute(
                    """UPDATE users
                       SET pyramid_profit = pyramid_profit + ?,
                           pyramid_money = pyramid_money + ?
                       WHERE id = ?""",
                    (reward["amount"], reward["amount"], user_id),
                )
            elif reward["type"] == "hlavna_cena":
                conn.execute(
                    "UPDATE users SET pyramid_hlavna_cena = 1 WHERE id = ?",
                    (user_id,),
                )


def get_user(user_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


# ---------- TICKETS ----------

def create_ticket(user_id: int, data: dict) -> int:
    """
    Vytvorí nový tiket. `placed_at` sa zapisuje automaticky (systémový čas podania,
    nezávislý od `match_date`/`match_time`, ktoré si zadáva používateľ ručne).
    Ak `data` už obsahuje kľúč `placed_at` (zriedkavé, napr. budúca API integrácia),
    táto explicitná hodnota má prednosť pred automatickým systémovým časom.
    """
    data = dict(data)  # nemutovať vstup volajúceho
    explicit_placed_at = data.pop("placed_at", None)
    fields = list(data.keys())
    placeholders = ", ".join(["?"] * len(fields))
    columns = ", ".join(fields)
    values = [data[f] for f in fields]
    ts = now()
    placed_at = explicit_placed_at or ts
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            f"INSERT INTO tickets (user_id, created_at, placed_at, {columns}) VALUES (?, ?, ?, {placeholders})",
            [user_id, ts, placed_at] + values,
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


def unshare_ticket(ticket_id: int):
    """Stiahne tiket zo Syndikátneho Feedu späť do súkromného režimu (shared = 0)."""
    update_ticket(ticket_id, {"shared": 0})


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


def get_private_tickets(user_id: int):
    """Tikety, ktoré patria danému používateľovi a NEBOLI zdieľané do Syndikátneho Feedu."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM tickets WHERE user_id = ? AND shared = 0 ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()


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
