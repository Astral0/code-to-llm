# web_server.py
from flask import Flask, request, jsonify, render_template, Response
from flask_socketio import SocketIO
import sys
import os
import logging
from pathlib import Path
from collections import defaultdict
import pathspec
import re
import configparser
import requests
import json
import concurrent.futures
import threading
import uuid
import time
import fnmatch

# Import des services pour centraliser la logique
from services.file_service import FileService
from services.context_builder_service import ContextBuilderService

TEXTCHARS = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)) - {0x7f})

def is_binary_string(bytes_to_check: bytes) -> bool:
    """Checks if a byte string appears to contain non-text characters."""
    return bool(bytes_to_check.translate(None, TEXTCHARS))

app = Flask(__name__, template_folder='templates', static_folder='static')

socketio = SocketIO(app, cors_allowed_origins="*") # Ajout de cors_allowed_origins

# Configure logging
logging.basicConfig(level=logging.INFO)

# --- Configuration des instructions prédéfinies ---
INSTRUCTION_TEXT_1 = "Ne fais rien, attends mes instructions." # Défaut
INSTRUCTION_TEXT_2 = "Si des modifications du code source est nécessaire, tu dois présenter ta réponse sous la forme d'un fichier patch Linux. Considère que le fichier patch a été lancé depuis le répertoire du code-to-llm." # Défaut

# --- Configuration du serveur LLM ---
LLM_SERVER_URL = None
LLM_SERVER_APIKEY = None
LLM_SERVER_MODEL = None
LLM_SERVER_ENABLED = False
LLM_SERVER_API_TYPE = "openai" # Default to openai
LLM_SERVER_STREAM_RESPONSE = False # Nouvelle variable globale

# --- Configuration du LLM de Résumé ---
SUMMARIZER_LLM_URL = None
SUMMARIZER_LLM_APIKEY = None
SUMMARIZER_LLM_MODEL = None
SUMMARIZER_LLM_ENABLED = False
SUMMARIZER_LLM_API_TYPE = "ollama" # Default to ollama for summarizer
SUMMARIZER_LLM_PROMPT = "" # Sera chargé depuis config.ini
SUMMARIZER_LLM_TIMEOUT = 120 # Default timeout for summarizer LLM calls
SUMMARIZER_MAX_WORKERS = 10 # Default max workers for summarizer thread pool
SUMMARIZER_LLM_MODELS_LIST = [] # Nouvelle variable globale

# --- Configuration du LLM pour le pilotage de navigateur ---
LLM_CONFIG = {} # Initialisation de la variable globale

# --- Configuration de la détection binaire ---
BINARY_DETECTION_CONFIG = {}

# --- Configuration de l'exclusion de fichiers ---
FILE_EXCLUSION_CONFIG = {}

# --- État partagé pour les tâches de résumé ---
progress_tasks = {}
progress_lock = threading.Lock()

# --- Initialisation des services ---
file_service = None
context_builder_service = None


def fetch_ollama_models(url):
    """Récupère les modèles disponibles depuis un serveur Ollama."""
    try:
        # L'URL doit pointer vers la racine de l'API, ex: http://localhost:11434
        target_url = url.rstrip('/') + "/api/tags"
        app.logger.info(f"Tentative de récupération des modèles Ollama depuis : {target_url}")
        response = requests.get(target_url, timeout=5) # Timeout court pour ne pas bloquer le démarrage
        response.raise_for_status()
        models_data = response.json()
        
        if "models" in models_data and isinstance(models_data["models"], list):
            model_names = [model.get("name") for model in models_data["models"] if "name" in model]
            app.logger.info(f"{len(model_names)} modèles Ollama trouvés.")
            return sorted(model_names)
        else:
            app.logger.warning(f"Format de réponse inattendu de l'API Ollama (tags): {models_data}")
            return []
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Impossible de contacter le serveur Ollama à {url} pour lister les modèles. Erreur : {e}")
        return []
    except Exception as e:
        app.logger.error(f"Erreur inattendue lors de la récupération des modèles Ollama : {e}")
        return []

def fetch_openai_models(url, api_key):
    """Récupère les modèles disponibles depuis une API compatible OpenAI."""
    if not api_key or api_key == "YOUR_LLM_API_KEY_HERE":
        app.logger.warning("Clé API (Summarizer) non fournie ou invalide, impossible de lister les modèles OpenAI.")
        return []
    try:
        # L'URL doit pointer vers la base de l'API, ex: https://api.openai.com
        target_url = url.rstrip('/') + "/v1/models"
        headers = {"Authorization": f"Bearer {api_key}"}
        app.logger.info(f"Tentative de récupération des modèles OpenAI depuis : {target_url}")
        response = requests.get(target_url, headers=headers, timeout=10)
        response.raise_for_status()
        models_data = response.json()

        if "data" in models_data and isinstance(models_data["data"], list):
            # Filtrer pour ne garder que les modèles potentiellement utiles pour la génération de texte
            model_names = [
                model.get("id") for model in models_data["data"]
                if "id" in model and ("gpt" in model.get("id") or "instruct" in model.get("id")) and "vision" not in model.get("id")
            ]
            app.logger.info(f"{len(model_names)} modèles OpenAI pertinents trouvés.")
            return sorted(model_names)
        else:
            app.logger.warning(f"Format de réponse inattendu de l'API OpenAI (models): {models_data}")
            return []
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Impossible de contacter le serveur OpenAI à {url} pour lister les modèles. Erreur : {e}")
        return []
    except Exception as e:
        app.logger.error(f"Erreur inattendue lors de la récupération des modèles OpenAI : {e}")
        return []

