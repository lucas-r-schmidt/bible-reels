"""
src/web/auth.py
---------------
Sistema de Autenticação e Controle de Acesso para o Bible Reels Studio.
Compatível com a arquitetura FlowMedia / Buffer Gateway:
- Contas novas entram como 'pending' (aguardando aprovação).
- Usuário Admin principal (lucas.r.schmidt@gmail.com) é sempre 'admin' e 'active'.
- Hash de senhas seguro via PBKDF2-SHA256 (310.000 iterações).
- Sessões via cookie HTTP seguro (SameSite=Lax, HttpOnly).
- Painel para o Admin aprovar/bloquear usuários pendentes.
"""
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from config.settings import DB_PATH
from src.utils.logger import get_logger

log = get_logger("web_auth")

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "lucas.r.schmidt@gmail.com").strip().lower()
SESSION_COOKIE_NAME = "br_session"
PBKDF2_ITERATIONS = 310_000

# Rate limit de tentativas de login
_LOGIN_FAILURES: dict[str, list[float]] = {}
MAX_LOGIN_ATTEMPTS = 6
LOCKOUT_WINDOW_SECONDS = 300


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH), timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    return con


def init_auth_db() -> None:
    """Cria tabelas de usuários e sessões se não existirem, e inicializa o Admin."""
    with _conn() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                name TEXT NOT NULL,
                password_hash TEXT,
                role TEXT NOT NULL DEFAULT 'editor',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                last_login_at TEXT
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )

        # Limpeza de sessões expiradas
        now_iso = datetime.now(timezone.utc).isoformat()
        con.execute("DELETE FROM sessions WHERE expires_at < ?", (now_iso,))

        # Garante Admin principal sempre ativo
        if ADMIN_EMAIL:
            row = con.execute("SELECT id, role, status, password_hash FROM users WHERE email = ?", (ADMIN_EMAIL,)).fetchone()
            if not row:
                con.execute(
                    """
                    INSERT INTO users (email, name, password_hash, role, status, created_at)
                    VALUES (?, 'Lucas Schmidt', NULL, 'admin', 'active', ?)
                    """,
                    (ADMIN_EMAIL, now_iso),
                )
                log.info(f"Conta Administradora inicial provisionada: {ADMIN_EMAIL}")
            else:
                con.execute("UPDATE users SET role = 'admin', status = 'active' WHERE id = ?", (row["id"],))


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${dk.hex()}"


def verify_password(password: str, stored_hash: Optional[str]) -> bool:
    if not stored_hash or "$" not in stored_hash:
        return False
    try:
        algo, iters_str, salt, hash_hex = stored_hash.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iters_str))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


def check_rate_limit(key: str) -> bool:
    now = time.time()
    attempts = [t for t in _LOGIN_FAILURES.get(key, []) if now - t < LOCKOUT_WINDOW_SECONDS]
    _LOGIN_FAILURES[key] = attempts
    return len(attempts) < MAX_LOGIN_ATTEMPTS


def record_login_failure(key: str) -> None:
    now = time.time()
    attempts = [t for t in _LOGIN_FAILURES.get(key, []) if now - t < LOCKOUT_WINDOW_SECONDS]
    attempts.append(now)
    _LOGIN_FAILURES[key] = attempts


def clear_login_failures(key: str) -> None:
    _LOGIN_FAILURES.pop(key, None)


def _format_user(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "role": row["role"],
        "status": row["status"],
        "has_password": bool(row["password_hash"]),
        "created_at": row["created_at"],
        "last_login_at": row["last_login_at"],
    }


def get_user_by_email(email: str) -> Optional[dict[str, Any]]:
    with _conn() as con:
        row = con.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
        return _format_user(row) if row else None


def get_user_by_id(user_id: int) -> Optional[dict[str, Any]]:
    with _conn() as con:
        row = con.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _format_user(row) if row else None


def list_users() -> list[dict[str, Any]]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM users ORDER BY CASE status WHEN 'pending' THEN 0 WHEN 'active' THEN 1 ELSE 2 END, created_at DESC"
        ).fetchall()
        return [_format_user(r) for r in rows]


