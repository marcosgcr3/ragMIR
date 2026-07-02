import os
import sys
import argparse
from pathlib import Path

import config
import vector_store
from rag_engine import RAGEngine

def check_api_keys_or_exit(need_deepseek=True):
    """Ensure required API keys are available before proceeding."""
    gemini_key = config.get_api_key_or_warn()
    if not gemini_key:
        print("ERROR: No se puede continuar sin una clave de API de Gemini válida.")
        print("Por favor, crea un archivo '.env' con tu clave GEMINI_API_KEY y vuelve a intentarlo.")
        sys.exit(1)
        
    if need_deepseek and config.GENERATION_PROVIDER == "deepseek":
        deepseek_key = config.get_deepseek_key_or_warn()
        if not deepseek_key:
            print("ERROR: No se puede continuar sin una clave de API de DeepSeek válida.")
            print("Por favor, crea un archivo '.env' con tu clave DEEPSEEK_API_KEY y vuelve a intentarlo.")
            sys.exit(1)
            
    return gemini_key

def handle_index(args):
    """Handle the indexing command."""
    api_key = check_api_keys_or_exit(need_deepseek=False)
    folder_path = Path(args.folder_path)
    
    if not folder_path.exists():
        print(f"ERROR: La ruta '{args.folder_path}' no existe.")
        sys.exit(1)
    if not folder_path.is_dir():
        print(f"ERROR: La ruta '{args.folder_path}' no es un directorio válido.")
        sys.exit(1)
        
    db_path = config.DEFAULT_DB_PATH
    engine = RAGEngine(api_key=api_key)
    
    print(f"\nIniciando indexación desde el directorio: {folder_path.resolve()}")
    print(f"Base de datos de destino: {db_path.resolve()}")
    
    try:
        indexed_files, total_chunks = engine.index_directory(folder_path, db_path, force=args.force)
        print("\n" + "="*50)
        print(f"PROCESO COMPLETADO:")
        print(f"- Archivos nuevos indexados: {indexed_files}")
        print(f"- Total de fragmentos de texto almacenados: {total_chunks}")
        print("="*50 + "\n")
    except Exception as e:
        print(f"\nERROR durante la indexación: {e}")
        sys.exit(1)

def handle_query(args):
    """Handle a single-shot query command."""
    api_key = check_api_keys_or_exit(need_deepseek=True)
    db_path = config.DEFAULT_DB_PATH
    
    status = vector_store.get_database_status(db_path)
    if not status["exists"] or status["total_chunks"] == 0:
        print(f"\nERROR: No se encontró la base de datos de indexación o está vacía.")
        print("Primero debes indexar tus documentos usando: python main.py index <ruta_de_carpeta>\n")
        sys.exit(1)
        
    engine = RAGEngine(api_key=api_key)
    print(f"\nPreguntando al RAG: '{args.question}'...")
    
    result = engine.query(args.question, db_path, top_k=args.top_k)
    
    print("\n" + "="*80)
    print("RESPUESTA:")
    print("="*80)
    print(result["answer"])
    print("="*80 + "\n")
    
    if result["sources"]:
        print("FUENTES CONSULTADAS:")
        # List unique source files and their locations
        seen_sources = set()
        for src in result["sources"]:
            src_key = (src["source"], src["location"])
            if src_key not in seen_sources:
                print(f"- {src['source']} ({src['location']}) [Similitud: {src['similarity']:.2%}]")
                seen_sources.add(src_key)
        print()

def handle_interactive(args):
    """Handle the interactive chat loop."""
    api_key = check_api_keys_or_exit(need_deepseek=True)
    db_path = config.DEFAULT_DB_PATH
    
    status = vector_store.get_database_status(db_path)
    if not status["exists"] or status["total_chunks"] == 0:
        print(f"\nERROR: No se encontró la base de datos de indexación o está vacía.")
        print("Primero debes indexar tus documentos usando: python main.py index <ruta_de_carpeta>\n")
        sys.exit(1)
        
    engine = RAGEngine(api_key=api_key)
    
    provider_display = "Gemini" if config.GENERATION_PROVIDER == "gemini" else "DeepSeek"
    print("\n" + "="*80)
    print(f" MODO INTERACTIVO RAG - SISTEMA DE CONSULTA DE DOCUMENTOS (Redacta {provider_display})")
    print(" Escribe o pega tu pregunta (puedes incluir líneas vacías).")
    print(" Para enviar, escribe '//' en una línea nueva y presiona Enter.")
    print(" Escribe '/salir' o '/quit' en una línea para terminar.")
    print("="*80 + "\n")
    
    while True:
        try:
            print("\nPregunta (escribe '//' para enviar) >")
            lines = []
            while True:
                line = input()
                if line.strip() == '//':
                    break
                if line.strip().lower() in ['/salir', '/quit', '/exit'] and not lines:
                    lines = [line.strip()]
                    break
                lines.append(line)
                
            user_input = "\n".join(lines).strip()
            if not user_input:
                continue
                
            if user_input.lower() in ['/salir', '/quit', '/exit']:
                print("\n¡Hasta luego!\n")
                break
                
            print("\nBuscando información y redactando respuesta...")
            result = engine.query(user_input, db_path, top_k=args.top_k)
            
            print("\n" + "-"*80)
            print(result["answer"])
            print("-"*80)
            
            if result["sources"]:
                print("\nFuentes de apoyo:")
                seen_sources = set()
                for src in result["sources"]:
                    src_key = (src["source"], src["location"])
                    if src_key not in seen_sources:
                        print(f"  * {src['source']} ({src['location']})")
                        seen_sources.add(src_key)
                        
        except KeyboardInterrupt:
            print("\n\nSesión terminada por el usuario. ¡Hasta luego!\n")
            break
        except Exception as e:
            print(f"\nOcurrió un error inesperado: {e}")