def load_config():
    global INSTRUCTION_TEXT_1, INSTRUCTION_TEXT_2
    global LLM_SERVER_URL, LLM_SERVER_APIKEY, LLM_SERVER_MODEL, LLM_SERVER_ENABLED, LLM_SERVER_API_TYPE, LLM_SERVER_STREAM_RESPONSE
    global SUMMARIZER_LLM_URL, SUMMARIZER_LLM_APIKEY, SUMMARIZER_LLM_MODEL, SUMMARIZER_LLM_ENABLED, SUMMARIZER_LLM_API_TYPE, SUMMARIZER_LLM_PROMPT, SUMMARIZER_LLM_TIMEOUT, SUMMARIZER_MAX_WORKERS, SUMMARIZER_LLM_MODELS_LIST
    global LLM_CONFIG, BINARY_DETECTION_CONFIG, FILE_EXCLUSION_CONFIG # Ajouter cette ligne
    config = configparser.ConfigParser()
    try:
        if os.path.exists('config.ini'):
            config.read('config.ini', encoding='utf-8')
            INSTRUCTION_TEXT_1 = config.get('Instructions', 'instruction1_text', fallback=INSTRUCTION_TEXT_1)
            INSTRUCTION_TEXT_2 = config.get('Instructions', 'instruction2_text', fallback=INSTRUCTION_TEXT_2)
            app.logger.info("Configuration des instructions chargée depuis config.ini")

            # AJOUTER CE BLOC pour la config du navigateur
            if 'chatgpt' in config:
                LLM_CONFIG['chatgpt'] = dict(config['chatgpt'])
            if 'gemini' in config:
                LLM_CONFIG['gemini'] = dict(config['gemini'])
            app.logger.info("Configuration pour le pilotage de navigateur (ChatGPT, Gemini) chargée.")

            # Charger la configuration de détection binaire
            if 'BinaryDetection' in config:
                blacklist_str = config.get('BinaryDetection', 'extension_blacklist', fallback='')
                whitelist_str = config.get('BinaryDetection', 'extension_whitelist', fallback='')
                
                # Convertir les chaînes en sets pour une performance O(1)
                BINARY_DETECTION_CONFIG['blacklist'] = {ext.strip() for ext in blacklist_str.split(',') if ext.strip()}
                BINARY_DETECTION_CONFIG['whitelist'] = {ext.strip() for ext in whitelist_str.split(',') if ext.strip()}
                
                app.logger.info(f"Binary detection lists loaded: {len(BINARY_DETECTION_CONFIG['blacklist'])} blacklisted, {len(BINARY_DETECTION_CONFIG['whitelist'])} whitelisted.")
            else:
                app.logger.warning("Section [BinaryDetection] not found in config.ini. Binary file filtering might be incomplete.")
                BINARY_DETECTION_CONFIG['blacklist'] = set()
                BINARY_DETECTION_CONFIG['whitelist'] = set()

            # Charger la configuration d'exclusion de fichiers
            if 'FileExclusion' in config:
                file_blacklist_str = config.get('FileExclusion', 'file_blacklist', fallback='')
                pattern_blacklist_str = config.get('FileExclusion', 'pattern_blacklist', fallback='')
                
                # Convertir les chaînes en sets/listes
                FILE_EXCLUSION_CONFIG['file_blacklist'] = {f.strip() for f in file_blacklist_str.split(',') if f.strip()}
                FILE_EXCLUSION_CONFIG['pattern_blacklist'] = [p.strip() for p in pattern_blacklist_str.split(',') if p.strip()]
                
                app.logger.info(f"File exclusion lists loaded: {len(FILE_EXCLUSION_CONFIG['file_blacklist'])} files, {len(FILE_EXCLUSION_CONFIG['pattern_blacklist'])} patterns")
            else:
                app.logger.warning("Section [FileExclusion] not found in config.ini.")
                FILE_EXCLUSION_CONFIG['file_blacklist'] = set()
                FILE_EXCLUSION_CONFIG['pattern_blacklist'] = []

            if 'LLMServer' in config:
                LLM_SERVER_URL = config.get('LLMServer', 'url', fallback=None)
                LLM_SERVER_APIKEY = config.get('LLMServer', 'apikey', fallback=None)
                LLM_SERVER_MODEL = config.get('LLMServer', 'model', fallback=None)
                LLM_SERVER_ENABLED = config.getboolean('LLMServer', 'enabled', fallback=False)
                LLM_SERVER_API_TYPE = config.get('LLMServer', 'api_type', fallback='openai').lower()
                LLM_SERVER_STREAM_RESPONSE = config.getboolean('LLMServer', 'stream_response', fallback=False)
                if LLM_SERVER_ENABLED:
                    app.logger.info(f"Configuration du serveur LLM chargée (Type: {LLM_SERVER_API_TYPE}, Streaming: {LLM_SERVER_STREAM_RESPONSE}).")
                else:
                    app.logger.info("Fonctionnalité LLM désactivée dans config.ini.")
            else:
                app.logger.info("Section [LLMServer] non trouvée dans config.ini. Fonctionnalité LLM désactivée.")
            
            if 'SummarizerLLM' in config:
                SUMMARIZER_LLM_ENABLED = config.getboolean('SummarizerLLM', 'enabled', fallback=False)
                if SUMMARIZER_LLM_ENABLED:
                    SUMMARIZER_LLM_URL = config.get('SummarizerLLM', 'url', fallback=None)
                    SUMMARIZER_LLM_APIKEY = config.get('SummarizerLLM', 'apikey', fallback=None) # Conserver car présent dans template
                    SUMMARIZER_LLM_MODEL = config.get('SummarizerLLM', 'model', fallback=None)
                    SUMMARIZER_LLM_API_TYPE = config.get('SummarizerLLM', 'api_type', fallback='ollama').lower()
                    SUMMARIZER_LLM_PROMPT = config.get('SummarizerLLM', 'summarizer_prompt', fallback='''Tu es un assistant d'analyse de code spécialisé. Ta seule et unique tâche est de générer un résumé JSON à partir d'un fichier de code source, en suivant un format STRICT et IMPÉRATIF.
 
 --- DEBUT DE L'EXEMPLE ---
 [CODE INPUT]
 ```python
 #
 # hello.py
 #
 def say_hello(name):
     print(f"Hello, {{name}}!")
 
 if __name__ == "__main__":
     say_hello("World")
 ```
 
 [JSON OUTPUT]
 ```json
 {{
   "file_purpose": "Script simple pour afficher un message de salutation.",
   "core_logic": [
     "Définit une fonction `say_hello` qui prend un nom en paramètre et l'affiche.",
     "Appelle la fonction `say_hello` avec 'World' si le script est exécuté directement."
   ],
   "key_interactions": [
     "Aucune interaction externe, utilise uniquement des fonctions natives de Python."
   ],
   "tech_stack": [
     "Python"
   ]
 }}
 ```
 --- FIN DE L'EXEMPLE ---
 
 Maintenant, applique exactement le même processus au code suivant. Le format de sortie doit être EXCLUSIVEMENT un objet JSON valide avec les clés "file_purpose", "core_logic", "key_interactions", et "tech_stack". NE PAS inventer d'autres clés ou structures. Si tu ne parviens pas à analyser le fichier pour une raison quelconque, retourne un objet JSON avec une seule clé "error" décrivant le problème (e.g., {{"error": "Le fichier est trop long."}}).
 
 Analyse le code du fichier `{file_path}` ci-dessous et génère le JSON correspondant.
 
 Code du fichier `{file_path}`:
 ---
 {content}
 ---
 
 Rappel : Ton unique sortie doit être un objet JSON valide respectant la structure de l'exemple.
 ''')
                    SUMMARIZER_LLM_TIMEOUT = config.getint('SummarizerLLM', 'summarizer_timeout_seconds', fallback=SUMMARIZER_LLM_TIMEOUT)
                    SUMMARIZER_MAX_WORKERS = config.getint('SummarizerLLM', 'summarizer_max_workers', fallback=SUMMARIZER_MAX_WORKERS)
                    # --- NOUVELLE LOGIQUE DE RÉCUPÉRATION DES MODÈLES ---
                    app.logger.info(f"Récupération de la liste des modèles pour le type d'API Summarizer : {SUMMARIZER_LLM_API_TYPE}")
                    if SUMMARIZER_LLM_API_TYPE == 'ollama':
                        # Pour Ollama, l'URL est généralement celle du service, ex: http://localhost:11434
                        SUMMARIZER_LLM_MODELS_LIST = fetch_ollama_models(SUMMARIZER_LLM_URL)
                    elif SUMMARIZER_LLM_API_TYPE == 'openai':
                        # Pour OpenAI, l'URL peut être custom, mais on utilise la clé API de la section
                        SUMMARIZER_LLM_MODELS_LIST = fetch_openai_models(SUMMARIZER_LLM_URL, SUMMARIZER_LLM_APIKEY)
                    else:
                        app.logger.warning(f"Type d'API '{SUMMARIZER_LLM_API_TYPE}' non supporté pour la récupération dynamique de modèles. Utilisation de la liste statique de config.ini.")
                        # Fallback sur la liste statique du fichier de config si le type n'est pas géré
                        SUMMARIZER_LLM_MODELS_LIST = [model.strip() for model in config.get('SummarizerLLM', 'models_list', fallback=SUMMARIZER_LLM_MODEL).split(',') if model.strip()]

                    # Si la liste est vide après la tentative de fetch, utiliser le modèle par défaut comme fallback
                    if not SUMMARIZER_LLM_MODELS_LIST and SUMMARIZER_LLM_MODEL:
                        app.logger.warning(f"La liste des modèles est vide. Ajout du modèle par défaut '{SUMMARIZER_LLM_MODEL}' comme seule option.")
                        SUMMARIZER_LLM_MODELS_LIST.append(SUMMARIZER_LLM_MODEL)
                    
                    # S'assurer que le modèle par défaut est dans la liste et en première position
                    if SUMMARIZER_LLM_MODEL and SUMMARIZER_LLM_MODEL in SUMMARIZER_LLM_MODELS_LIST:
                        SUMMARIZER_LLM_MODELS_LIST.remove(SUMMARIZER_LLM_MODEL)
                        SUMMARIZER_LLM_MODELS_LIST.insert(0, SUMMARIZER_LLM_MODEL)
                    elif SUMMARIZER_LLM_MODEL and SUMMARIZER_LLM_MODEL not in SUMMARIZER_LLM_MODELS_LIST:
                         SUMMARIZER_LLM_MODELS_LIST.insert(0, SUMMARIZER_LLM_MODEL)

                    app.logger.info(f"Configuration du Summarizer LLM chargée (Modèle par défaut: {SUMMARIZER_LLM_MODEL}). Modèles disponibles: {len(SUMMARIZER_LLM_MODELS_LIST)}")
                else:
                    app.logger.info("Fonctionnalité LLM de Résumé désactivée dans config.ini.")
            else:
                app.logger.info("Section [SummarizerLLM] non trouvée. La compression par IA sera désactivée.")
        else:
            app.logger.warning("config.ini non trouvé, utilisation des instructions par défaut.")
    except Exception as e:
        app.logger.error(f"Erreur lors de la lecture de config.ini: {e}. Utilisation des instructions par défaut.")
    
    # Initialiser les services avec la configuration chargée
    global file_service, context_builder_service
    
    # Configuration pour FileService
    file_service_config = {
        'debug': False,
        'binary_blacklist': BINARY_DETECTION_CONFIG.get('blacklist', set()),
        'binary_whitelist': BINARY_DETECTION_CONFIG.get('whitelist', set()),
        'file_blacklist': FILE_EXCLUSION_CONFIG.get('file_blacklist', set()),
        'pattern_blacklist': FILE_EXCLUSION_CONFIG.get('pattern_blacklist', [])
    }
    file_service = FileService(file_service_config)
    
    # Configuration pour ContextBuilderService
    context_builder_service = ContextBuilderService({})
    
    app.logger.info("Services FileService et ContextBuilderService initialisés")

