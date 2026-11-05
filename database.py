import sqlite3
from datetime import datetime

DB = "bot.db"


def connect():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = connect()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        points INTEGER DEFAULT 0,
        referred_by INTEGER,
        captcha_ok INTEGER DEFAULT 0,
        joined_ok INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT UNIQUE,
        title TEXT,
        required INTEGER DEFAULT 1
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        product TEXT,
        points INTEGER,
        status TEXT DEFAULT 'pending',
        created_at TEXT
    )
    """)

    conn.commit()
    conn.close()


def add_user(user_id, username, referred_by=None):
    conn = connect()
    cur = conn.cursor()

    cur.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    exists = cur.fetchone()

    if not exists:
        cur.execute("""
        INSERT INTO users
        (user_id, username, referred_by, created_at)
        VALUES (?, ?, ?, ?)
        """, (
            user_id,
            username,
            referred_by,
            datetime.now().isoformat()
        ))

        if referred_by and referred_by != user_id:
            cur.execute("""
            UPDATE users
            SET points = points + 1
            WHERE user_id = ?
            """, (referred_by,))

    conn.commit()
    conn.close()


def get_user(user_id):
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = cur.fetchone()
    conn.close()
    return user


def set_captcha_ok(user_id):
    conn = connect()
    conn.execute(
        "UPDATE users SET captcha_ok=1 WHERE user_id=?",
        (user_id,)
    )
    conn.commit()
    conn.close()


def set_joined_ok(user_id):
    conn = connect()
    conn.execute(
        "UPDATE users SET joined_ok=1 WHERE user_id=?",
        (user_id,)
    )
    conn.commit()
    conn.close()


def get_points(user_id):
    user = get_user(user_id)
    return user["points"] if user else 0


def remove_points(user_id, points):
    conn = connect()
    cur = conn.cursor()

    cur.execute("""
    UPDATE users
    SET points = points - ?
    WHERE user_id=? AND points >= ?
    """, (points, user_id, points))

    success = cur.rowcount > 0

    conn.commit()
    conn.close()

    return success


def add_channel(chat_id, title):
    conn = connect()
    conn.execute("""
    INSERT OR IGNORE INTO channels(chat_id, title)
    VALUES (?, ?)
    """, (chat_id, title))
    conn.commit()
    conn.close()


def remove_channel(chat_id):
    conn = connect()
    conn.execute(
        "DELETE FROM channels WHERE chat_id=?",
        (chat_id,)
    )
    conn.commit()
    conn.close()


def get_channels():
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM channels WHERE required=1")
    rows = cur.fetchall()
    conn.close()
    return rows


def create_request(user_id, username, product, points):
    conn = connect()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO requests
    (user_id, username, product, points, created_at)
    VALUES (?, ?, ?, ?, ?)
    """, (
        user_id,
        username,
        product,
        points,
        datetime.now().isoformat()
    ))

    request_id = cur.lastrowid

    conn.commit()
    conn.close()

    return request_id


def update_request(request_id, status):
    conn = connect()
    conn.execute("""
    UPDATE requests
    SET status=?
    WHERE id=?
    """, (status, request_id))
    conn.commit()
    conn.close()


def get_request(request_id):
    conn = connect()
    cur = conn.cursor()

    cur.execute("""
    SELECT * FROM requests
    WHERE id=?
    """, (request_id,))

    row = cur.fetchone()
    conn.close()

    return row


def users_count():
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()[0]
    conn.close()
    return count
