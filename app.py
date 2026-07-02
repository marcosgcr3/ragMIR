import os
import io
import shutil
import urllib3
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, File, UploadFile, Form, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import config
import vector_store
from rag_engine import RAGEngine

# Suppress self-signed certificate warnings for local Qdrant VPS calls
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Ensure manuals directory exists
MANUALS_DIR = config.BASE_DIR / "manuals"
MANUALS_DIR.mkdir(exist_ok=True)

# Initialize RAGEngine
engine = RAGEngine()

app = FastAPI(title="RAG MIR Assistant API")

# Check if static directory exists
STATIC_DIR = config.BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)

@app.get("/", response_class=HTMLResponse)
async def read_root():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
         raise HTTPException(status_code=404, detail="Frontend index.html not found.")
    return index_file.read_text(encoding="utf-8")

@app.get("/api/status")
async def get_status():
    """Get database statistics and status."""
    try:
        status = vector_store.get_database_status(config.DEFAULT_DB_PATH)
        # Convert files dict to list for easier frontend rendering
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
    history: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None)
):
    """Execute RAG query, supporting text, history/memory, and optional image uploads."""
    import json
    try:
        image_bytes = None
        if image and image.filename:
            image_bytes = await image.read()
            
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
    background_tasks: BackgroundTasks = BackgroundTasks()
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
async def post_clear():
    """Clear the vector database collection."""
    try:
        vector_store.clear_database(config.DEFAULT_DB_PATH)
        return {"message": "Colección de base de datos vaciada con éxito."}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Error al vaciar la base de datos: {str(e)}"}
        )

# Mount static folder
app.mount("/static", StaticFiles(directory="static"), name="static")