load_config() # Charger la configuration au démarrage

# --- In-memory cache for uploaded files ---
# Each uploaded file is a dictionary with keys: "name", "path", "content"
analysis_cache = {
    "uploaded_files": [],
    "ignored_patterns": []  # Store ignored patterns for debugging
}

from pathspec.patterns import GitWildMatchPattern  # Explicit import

# Les fonctions de détection de secrets et compact_code sont maintenant dans les services

# --- Utility functions to build the tree and context ---

def generate_tree_from_paths(relative_paths, root_name):
    tree = defaultdict(dict)
    for rel_path in relative_paths:
        parts = rel_path.split('/')
        current_level = tree
        for i, part in enumerate(parts):
            if not part:
                continue
            if i == len(parts) - 1:
                current_level[part] = True
            else:
                if part not in current_level or not isinstance(current_level[part], dict):
                    current_level[part] = {}
                current_level = current_level[part]
    lines = [f"{root_name}/"]
    def format_level(level, prefix=""):
        items = sorted(level.keys(), key=lambda k: (not isinstance(level[k], dict), k.lower()))
        for i, key in enumerate(items):
            connector = "└── " if i == len(items)-1 else "├── "
            lines.append(prefix + connector + key)
            if isinstance(level[key], dict) and level[key]:
                new_prefix = prefix + ("    " if i == len(items)-1 else "│   ")
                format_level(level[key], new_prefix)
    format_level(tree)
    return "\n".join(lines)

def detect_language(filename):
    ext = Path(filename).suffix.lower()
    lang_map = {
        ".py": "python", ".pyw": "python",
        ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
        ".html": "html", ".htm": "html",
        ".css": "css",
        ".json": "json",
        ".md": "markdown",
        ".txt": "text",
        ".java": "java", ".cs": "csharp", ".cpp": "cpp", ".c": "c", ".h": "c",
        ".rb": "ruby", ".php": "php", ".swift": "swift", ".kt": "kotlin",
        ".rs": "rust", ".go": "go", ".ts": "typescript", ".tsx": "typescript",
        ".sh": "bash", ".bat": "batch", ".ps1": "powershell",
        ".yaml": "yaml", ".yml": "yaml", ".xml": "xml", ".toml": "toml", ".ini": "ini"
    }
    return lang_map.get(ext, "")

# Les fonctions estimate_tokens et get_model_compatibility sont maintenant dans ContextBuilderService

