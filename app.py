import os
import io
import json
import shutil
import base64
import random
import urllib3
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, File, UploadFile, Form, BackgroundTasks, HTTPException, Depends, Request, Cookie
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from google.genai import types

import config
import vector_store
import database
from rag_engine import RAGEngine

# Suppress self-signed certificate warnings for local Qdrant VPS calls
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Ensure manuals directory exists
MANUALS_DIR = config.BASE_DIR / "manuals"
MANUALS_DIR.mkdir(exist_ok=True)

# Initialize Relational Database
database.init_db(config.DEFAULT_DB_PATH)

# Initialize RAGEngine
engine = RAGEngine()

app = FastAPI(title="RAG MIR Assistant API")

# Dependency: Get current logged-in user
async def get_current_user(request: Request, session_token: Optional[str] = Cookie(None)):
    user = database.validate_session(config.DEFAULT_DB_PATH, session_token)
    if not user:
        raise HTTPException(status_code=401, detail="No autorizado. Por favor inicia sesión.")
    return user

# Serve Frontend Index
STATIC_DIR = config.BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)

@app.get("/", response_class=HTMLResponse)
async def read_root():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
         raise HTTPException(status_code=404, detail="Frontend index.html no encontrado.")
    return index_file.read_text(encoding="utf-8")

@app.get("/test", response_class=HTMLResponse)
async def read_test_root():
    test_file = STATIC_DIR / "test.html"
    if not test_file.exists():
         raise HTTPException(status_code=404, detail="Frontend test.html no encontrado.")
    return test_file.read_text(encoding="utf-8")

# --- AUTH ENPOINTS ---
@app.post("/api/auth/login")
async def login(username: str = Form(...), password: str = Form(...)):
    db_path = config.DEFAULT_DB_PATH
    with database.get_db_connection(db_path) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, password_hash, salt FROM users WHERE username = ?", (username,))
        row = cur.fetchone()
        
    if not row or not database.verify_password(password, row["password_hash"], row["salt"]):
        raise HTTPException(status_code=400, detail="Usuario o contraseña incorrectos.")
        
    token = database.create_session(db_path, row["id"])
    
    response = JSONResponse(content={"message": "Sesión iniciada con éxito", "username": username})
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        max_age=30 * 24 * 60 * 60, # 30 days
        samesite="lax",
        secure=False # Set to True if using HTTPS
    )
    return response

@app.post("/api/auth/logout")
async def logout(request: Request, session_token: Optional[str] = Cookie(None)):
    database.delete_session(config.DEFAULT_DB_PATH, session_token)
    response = JSONResponse(content={"message": "Sesión cerrada con éxito"})
    response.delete_cookie("session_token")
    return response

@app.get("/api/auth/me")
async def get_me(user: dict = Depends(get_current_user)):
    return user

# --- CHAT SESSION ENDPOINTS ---
@app.get("/api/sessions")
async def list_sessions(user: dict = Depends(get_current_user)):
    return database.get_user_sessions(config.DEFAULT_DB_PATH, user["id"])

@app.post("/api/sessions")
async def create_session(session_id: str = Form(...), title: str = Form(...), user: dict = Depends(get_current_user)):
    return database.create_user_session(config.DEFAULT_DB_PATH, user["id"], session_id, title)

@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str, user: dict = Depends(get_current_user)):
    database.delete_user_session(config.DEFAULT_DB_PATH, user["id"], session_id)
    return {"message": "Sesión eliminada con éxito"}

