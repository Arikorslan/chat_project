from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import bcrypt

PROJECT_ROOT = Path(__file__).resolve().parent.parent
USERS_PATH = PROJECT_ROOT / "Backend_logic" / "users.json"

DEFAULT_USER_STATUS = "offline"


def _ensure_users_file() -> None:
    if not USERS_PATH.exists():
        save_users({})


def load_users() -> Dict[str, Any]:
    _ensure_users_file()
    try:
        with USERS_PATH.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError):
        return {}


def save_users(users: Dict[str, Any]) -> None:
    with USERS_PATH.open("w", encoding="utf-8") as handle:
        json.dump(users, handle, indent=2)


def _hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class UserStorage:
    def __init__(self) -> None:
        self.users = load_users()

    def save(self) -> None:
        save_users(self.users)

    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        return self.users.get(username)

    def create_user(self, username: str, password: str, email: Optional[str] = None) -> Dict[str, Any]:
        if username in self.users:
            raise ValueError("username_already_exists")
        if len(password) < 6:
            raise ValueError("password_too_short")

        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        user_record = {
            "username": username,
            "password_hash": password_hash,
            "email": email or "",
            "email_verified": False,
            "friends": [],
            "incoming_requests": [],
            "outgoing_requests": [],
            "blocked": [],
            "session_tokens": [],
            "last_seen": None,
            "created_at": time.time(),
        }
        self.users[username] = user_record
        self.save()
        return user_record

    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        user = self.get_user(username)
        if not user:
            return None
        stored_hash = user.get("password_hash", "")
        if bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8")):
            return user
        return None

    def create_session_token(self, username: str) -> str:
        token = secrets.token_urlsafe(32)
        hashed = _hash_session_token(token)
        user = self.get_user(username)
        if not user:
            raise ValueError("user_not_found")
        user.setdefault("session_tokens", []).append(hashed)
        self.save()
        return token

    def verify_session_token(self, username: str, token: str) -> bool:
        user = self.get_user(username)
        if not user:
            return False
        hashed = _hash_session_token(token)
        return hashed in user.get("session_tokens", [])

    def revoke_session_token(self, username: str, token: str) -> None:
        user = self.get_user(username)
        if not user:
            return
        hashed = _hash_session_token(token)
        user["session_tokens"] = [t for t in user.get("session_tokens", []) if t != hashed]
        self.save()

    def add_friend_request(self, sender: str, target: str) -> None:
        if sender == target:
            raise ValueError("cannot_friend_self")
        sender_user = self.get_user(sender)
        target_user = self.get_user(target)
        if not sender_user or not target_user:
            raise ValueError("user_not_found")
        if target in sender_user.get("blocked", []):
            raise ValueError("target_blocked")
        if sender in target_user.get("blocked", []):
            raise ValueError("blocked_by_target")
        if target in sender_user.get("friends", []):
            raise ValueError("already_friends")
        if target in sender_user.get("outgoing_requests", []):
            raise ValueError("request_already_sent")
        if sender in target_user.get("incoming_requests", []):
            raise ValueError("request_already_pending")

        sender_user.setdefault("outgoing_requests", []).append(target)
        target_user.setdefault("incoming_requests", []).append(sender)
        self.save()

    def respond_friend_request(self, target: str, sender: str, accept: bool) -> None:
        sender_user = self.get_user(sender)
        target_user = self.get_user(target)
        if not sender_user or not target_user:
            raise ValueError("user_not_found")
        if sender not in target_user.get("incoming_requests", []):
            raise ValueError("request_not_found")

        target_user["incoming_requests"] = [user for user in target_user.get("incoming_requests", []) if user != sender]
        sender_user["outgoing_requests"] = [user for user in sender_user.get("outgoing_requests", []) if user != target]

        if accept:
            sender_user.setdefault("friends", []).append(target)
            target_user.setdefault("friends", []).append(sender)
        self.save()

    def block_user(self, username: str, blocked_username: str) -> None:
        user = self.get_user(username)
        blocked = self.get_user(blocked_username)
        if not user or not blocked:
            raise ValueError("user_not_found")
        if blocked_username not in user.get("blocked", []):
            user.setdefault("blocked", []).append(blocked_username)

        user["incoming_requests"] = [u for u in user.get("incoming_requests", []) if u != blocked_username]
        user["outgoing_requests"] = [u for u in user.get("outgoing_requests", []) if u != blocked_username]
        user["friends"] = [u for u in user.get("friends", []) if u != blocked_username]
        blocked["friends"] = [u for u in blocked.get("friends", []) if u != username]
        self.save()

    def is_blocked(self, username: str, target: str) -> bool:
        user = self.get_user(username)
        if not user:
            return False
        return target in user.get("blocked", [])

    def get_friends(self, username: str) -> List[str]:
        user = self.get_user(username)
        if not user:
            return []
        return list(user.get("friends", []))

    def get_pending_friend_requests(self, username: str) -> List[str]:
        user = self.get_user(username)
        if not user:
            return []
        return list(user.get("incoming_requests", []))

    def update_last_seen(self, username: str, timestamp: float) -> None:
        user = self.get_user(username)
        if not user:
            return
        user["last_seen"] = timestamp
        self.save()

    def get_last_seen(self, username: str) -> Optional[float]:
        user = self.get_user(username)
        if not user:
            return None
        return user.get("last_seen")
