import os
from pathlib import Path
from typing import List, Dict, Any
from pypdf import PdfReader
from docx import Document
import config

def extract_text_from_pdf(file_path: Path) -> List[Dict[str, Any]]:
    """
    Extracts text page-by-page from a PDF file.
    Returns a list of dicts with 'text', 'source', and 'page' index.
    """
    pages_data = []
    try:
        reader = PdfReader(file_path)
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text and text.strip():
                pages_data.append({
                    "text": text.strip(),
                    "source": file_path.name,
                    "location": f"Page {i + 1}"
                })
    except Exception as e:
        print(f"Error reading PDF {file_path.name}: {e}")
    return pages_data

def extract_text_from_docx(file_path: Path) -> List[Dict[str, Any]]:
    """
    Extracts text from a Word (.docx) file.
    Returns a list of dicts containing paragraph groupings.
    """
    paragraphs_data = []
    try:
        doc = Document(file_path)
        current_text = []
        para_count = 0
        
        # Group paragraphs to mimic pages or logical sections (e.g., every 3-5 paragraphs)
        for para in doc.paragraphs:
            if para.text.strip():
                current_text.append(para.text.strip())
                para_count += 1
                
                # Create a chunk every 5 non-empty paragraphs
                if len(current_text) >= 5:
                    paragraphs_data.append({
                        "text": "\n".join(current_text),
                        "source": file_path.name,
                        "location": f"Paragraphs {para_count - len(current_text) + 1}-{para_count}"
                    })
                    current_text = []
        
        # Append remaining paragraphs
        if current_text:
            paragraphs_data.append({
                "text": "\n".join(current_text),
                "source": file_path.name,
                "location": f"Paragraphs {para_count - len(current_text) + 1}-{para_count}"
            })
            
    except Exception as e:
        print(f"Error reading Word document {file_path.name}: {e}")
    return paragraphs_data

def split_text_into_chunks(text: str, chunk_size: int = config.CHUNK_SIZE, overlap: int = config.CHUNK_OVERLAP) -> List[str]:
    """
    Splits a long text string into smaller overlapping chunks on word boundaries.
    """
    if len(text) <= chunk_size:
        return [text]
        
    chunks = []
    words = text.split()
    current_chunk = []
    current_len = 0
    
    for word in words:
        current_chunk.append(word)
        # Approximate character count including spaces
        current_len += len(word) + 1
        
        if current_len >= chunk_size:
            # Join and save current chunk
            chunk_str = " ".join(current_chunk)
            chunks.append(chunk_str)
            
            # Keep overlap: find how many words from the end of current_chunk fit in the overlap size
            overlap_words = []
            overlap_len = 0
            for w in reversed(current_chunk):
                if overlap_len + len(w) + 1 > overlap:
                    break
                overlap_words.insert(0, w)
                overlap_len += len(w) + 1
                
            current_chunk = overlap_words
            current_len = overlap_len
            
    if current_chunk:
        chunks.append(" ".join(current_chunk))
        
    return chunks

def load_and_chunk_document(file_path: Path, source_name: str = None) -> List[Dict[str, Any]]:
    """
    Reads a document (PDF or DOCX), chunks the text, and returns a list of chunk dicts
    with 'text' and metadata ('source', 'location', 'chunk_index').
    """
    ext = file_path.suffix.lower()
    sections = []
    
    if ext == ".pdf":
        sections = extract_text_from_pdf(file_path)
    elif ext == ".docx":
        sections = extract_text_from_docx(file_path)
    else:
        print(f"Unsupported file format: {ext}")
        return []
        
    all_chunks = []
    for section in sections:
        text = section["text"]
        chunks = split_text_into_chunks(text, config.CHUNK_SIZE, config.CHUNK_OVERLAP)
        
        # Override source name with relative path if provided
        source = source_name if source_name else section["source"]
        
        for idx, chunk in enumerate(chunks):
            all_chunks.append({
                "text": chunk,
                "source": source,
                "location": section["location"],
                "chunk_index": idx
            })
            
    return all_chunks
