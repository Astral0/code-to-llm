# web_server.py
from flask import Flask, request, jsonify, render_template, Response
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

app = Flask(__name__, template_folder='templates', static_folder='static')

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

def load_config():
    global INSTRUCTION_TEXT_1, INSTRUCTION_TEXT_2
    global LLM_SERVER_URL, LLM_SERVER_APIKEY, LLM_SERVER_MODEL, LLM_SERVER_ENABLED, LLM_SERVER_API_TYPE, LLM_SERVER_STREAM_RESPONSE
    config = configparser.ConfigParser()
    try:
        if os.path.exists('config.ini'):
            config.read('config.ini', encoding='utf-8')
            INSTRUCTION_TEXT_1 = config.get('Instructions', 'instruction1_text', fallback=INSTRUCTION_TEXT_1)
            INSTRUCTION_TEXT_2 = config.get('Instructions', 'instruction2_text', fallback=INSTRUCTION_TEXT_2)
            app.logger.info("Configuration des instructions chargée depuis config.ini")

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
        else:
            app.logger.warning("config.ini non trouvé, utilisation des instructions par défaut.")
    except Exception as e:
        app.logger.error(f"Erreur lors de la lecture de config.ini: {e}. Utilisation des instructions par défaut.")

load_config() # Charger la configuration au démarrage

# --- In-memory cache for uploaded files ---
# Each uploaded file is a dictionary with keys: "name", "path", "content"
analysis_cache = {
    "uploaded_files": [],
    "ignored_patterns": []  # Store ignored patterns for debugging
}

# Import pour detect-secrets avec corrections
try:
    from detect_secrets import SecretsCollection
    from detect_secrets.settings import default_settings
    # from detect_secrets.plugins.base import BasePlugin # Moins utilisé directement
    # from detect_secrets.core import baseline # Moins utilisé directement
    from detect_secrets.plugins import initialize as initialize_detect_secrets_plugins
    HAS_DETECT_SECRETS = True
except ImportError:
    app.logger.warning("detect-secrets library not found. Secret masking will be disabled.")
    HAS_DETECT_SECRETS = False

from pathspec.patterns import GitWildMatchPattern  # Explicit import

# --- Fonctions de détection et masquage des secrets ---

def detect_and_redact_secrets(content, file_path, redact_mode='mask'):
    """
    Détecte et masque les secrets dans le contenu d'un fichier.
    
    Args:
        content (str): Le contenu du fichier à analyser
        file_path (str): Le chemin du fichier (utilisé pour les règles spécifiques au format)
        redact_mode (str): Le mode de redaction ('mask' pour [MASKED SECRET], 'remove' pour supprimer la ligne)
    
    Returns:
        tuple: (contenu redacté, nombre de secrets détectés)
    """
    # Vérifier si la bibliothèque detect-secrets est disponible
    if not HAS_DETECT_SECRETS:
        return content, 0

    try:
        # Initialiser la collection de secrets
        secrets = SecretsCollection()
        
        # Initialiser les plugins de détection disponibles
        plugins_used = list(initialize_detect_secrets_plugins.from_parser_builder([]))
        for plugin in plugins_used:
            try:
                secrets.scan_string_content(content, plugin, path=file_path)
            except Exception as plugin_error:
                app.logger.debug(f"Plugin {plugin.__class__.__name__} failed for {file_path}: {plugin_error}")
        
        # Si aucun secret n'est détecté, retourner le contenu original
        if not secrets.data:
            return content, 0
        
        # Redacter les secrets détectés
        lines = content.splitlines()
        redacted_lines = list(lines)  # Copie pour modification
        
        # Trier les secrets par numéro de ligne
        secrets_by_line = {}
        for filename, secret_list in secrets.data.items():
            for secret in secret_list:
                line_num = secret['line_number'] - 1  # Ajuster pour l'indexation à 0
                if line_num not in secrets_by_line:
                    secrets_by_line[line_num] = []
                secrets_by_line[line_num].append(secret)
        
        # Redacter chaque ligne contenant des secrets
        secrets_count = 0
        for line_num, line_secrets in sorted(secrets_by_line.items(), reverse=True):
            if line_num >= len(redacted_lines):
                continue  # Ignorer si la ligne est hors limites
            
            if redact_mode == 'remove':
                # Supprimer la ligne entière
                redacted_lines[line_num] = f"[LINE REMOVED DUE TO DETECTED SECRET]"
                secrets_count += len(line_secrets)
            else:
                # Mode par défaut: masquer les secrets individuellement
                # Pour l'API actuelle de detect-secrets, nous ne pouvons pas facilement
                # obtenir la position exacte du secret. Masquons donc la ligne entière.
                current_line = redacted_lines[line_num]
                redacted_lines[line_num] = f"[LINE CONTAINING SENSITIVE DATA: {line_secrets[0]['type']}]"
                secrets_count += 1
        
        # Reconstituer le contenu avec les lignes redactées
        redacted_content = "\n".join(redacted_lines)
        
        return redacted_content, secrets_count
        
    except Exception as e:
        app.logger.error(f"Error using detect-secrets: {e}")
        return content, 0