def authenticate_email_password(email: str, password: str) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    clean_email = email.strip().lower()
    if not clean_email or not password:
        return None, "Informe e-mail e senha."

    with _conn() as con:
        row = con.execute("SELECT * FROM users WHERE email = ?", (clean_email,)).fetchone()
        if not row:
            return None, "E-mail ou senha inválidos."

        # Primeiro acesso do Admin principal sem senha: cadastra senha informada
        if clean_email == ADMIN_EMAIL and not row["password_hash"]:
            if len(password) < 6:
                return None, "Para seu primeiro acesso de Administrador, escolha uma senha com pelo menos 6 caracteres."
            new_hash = hash_password(password)
            now_iso = datetime.now(timezone.utc).isoformat()
            con.execute(
                "UPDATE users SET password_hash = ?, role = 'admin', status = 'active', last_login_at = ? WHERE id = ?",
                (new_hash, now_iso, row["id"]),
            )
            updated = con.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone()
            log.info(f"Senha inicial configurada para o Admin: {clean_email}")
            return _format_user(updated), None

        if not row["password_hash"]:
            return None, "Conta sem senha definida."

        if not verify_password(password, row["password_hash"]):
            return None, "E-mail ou senha inválidos."

        now_iso = datetime.now(timezone.utc).isoformat()
        con.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now_iso, row["id"]))
        updated = con.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone()
        return _format_user(updated), None


def register_user(name: str, email: str, password: str) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    clean_email = email.strip().lower()
    clean_name = name.strip()
    if not clean_name:
        return None, "Informe seu nome."
    if not clean_email or "@" not in clean_email:
        return None, "Informe um e-mail válido."
    if len(password) < 6:
        return None, "A senha deve ter no mínimo 6 caracteres."

    is_admin = (clean_email == ADMIN_EMAIL)
    role = "admin" if is_admin else "editor"
    # Qualquer nova conta é pendente exceto o próprio e-mail do Admin
    status = "active" if is_admin else "pending"
    now_iso = datetime.now(timezone.utc).isoformat()
    pwd_hash = hash_password(password)

    with _conn() as con:
        existing = con.execute("SELECT * FROM users WHERE email = ?", (clean_email,)).fetchone()
        if existing:
            if is_admin and not existing["password_hash"]:
                con.execute(
                    "UPDATE users SET name = ?, password_hash = ?, role = 'admin', status = 'active', last_login_at = ? WHERE id = ?",
                    (clean_name, pwd_hash, now_iso, existing["id"]),
                )
                row = con.execute("SELECT * FROM users WHERE id = ?", (existing["id"],)).fetchone()
                return _format_user(row), None
            return None, "Já existe uma conta cadastrada com este e-mail."

        cur = con.execute(
            """
            INSERT INTO users (email, name, password_hash, role, status, created_at, last_login_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (clean_email, clean_name, pwd_hash, role, status, now_iso, now_iso),
        )
        row = con.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
        log.info(f"Novo usuário cadastrado no Bible Reels: {clean_email} (status={status})")
        return _format_user(row), None


def update_user_status(user_id: int, status: str, role: Optional[str] = None) -> tuple[bool, Optional[str]]:
    if status not in ("active", "pending", "disabled"):
        return False, f"Status inválido: {status}"

    with _conn() as con:
        row = con.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return False, "Usuário não encontrado."
        if row["email"].lower() == ADMIN_EMAIL and status != "active":
            return False, "O status do Administrador principal não pode ser alterado."

        if role and role in ("admin", "editor", "viewer"):
            con.execute("UPDATE users SET status = ?, role = ? WHERE id = ?", (status, role, user_id))
        else:
            con.execute("UPDATE users SET status = ? WHERE id = ?", (status, user_id))
        return True, None


def delete_user(user_id: int) -> tuple[bool, Optional[str]]:
    with _conn() as con:
        row = con.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return False, "Usuário não encontrado."
        if row["email"].lower() == ADMIN_EMAIL:
            return False, "O Administrador principal não pode ser excluído."
        con.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return True, None


def create_session(user_id: int, remember_me: bool = True, ip: Optional[str] = None, user_agent: Optional[str] = None) -> tuple[str, int]:
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    days = 30 if remember_me else 1
    max_age = days * 86400
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=max_age)
    with _conn() as con:
        con.execute(
            """
            INSERT INTO sessions (token_hash, user_id, expires_at, ip_address, user_agent, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (token_hash, user_id, expires.isoformat(), ip, (user_agent or "")[:250], now.isoformat()),
        )
    return raw_token, max_age


def get_session_user(raw_token: Optional[str]) -> Optional[dict[str, Any]]:
    if not raw_token:
        return None
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    now_iso = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        s_row = con.execute(
            "SELECT user_id, expires_at FROM sessions WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
        if not s_row:
            return None
        if s_row["expires_at"] < now_iso:
            con.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
            return None
        u_row = con.execute("SELECT * FROM users WHERE id = ?", (s_row["user_id"],)).fetchone()
        if not u_row or u_row["status"] == "disabled":
            con.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
            return None
        return _format_user(u_row)


def revoke_session(raw_token: Optional[str]) -> None:
    if not raw_token:
        return
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    with _conn() as con:
        con.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
