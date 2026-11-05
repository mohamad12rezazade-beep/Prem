import os
import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")


def get_conn():
    return psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row
    )


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    points INTEGER NOT NULL DEFAULT 0,
                    referred_by BIGINT,
                    referral_count INTEGER NOT NULL DEFAULT 0,
                    captcha_verified BOOLEAN NOT NULL DEFAULT FALSE,
                    membership_verified BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS forced_channels (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    title TEXT,
                    protected BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    product TEXT NOT NULL,
                    points INTEGER NOT NULL,
                    telegram_username TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            cur.execute("""
                INSERT INTO forced_channels
                (username, title, protected)
                VALUES
                ('@Poneix', 'Poneix', TRUE),
                ('@BET_1XZX', 'BET_1XZX', TRUE)
                ON CONFLICT (username) DO NOTHING
            """)

        conn.commit()


def create_user(user_id, username=None, referred_by=None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (user_id, username, referred_by)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO NOTHING
            """, (user_id, username, referred_by))

        conn.commit()


def get_user(user_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM users WHERE user_id = %s",
                (user_id,)
            )
            return cur.fetchone()


def add_points(user_id, amount):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users
                SET points = points + %s
                WHERE user_id = %s
            """, (amount, user_id))

        conn.commit()


def get_points(user_id):
    user = get_user(user_id)
    return user["points"] if user else 0


def set_captcha_verified(user_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users
                SET captcha_verified = TRUE
                WHERE user_id = %s
            """, (user_id,))

        conn.commit()


def set_membership_verified(user_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users
                SET membership_verified = TRUE
                WHERE user_id = %s
            """, (user_id,))

        conn.commit()


def get_forced_channels():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT *
                FROM forced_channels
                ORDER BY id
            """)
            return cur.fetchall()


def add_forced_channel(username, title=None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO forced_channels (username, title)
                VALUES (%s, %s)
                ON CONFLICT (username) DO NOTHING
            """, (username, title))

        conn.commit()


def remove_forced_channel(username):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM forced_channels
                WHERE username = %s
                AND protected = FALSE
            """, (username,))

        conn.commit()


def create_order(user_id, product, points, telegram_username):
    with get_conn() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT points
                FROM users
                WHERE user_id = %s
                FOR UPDATE
            """, (user_id,))

            user = cur.fetchone()

            if not user or user["points"] < points:
                return False

            cur.execute("""
                UPDATE users
                SET points = points - %s
                WHERE user_id = %s
            """, (points, user_id))

            cur.execute("""
                INSERT INTO orders
                    (user_id, product, points, telegram_username)
                VALUES
                    (%s, %s, %s, %s)
                RETURNING id
            """, (
                user_id,
                product,
                points,
                telegram_username
            ))

            order_id = cur.fetchone()["id"]

        conn.commit()

    return order_id


def update_order_status(order_id, status):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE orders
                SET status = %s
                WHERE id = %s
            """, (status, order_id))

        conn.commit()


def get_order(order_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT *
                FROM orders
                WHERE id = %s
            """, (order_id,))
            return cur.fetchone()