# Fonction supplémentaire pour détecter les secrets avec regex
def detect_and_redact_with_regex(content, file_path):
    """
    Détecte et masque les patterns courants de secrets avec des expressions régulières.
    Complémentaire à detect-secrets pour des cas spécifiques.
    
    Args:
        content (str): Le contenu du fichier
        file_path (str): Le chemin du fichier (pour le logging)
        
    Returns:
        tuple: (contenu redacté, nombre de secrets détectés)
    """
    # Patterns courants de secrets et informations d'identification
    patterns = {
        # API Keys - différents formats courants
        'api_key': r'(?i)(api[_-]?key|apikey|api_token|auth_token|authorization_token|bearer_token)["\']?\s*[:=]\s*["\']?([0-9a-zA-Z\-_\.]{16,128})["\']?',
        # Tokens divers (OAuth, JWT, etc.)
        'token': r'(?i)(access_token|auth_token|token)["\']?\s*[:=]\s*["\']?([0-9a-zA-Z._\-]{8,64})["\']?',
        # Clés AWS
        'aws_key': r'(?i)(AKIA[0-9A-Z]{16})',
        # URLs contenant username:password
        'url_auth': r'(?i)https?://[^:@/\s]+:[^:@/\s]+@[^/\s]+',
        # Clés privées
        'private_key_pem': r'-----BEGIN ((RSA|EC|OPENSSH|PGP) )?PRIVATE KEY-----',
        # Documentation de credentials/variables sensibles avec valeurs
        'credentials_doc': r'(?i)# ?(password|secret|key|token|credential).*[=:] ?"[^"]{3,}"',
        # Clés AWS
        'aws_secret': r'(?i)(aws[\w_\-]*secret[\w_\-]*key)["\']?\s*[:=]\s*["\']?([0-9a-zA-Z\-_\/+]{40})["\']?',
        # Clés privées
        'private_key': r'(?i)(-----BEGIN [A-Z]+ PRIVATE KEY-----)',
        # Connection strings
        'connection_string': r'(?i)(mongodb|mysql|postgresql|sqlserver|redis|amqp)://[^:]+:[^@]+@[:\w\.\-]+[/:\w\d\?=&%\-\.]*'
    }
    
    # Initialiser les variables
    lines = content.splitlines()
    redacted_lines = list(lines)
    count = 0
    
    # Parcourir chaque ligne pour détecter les patterns
    for i, line in enumerate(lines):
        for pattern_name, pattern in patterns.items():
            matches = list(re.finditer(pattern, line))
            if matches:
                redacted_lines[i] = f"[LINE CONTAINING SENSITIVE DATA: {pattern_name}]"
                count += 1
                break  # Passer à la ligne suivante une fois qu'un pattern est trouvé
    
    # Reconstituer le contenu
    redacted_content = "\n".join(redacted_lines)
    
    return redacted_content, count

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

def estimate_tokens(text):
    """
    Estimates the number of tokens in a text.
    Uses a simple heuristic of 4 characters per token.
    """
    char_count = len(text)
    # Simple heuristic: on average 4 characters per token
    estimated_tokens = char_count / 4
    
    # Ajouter un message au sujet du masquage des secrets dans l'estimation
    masked_secrets_prefix = " (including masked sensitive information)" if "SENSITIVE DATA" in text else ""
    
    # Retourner l'estimation avec un message sur le masquage si applicable
    
    return char_count, estimated_tokens