@app.get("/api/sessions/{session_id}/messages")
async def get_messages(session_id: str, user: dict = Depends(get_current_user)):
    db_path = config.DEFAULT_DB_PATH
    with database.get_db_connection(db_path) as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM chat_sessions WHERE id = ?", (session_id,))
        row = cur.fetchone()
        
    if not row:
        raise HTTPException(status_code=404, detail="Sesión no encontrada.")
    if row["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="No tienes acceso a esta sesión de chat.")
        
    return database.get_session_messages(db_path, session_id)

# --- CORE RAG ENDPOINTS ---
@app.get("/api/status")
async def get_status(user: dict = Depends(get_current_user)):
    """Get database statistics and status."""
    try:
        status = vector_store.get_database_status(config.DEFAULT_DB_PATH)
        files_list = []
        if status.get("files"):
            for filename, info in status["files"].items():
                files_list.append({
                    "name": filename,
                    "readable_name": config.MANUAL_NAMES.get(filename, filename.replace(".pdf", "")),
                    "chunks": info.get("chunk_count", 0)
                })
        return {
            "exists": status.get("exists", False),
            "collection": config.QDRANT_COLLECTION,
            "total_chunks": status.get("total_chunks", 0),
            "provider": config.GENERATION_PROVIDER,
            "model": config.GENERATION_MODEL,
            "files": files_list
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Error al obtener el estado: {str(e)}"}
        )

@app.post("/api/query")
async def post_query(
    question: str = Form(...),
    session_id: str = Form(...),
    history: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    user: dict = Depends(get_current_user)
):
    """Execute RAG query, supporting text, history/memory, and optional image uploads."""
    try:
        image_bytes = None
        image_base64_str = None
        if image and image.filename:
            image_bytes = await image.read()
            mime = image.content_type or "image/png"
            image_base64_str = f"data:{mime};base64,{base64.b64encode(image_bytes).decode('utf-8')}"
            
        history_list = None
        if history:
            try:
                history_list = json.loads(history)
            except Exception as json_err:
                print(f"Error parsing history in app.py: {json_err}")
            
        result = engine.query(
            user_query=question,
            db_path=config.DEFAULT_DB_PATH,
            top_k=5,
            image_bytes=image_bytes,
            history=history_list
        )
        
        sources = []
        seen = set()
        for src in result.get("sources", []):
            src_key = (src["source"], src["location"])
            if src_key not in seen:
                sources.append({
                    "source": src["source"],
                    "location": src["location"],
                    "similarity": float(src.get("similarity", 0))
                })
                seen.add(src_key)
                
        database.add_session_message(
            config.DEFAULT_DB_PATH, 
            session_id, 
            "user", 
            question, 
            image_base64_str
        )
        database.add_session_message(
            config.DEFAULT_DB_PATH, 
            session_id, 
            "model", 
            result.get("answer", "Sin respuesta."), 
            None, 
            sources
        )
        
        tokens = result.get("usage", {}).get("total_tokens", 0) if result.get("usage") else 0
        database.log_usage(
            config.DEFAULT_DB_PATH, 
            user["id"], 
            question, 
            result.get("answer", "Sin respuesta."), 
            tokens
        )
        
        return {
            "answer": result.get("answer", "Sin respuesta."),
            "sources": sources,
            "usage": result.get("usage")
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Error al procesar la consulta: {str(e)}"}
        )

# Global indexing lock to prevent concurrent indexing processes
is_indexing = False

def run_indexing():
    global is_indexing
    try:
        print("[Web App] Starting background indexing...")
        engine.index_directory(MANUALS_DIR, config.DEFAULT_DB_PATH, force=False)
        print("[Web App] Background indexing completed successfully.")
    except Exception as e:
        print(f"[Web App] Error during background indexing: {e}")
    finally:
        is_indexing = False

@app.post("/api/upload")
async def post_upload(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    user: dict = Depends(get_current_user)
):
    """Upload a PDF manual and trigger background indexing."""
    global is_indexing
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos PDF.")
        
    try:
        # Save file to manuals directory
        file_path = MANUALS_DIR / file.filename
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Trigger background indexing if not already indexing
        if not is_indexing:
            is_indexing = True
            background_tasks.add_task(run_indexing)
            return {"message": f"Archivo '{file.filename}' subido. Indexando en segundo plano..."}
        else:
            return {"message": f"Archivo '{file.filename}' subido. Se indexará al finalizar el proceso actual."}
            
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Error al subir o procesar el archivo: {str(e)}"}
        )

@app.post("/api/clear")
async def post_clear(user: dict = Depends(get_current_user)):
    """Clear the vector database collection."""
    try:
        vector_store.clear_database(config.DEFAULT_DB_PATH)
        return {"message": "Colección de base de datos vaciada con éxito."}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Error al vaciar la base de datos: {str(e)}"}
        )

