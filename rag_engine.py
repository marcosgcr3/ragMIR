import os
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple
import numpy as np
from google import genai
from google.genai import types
from tqdm import tqdm
import openai

import config
import document_loader
import vector_store


class RAGEngine:
    def __init__(self, api_key: str = None, deepseek_api_key: str = None):
        """Initialize Gemini (embeddings/generation) and/or DeepSeek clients depending on config."""
        self.gemini_api_key = api_key or config.get_api_key_or_warn()
        
        if config.GENERATION_PROVIDER == "deepseek":
            self.deepseek_api_key = deepseek_api_key or config.get_deepseek_key_or_warn()
        else:
            self.deepseek_api_key = deepseek_api_key or os.environ.get("DEEPSEEK_API_KEY")
        
        if not self.gemini_api_key:
            self.gemini_client = None
        else:
            self.gemini_client = genai.Client(api_key=self.gemini_api_key)
            
        if not self.deepseek_api_key:
            self.deepseek_client = None
        else:
            self.deepseek_client = openai.OpenAI(
                api_key=self.deepseek_api_key,
                base_url=config.DEEPSEEK_BASE_URL
            )

    def _check_gemini_client(self):
        """Ensure the Gemini client is initialized."""
        if not self.gemini_client:
            raise ValueError(
                "El cliente de API de Gemini no está inicializado. Por favor, configura GEMINI_API_KEY."
            )

    def _check_deepseek_client(self):
        """Ensure the DeepSeek client is initialized."""
        if not self.deepseek_client:
            raise ValueError(
                "El cliente de API de DeepSeek no está inicializado. Por favor, configura DEEPSEEK_API_KEY."
            )

    def get_embedding(self, text: str) -> np.ndarray:
        """Generate embedding for a single text chunk using Gemini."""
        self._check_gemini_client()
        try:
            response = self.gemini_client.models.embed_content(
                model=config.EMBEDDING_MODEL,
                contents=text
            )
            # Response embeddings contains a list of embeddings. For a single content, we take the first.
            embedding_vals = response.embeddings[0].values
            return np.array(embedding_vals, dtype=np.float32)
        except Exception as e:
            print(f"Error generating embedding: {e}")
            raise

    def get_embeddings_batch(self, texts: List[str], batch_size: int = 50) -> List[np.ndarray]:
        """
        Generate embeddings for a list of texts in batches to improve efficiency
        and avoid hitting rate limits. Includes retry logic for 429 RESOURCE_EXHAUSTED.
        """
        self._check_gemini_client()
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            
            max_retries = 5
            base_delay = 5  # seconds
            
            for attempt in range(max_retries):
                try:
                    response = self.gemini_client.models.embed_content(
                        model=config.EMBEDDING_MODEL,
                        contents=batch
                    )
                    for emb in response.embeddings:
                        all_embeddings.append(np.array(emb.values, dtype=np.float32))
                    break  # Success, break the retry loop
                except Exception as e:
                    # Detect 429 Rate Limit
                    is_rate_limit = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)
                    
                    if is_rate_limit and attempt < max_retries - 1:
                        sleep_time = base_delay * (2 ** attempt)
                        print(f"\n[!] Límite de cuota alcanzado (429). Esperando {sleep_time} segundos antes de reintentar (intento {attempt + 1}/{max_retries})...")
                        time.sleep(sleep_time)
                    else:
                        print(f"Error in batch embedding (index {i} to {i+len(batch)}): {e}")
                        raise
                        
        return all_embeddings

    def index_directory(self, folder_path: Path, db_path: Path, force: bool = False) -> Tuple[int, int]:
        """
        Scans a directory for .pdf and .docx files, chunks them,
        generates embeddings, and stores them in the SQLite vector database.
        Returns (number of files indexed, number of chunks created).
        """
        self._check_gemini_client()
        vector_store.init_db(db_path)
        
        path = Path(folder_path)
        if not path.exists() or not path.is_dir():
            raise FileNotFoundError(f"The path {folder_path} is not a valid directory.")
            
        # Supported extensions
        extensions = [".pdf", ".docx"]
        # Use rglob to recursively search all subdirectories
        files = [f for f in path.rglob("*") if f.is_file() and f.suffix.lower() in extensions]
        
        if not files:
            print("No PDF or DOCX files found in the specified directory or its subdirectories.")
            return 0, 0
            
        indexed_files_count = 0
        total_chunks_count = 0
        
        print(f"Found {len(files)} files to index. Checking status...")
        
        for file in files:
            # Determine display name (relative path from root directory)
            relative_name = str(file.relative_to(path)).replace('\\', '/')
            
            is_indexed = vector_store.is_file_indexed(db_path, relative_name)
            
            if is_indexed and not force:
                print(f"[-] Skipping already indexed file: {relative_name}")
                continue
                
            if is_indexed and force:
                print(f"[!] Re-indexing file (force=True): {relative_name}")
                vector_store.delete_file_from_index(db_path, relative_name)
                
            print(f"[+] Indexing file: {relative_name}")
            
            # Load and chunk
            chunks = document_loader.load_and_chunk_document(file, source_name=relative_name)
            if not chunks:
                print(f"    No text extracted or chunks generated from {relative_name}.")
                continue
                
            print(f"    Generated {len(chunks)} chunks. Generating embeddings...")
            
            # Extract text strings for batch embeddings API call
            texts_to_embed = [chunk["text"] for chunk in chunks]
            
            # Generate embeddings
            try:
                # Using tqdm to show progress bar for embeddings generation
                embeddings = []
                # Batch processing with a visible bar
                for j in range(0, len(texts_to_embed), 50):
                    batch_texts = texts_to_embed[j : j + 50]
                    batch_embeddings = self.get_embeddings_batch(batch_texts)
                    embeddings.extend(batch_embeddings)
                    
                # Insert chunks and embeddings into SQLite DB
                vector_store.insert_chunks(db_path, chunks, embeddings)
                
                indexed_files_count += 1
                total_chunks_count += len(chunks)
                print(f"    Successfully indexed {relative_name} ({len(chunks)} chunks).")
                
            except Exception as e:
                print(f"    Failed to index {relative_name} due to an error: {e}")
                
        return indexed_files_count, total_chunks_count

    def query(self, user_query: str, db_path: Path, top_k: int = 5, image_bytes: bytes = None, history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Processes a user question: retrieves similar document chunks from the Qdrant DB,
        constructs the prompt, queries the generative model (Gemini or DeepSeek), and returns the answer.
        Supports dialog history and token usage reporting.
        """
        self._check_gemini_client()
        if config.GENERATION_PROVIDER == "deepseek":
            self._check_deepseek_client()
        
        # 1. Generate query embedding
        try:
            query_emb = self.get_embedding(user_query)
        except Exception as e:
            return {
                "answer": f"Error generating query embedding: {e}",
                "sources": []
            }
            
        # 2. Search database for top-k similar chunks
        results = vector_store.search_similar_chunks(db_path, query_emb, top_k=top_k)
        
        if not results:
            return {
                "answer": "No hay documentos indexados en la base de datos o no se encontraron coincidencias. Por favor, indexa primero algún documento usando el comando 'index'.",
                "sources": []
            }
            
        # 3. Format the context for the model prompt
        context_parts = []
        for i, chunk in enumerate(results):
            source_info = f"[Fuente: {chunk['source']} - Ubicación: {chunk['location']}]"
            context_parts.append(f"--- DOCUMENTO REF {i+1} ---\n{source_info}\n{chunk['text']}")
            
        context_str = "\n\n".join(context_parts)
        
        # 4. Construct prompt with rules and query
        system_instruction = (
            "Eres un asistente de estudio experto y tutor médico especializado en la preparación del examen MIR (Médico Interno Residente). "
            "Responde a la pregunta de medicina del usuario utilizando la información de los fragmentos de los manuales médicos provistos a continuación. "
            "Si la información es insuficiente para responder a la pregunta, indícalo claramente y sugiere qué podría faltar, "
            "pero no inventes ni alucines respuestas. "
            "Cita siempre el manual/asignatura y páginas o ubicaciones provistas al dar la respuesta para fundamentar tus afirmaciones de forma rigurosa."
        )
        
        user_message_content = f"""DOCUMENTOS DE REFERENCIA PROPORCIONADOS:
{context_str}

---
PREGUNTA DEL USUARIO: {user_query}

RESPUESTA DETALLADA (en español, bien estructurada, citando las fuentes/ubicaciones provistas):"""

        # 5. Call generative model
        try:
            usage = None
            if config.GENERATION_PROVIDER == "gemini":
                contents_list = []
                if history:
                    for msg in history:
                        role = "user" if msg["role"] == "user" else "model"
                        contents_list.append(
                            types.Content(
                                role=role,
                                parts=[types.Part.from_text(text=msg["content"])]
                            )
                        )
                
                # Append current user prompt as the last content
                current_parts = []
                if image_bytes:
                    from PIL import Image
                    import io
                    try:
                        image = Image.open(io.BytesIO(image_bytes))
                        current_parts.append(image)
                    except Exception as img_err:
                        print(f"Error loading image in RAGEngine: {img_err}")
                
                current_parts.append(types.Part.from_text(text=user_message_content))
                contents_list.append(
                    types.Content(
                        role="user",
                        parts=current_parts
                    )
                )

                response = self.gemini_client.models.generate_content(
                    model=config.GENERATION_MODEL,
                    contents=contents_list,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.3
                    )
                )
                answer = response.text
                
                if hasattr(response, "usage_metadata") and response.usage_metadata:
                    usage = {
                        "prompt_tokens": response.usage_metadata.prompt_token_count,
                        "completion_tokens": response.usage_metadata.candidates_token_count,
                        "total_tokens": response.usage_metadata.total_token_count
                    }
            else:
                messages = [{"role": "system", "content": system_instruction}]
                if history:
                    for msg in history:
                        messages.append({"role": msg["role"], "content": msg["content"]})
                
                if image_bytes:
                    user_message_content = "(Nota: Imagen ignorada ya que el proveedor seleccionado no la soporta)\n" + user_message_content
                
                messages.append({"role": "user", "content": user_message_content})

                response = self.deepseek_client.chat.completions.create(
                    model=config.DEEPSEEK_MODEL,
                    messages=messages,
                    temperature=0.3
                )
                answer = response.choices[0].message.content
                
                if hasattr(response, "usage") and response.usage:
                    usage = {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens
                    }
                
            return {
                "answer": answer,
                "sources": results,
                "usage": usage
            }
        except Exception as e:
            provider_name = "Gemini" if config.GENERATION_PROVIDER == "gemini" else "DeepSeek"
            return {
                "answer": f"Error al generar la respuesta de {provider_name}: {e}",
                "sources": results,
                "usage": None
            }
