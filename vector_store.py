import uuid
import numpy as np
from pathlib import Path
from typing import List, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue

import config

def get_client() -> QdrantClient:
    """Initialize the Qdrant client using config settings."""
    if not config.QDRANT_URL or "<vps_ip>" in config.QDRANT_URL:
        # Fallback to local memory if not configured
        raise ValueError(
            "QDRANT_URL no está configurada o contiene el marcador '<vps_ip>'. "
            "Por favor, edita tu archivo '.env' y pon la IP o dominio correcto de tu VPS."
        )
    # Configure SSL verification (either verify boolean or path to CA bundle)
    verify_val = config.QDRANT_CA_PEM if config.QDRANT_CA_PEM else config.QDRANT_VERIFY_SSL
    return QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY, verify=verify_val)

def init_db(db_path: Path) -> None:
    """Initialize the Qdrant database and create the collection if it doesn't exist."""
    client = get_client()
    collection = config.QDRANT_COLLECTION
    
    try:
        collections_resp = client.get_collections()
        existing = [col.name for col in collections_resp.collections]
        
        if collection not in existing:
            # Create collection. gemini-embedding-001 has 3072 dimensions.
            # We use Cosine similarity.
            client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=3072, distance=Distance.COSINE)
            )
            print(f"[!] Creada nueva colección en Qdrant: {collection}")
    except Exception as e:
        print(f"Error al inicializar la colección de Qdrant: {e}")
        raise

def is_file_indexed(db_path: Path, filename: str) -> bool:
    """Check if any points with the given filename payload exist in Qdrant."""
    client = get_client()
    collection = config.QDRANT_COLLECTION
    
    try:
        results, _ = client.scroll(
            collection_name=collection,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="source",
                        match=MatchValue(value=filename)
                    )
                ]
            ),
            limit=1,
            with_payload=False,
            with_vectors=False
        )
        return len(results) > 0
    except Exception:
        return False

def delete_file_from_index(db_path: Path, filename: str) -> None:
    """Delete all points associated with a specific file in Qdrant."""
    client = get_client()
    collection = config.QDRANT_COLLECTION
    
    try:
        client.delete(
            collection_name=collection,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="source",
                        match=MatchValue(value=filename)
                    )
                ]
            )
        )
    except Exception as e:
        print(f"Error al borrar el archivo en Qdrant: {e}")
        raise

def clear_database(db_path: Path) -> None:
    """Delete and recreate the collection in Qdrant."""
    client = get_client()
    collection = config.QDRANT_COLLECTION
    
    try:
        client.delete_collection(collection_name=collection)
        client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=3072, distance=Distance.COSINE)
        )
        print(f"[!] Colección '{collection}' vaciada correctamente en Qdrant.")
    except Exception as e:
        print(f"Error al vaciar la colección de Qdrant: {e}")
        raise

def insert_chunks(db_path: Path, chunks: List[Dict[str, Any]], embeddings: List[np.ndarray]) -> None:
    """Insert chunks of text along with their vector embeddings into Qdrant."""
    client = get_client()
    collection = config.QDRANT_COLLECTION
    
    points = []
    for chunk, embedding in zip(chunks, embeddings):
        # Generate a deterministic UUID based on source name, location, and chunk index to avoid duplicates
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{chunk['source']}_{chunk['location']}_{chunk['chunk_index']}"))
        
        # Convert embedding numpy array to standard list of floats
        vector = [float(val) for val in embedding]
        
        points.append(PointStruct(
            id=point_id,
            vector=vector,
            payload={
                "source": chunk["source"],
                "location": chunk["location"],
                "chunk_index": chunk["chunk_index"],
                "text": chunk["text"]
            }
        ))
        
    try:
        # Upsert in batches of 100 points
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            client.upsert(
                collection_name=collection,
                points=batch
            )
    except Exception as e:
        print(f"Error al insertar puntos en Qdrant: {e}")
        raise

def search_similar_chunks(db_path: Path, query_embedding: np.ndarray, top_k: int = 5) -> List[Dict[str, Any]]:
    """Retrieve top K matching chunks using Qdrant's vector search."""
    client = get_client()
    collection = config.QDRANT_COLLECTION
    
    # Convert query embedding to list of floats
    vector = [float(val) for val in query_embedding]
    
    try:
        query_result = client.query_points(
            collection_name=collection,
            query=vector,
            limit=top_k
        )
        
        results = []
        for scored_point in query_result.points:
            payload = scored_point.payload
            if payload:
                results.append({
                    "id": scored_point.id,
                    "source": payload.get("source", "Desconocido"),
                    "location": payload.get("location", ""),
                    "chunk_index": payload.get("chunk_index", 0),
                    "text": payload.get("text", ""),
                    "similarity": scored_point.score
                })
        return results
    except Exception as e:
        print(f"Error al realizar la búsqueda en Qdrant: {e}")
        return []

def get_database_status(db_path: Path) -> Dict[str, Any]:
    """Retrieve statistics about the collection in Qdrant."""
    if not config.QDRANT_URL or "<vps_ip>" in config.QDRANT_URL:
        return {"exists": False, "total_chunks": 0, "files": {}}
        
    try:
        client = get_client()
        collection = config.QDRANT_COLLECTION
        
        collections_resp = client.get_collections()
        existing = [col.name for col in collections_resp.collections]
        
        if collection not in existing:
            return {"exists": False, "total_chunks": 0, "files": {}}
            
        col_info = client.get_collection(collection_name=collection)
        total_chunks = col_info.points_count
        
        # Scroll through the collection to count unique files
        files = {}
        next_page = None
        
        while True:
            scroll_result, next_page = client.scroll(
                collection_name=collection,
                limit=1000,
                with_payload=True,
                with_vectors=False,
                scroll_filter=None,
                offset=next_page
            )
            
            for point in scroll_result:
                payload = point.payload
                if payload:
                    filename = payload.get("source", "Desconocido")
                    if filename not in files:
                        files[filename] = {"chunk_count": 0}
                    files[filename]["chunk_count"] += 1
                    
            if not next_page:
                break
                
        return {
            "exists": True,
            "total_chunks": total_chunks,
            "files": files
        }
    except Exception as e:
        # If connection fails, return not exists
        return {"exists": False, "total_chunks": 0, "files": {}}