def build_uploaded_context_string(uploaded_files, root_name="Uploaded_Directory", enable_masking=True, mask_mode="mask", instructions=None):
    # Generate the tree from relative paths
    relative_paths = [f["path"] for f in uploaded_files]
    tree_string = generate_tree_from_paths(relative_paths, root_name)
    
    context_parts = []
    # Standard header
    header = (
        "--- START CONTEXT ---\n"
        "Objective: Provide the complete context of a project to enable an LLM to understand the code and apply user-requested modifications.\n"
        "Structure: First, the project's directory tree is presented, followed by the full content of each relevant file.\n"
        "Security Note: Sensitive information such as API keys, tokens, passwords, and credentials have been automatically masked in this context.\n"
        "File Identification: Each file begins with `--- START FILE: [relative/path/to/file] ---` and ends with `--- END FILE: [relative/path/to/file] ---`.\n"
        "Code Format: Source code content is generally enclosed in Markdown code blocks with the language specified (e.g., ```python).\n"
        f"Considered project directory: {root_name}\n"
        f"Total files included: {len(uploaded_files)}\n"
        "--- END HEADER ---\n\n"
    )
    context_parts.append(header)
    context_parts.append("--- START DIRECTORY TREE ---\n" + tree_string + "\n--- END DIRECTORY TREE ---\n\n")
    
    # For each file, add the formatted content
    total_secrets_masked = 0
    files_with_secrets_list = []
    
    for file_obj in sorted(uploaded_files, key=lambda f: f["path"]):
        relative_path = file_obj["path"]
        header_file = f"--- START FILE: {relative_path} ---\n"
        footer_file = f"--- END FILE: {relative_path} ---\n\n"
        lang = detect_language(relative_path)
        
        content = file_obj["content"].rstrip()
        
        redacted_content = content
        secrets_count_ds = 0
        secrets_count_regex = 0
        
        if enable_masking:
            # Utiliser FileService pour la détection et le masquage des secrets
            redacted_content, secrets_count_ds = file_service.detect_and_redact_secrets(content, relative_path, mask_mode)
            # Apply regex on potentially already redacted content if first pass found something.
            # Or on original if first pass found nothing.
            final_redacted_content, secrets_count_regex = file_service.detect_and_redact_with_regex(redacted_content, relative_path)
            if secrets_count_regex > 0 : # if regex found new things
                 redacted_content = final_redacted_content

        current_file_secrets_masked = secrets_count_ds + secrets_count_regex
        if current_file_secrets_masked > 0:
            app.logger.info(f"Masked {current_file_secrets_masked} secrets in {relative_path}")
            if relative_path not in files_with_secrets_list:
                 files_with_secrets_list.append(relative_path)
            total_secrets_masked += current_file_secrets_masked
        
        content_to_use = redacted_content
        
        if lang:
            formatted_content = f"```{lang}\n{content_to_use}\n```\n"
        else:
            formatted_content = content_to_use + "\n"
        context_parts.append(header_file + formatted_content + footer_file)
    
    if instructions:
        instructions_part = "\n--- INSTRUCTIONS ---\n" + instructions + "\n--- END INSTRUCTIONS ---\n"
        context_parts.append(instructions_part)
    
    full_context = "".join(context_parts)
    
    # Utiliser ContextBuilderService pour l'estimation des tokens
    token_stats = context_builder_service.estimate_tokens(full_context)
    char_count_val = token_stats['char_count']
    estimated_tokens_val = token_stats['estimated_tokens']
    model_compatibility_val = token_stats['model_compatibility']
    
    # Calculer la taille de chaque fichier et les trier
    files_with_size = [
        {'path': f['path'], 'size': len(f['content'])}
        for f in uploaded_files
    ]
    largest_files = sorted(files_with_size, key=lambda f: f['size'], reverse=True)[:10]
    
    summary = {
        "total_files": len(analysis_cache.get("uploaded_files", [])),
        "included_files_count": len(uploaded_files),
        "excluded_files_count": len(analysis_cache.get("uploaded_files", [])) - len(uploaded_files),
        "total_lines": sum(f["content"].count('\n') for f in uploaded_files),
        "total_chars": char_count_val,
        "estimated_tokens": int(estimated_tokens_val),
        "model_compatibility": model_compatibility_val,
        "secrets_masked": total_secrets_masked,
        "files_with_secrets": files_with_secrets_list,
        "largest_files": largest_files  # NOUVELLE DONNÉE
    }
    
    return full_context, summary


# --- Application routes ---
# Gestion du favicon pour éviter les 404
@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/')
def index():
    app.logger.info("Received request for '/' - Serving index.html")
    app.logger.info(f"LLM_SERVER_ENABLED value: {LLM_SERVER_ENABLED}")
    return render_template('index.html',
                           instruction_text_1=INSTRUCTION_TEXT_1,
                           instruction_text_2=INSTRUCTION_TEXT_2,
                           llm_feature_enabled=LLM_SERVER_ENABLED,
                           llm_stream_response_enabled=LLM_SERVER_STREAM_RESPONSE,
                           summarizer_llm_enabled=SUMMARIZER_LLM_ENABLED,
                           summarizer_llm_models_list=SUMMARIZER_LLM_MODELS_LIST, # Add this
                           summarizer_max_workers=SUMMARIZER_MAX_WORKERS,     # Add this
                           has_md_files=analysis_cache.get('has_md_files', False))

@app.route('/toolbox')
def toolbox():
    app.logger.info("Received request for '/toolbox' - Serving toolbox.html")
    return render_template('toolbox.html')

@app.route('/upload', methods=['POST'])
def upload_directory():
    """
    Endpoint to receive the uploaded files from the browser.
    ...
    """
    if not request.is_json:
        return jsonify({"success": False, "error": "Invalid request format: JSON expected."}), 400
    data = request.get_json()
    if not data or "files" not in data or not isinstance(data["files"], list):
        return jsonify({"success": False, "error": "Missing or invalid file list."}), 400
    
    uploaded_files = []
    for file_obj in data["files"]:
        if isinstance(file_obj, dict) and all(k in file_obj for k in ["name", "path", "content"]):
            posix_path = file_obj["path"].replace("\\", "/")
            uploaded_files.append({
                "name": file_obj["name"],
                "path": posix_path,
                "content": file_obj["content"]
            })

    if not uploaded_files:
        return jsonify({"success": False, "error": "No valid file received."}), 400

    # --- NOUVELLE LOGIQUE DE FILTRAGE HYBRIDE ---
    app.logger.info("Applying 3-tier binary file detection...")
    filtered_by_binary_detection = []
    binary_files_detected = []
    
    # Temporairement stocker le contenu binaire pour l'analyse
    temp_file_contents = {f['path']: f['content'] for f in uploaded_files}
    
    for file_obj in uploaded_files:
        file_path_str = file_obj['path']
        ext = os.path.splitext(file_path_str)[1].lower()
        filename = os.path.basename(file_path_str)
        
        # Vérifier d'abord les exclusions de fichiers spécifiques
        if filename in FILE_EXCLUSION_CONFIG.get('file_blacklist', set()):
            binary_files_detected.append(file_path_str)
            app.logger.debug(f"Fichier exclu (blacklist): {filename}")
            continue
        
        # Vérifier les patterns d'exclusion
        excluded_by_pattern = False
        for pattern in FILE_EXCLUSION_CONFIG.get('pattern_blacklist', []):
            if fnmatch.fnmatch(filename, pattern):
                binary_files_detected.append(file_path_str)
                app.logger.debug(f"Fichier exclu (pattern '{pattern}'): {filename}")
                excluded_by_pattern = True
                break
        
        if excluded_by_pattern:
            continue

        # Niveau 1: Liste Noire d'extensions (Rejet Immédiat)
        if ext in BINARY_DETECTION_CONFIG.get('blacklist', set()):
            binary_files_detected.append(file_path_str)
            continue

        # Niveau 2: Liste Blanche d'extensions (Acceptation Immédiate)
        if ext in BINARY_DETECTION_CONFIG.get('whitelist', set()):
            filtered_by_binary_detection.append(file_obj)
            continue
            
        # Niveau 3: Analyse de contenu pour les cas restants
        try:
            # Pour la détection, nous n'avons besoin que des premiers octets.
            # Le contenu est déjà en mémoire, donc nous l'utilisons directement.
            # Note: le contenu est une chaîne, nous devons l'encoder pour la vérification.
            file_content_str = file_obj['content']
            # On ne vérifie que le début pour la performance, même si tout est en mémoire.
            if is_binary_string(file_content_str[:1024].encode('latin-1', errors='ignore')):
                binary_files_detected.append(file_path_str)
            else:
                filtered_by_binary_detection.append(file_obj)
        except Exception as e:
            app.logger.warning(f"Could not perform binary check on {file_path_str}, excluding it. Error: {e}")
            binary_files_detected.append(file_path_str)

    app.logger.info(f"Binary detection complete. Excluded {len(binary_files_detected)} files.")
    uploaded_files = filtered_by_binary_detection # Remplacer la liste par la version filtrée
    # --- FIN DE LA LOGIQUE DE FILTRAGE ---

    # --- NOUVELLE LOGIQUE AMÉLIORÉE ---

    # 1. Trouver dynamiquement la racine du projet dans les fichiers uploadés
    all_paths = [f['path'] for f in uploaded_files]
    project_root_prefix = ''
    if all_paths:
        common_prefix = os.path.commonpath(all_paths)
        # S'assurer que la racine est un "répertoire" et non un simple préfixe de nom de fichier
        if common_prefix and any(p.startswith(common_prefix + '/') for p in all_paths):
             project_root_prefix = common_prefix + '/'

    app.logger.info(f"Detected project root prefix in upload: '{project_root_prefix}'")

    # 2. Chercher et lire le .gitignore à la racine trouvée
    gitignore_path = f"{project_root_prefix}.gitignore".lstrip('/')
    gitignore_content = None
    for f in uploaded_files:
        if f['path'].lower() == gitignore_path:
            gitignore_content = f['content']
            app.logger.info(f"Found .gitignore file at: '{gitignore_path}'")
            break

    # 3. Construire les règles d'ignorance
    default_patterns = ['.git/'] # On peut simplifier, .gitignore est maintenant géré
    all_patterns = default_patterns.copy()
    if gitignore_content:
        lines = [line.strip() for line in gitignore_content.splitlines() if line.strip() and not line.strip().startswith("#")]
        all_patterns.extend(lines)
    else:
        app.logger.warning(f"Could not find .gitignore at path '{gitignore_path}'. Using default patterns only.")
        
    try:
        spec = pathspec.PathSpec.from_lines(GitWildMatchPattern, all_patterns)
        app.logger.info(f"Pathspec loaded with {len(spec.patterns)} total rules.")
        analysis_cache["ignored_patterns"] = all_patterns
    except Exception as e:
        app.logger.error(f"Error creating PathSpec: {e}")
        spec = pathspec.PathSpec.from_lines(GitWildMatchPattern, default_patterns)
        analysis_cache["ignored_patterns"] = default_patterns

    # 4. Appliquer le filtre sur les chemins relatifs à la racine trouvée
    filtered_files = []
    ignored_files_paths = []
    
    for file_obj in uploaded_files:
        # Obtenir le chemin relatif à la racine du projet détectée
        relative_path = file_obj['path'].removeprefix(project_root_prefix)
        
        if spec.match_file(relative_path):
            ignored_files_paths.append(file_obj['path']) # loguer le chemin complet
        else:
            # Conserver le fichier avec son chemin normalisé pour l'affichage
            file_obj['path'] = relative_path # On utilise maintenant le chemin relatif pour la suite
            filtered_files.append(file_obj)
            
    # --- FIN DE LA NOUVELLE LOGIQUE ---

    app.logger.info(f"Ignored files for context ({len(ignored_files_paths)}): {', '.join(ignored_files_paths[:5])}{'...' if len(ignored_files_paths) > 5 else ''}")
    app.logger.info(f"Upload successful: {len(filtered_files)} files kept for selection after applying rules.")
    
    analysis_cache["uploaded_files"] = filtered_files # Stocker les fichiers avec leur chemin relatif corrigé

    # Détecter la présence de fichiers Markdown
    has_md_files = any(f['path'].lower().endswith('.md') for f in filtered_files)
    analysis_cache['has_md_files'] = has_md_files
    app.logger.info(f"Markdown files detected: {has_md_files}")

    # La structure pour le rendu de l'arbre utilise maintenant les chemins relatifs
    file_tree_data = [{"path": f["path"]} for f in filtered_files]
    
    return jsonify({
        "success": True,
        "files": file_tree_data,
        "debug": {
            "ignored_patterns_used": analysis_cache["ignored_patterns"],
            "ignored_files_log": ignored_files_paths,
            "final_selectable_files_count": len(filtered_files)
        }
    })