def handle_clear(args):
    """Handle clearing the vector database."""
    db_path = config.DEFAULT_DB_PATH
    status = vector_store.get_database_status(db_path)
    if not status["exists"]:
        print(f"\nLa colección de base de datos '{config.QDRANT_COLLECTION}' no existe, no hay nada que limpiar.\n")
        return
        
    confirm = input(f"\n¿Estás seguro de que deseas vaciar la colección '{config.QDRANT_COLLECTION}'? Todos los datos se borrarán. [s/N]: ").strip().lower()
    if confirm in ['s', 'si', 'y', 'yes']:
        try:
            vector_store.clear_database(db_path)
            # Alternatively delete the file if it exists
            if db_path.exists():
                os.remove(db_path)
            print(f"\nColección '{config.QDRANT_COLLECTION}' vaciada y limpiada correctamente.\n")
        except Exception as e:
            print(f"\nERROR al limpiar la base de datos: {e}\n")
    else:
        print("\nOperación cancelada.\n")

def handle_status(args):
    """Handle database status check."""
    db_path = config.DEFAULT_DB_PATH
    status = vector_store.get_database_status(db_path)
    
    print("\n" + "="*60)
    print(" ESTADO DE LA BASE DE DATOS VECTORIAL")
    print("="*60)
    print(f"Ruta: {db_path.resolve()}")
    
    if not status["exists"] or status["total_chunks"] == 0:
        print("Estado: NO INICIALIZADA / VACÍA")
        print("Instrucciones: Indexa algún archivo usando 'python main.py index <carpeta>'")
    else:
        print("Estado: ACTIVA")
        print(f"Total de fragmentos (chunks): {status['total_chunks']}")
        print(f"Total de archivos indexados: {len(status['files'])}")
        print("-"*60)
        print("Archivos indexados:")
        for idx, (filename, info) in enumerate(status["files"].items(), 1):
            print(f"  {idx}. {filename} ({info['chunk_count']} fragmentos)")
            
    print("="*60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="RAG CLI - Consulta de documentos locales (PDF y DOCX) usando Gemini API"
    )
    subparsers = parser.add_subparsers(dest="command", help="Comandos disponibles")
    
    # Parser for 'index' command
    parser_index = subparsers.add_parser("index", help="Indexa archivos PDF y DOCX de una carpeta")
    parser_index.add_argument("folder_path", type=str, help="Ruta de la carpeta con los documentos")
    parser_index.add_argument(
        "--force", 
        action="store_true", 
        help="Fuerza la reindexación de archivos que ya están en la base de datos"
    )
    
    # Parser for 'query' command
    parser_query = subparsers.add_parser("query", help="Realiza una consulta puntual sobre los documentos")
    parser_query.add_argument("question", type=str, help="La pregunta que quieres hacer")
    parser_query.add_argument(
        "--top_k", 
        type=int, 
        default=5, 
        help="Número de fragmentos de texto relevantes a consultar como contexto"
    )
    
    # Parser for 'interactive' command
    parser_interactive = subparsers.add_parser(
        "interactive", 
        help="Inicia una conversación interactiva de preguntas y respuestas"
    )
    parser_interactive.add_argument(
        "--top_k", 
        type=int, 
        default=5, 
        help="Número de fragmentos de texto relevantes a consultar como contexto"
    )
    
    # Parser for 'clear' command
    parser_clear = subparsers.add_parser("clear", help="Vacia y elimina el índice local")
    
    # Parser for 'status' command
    parser_status = subparsers.add_parser("status", help="Muestra el estado actual del índice y los documentos guardados")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
        
    if args.command == "index":
        handle_index(args)
    elif args.command == "query":
        handle_query(args)
    elif args.command == "interactive":
        handle_interactive(args)
    elif args.command == "clear":
        handle_clear(args)
    elif args.command == "status":
        handle_status(args)

if __name__ == "__main__":
    main()
