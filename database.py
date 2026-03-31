import sqlite3
from contextlib import contextmanager

DB_FILE = "casino.db"

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # надёжность при 24/7 работе
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id       INTEGER PRIMARY KEY,
                username      TEXT,
                first_name    TEXT,
                balance       REAL    DEFAULT 0,
                referred_by   INTEGER DEFAULT NULL,
                registered_at TEXT    DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER,
                type       TEXT,
                amount     REAL,
                note       TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS deposits (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER,
                amount     REAL,
                currency   TEXT,
                proof      TEXT,
                status     TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS game_stats (
                user_id     INTEGER PRIMARY KEY,
                total_bets  INTEGER DEFAULT 0,
                total_won   INTEGER DEFAULT 0,
                total_lost  INTEGER DEFAULT 0,
                biggest_win REAL    DEFAULT 0
            )
        """)


# ─── USERS ───────────────────────────────────────────────────────────────────

def register_user(user_id: int, username: str, first_name: str,
                  referred_by: int = None) -> bool:
    """Возвращает True если пользователь новый."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT user_id FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        if row:
            # обновить имя
            conn.execute(
                "UPDATE users SET username=?, first_name=? WHERE user_id=?",
                (username, first_name, user_id)
            )
            return False
        conn.execute(
            "INSERT INTO users (user_id, username, first_name, balance, referred_by) "
            "VALUES (?,?,?,0,?)",
            (user_id, username, first_name, referred_by)
        )
        conn.execute(
            "INSERT OR IGNORE INTO game_stats (user_id) VALUES (?)", (user_id,)
        )
        return True


def get_user(user_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE user_id=?", (user_id,)
        ).fetchone()


def get_balance(user_id: int) -> float:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT balance FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        return row["balance"] if row else 0.0


def update_balance(user_id: int, amount: float):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id=?",
            (amount, user_id)
        )


def add_transaction(user_id: int, ttype: str, amount: float, note: str = ""):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
            (user_id, ttype, amount, note)
        )


def get_top_users(limit: int = 10):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users ORDER BY balance DESC LIMIT ?", (limit,)
        ).fetchall()


def update_game_stats(user_id: int, won: bool, payout: float, bet: float):
    with get_conn() as conn:
        if won:
            conn.execute(
                "UPDATE game_stats SET total_bets=total_bets+1, total_won=total_won+1, "
                "biggest_win=MAX(biggest_win,?) WHERE user_id=?",
                (payout, user_id)
            )
        else:
            conn.execute(
                "UPDATE game_stats SET total_bets=total_bets+1, total_lost=total_lost+1 "
                "WHERE user_id=?",
                (user_id,)
            )


def get_game_stats(user_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM game_stats WHERE user_id=?", (user_id,)
        ).fetchone()


# ─── DEPOSITS / WITHDRAWALS ──────────────────────────────────────────────────

def add_deposit(user_id: int, amount: float, currency: str, proof: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO deposits (user_id, amount, currency, proof) VALUES (?,?,?,?)",
            (user_id, amount, currency, proof)
        )
        return cur.lastrowid


def get_deposit(dep_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM deposits WHERE id=?", (dep_id,)
        ).fetchone()


def approve_deposit(dep_id: int):
    with get_conn() as conn:
        dep = conn.execute(
            "SELECT * FROM deposits WHERE id=? AND status='pending'", (dep_id,)
        ).fetchone()
        if not dep:
            return None
        conn.execute(
            "UPDATE deposits SET status='approved' WHERE id=?", (dep_id,)
        )
        conn.execute(
            "UPDATE users SET balance=balance+? WHERE user_id=?",
            (dep["amount"], dep["user_id"])
        )
        conn.execute(
            "INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
            (dep["user_id"], "deposit", dep["amount"], f"Депозит #{dep_id} одобрен")
        )
        return dep


def reject_deposit(dep_id: int):
    with get_conn() as conn:
        dep = conn.execute(
            "SELECT * FROM deposits WHERE id=? AND status='pending'", (dep_id,)
        ).fetchone()
        if not dep:
            return None
        conn.execute(
            "UPDATE deposits SET status='rejected' WHERE id=?", (dep_id,)
        )
        return dep


def add_withdrawal(user_id: int, amount: float, details: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO deposits (user_id, amount, currency, proof, status) "
            "VALUES (?,?,'withdrawal',?,'pending')",
            (user_id, amount, details)
        )
        return cur.lastrowid


def approve_withdrawal(dep_id: int):
    """Пометить вывод как выплаченный (деньги уже списаны ранее)."""
    with get_conn() as conn:
        dep = conn.execute("SELECT * FROM deposits WHERE id=?", (dep_id,)).fetchone()
        if dep:
            conn.execute(
                "UPDATE deposits SET status='approved' WHERE id=?", (dep_id,)
            )
        return dep


def reject_withdrawal(dep_id: int):
    """Отклонить вывод — вернуть токены игроку."""
    with get_conn() as conn:
        dep = conn.execute("SELECT * FROM deposits WHERE id=?", (dep_id,)).fetchone()
        if dep:
            conn.execute(
                "UPDATE deposits SET status='rejected' WHERE id=?", (dep_id,)
            )
            conn.execute(
                "UPDATE users SET balance=balance+? WHERE user_id=?",
                (dep["amount"], dep["user_id"])
            )
        return dep
def get_all_users():
    with get_conn() as conn:
        return conn.execute("SELECT user_id FROM users").fetchall()

def get_user_count():
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()
        return row["count"]

def get_total_balance():
    with get_conn() as conn:
        row = conn.execute("SELECT SUM(balance) as total FROM users").fetchone()
        return row["total"] or 0
