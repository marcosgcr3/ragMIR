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
    # 600,000 iterations is the recommended value by OWASP for PBKDF2-HMAC-SHA256
    pw_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 600000)
    return pw_hash.hex(), salt.hex()

def verify_password(password: str, password_hash_hex: str, salt_hex: str) -> bool:
    salt = bytes.fromhex(salt_hex)
    pw_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 600000)
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
        # Create diagnostic_sessions table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS diagnostic_sessions (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                total_questions INTEGER NOT NULL,
                correct_answers INTEGER DEFAULT 0,
                incorrect_answers INTEGER DEFAULT 0,
                skipped_answers INTEGER DEFAULT 0,
                mir_score REAL DEFAULT 0,
                completed INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # Create diagnostic_answers table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS diagnostic_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                question_id INTEGER,
                selected_index INTEGER,
                is_correct INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES diagnostic_sessions(id) ON DELETE CASCADE,
                FOREIGN KEY (question_id) REFERENCES question_pool(id) ON DELETE SET NULL
            )
        """)
        conn.commit()
        
    # Auto-populate Marcos and Elsa
    cto_password = os.environ.get("CTO_PASSWORD")
    
    if cto_password:
        with get_db_connection(db_path) as conn:
            for username in ["Marcos", "Elsa"]:
                cur = conn.cursor()
                cur.execute("SELECT id FROM users WHERE username = ?", (username,))
                row = cur.fetchone()
                pw_hash, salt = hash_password(cto_password)
                if not row:
                    conn.execute(
                        "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
                        (username, pw_hash, salt)
                    )
                    print(f"[!] Usuario inicial creado: {username}")
                else:
                    # Update password in case CTO_PASSWORD changed in environment variables
                    conn.execute(
                        "UPDATE users SET password_hash = ?, salt = ? WHERE id = ?",
                        (pw_hash, salt, row["id"])
                    )
                    print(f"[!] Contraseña de usuario inicial actualizada: {username}")
    else:
        print("[!] ADVERTENCIA: CTO_PASSWORD no está definida en el entorno. No se crearán ni actualizarán los usuarios iniciales automáticos.")
        
        # Seed official MIR questions if question_pool is empty
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM question_pool")
        q_count = cur.fetchone()[0]
        if q_count < 1200:
            conn.execute("DELETE FROM question_pool")
            seed_file = Path(__file__).parent / "static" / "official_questions_seed.json"
            if seed_file.exists():
                try:
                    with open(seed_file, "r", encoding="utf-8") as f:
                        questions = json.load(f)
                    for q in questions:
                        options_str = json.dumps(q["options"])
                        conn.execute(
                            """
                            INSERT INTO question_pool (subject, difficulty, question, options, correct_index, explanation, source_doc, source_page)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (q["subject"], q["difficulty"], q["question"], options_str, q["correct_index"], q["explanation"], q["source_doc"], q["source_page"])
                        )
                    print(f"[!] Seeder: Cargadas {len(questions)} preguntas oficiales del MIR en el banco.")
                except Exception as seed_err:
                    print(f"[!] Seeder Error: No se pudo sembrar el banco de preguntas: {seed_err}")
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

