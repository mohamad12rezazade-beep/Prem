import os
from datetime import datetime, timezone
from supabase import create_client, Client

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

supabase: Client = create_client(url, key)


def now():
    return datetime.now(timezone.utc).isoformat()


def add_user(user_id, username, referred_by=None):
    result = supabase.table("users").select("*").eq(
        "user_id", user_id
    ).execute()

    if result.data:
        return

    supabase.table("users").insert({
        "user_id": user_id,
        "username": username,
        "points": 0,
        "referred_by": referred_by,
        "captcha_ok": False,
        "joined_ok": False,
        "created_at": now()
    }).execute()

    if referred_by and referred_by != user_id:
        ref = supabase.table("users").select(
            "user_id"
        ).eq("user_id", referred_by).execute()

        if ref.data:
            supabase.rpc(
                "add_points",
                {
                    "target_user_id": referred_by,
                    "amount": 1
                }
            ).execute()


def get_user(user_id):
    result = supabase.table("users").select("*").eq(
        "user_id", user_id
    ).maybe_single().execute()

    return result.data


def set_captcha_ok(user_id):
    supabase.table("users").update({
        "captcha_ok": True
    }).eq("user_id", user_id).execute()


def set_joined_ok(user_id):
    supabase.table("users").update({
        "joined_ok": True
    }).eq("user_id", user_id).execute()


def get_points(user_id):
    user = get_user(user_id)
    return int(user["points"]) if user else 0


def remove_points(user_id, amount):
    result = supabase.rpc(
        "remove_points",
        {
            "target_user_id": user_id,
            "amount": amount
        }
    ).execute()

    return bool(result.data)


def get_channels():
    result = supabase.table("channels").select(
        "*"
    ).eq("required", True).execute()

    return result.data


def add_channel(chat_id, title):
    existing = supabase.table("channels").select(
        "id"
    ).eq("chat_id", chat_id).execute()

    if existing.data:
        return False

    supabase.table("channels").insert({
        "chat_id": chat_id,
        "title": title,
        "required": True,
        "protected": False
    }).execute()

    return True


def remove_channel(chat_id):
    channel = supabase.table("channels").select(
        "*"
    ).eq("chat_id", chat_id).maybe_single().execute()

    if not channel.data:
        return False

    if channel.data.get("protected"):
        return False

    supabase.table("channels").delete().eq(
        "chat_id", chat_id
    ).execute()

    return True


def create_request(user_id, username, product, points):
    result = supabase.table("requests").insert({
        "user_id": user_id,
        "username": username,
        "product": product,
        "points": points,
        "status": "pending",
        "created_at": now()
    }).execute()

    return result.data[0]["id"]


def get_request(request_id):
    result = supabase.table("requests").select(
        "*"
    ).eq("id", request_id).maybe_single().execute()

    return result.data


def update_request(request_id, status):
    supabase.table("requests").update({
        "status": status
    }).eq("id", request_id).execute()


def users_count():
    result = supabase.table("users").select(
        "user_id", count="exact"
    ).execute()

    return result.count or 0