def run_summarization_task(task_id, context_files, effective_model, effective_workers, masking_options, instructions):
    """
    Exécute la tâche de résumé dans un thread séparé et met à jour la progression.
    """
    try:
        summaries = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=effective_workers) as executor:
            future_to_file = {executor.submit(summarize_code_with_llm, f['content'], f['path'], effective_model): f for f in context_files}
            
            for future in concurrent.futures.as_completed(future_to_file):
                file_obj = future_to_file[future]
                try:
                    summaries[file_obj['path']] = future.result()
                except Exception as exc:
                    app.logger.error(f"Future for {file_obj['path']} generated an exception: {exc}")
                    summaries[file_obj['path']] = f"### [ERROR generating summary for {file_obj['path']}]"
                
                # Mettre à jour la progression
                with progress_lock:
                    if task_id in progress_tasks:
                        progress_tasks[task_id]['completed'] += 1

        # Une fois la boucle terminée, assembler le résultat final
        all_summaries_content = "\n\n---\n\n".join(summaries[f['path']] for f in context_files)
        summary_file = {
            "path": "AI_GENERATED_PROJECT_SUMMARY.md",
            "name": "AI_GENERATED_PROJECT_SUMMARY.md",
            "content": all_summaries_content
        }
        final_context_files = [summary_file]

        markdown_context, summary = build_uploaded_context_string(
            uploaded_files=final_context_files,
            root_name="Uploaded_Directory",
            enable_masking=masking_options.get("enable_masking", True),
            mask_mode=masking_options.get("mask_mode", "mask"),
            instructions=instructions
        )
        
        final_result = {
            "markdown": markdown_context,
            "summary": summary
        }

        # Mettre à jour la tâche avec le statut "complete" et le résultat
        with progress_lock:
            if task_id in progress_tasks:
                progress_tasks[task_id]['status'] = 'complete'
                progress_tasks[task_id]['result'] = final_result

    except Exception as e:
        app.logger.error(f"Error in summarization thread for task {task_id}: {e}")
        with progress_lock:
            if task_id in progress_tasks:
                progress_tasks[task_id]['status'] = 'error'
                progress_tasks[task_id]['result'] = {"error": str(e)}