def get_test_session(db_path: Path, test_session_id: str) -> Optional[Dict[str, Any]]:
    with get_db_connection(db_path) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, user_id, subject, difficulty, total_questions FROM test_sessions WHERE id = ?", (test_session_id,))
        row = cur.fetchone()
        if row:
            return dict(row)
    return None

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
            
        # Exclude questions answered in the last 100 attempts by this user
        query += """
            AND id NOT IN (
                SELECT a.question_id 
                FROM test_answers a
                JOIN test_sessions s ON a.test_session_id = s.id
                WHERE s.user_id = ? AND a.question_id IS NOT NULL
                ORDER BY a.created_at DESC
                LIMIT 100
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
                opts = json.loads(q["options"])
                q["options"] = [opt for opt in opts if opt is not None]
            except Exception:
                q["options"] = []
            questions.append(q)
            
        return questions

# ─── DIAGNOSTIC FUNCTIONS ────────────────────────────────────────────────────

DIAGNOSTIC_DISTRIBUTION = {
    # subject_file: number of questions in the 50-question diagnostic
    "CD.pdf": 4, "NR.pdf": 3, "DG.pdf": 3, "PD.pdf": 2, "GC.pdf": 2,
    "ED.pdf": 2, "TM.pdf": 2, "IF.pdf": 2, "NF.pdf": 2, "NM.pdf": 2,
    "HM.pdf": 2, "RH.pdf": 1, "CG.pdf": 1, "DM.pdf": 1, "PQ.pdf": 1,
    "ON.pdf": 1, "AN.pdf": 1, "OF.pdf": 1, "OR.pdf": 1, "FC.pdf": 1,
    "AP.pdf": 1, "UG.pdf": 1, "EP.pdf": 1, "AL.pdf": 1, "IG.pdf": 1,
    "GT.pdf": 1, "AT.pdf": 1, "UR.pdf": 1, "BL.pdf": 1, "GR.pdf": 1,
    "RX.pdf": 1, "NQ.pdf": 1, "MF.pdf": 1, "CI.pdf": 1, "RE.pdf": 1,
}

def create_diagnostic_session(db_path: Path, user_id: int, session_id: str, total_questions: int) -> None:
    with get_db_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO diagnostic_sessions (id, user_id, total_questions) VALUES (?, ?, ?)",
            (session_id, user_id, total_questions)
        )
        conn.commit()

def get_diagnostic_questions(
    db_path: Path,
    user_id: int,
    extra_subjects: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """Select 50 questions proportionally by subject, excluding previously seen ones.
    extra_subjects: list of subject filenames to add extra weight to (weakness boosting)."""
    import random as _random

    distribution = dict(DIAGNOSTIC_DISTRIBUTION)

    # Boost weak subjects: add 1 extra question for each weakness subject (up to 7 extra)
    if extra_subjects:
        total_base = sum(distribution.values())
        slots_remaining = 50 - total_base
        boosted = 0
        for subj in extra_subjects:
            if boosted >= slots_remaining:
                break
            if subj in distribution:
                distribution[subj] += 1
                boosted += 1

    all_questions: List[Dict[str, Any]] = []

    with get_db_connection(db_path) as conn:
        cur = conn.cursor()
        # Get IDs of questions previously seen in any diagnostic by this user
        cur.execute(
            """
            SELECT DISTINCT da.question_id
            FROM diagnostic_answers da
            JOIN diagnostic_sessions ds ON da.session_id = ds.id
            WHERE ds.user_id = ? AND da.question_id IS NOT NULL
            """,
            (user_id,)
        )
        seen_ids = {row[0] for row in cur.fetchall()}

        for subject, count in distribution.items():
            params: List[Any] = [subject]
            query = """
                SELECT id, subject, difficulty, question, options, correct_index, explanation, source_doc, source_page
                FROM question_pool WHERE subject = ?
            """
            if seen_ids:
                placeholders = ",".join("?" * len(seen_ids))
                query += f" AND id NOT IN ({placeholders})"
                params.extend(list(seen_ids))
            query += " ORDER BY RANDOM() LIMIT ?"
            params.append(count)

            cur.execute(query, tuple(params))
            for row in cur.fetchall():
                q = dict(row)
                try:
                    opts = json.loads(q["options"])
                    q["options"] = [o for o in opts if o is not None]
                except Exception:
                    q["options"] = []
                all_questions.append(q)

    _random.shuffle(all_questions)
    return all_questions

def log_diagnostic_answer(
    db_path: Path,
    session_id: str,
    question_id: Optional[int],
    selected_index: Optional[int],
    is_correct: int
) -> None:
    with get_db_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO diagnostic_answers (session_id, question_id, selected_index, is_correct) VALUES (?, ?, ?, ?)",
            (session_id, question_id, selected_index, is_correct)
        )
        conn.commit()

def complete_diagnostic_session(db_path: Path, session_id: str) -> Dict[str, Any]:
    """Compute MIR-style score and mark session as completed."""
    with get_db_connection(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT is_correct, selected_index FROM diagnostic_answers WHERE session_id = ?",
            (session_id,)
        )
        rows = cur.fetchall()
        correct = sum(1 for r in rows if r[0] == 1)
        incorrect = sum(1 for r in rows if r[0] == 0 and r[1] is not None)
        skipped = sum(1 for r in rows if r[1] is None)
        # MIR scoring: +3 correct, -1 incorrect, 0 skipped
        raw = correct * 3 - incorrect * 1
        total_q = len(rows) if rows else 1
        max_score = total_q * 3
        mir_score = round(max(0, raw / max_score * 10), 2) if max_score > 0 else 0
        conn.execute(
            """
            UPDATE diagnostic_sessions
            SET correct_answers=?, incorrect_answers=?, skipped_answers=?,
                mir_score=?, completed=1
            WHERE id=?
            """,
            (correct, incorrect, skipped, mir_score, session_id)
        )
        conn.commit()
        return {"correct": correct, "incorrect": incorrect, "skipped": skipped, "mir_score": mir_score}

def get_diagnostic_results(db_path: Path, session_id: str, user_id: int) -> Optional[Dict[str, Any]]:
    """Return full results for a diagnostic session: overall stats + per-subject breakdown."""
    with get_db_connection(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM diagnostic_sessions WHERE id=? AND user_id=?",
            (session_id, user_id)
        )
        session = cur.fetchone()
        if not session:
            return None
        session = dict(session)

        # Per-subject breakdown
        cur.execute(
            """
            SELECT qp.subject,
                   COUNT(*) as total,
                   SUM(da.is_correct) as correct
            FROM diagnostic_answers da
            JOIN question_pool qp ON da.question_id = qp.id
            WHERE da.session_id = ?
            GROUP BY qp.subject
            """,
            (session_id,)
        )
        subjects = []
        for row in cur.fetchall():
            total = row[1]
            correct = row[2] or 0
            subjects.append({
                "subject": row[0],
                "total": total,
                "correct": correct,
                "incorrect": total - correct,
                "percent": round(correct / total * 100, 1) if total > 0 else 0
            })
        session["subjects"] = subjects
        return session

def get_diagnostic_history(db_path: Path, user_id: int) -> List[Dict[str, Any]]:
    """Return list of completed diagnostic sessions for the user, newest first."""
    with get_db_connection(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, total_questions, correct_answers, incorrect_answers,
                   skipped_answers, mir_score, created_at
            FROM diagnostic_sessions
            WHERE user_id=? AND completed=1
            ORDER BY created_at DESC
            """,
            (user_id,)
        )
        return [dict(r) for r in cur.fetchall()]

def get_diagnostic_weakness_subjects(db_path: Path, user_id: int) -> List[str]:
    """Return subject filenames where the user performs worst (for adaptive boosting)."""
    with get_db_connection(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT qp.subject,
                   COUNT(*) as total,
                   SUM(da.is_correct) as correct
            FROM diagnostic_answers da
            JOIN question_pool qp ON da.question_id = qp.id
            JOIN diagnostic_sessions ds ON da.session_id = ds.id
            WHERE ds.user_id=? AND ds.completed=1
            GROUP BY qp.subject
            HAVING total > 0
            ORDER BY (CAST(correct AS REAL)/total) ASC
            LIMIT 7
            """,
            (user_id,)
        )
        return [row[0] for row in cur.fetchall()]

# ─────────────────────────────────────────────────────────────────────────────

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
