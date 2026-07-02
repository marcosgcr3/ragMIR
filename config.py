import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Workspace paths
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "db" / os.environ.get("DB_PATH", "rag_store.db")

# Qdrant Configuration
QDRANT_URL = os.environ.get("QDRANT_URL")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY")
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "oposiciones")

# Model Configuration
# Google's recommended embedding model: gemini-embedding-001
EMBEDDING_MODEL = "gemini-embedding-001"
# DeepSeek configuration for generation
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# Provider settings
GENERATION_PROVIDER = os.environ.get("GENERATION_PROVIDER", "gemini").lower()
GENERATION_MODEL = os.environ.get("GENERATION_MODEL", "gemini-2.5-flash")

# Chunking Configuration
CHUNK_SIZE = 1000  # Target character size for each text chunk
CHUNK_OVERLAP = 200  # Character overlap between chunks

# API Key Validation
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")

def get_api_key_or_warn():
    """Retrieve Gemini API key or display warning instructions (for backwards compatibility)."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("\n" + "="*60)
        print("WARNING: GEMINI_API_KEY is not set.")
        print("Please create a '.env' file in this folder and add your key:")
        print("GEMINI_API_KEY=your_actual_api_key")
        print("You can get a free key at: https://aistudio.google.com/")
        print("="*60 + "\n")
    return key

def get_deepseek_key_or_warn():
    """Retrieve DeepSeek API key or display warning instructions."""
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        print("\n" + "="*60)
        print("WARNING: DEEPSEEK_API_KEY is not set.")
        print("Please create a '.env' file in this folder and add your key:")
        print("DEEPSEEK_API_KEY=your_actual_deepseek_key")
        print("You can get a key at: https://platform.deepseek.com/")
        print("="*60 + "\n")
    return key