@app.route('/generate', methods=['POST'])
def generate_context():
    if not request.is_json:
        return jsonify({"success": False, "error": "Invalid request format: JSON expected."}), 400
    data = request.get_json()
    if not data or "selected_files" not in data or not isinstance(data["selected_files"], list):
        return jsonify({"success": False, "error": "Missing or invalid selected files list."}), 400
    
    masking_options = data.get("masking_options", {})
    enable_masking = masking_options.get("enable_masking", True)
    mask_mode = masking_options.get("mask_mode", "mask")
    
    instructions = data.get("instructions", "")
    compression_mode = data.get("compression_mode", "none")
    summarizer_model_override = data.get("summarizer_model", None)
    summarizer_workers_override = data.get("summarizer_max_workers", None)
    
    app.logger.info(f"Secret masking: {'enabled' if enable_masking else 'disabled'}, mode: {mask_mode}")
    app.logger.info(f"Instructions reçues: {instructions[:100]}{'...' if len(instructions) > 100 else ''}")
    app.logger.info(f"Compression mode selected: {compression_mode}")
    
    selected_paths = data["selected_files"]
    all_selectable_files = analysis_cache.get("uploaded_files", [])
    
    context_files = [f for f in all_selectable_files if f["path"] in selected_paths]
    if not context_files:
        if selected_paths:
             app.logger.warning(f"User selected paths {selected_paths}, but these did not match any available selectable files.")
        return jsonify({"success": False, "error": "No files selected or selection did not match available files."}), 400
        
    if compression_mode == "compact":
        app.logger.info("Applying 'Compact Mode' compression.")
        for file_obj in context_files:
            if file_obj['content']:
                file_obj['content'] = context_builder_service.compact_code(file_obj['content'])
    
    elif compression_mode == "summarize":
        app.logger.info("Applying 'Summarize with AI' compression.")
        
        effective_workers = SUMMARIZER_MAX_WORKERS
        if summarizer_workers_override is not None:
            try:
                effective_workers = int(summarizer_workers_override)
            except (ValueError, TypeError):
                app.logger.warning(f"Invalid summarizer_max_workers value received: {summarizer_workers_override}. Falling back to default.")
        
        effective_model = SUMMARIZER_LLM_MODEL
        if summarizer_model_override and summarizer_model_override in SUMMARIZER_LLM_MODELS_LIST:
            effective_model = summarizer_model_override

        app.logger.info(f"Summarizing with model: '{effective_model}' and max_workers: {effective_workers}")

        task_id = str(uuid.uuid4())
        with progress_lock:
            progress_tasks[task_id] = {
                'completed': 0,
                'total': len(context_files),
                'status': 'running',
                'result': None
            }
        
        # Démarrer la tâche de résumé en arrière-plan
        thread = threading.Thread(target=run_summarization_task, args=(
            task_id, context_files, effective_model, effective_workers, masking_options, instructions
        ))
        thread.start()
        
        return jsonify({"success": True, "task_id": task_id})

    # Pour les modes "none" et "compact", le comportement reste le même
    markdown_context, summary = build_uploaded_context_string(
        uploaded_files=context_files,
        root_name="Uploaded_Directory",
        enable_masking=enable_masking,
        mask_mode=mask_mode,
        instructions=instructions
    )
    
    return jsonify({
        "success": True, 
        "markdown": markdown_context,
        "summary": summary
    })

@app.route('/summarize_progress')
def summarize_progress():
    task_id = request.args.get('task_id')
    if not task_id:
        return Response("data: {\"error\": \"task_id is required\"}\n\n", mimetype='text/event-stream')

    def generate():
        while True:
            with progress_lock:
                task = progress_tasks.get(task_id)
                if not task:
                    yield f"data: {json.dumps({'status': 'error', 'message': 'Task not found'})}\n\n"
                    break
                
                status = task['status']
                if status == 'running':
                    progress_data = {
                        'status': 'running',
                        'completed': task['completed'],
                        'total': task['total']
                    }
                    yield f"data: {json.dumps(progress_data)}\n\n"
                elif status == 'complete':
                    result_data = {
                        'status': 'complete',
                        'result': task['result']
                    }
                    yield f"event: done\ndata: {json.dumps(result_data)}\n\n"
                    # Nettoyer la tâche après l'envoi du résultat
                    del progress_tasks[task_id]
                    break
                elif status == 'error':
                    error_data = {
                        'status': 'error',
                        'message': task.get('result', {}).get('error', 'An unknown error occurred.')
                    }
                    yield f"data: {json.dumps(error_data)}\n\n"
                    del progress_tasks[task_id]
                    break
            
            time.sleep(0.5)

    return Response(generate(), mimetype='text/event-stream')


@app.route('/debug_gitignore', methods=['GET'])
def debug_gitignore():
    return jsonify(analysis_cache.get("ignored_patterns", []))

