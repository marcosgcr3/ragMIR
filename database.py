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
        
        # Drop old test tables if we need to modify schema
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(test_sessions)")
        cols = [c[1] for c in cur.fetchall()]
        if cols and "difficulty" not in cols:
            conn.execute("DROP TABLE IF EXISTS test_answers")
            conn.execute("DROP TABLE IF EXISTS test_sessions")
            
        # Create test_sessions table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS test_sessions (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                subject TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                total_questions INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        # Create question_pool table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS question_pool (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                question TEXT NOT NULL,
                options TEXT NOT NULL, -- JSON string
                correct_index INTEGER NOT NULL,
                explanation TEXT NOT NULL,
                source_doc TEXT NOT NULL,
                source_page TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create test_answers table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS test_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_session_id TEXT NOT NULL,
                question_id INTEGER,
                is_correct INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (test_session_id) REFERENCES test_sessions(id) ON DELETE CASCADE,
                FOREIGN KEY (question_id) REFERENCES question_pool(id) ON DELETE SET NULL
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
            "INSERT INTO chat_sessions (id, user_id, title) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET title = excluded.title",
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

# Test Sessions & Simulator Operations
def create_test_session(db_path: Path, user_id: int, test_id: str, subject: str, difficulty: str, total_questions: int) -> None:
    with get_db_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO test_sessions (id, user_id, subject, difficulty, total_questions) VALUES (?, ?, ?, ?, ?)",
            (test_id, user_id, subject, difficulty, total_questions)
        )
        conn.commit()

def log_test_answer(db_path: Path, test_session_id: str, question_id: int, is_correct: int) -> None:
    with get_db_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO test_answers (test_session_id, question_id, is_correct) VALUES (?, ?, ?)",
            (test_session_id, question_id, is_correct)
        )
        conn.commit()

def get_test_stats(db_path: Path, user_id: int) -> Dict[str, Any]:
    with get_db_connection(db_path) as conn:
        cur = conn.cursor()
        
        # Total questions answered
        cur.execute("""
            SELECT COUNT(*) 
            FROM test_answers a 
            JOIN test_sessions s ON a.test_session_id = s.id 
            WHERE s.user_id = ?
        """, (user_id,))
        total_answers = cur.fetchone()[0]
        
        # Correct questions answered
        cur.execute("""
            SELECT COUNT(*) 
            FROM test_answers a 
            JOIN test_sessions s ON a.test_session_id = s.id 
            WHERE s.user_id = ? AND a.is_correct = 1
        """, (user_id,))
        correct_answers = cur.fetchone()[0]
        
        # Breakdown by subject (joining with question_pool to get subject of the question)
        cur.execute("""
            SELECT q.subject, COUNT(*) as total, SUM(a.is_correct) as correct
            FROM test_answers a 
            JOIN test_sessions s ON a.test_session_id = s.id 
            JOIN question_pool q ON a.question_id = q.id
            WHERE s.user_id = ?
            GROUP BY q.subject
        """, (user_id,))
        
        subject_breakdown = []
        for row in cur.fetchall():
            subj = row["subject"]
            tot = row["total"]
            corr = row["correct"] or 0
            pct = round((corr / tot) * 100, 1) if tot > 0 else 0
            subject_breakdown.append({
                "subject": subj,
                "total": tot,
                "correct": corr,
                "incorrect": tot - corr,
                "percent": pct
            })
            
        success_rate = round((correct_answers / total_answers) * 100, 1) if total_answers > 0 else 0
        
        return {
            "total_answers": total_answers,
            "correct_answers": correct_answers,
            "success_rate": success_rate,
            "subjects": subject_breakdown
        }

def get_pool_questions(db_path: Path, user_id: int, subject: str, difficulty: str, limit: int) -> List[Dict[str, Any]]:
    with get_db_connection(db_path) as conn:
        cur = conn.cursor()
        
        # Construct filter query
        query = """
            SELECT id, subject, difficulty, question, options, correct_index, explanation, source_doc, source_page
            FROM question_pool
            WHERE 1=1
        """
        params = []
        
        if subject != "All":
            query += " AND subject = ?"
            params.append(subject)
            
        if difficulty != "exam":
            query += " AND difficulty = ?"
            params.append(difficulty)
            
        # Spaced repetition: Exclude questions answered in the last 50 attempts by this user
        query += """
            AND id NOT IN (
                SELECT a.question_id 
                FROM test_answers a
                JOIN test_sessions s ON a.test_session_id = s.id
                WHERE s.user_id = ? AND a.question_id IS NOT NULL
                ORDER BY a.created_at DESC
                LIMIT 50
            )
        """
        params.append(user_id)
        
        query += " ORDER BY RANDOM() LIMIT ?"
        params.append(limit)
        
        cur.execute(query, tuple(params))
        
        questions = []
        for row in cur.fetchall():
            q = dict(row)
            try:
                q["options"] = json.loads(q["options"])
            except Exception:
                q["options"] = []
            questions.append(q)
            
        return questions

def add_pool_question(db_path: Path, subject: str, difficulty: str, question: str, options: List[str], correct_index: int, explanation: str, source_doc: str, source_page: str) -> int:
    options_str = json.dumps(options)
    with get_db_connection(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO question_pool (subject, difficulty, question, options, correct_index, explanation, source_doc, source_page)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (subject, difficulty, question, options_str, correct_index, explanation, source_doc, source_page)
        )
        conn.commit()
        return cur.lastrowid