def get_model_compatibility(tokens):
    """
    Returns information about model compatibility based on the estimated token count.
    """
    if tokens < 3500:
        return "Compatible with most models (~4k+ context)"
    elif tokens < 7000:
        return "Compatible with standard models (~8k+ context)"
    elif tokens < 14000:
        return "Compatible with ~16k+ context models"
    elif tokens < 28000:
        return "Compatible with ~32k+ context models"
    elif tokens < 100000:
        return "Compatible with large models (~128k+ context)"
    elif tokens < 180000:
        return "Compatible with very large models (~200k+ context)"
    else:
        return "Very large size (>180k tokens), requires specific models or context reduction"

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
            redacted_content, secrets_count_ds = detect_and_redact_secrets(content, relative_path, mask_mode)
            # Apply regex on potentially already redacted content if first pass found something.
            # Or on original if first pass found nothing.
            final_redacted_content, secrets_count_regex = detect_and_redact_with_regex(redacted_content, relative_path)
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
    
    char_count_val, estimated_tokens_val = estimate_tokens(full_context)
    model_compatibility_val = get_model_compatibility(estimated_tokens_val)
    
    summary = {
        "total_files": len(analysis_cache.get("uploaded_files", [])),
        "included_files_count": len(uploaded_files),
        "excluded_files_count": len(analysis_cache.get("uploaded_files", [])) - len(uploaded_files),
        "total_lines": sum(f["content"].count('\n') for f in uploaded_files),
        "total_chars": char_count_val,
        "estimated_tokens": int(estimated_tokens_val),
        "model_compatibility": model_compatibility_val,
        "secrets_masked": total_secrets_masked,
        "files_with_secrets": files_with_secrets_list
    }
    
    return full_context, summary

def should_ignore_path(path, spec):
    """
    Determines if a path should be ignored according to the PathSpec.
    Performs several checks including exact pattern match and checking path segments.
    """
    # 1. Check the complete path with pathspec
    if spec.match_file(path):
        app.logger.debug(f"File ignored (direct match): {path}")
        return True
    
    # 2. Check if the path contains a directory that is ignored
    parts = path.split('/')
    for i in range(1, len(parts)):
        partial_path_as_dir = '/'.join(parts[:i]) + '/'
        if spec.match_file(partial_path_as_dir):
            app.logger.debug(f"File ignored (parent directory ignored): {path}, ignored portion: {partial_path_as_dir}")
            return True
        # Also check without trailing slash if some patterns might be defined like that
        partial_path_as_file_prefix = '/'.join(parts[:i])
        if spec.match_file(partial_path_as_file_prefix) and any(p.pattern.endswith('/') for p in spec.patterns if partial_path_as_file_prefix == p.pattern.rstrip('/')):
             app.logger.debug(f"File ignored (parent directory pattern match): {path}, ignored portion: {partial_path_as_file_prefix}")
             return True

    # 3. Check specific patterns such as __pycache__ (already covered if in .gitignore, but good fallback)
    if '__pycache__' in path:
        app.logger.debug(f"File ignored (hardcoded pattern __pycache__): {path}")
        return True
    
    return False

# --- Application routes ---

@app.route('/')
def index():
    app.logger.info("Received request for '/' - Serving index.html")
    return render_template('index.html', 
                           instruction_text_1=INSTRUCTION_TEXT_1, 
                           instruction_text_2=INSTRUCTION_TEXT_2,
                           llm_feature_enabled=LLM_SERVER_ENABLED,
                           llm_stream_response_enabled=LLM_SERVER_STREAM_RESPONSE)