@app.delete("/api/documents/{filename}")
async def delete_document(filename: str, user: dict = Depends(get_current_user)):
    """Delete a document from Qdrant index and the physical storage."""
    import re
    if re.match(r"^[A-Z]{2}\.pdf$", filename):
        raise HTTPException(status_code=400, detail="No se pueden eliminar los manuales oficiales.")
        
    try:
        # Delete from Qdrant index
        vector_store.delete_file_from_index(config.DEFAULT_DB_PATH, filename)
        
        # Delete physical file
        file_path = MANUALS_DIR / filename
        if file_path.exists():
            file_path.unlink()
            
        return {"message": f"Documento '{filename}' eliminado con éxito."}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Error al eliminar documento: {str(e)}"}
        )

# --- TEST SIMULATOR ENDPOINTS ---
def generate_and_save_question(subject_filter: str, difficulty: str) -> dict:
    """Helper to generate a question from Qdrant/Gemini and save it to the question pool."""
    client = vector_store.get_client()
    collection = config.QDRANT_COLLECTION
    
    # 1. Fetch a random chunk from Qdrant
    filter_obj = None
    if subject_filter != "All":
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        filter_obj = Filter(
            must=[FieldCondition(key="source", match=MatchValue(value=subject_filter))]
        )
        
    try:
        results, _ = client.scroll(
            collection_name=collection,
            scroll_filter=filter_obj,
            limit=100,
            with_payload=True,
            with_vectors=False
        )
    except Exception as err:
        print(f"Error scrolling Qdrant: {err}")
        results = []
        
    if not results:
        raise HTTPException(status_code=400, detail="No hay suficientes documentos indexados para generar preguntas.")
        
    point = random.choice(results)
    payload = point.payload
    chunk_text = payload.get("text", "")
    filename = payload.get("source", "Desconocido")
    location = payload.get("location", "")
    
    # Determine difficulty level prompt
    diff_val = difficulty
    if diff_val == "exam":
        diff_val = random.choice(["easy", "medium", "hard"])
        
    difficulty_instructions = ""
    if diff_val == "easy":
        difficulty_instructions = "Genera una pregunta directa y relativamente fácil de memorización o concepto básico del MIR. Por ejemplo, definir un síntoma clásico, una definición o una asociación directa."
    elif diff_val == "medium":
        difficulty_instructions = "Genera una pregunta de dificultad intermedia tipo caso clínico MIR convencional, donde se describa la historia de un paciente con síntomas estándar y se solicite el diagnóstico más probable o el tratamiento de primera elección."
    elif diff_val == "hard":
        difficulty_instructions = "Genera una pregunta MIR de dificultad de examen muy elevada. Puede ser un caso clínico complejo con síntomas atípicos, diagnóstico diferencial sutil, o preguntas específicas sobre fármacos de segunda línea, efectos adversos raros o dosificaciones específicas."
        
    # 2. Query Gemini
    prompt = f"""
    Basándote en el siguiente texto de un manual de medicina, genera una pregunta de opción múltiple tipo test del examen MIR en España.
    {difficulty_instructions}
    
    Genera exactamente 4 opciones de respuesta coherentes (donde solo una sea correcta).
    Devuelve la respuesta en formato JSON con la siguiente estructura exacta:
    {{
        "question": "Texto de la pregunta...",
        "options": ["Opción 1", "Opción 2", "Opción 3", "Opción 4"],
        "correct_index": 0, // Índice de la opción correcta de 0 a 3
        "explanation": "Explicación detallada de por qué es la opción correcta y por qué las otras son incorrectas..."
    }}

    Texto médico de referencia:
    \"\"\"
    {chunk_text}
    \"\"\"
    """
    
    try:
        response = engine.gemini_client.models.generate_content(
            model=config.GENERATION_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.4,
                response_mime_type="application/json"
            )
        )
        
        q_data = json.loads(response.text)
        
        # Save to pool
        qid = database.add_pool_question(
            config.DEFAULT_DB_PATH,
            filename,
            diff_val,
            q_data["question"],
            q_data["options"],
            q_data["correct_index"],
            q_data["explanation"],
            filename,
            location
        )
        
        return {
            "id": qid,
            "subject": filename,
            "difficulty": diff_val,
            "question": q_data["question"],
            "options": q_data["options"],
            "correct_index": q_data["correct_index"],
            "explanation": q_data["explanation"],
            "source_doc": filename,
            "source_page": location
        }
    except Exception as err:
        print(f"Error generating question via Gemini: {err}")
        raise HTTPException(status_code=500, detail="Error al generar preguntas dinámicas mediante Gemini.")