@app.route('/send_to_llm', methods=['POST'])
def send_to_llm():
    if not LLM_SERVER_ENABLED:
        return jsonify({"error": "LLM feature is not enabled in config.ini"}), 400

    if not LLM_SERVER_URL or not LLM_SERVER_MODEL or \
       (LLM_SERVER_API_TYPE != "ollama" and not LLM_SERVER_APIKEY):
        app.logger.error(f"LLM server configuration incomplete. URL: {LLM_SERVER_URL}, Model: {LLM_SERVER_MODEL}, APIKey set: {bool(LLM_SERVER_APIKEY)}, Type: {LLM_SERVER_API_TYPE}")
        return jsonify({"error": "LLM server configuration is incomplete in config.ini"}), 400

    data = request.get_json()
    messages_history = data.get('messages')

    app.logger.info(f"Dans /send_to_llm, LLM_SERVER_API_TYPE = {LLM_SERVER_API_TYPE}, Streaming: {LLM_SERVER_STREAM_RESPONSE}")
    if messages_history and len(messages_history) > 0:
        log_msg_content = messages_history[-1]['content']
        app.logger.info(f"Dernier message ({messages_history[-1]['role']}): {log_msg_content[:150]}{'...' if len(log_msg_content)>150 else ''}")
    else:
        app.logger.warning("Aucun historique de messages reçu pour /send_to_llm.")
        return jsonify({"error": "No messages provided"}), 400 # No messages, so error

    headers = {"Content-Type": "application/json"}
    if LLM_SERVER_APIKEY and LLM_SERVER_API_TYPE != "ollama":
        headers["Authorization"] = f"Bearer {LLM_SERVER_APIKEY}"

    payload = {
        "model": LLM_SERVER_MODEL,
        "messages": messages_history,
        "stream": LLM_SERVER_STREAM_RESPONSE # Global stream setting
    }

    # Specific handling for Ollama if not streaming (as it has a slightly different non-stream payload expectation sometimes)
    # If streaming is globally enabled, we assume Ollama supports the OpenAI-compatible stream format.
    if LLM_SERVER_API_TYPE == "ollama" and not LLM_SERVER_STREAM_RESPONSE:
        # Ollama's non-streaming /api/chat doesn't need "stream":false if it's the default.
        # However, to be explicit if we were to add other ollama specific non-stream params, this is where they'd go.
        # For now, just removing "stream" if it was added and global stream is false.
        if "stream" in payload and not payload["stream"]: # if stream:false was set by global default
             del payload["stream"] # Ollama might not like stream:false explicitly on non-stream endpoint for /api/chat

    target_url = LLM_SERVER_URL
    # URL normalization logic (déjà revue et corrigée)
    if LLM_SERVER_API_TYPE == "ollama":
        normalized_url = target_url.rstrip('/')
        ollama_suffix = "api/chat"
        openai_compatible_suffix = "v1/chat/completions"
        if not (normalized_url.endswith(ollama_suffix) or normalized_url.endswith(openai_compatible_suffix)):
            target_url = f"{normalized_url}/{ollama_suffix}"
        else:
            target_url = normalized_url
        app.logger.info(f"Appel à l'API Ollama sur l'URL: {target_url}")
    elif LLM_SERVER_API_TYPE == "openai":
        normalized_url = target_url.rstrip('/')
        openai_suffix = "v1/chat/completions"
        if not normalized_url.endswith(openai_suffix):
            target_url = f"{normalized_url}/{openai_suffix}"
        else:
            target_url = normalized_url
        app.logger.info(f"Appel à l'API OpenAI sur l'URL: {target_url}")

    app.logger.info(f"En-têtes envoyés à l'API: {headers}")
    
    try:
        # Pass stream=True to requests.post to enable response streaming from requests library perspective
        api_response = requests.post(target_url, headers=headers, json=payload, timeout=180, stream=LLM_SERVER_STREAM_RESPONSE)
        api_response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

        if LLM_SERVER_STREAM_RESPONSE:
            def generate_stream_response():
                app.logger.info(f"Streaming activé. Début du traitement du flux depuis {LLM_SERVER_API_TYPE}.")
                # Using iter_lines to process Server-Sent Events (SSE)
                for line in api_response.iter_lines():
                    if line:
                        decoded_line = line.decode('utf-8')
                        if decoded_line.startswith("data: "):
                            json_content = decoded_line[len("data: "):].strip()
                            if json_content == "[DONE]": # OpenAI stream termination
                                app.logger.info("Stream terminé par [DONE].")
                                yield f"data: {json.dumps({'type': 'done', 'content': ''})}\\n\\n"
                                break
                            
                            try:
                                data_chunk = json.loads(json_content)
                                token_content = ""
                                event_type = "content" # default

                                if LLM_SERVER_API_TYPE == "openai":
                                    if data_chunk.get("choices") and len(data_chunk["choices"]) > 0:
                                        delta = data_chunk["choices"][0].get("delta")
                                        if delta and "content" in delta and delta["content"] is not None:
                                            token_content = delta["content"]
                                        # Could also check for finish_reason if needed, e.g. data_chunk["choices"][0].get("finish_reason")
                                
                                elif LLM_SERVER_API_TYPE == "ollama":
                                    # Ollama streaming for /api/chat:
                                    # { "model": "...", "created_at": "...", "message": { "role": "assistant", "content": "..." }, "done": false }
                                    # When done is true, message may or may not have content.
                                    if data_chunk.get("message") and "content" in data_chunk["message"]:
                                        token_content = data_chunk["message"]["content"]
                                    
                                    if data_chunk.get("done"): # Ollama stream termination
                                        app.logger.info("Stream Ollama terminé (done: true).")
                                        # Send final accumulated content if any, then DONE signal
                                        if token_content: # Send last part if "done" is true and content exists
                                             yield f"data: {json.dumps({'type': 'content', 'content': token_content})}\\n\\n"
                                        yield f"data: {json.dumps({'type': 'done', 'content': ''})}\\n\\n"
                                        break # Stop generation

                                if token_content: # Send if there is actual content
                                    # app.logger.debug(f"Stream chunk: {token_content}")
                                    yield f"data: {json.dumps({'type': event_type, 'content': token_content})}\\n\\n"
                                elif data_chunk.get("error"): # Check for streamed error messages
                                    error_message = data_chunk.get("error")
                                    app.logger.error(f"Erreur reçue dans le flux: {error_message}")
                                    yield f"data: {json.dumps({'type': 'error', 'content': error_message})}\\n\\n"
                                    break # Stop on error

                            except json.JSONDecodeError:
                                app.logger.warning(f"Ligne non-JSON dans le flux (ignorée): {json_content}")
                            except Exception as e_stream:
                                app.logger.error(f"Erreur pendant le traitement du flux: {e_stream}")
                                yield f"data: {json.dumps({'type': 'error', 'content': str(e_stream)})}\\n\\n"
                                break # Stop on unexpected error
                app.logger.info("Générateur de flux terminé.")
            return Response(generate_stream_response(), mimetype='text/event-stream')
        else:
            # Non-streaming response handling
            llm_response_json = api_response.json()
            content_to_return = ""
            if LLM_SERVER_API_TYPE == "openai":
                choices = llm_response_json.get("choices")
                if choices and len(choices) > 0 and choices[0].get("message"):
                    content_to_return = choices[0]["message"].get("content", "")
                else:
                    app.logger.error(f"Format de réponse OpenAI non-streamé inattendu: {llm_response_json}")
                    return jsonify({"error": "Invalid OpenAI response format", "details": llm_response_json}), 500
            elif LLM_SERVER_API_TYPE == "ollama":
                if llm_response_json.get("message") and "content" in llm_response_json["message"]:
                    content_to_return = llm_response_json["message"]["content"]
                elif "error" in llm_response_json: # Ollama can return an error object
                     app.logger.error(f"Erreur de l'API Ollama (non-streamé): {llm_response_json['error']}")
                     return jsonify({"error": f"Ollama API error: {llm_response_json['error']}", "details": llm_response_json}), 500
                else:
                    app.logger.error(f"Format de réponse Ollama non-streamé inattendu: {llm_response_json}")
                    return jsonify({"error": "Invalid Ollama response format", "details": llm_response_json}), 500
            else:
                return jsonify({"error": f"Unsupported LLM API type: {LLM_SERVER_API_TYPE}"}), 400
            
            return jsonify({"response": content_to_return})

    except requests.exceptions.HTTPError as http_err:
        error_details = "Unknown error"
        try:
            error_details = http_err.response.json()
        except json.JSONDecodeError:
            error_details = http_err.response.text
        app.logger.error(f"HTTP error calling LLM: {http_err} - Details: {error_details}")
        return jsonify({"error": f"HTTP error: {http_err}", "details": error_details}), \
               http_err.response.status_code if http_err.response else 500
    except requests.exceptions.RequestException as req_err:
        app.logger.error(f"Request exception calling LLM: {req_err}")
        return jsonify({"error": f"Request error: {str(req_err)}"}), 500
    except Exception as e:
        app.logger.error(f"Unexpected error in send_to_llm: {e}", exc_info=True)
        return jsonify({"error": f"Unexpected server error: {str(e)}"}), 500

@socketio.on('connect')
def handle_connect():
    app.logger.info('Client Socket.IO connecté')

@socketio.on('disconnect')
def handle_disconnect():
    app.logger.info('Client Socket.IO déconnecté')



def summarize_code_with_llm(content: str, file_path: str, model: str) -> str:
    """Appelle le LLM de résumé pour obtenir un résumé du code en utilisant l'endpoint /api/generate."""
    if not SUMMARIZER_LLM_ENABLED or not SUMMARIZER_LLM_URL or not model: # Check model argument
        return f"### [SUMMARIZER NOT CONFIGURED FOR {file_path}]"

    prompt = SUMMARIZER_LLM_PROMPT.format(file_path=file_path, content=content)
    
    headers = {"Content-Type": "application/json"}
    # Payload pour l'endpoint /api/generate d'Ollama
    payload = {
        "model": model, # Use the model argument here
        "prompt": prompt,
        "format": "json",
        "stream": False
    }
    
    try:
        target_url = SUMMARIZER_LLM_URL
        # Normalisation de l'URL pour /api/generate
        if SUMMARIZER_LLM_API_TYPE == "ollama":
            normalized_url = target_url.rstrip('/')
            ollama_suffix = "api/generate"  # Utiliser l'endpoint de génération
            if not normalized_url.endswith(ollama_suffix):
                target_url = f"{normalized_url}/{ollama_suffix}"
            else:
                target_url = normalized_url
        
        app.logger.info(f"Calling Summarizer API (Ollama) at URL: {target_url}")
        response = requests.post(target_url, headers=headers, json=payload, timeout=SUMMARIZER_LLM_TIMEOUT)
        response.raise_for_status()
        summary_json = response.json()
        llm_response_str = summary_json.get('response', '{}')
        app.logger.info(f"LLM summarizer raw response for {file_path}: {llm_response_str}")

        if not llm_response_str.strip():
            app.logger.warning(f"LLM summarizer returned an empty response for {file_path}.")
            summary_content = {}
        else:
            summary_content = json.loads(llm_response_str)

        if 'error' in summary_content:
            app.logger.error(f"LLM returned an error for {file_path}: {summary_content['error']}")
            return f"### [SUMMARY FAILED for {file_path}]\n\n*LLM Error: {summary_content['error']}*"

        # --- NOUVELLE LOGIQUE DE VALIDATION ---
        required_keys = ["file_purpose", "core_logic", "key_interactions", "tech_stack"]
        if not all(key in summary_content for key in required_keys):
            app.logger.warning(f"LLM response for {file_path} is missing required keys. Raw content: {summary_content}")
            return (
                f"### Résumé partiel de `{file_path}` (Format de réponse inattendu)\n\n"
                f"**Objectif:** {summary_content.get('file_purpose', 'Non spécifié')}\n\n"
                f"**Logique principale:**\n- {summary_content.get('core_logic', 'Non spécifié')}\n\n"
                f"**Données brutes reçues:**\n```json\n{json.dumps(summary_content, indent=2)}\n```"
            )

        formatted_summary = (
            f"### Résumé de `{file_path}`\n\n"
            f"**Objectif:** {summary_content.get('file_purpose', 'N/A')}\n\n"
            f"**Logique principale:**\n- {'\n- '.join(summary_content.get('core_logic', ['N/A']))}\n\n"
            f"**Interactions clés:**\n- {'\n- '.join(summary_content.get('key_interactions', ['N/A']))}\n\n"
            f"**Stack technique:** {', '.join(summary_content.get('tech_stack', ['N/A']))}"
        )
        return formatted_summary
    except json.JSONDecodeError as e:
        app.logger.error(f"Failed to decode JSON from LLM for {file_path}. Error: {e}. Raw response was: {llm_response_str}")
        return f"### [SUMMARY FAILED for {file_path}]\n\n*Error: LLM returned invalid JSON*"
    except Exception as e:
        app.logger.error(f"Error summarizing {file_path}: {e}")
        return f"### [SUMMARY FAILED for {file_path}]\n\n*Error: {e}*"

