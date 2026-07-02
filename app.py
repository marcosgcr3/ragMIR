import os
import io
import json
import shutil
import base64
import urllib3
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, File, UploadFile, Form, BackgroundTasks, HTTPException, Depends, Request, Cookie
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

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
            # Convert image to base64 to store in messages
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
        
        # Format sources
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
                
        # Save messages to Relational Database
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
        
        # Log Usage stats
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

@app.get("/api/stats")
async def get_stats(user: dict = Depends(get_current_user)):
    """Get the usage stats for the authenticated user."""
    try:
        stats = database.get_user_stats(config.DEFAULT_DB_PATH, user["id"])
        return stats
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Error al obtener estadísticas: {str(e)}"}
        )

# Mount static folder
app.mount("/static", StaticFiles(directory="static"), name="static")