def background_generate_questions(subject_filter: str, difficulty: str, count: int):
    """Generate new questions in the background to grow the pool without slowing down tests."""
    for _ in range(count):
        try:
            subj_filter = subject_filter
            if subject_filter == "All":
                status = vector_store.get_database_status(config.DEFAULT_DB_PATH)
                files = list(status.get("files", {}).keys())
                if files:
                    subj_filter = random.choice(files)
                else:
                    print("[Background] No files indexed. Cannot generate new questions.")
                    break
            generate_and_save_question(subj_filter, difficulty)
            print(f"[Background] Successfully generated and stored a new question for {subj_filter} ({difficulty}).")
        except Exception as e:
            print(f"[Background] Error generating question: {e}")

@app.post("/api/tests/start")
async def start_test_session(
    background_tasks: BackgroundTasks,
    subject: str = Form(...),
    difficulty: str = Form(...),
    total_questions: int = Form(...),
    user: dict = Depends(get_current_user)
):
    """Start a test session, load questions instantly, and generate new pool questions asynchronously."""
    test_id = str(int(random.random() * 1000000000))
    
    # 1. Create the session in the DB
    database.create_test_session(
        config.DEFAULT_DB_PATH, 
        user["id"], 
        test_id, 
        subject, 
        difficulty, 
        total_questions
    )
    
    # 2. Get existing questions from pool up to the requested count
    questions = database.get_pool_questions(
        config.DEFAULT_DB_PATH, 
        user["id"], 
        subject, 
        difficulty, 
        total_questions
    )
    
    # 3. Check if we have enough questions in the database
    needed = total_questions - len(questions)
    if needed <= 0:
        # We have enough questions! Respond instantly and queue background generation of new questions
        # This keeps the pool growing without making the user wait.
        forced_new_count = max(1, min(3, int(total_questions * 0.2)))
        background_tasks.add_task(background_generate_questions, subject, difficulty, forced_new_count)
    else:
        # If we don't have enough, generate the missing questions synchronously
        print(f"Pool only had {len(questions)}/{total_questions} questions. Generating {needed} synchronously...")
        for _ in range(needed):
            try:
                subj_filter = subject
                if subject == "All":
                    status = vector_store.get_database_status(config.DEFAULT_DB_PATH)
                    files = list(status.get("files", {}).keys())
                    if files:
                        subj_filter = random.choice(files)
                    else:
                        print("Sync generation fallback: No files indexed in vector store.")
                        break
                        
                new_q = generate_and_save_question(subj_filter, difficulty)
                questions.append(new_q)
            except Exception as e:
                print(f"Error generating question synchronously: {e}")
                
    if not questions:
        raise HTTPException(
            status_code=400, 
            detail="No se pudieron recuperar o generar preguntas para este tema/dificultad. Verifica que tus manuales estén indexados."
        )
        
    return {
        "test_session_id": test_id,
        "questions": questions
    }

@app.post("/api/tests/answer")
async def save_test_answer(
    test_session_id: str = Form(...),
    question_id: int = Form(...),
    is_correct: int = Form(...), # 1 or 0
    user: dict = Depends(get_current_user)
):
    """Save user test answer in the database."""
    try:
        database.log_test_answer(config.DEFAULT_DB_PATH, test_session_id, question_id, is_correct)
        return {"message": "Respuesta guardada con éxito."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al guardar respuesta: {str(e)}")

@app.get("/api/tests/stats")
async def get_test_stats(user: dict = Depends(get_current_user)):
    """Retrieve detailed test stats and breakdown by medical specialty."""
    try:
        stats = database.get_test_stats(config.DEFAULT_DB_PATH, user["id"])
        # Map filenames to human-readable names
        subjects_mapped = []
        for s in stats["subjects"]:
            filename = s["subject"]
            readable_name = config.MANUAL_NAMES.get(filename, filename.replace(".pdf", ""))
            subjects_mapped.append({
                "filename": filename,
                "name": readable_name,
                "total": s["total"],
                "correct": s["correct"],
                "incorrect": s["incorrect"],
                "percent": s["percent"]
            })
        stats["subjects"] = subjects_mapped
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al recuperar estadísticas de test: {str(e)}")

# Mount static folder
app.mount("/static", StaticFiles(directory="static"), name="static")