@app.route('/summarize_code', methods=['POST'])
def summarize_code():
    if not SUMMARIZER_LLM_ENABLED:
        return jsonify({"error": "Summarizer LLM feature is not enabled in config.ini"}), 400

    if not SUMMARIZER_LLM_URL or not SUMMARIZER_LLM_MODEL or \
       (SUMMARIZER_LLM_API_TYPE != "ollama" and not SUMMARIZER_LLM_APIKEY):
        app.logger.error(f"Summarizer LLM server configuration incomplete. URL: {SUMMARIZER_LLM_URL}, Model: {SUMMARIZER_LLM_MODEL}, APIKey set: {bool(SUMMARIZER_LLM_APIKEY)}, Type: {SUMMARIZER_LLM_API_TYPE}")
        return jsonify({"error": "Summarizer LLM server configuration is incomplete in config.ini"}), 400

    data = request.get_json()
    code_to_summarize = data.get('code')
    if not code_to_summarize:
        return jsonify({"error": "No code provided for summarization"}), 400

    app.logger.info(f"Sending code to summarizer LLM (Type: {SUMMARIZER_LLM_API_TYPE}).")

    headers = {"Content-Type": "application/json"}
    if SUMMARIZER_LLM_APIKEY and SUMMARIZER_LLM_API_TYPE != "ollama":
        headers["Authorization"] = f"Bearer {SUMMARIZER_LLM_APIKEY}"

    # Utiliser la fonction centralisée pour obtenir le résumé
    try:
        summary = summarize_code_with_llm(code_to_summarize, "test_code_snippet", SUMMARIZER_LLM_MODEL)
        # La fonction retourne déjà un formatage, mais pour un test API, on peut vouloir le JSON brut
        # Pour l'instant, on retourne le résumé formaté pour être cohérent
        if "SUMMARY FAILED" in summary or "NOT CONFIGURED" in summary:
             return jsonify({"error": "Failed to get summary from LLM.", "details": summary}), 500
        
        return jsonify({"summary": summary})

    except requests.exceptions.HTTPError as http_err:
        error_details = "Unknown error"
        try:
            error_details = http_err.response.json()
        except json.JSONDecodeError:
            error_details = http_err.response.text
        app.logger.error(f"HTTP error calling Summarizer LLM: {http_err} - Details: {error_details}")
        return jsonify({"error": f"HTTP error: {http_err}", "details": error_details}), \
               http_err.response.status_code if http_err.response else 500
    except requests.exceptions.RequestException as req_err:
        app.logger.error(f"Request exception calling Summarizer LLM: {req_err}")
        return jsonify({"error": f"Request error: {str(req_err)}"}), 500
    except Exception as e:
        app.logger.error(f"Unexpected error in summarize_code: {e}", exc_info=True)
        return jsonify({"error": f"Unexpected server error: {str(e)}"}), 500

@app.route('/api/llm/chat', methods=['POST'])
def llm_chat():
    """API endpoint pour le chat avec le LLM depuis la Toolbox"""
    if not LLM_SERVER_ENABLED:
        return jsonify({"error": "LLM feature is not enabled in config.ini"}), 400
    
    if not LLM_SERVER_URL or not LLM_SERVER_MODEL:
        return jsonify({"error": "LLM server configuration is incomplete in config.ini"}), 400
    
    data = request.get_json()
    messages = data.get('messages', [])
    stream = data.get('stream', False)
    
    if not messages:
        return jsonify({"error": "No messages provided"}), 400
    
    app.logger.info(f"Sending chat to LLM with {len(messages)} messages (streaming: {stream})")
    
    headers = {"Content-Type": "application/json"}
    if LLM_SERVER_APIKEY:
        headers["Authorization"] = f"Bearer {LLM_SERVER_APIKEY}"
    
    try:
        if LLM_SERVER_API_TYPE == "openai":
            payload = {
                "model": LLM_SERVER_MODEL,
                "messages": messages,
                "stream": stream
            }
            target_url = LLM_SERVER_URL.rstrip('/') + "/chat/completions"
        else:  # ollama
            # Pour Ollama, on doit formater différemment
            # Concaténer tous les messages en un seul prompt
            prompt = "\n\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in messages])
            payload = {
                "model": LLM_SERVER_MODEL,
                "prompt": prompt,
                "stream": stream
            }
            target_url = LLM_SERVER_URL.rstrip('/') + "/api/generate"
        
        if stream and LLM_SERVER_STREAM_RESPONSE:
            # Pour le streaming, on retourne directement la réponse
            response = requests.post(target_url, headers=headers, json=payload, stream=True)
            response.raise_for_status()
            
            def generate():
                for line in response.iter_lines():
                    if line:
                        yield line.decode('utf-8') + '\n\n'
            
            return Response(generate(), mimetype='text/event-stream')
        else:
            # Mode non-stream
            response = requests.post(target_url, headers=headers, json=payload)
            response.raise_for_status()
            
            if LLM_SERVER_API_TYPE == "openai":
                result = response.json()
                assistant_message = result['choices'][0]['message']['content']
            else:  # ollama
                result = response.json()
                assistant_message = result.get('response', '')
            
            return jsonify({"response": assistant_message})
            
    except requests.exceptions.HTTPError as http_err:
        error_details = "Unknown error"
        try:
            error_details = http_err.response.json()
        except:
            error_details = http_err.response.text
        app.logger.error(f"HTTP error calling LLM: {http_err} - Details: {error_details}")
        return jsonify({"error": f"HTTP error: {http_err}", "details": error_details}), 500
    except Exception as e:
        app.logger.error(f"Error in llm_chat: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500