@app.route('/upload', methods=['POST'])
def upload_directory():
    """
    Endpoint to receive the uploaded files from the browser.
    Expects a JSON of the form:
    {
       "files": [
           {"name": "file1.py", "path": "folder/file1.py", "content": "content..."},
           ...
       ]
    }
    Applies the .gitignore rules (as in CLI mode) to include only non-ignored files.
    """
    if not request.is_json:
        return jsonify({"success": False, "error": "Invalid request format: JSON expected."}), 400
    data = request.get_json()
    if not data or "files" not in data or not isinstance(data["files"], list):
        return jsonify({"success": False, "error": "Missing or invalid file list."}), 400
    
    uploaded_files = []
    for file_obj in data["files"]:
        if not isinstance(file_obj, dict):
            continue
        name = file_obj.get("name")
        path = file_obj.get("path")
        content = file_obj.get("content")
        if name and path and content is not None:
            # Ensure the path is in POSIX style (using "/" only)
            posix_path = path.replace("\\", "/")
            uploaded_files.append({
                "name": name,
                "path": posix_path,
                "content": content
            })
    if not uploaded_files:
        return jsonify({"success": False, "error": "No valid file received."}), 400

    # Use the same routine as the CLI version for .gitignore
    # Look for a .gitignore file at the root level (exact path ".gitignore")
    gitignore_files = [f for f in uploaded_files if f["path"].lower() == ".gitignore"]
    
    # Default patterns to always ignore
    default_patterns = [
        '.git/',
        '__pycache__/',
        '*.pyc',
        # '.gitignore' # .gitignore itself should not be ignored for parsing, but not included in context
    ]
    
    all_patterns = default_patterns.copy()
    
    if gitignore_files:
        gitignore_content = gitignore_files[0]["content"]
        # Clean lines: remove spaces, comments, empty lines
        lines = [line.strip() for line in gitignore_content.splitlines() if line.strip() and not line.strip().startswith("#")]
        all_patterns.extend(lines)
    
    try:
        spec = pathspec.PathSpec.from_lines(GitWildMatchPattern, all_patterns)
        app.logger.info(f".gitignore loaded with {len(spec.patterns)} rules.")
        analysis_cache["ignored_patterns"] = all_patterns
    except Exception as e:
        app.logger.error(f"Error loading .gitignore: {e}")
        spec = pathspec.PathSpec([]) # fallback to empty spec
        analysis_cache["ignored_patterns"] = []

    # Filter files by excluding those that match the .gitignore rules (applied on the relative POSIX path)
    filtered_files = []
    ignored_files_paths = [] # Store paths of ignored files for logging
    
    # Ensure .gitignore itself is not included in the context even if not explicitly in patterns
    # (it's used for rules, not usually for LLM context directly unless specified)
    # However, our current logic would select it if user checks it.
    # For now, we let the user decide. `default_patterns` could include '.gitignore' to force exclusion.

    for file_obj in uploaded_files:
        path_to_check = file_obj["path"]
        # Special handling for .gitignore itself: always parse it, but exclude from final list for context generation
        if path_to_check.lower() == ".gitignore":
            if path_to_check not in ignored_files_paths:
                 ignored_files_paths.append(path_to_check) # Log as "ignored" for context
            continue # Skip adding .gitignore to filtered_files

        if should_ignore_path(path_to_check, spec):
            if path_to_check not in ignored_files_paths:
                ignored_files_paths.append(path_to_check)
        else:
            filtered_files.append(file_obj)
    
    app.logger.info(f"Ignored files for context ({len(ignored_files_paths)}): {', '.join(ignored_files_paths[:10])}{'...' if len(ignored_files_paths) > 10 else ''}")
    app.logger.info(f"Upload successful: {len(filtered_files)} files kept for selection after applying .gitignore rules.")
    
    analysis_cache["uploaded_files"] = filtered_files # Store only files available for selection

    file_tree_data = [{"path": f["path"]} for f in filtered_files] # Data for client-side tree
    
    return jsonify({
        "success": True, 
        "files": file_tree_data, # Files to display in tree
        "debug": {
            "ignored_patterns_used": analysis_cache["ignored_patterns"],
            "ignored_files_log": ignored_files_paths, # Log of files ignored
            "final_selectable_files_count": len(filtered_files)
        }
    })

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
    
    app.logger.info(f"Secret masking: {'enabled' if enable_masking else 'disabled'}, mode: {mask_mode}")
    app.logger.info(f"Instructions reçues: {instructions[:100]}{'...' if len(instructions) > 100 else ''}")
    
    selected_paths = data["selected_files"]
    # analysis_cache["uploaded_files"] now contains only non-ignored files
    all_selectable_files = analysis_cache.get("uploaded_files", []) 
    
    if not all_selectable_files and selected_paths : # Check if selectable files list is empty but user selected some (should not happen)
         app.logger.warning("User selected files, but the list of selectable files is empty. Re-analyze might be needed.")
         # Potentially could re-trigger analysis or send specific error.
         # For now, assume this implies an issue if selected_paths is not empty.

    # Filter uploaded files based on the selected paths by user
    context_files = [f for f in all_selectable_files if f["path"] in selected_paths]
    if not context_files: # No files selected or selection is empty
        # check if selected_paths was non-empty, means selection led to 0 files from selectable ones
        if selected_paths: 
             app.logger.warning(f"User selected paths {selected_paths}, but these did not match any available selectable files.")
        return jsonify({"success": False, "error": "No files selected or selection did not match available files."}), 400
        
    markdown_context, summary = build_uploaded_context_string(
        uploaded_files=context_files, # Use the user-selected files
        root_name="Uploaded_Directory",
        enable_masking=enable_masking,
        mask_mode=mask_mode,
        instructions=instructions
    )
    
    return jsonify({
        "success": True, 
        "markdown": markdown_context,
        "summary": summary # Summary is now more detailed
    })

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

if __name__ == '__main__':
    port = 5000
    host = '127.0.0.1'
    if '--port' in sys.argv:
        try:
            port = int(sys.argv[sys.argv.index('--port') + 1])
        except (IndexError, ValueError):
            print("Erreur: --port nécessite un argument de numéro de port valide.", file=sys.stderr)
            sys.exit(1)
    if '--host' in sys.argv:
        try:
            host = sys.argv[sys.argv.index('--host') + 1]
        except IndexError:
            print("Erreur: --host nécessite un argument d'adresse IP.", file=sys.stderr)
            sys.exit(1)
            
    app.run(host=host, port=port, debug=True)