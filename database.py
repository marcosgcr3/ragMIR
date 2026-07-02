import hashlib
import os
import uuid
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

# Password utilities using standard hashlib pbkdf2
def hash_password(password: str, salt: bytes = None) -> tuple:
    if salt is None:
        salt = os.urandom(16)
    pw_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return pw_hash.hex(), salt.hex()

def verify_password(password: str, password_hash_hex: str, salt_hex: str) -> bool:
    salt = bytes.fromhex(salt_hex)
    pw_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return pw_hash.hex() == password_hash_hex

def get_db_connection(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(exist_ok=True, parents=True)
    
    with get_db_connection(db_path) as conn:
        # Create users table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create user_sessions table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        # Create chat_sessions table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        # Create messages table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                image_base64 TEXT,
                sources TEXT, -- stored as JSON string
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
            )
        """)
        
        # Create usage_stats table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS usage_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                query_text TEXT NOT NULL,
                response_text TEXT NOT NULL,
                tokens_used INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        conn.commit()
        
    # Auto-populate Marcos and Elsa
    cto_password = os.environ.get("CTO_PASSWORD", "ragmir2026")
    
    with get_db_connection(db_path) as conn:
        for username in ["Marcos", "Elsa"]:
            cur = conn.cursor()
            cur.execute("SELECT id FROM users WHERE username = ?", (username,))
            row = cur.fetchone()
            if not row:
                pw_hash, salt = hash_password(cto_password)
                conn.execute(
                    "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
                    (username, pw_hash, salt)
                )
                print(f"[!] Usuario inicial creado: {username}")
        conn.commit()

# Session Management
def create_session(db_path: Path, user_id: int, days_valid: int = 30) -> str:
    token = uuid.uuid4().hex
    expires_at = (datetime.utcnow() + timedelta(days=days_valid)).isoformat()
    with get_db_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO user_sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, expires_at)
        )
        conn.commit()
    return token

def validate_session(db_path: Path, token: str) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    now = datetime.utcnow().isoformat()
    with get_db_connection(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT u.id, u.username FROM user_sessions s JOIN users u ON s.user_id = u.id WHERE s.token = ? AND s.expires_at > ?",
            (token, now)
        )
        row = cur.fetchone()
        if row:
            return {"id": row["id"], "username": row["username"]}
    return None

def delete_session(db_path: Path, token: str) -> None:
    if not token:
        return
    with get_db_connection(db_path) as conn:
        conn.execute("DELETE FROM user_sessions WHERE token = ?", (token,))
        conn.commit()

# Chat Sessions CRUD
def get_user_sessions(db_path: Path, user_id: int) -> List[Dict[str, Any]]:
    with get_db_connection(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, title, created_at FROM chat_sessions WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        )
        return [dict(row) for row in cur.fetchall()]

def create_user_session(db_path: Path, user_id: int, session_id: str, title: str) -> Dict[str, Any]:
    with get_db_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO chat_sessions (id, user_id, title) VALUES (?, ?, ?)",
            (session_id, user_id, title)
        )
        conn.commit()
    return {"id": session_id, "title": title}

def delete_user_session(db_path: Path, user_id: int, session_id: str) -> None:
    with get_db_connection(db_path) as conn:
        conn.execute(
            "DELETE FROM chat_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id)
        )
        conn.commit()

# Messages CRUD
def get_session_messages(db_path: Path, session_id: str) -> List[Dict[str, Any]]:
    with get_db_connection(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT role, content, image_base64, sources, created_at FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,)
        )
        rows = []
        for r in cur.fetchall():
            row = dict(r)
            if row["sources"]:
                try:
                    row["sources"] = json.loads(row["sources"])
                except Exception:
                    row["sources"] = []
            else:
                row["sources"] = []
            rows.append(row)
        return rows

def add_session_message(db_path: Path, session_id: str, role: str, content: str, image_base64: str = None, sources: List = None) -> None:
    sources_str = json.dumps(sources) if sources else None
    with get_db_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO messages (session_id, role, content, image_base64, sources) VALUES (?, ?, ?, ?, ?)",
            (session_id, role, content, image_base64, sources_str)
        )
        conn.commit()

# Statistics & Analytics
def log_usage(db_path: Path, user_id: int, query_text: str, response_text: str, tokens_used: int = 0) -> None:
    with get_db_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO usage_stats (user_id, query_text, response_text, tokens_used) VALUES (?, ?, ?, ?)",
            (user_id, query_text, response_text, tokens_used)
        )
        conn.commit()

def get_user_stats(db_path: Path, user_id: int) -> Dict[str, Any]:
    with get_db_connection(db_path) as conn:
        cur = conn.cursor()
        
        # Total queries
        cur.execute("SELECT COUNT(*) FROM usage_stats WHERE user_id = ?", (user_id,))
        total_queries = cur.fetchone()[0]
        
        # Total tokens used
        cur.execute("SELECT SUM(tokens_used) FROM usage_stats WHERE user_id = ?", (user_id,))
        total_tokens = cur.fetchone()[0] or 0
        
        # Active days
        cur.execute("SELECT COUNT(DISTINCT DATE(created_at)) FROM usage_stats WHERE user_id = ?", (user_id,))
        active_days = cur.fetchone()[0]
        
        # Recent queries count per day (last 7 days)
        cur.execute("""
            SELECT DATE(created_at) as date, COUNT(*) as count 
            FROM usage_stats 
            WHERE user_id = ? AND created_at >= date('now', '-7 days')
            GROUP BY DATE(created_at)
            ORDER BY DATE(created_at) ASC
        """, (user_id,))
        queries_by_day = [dict(row) for row in cur.fetchall()]
        
        return {
            "total_queries": total_queries,
            "total_tokens": total_tokens,
            "active_days": active_days,
            "queries_by_day": queries_by_day
        }
