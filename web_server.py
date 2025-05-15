# web_server.py
from flask import Flask, request, jsonify, render_template
import sys
import os
import logging
from pathlib import Path
from collections import defaultdict
import pathspec
import re
import configparser
import requests

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

def load_config():
    global INSTRUCTION_TEXT_1, INSTRUCTION_TEXT_2
    global LLM_SERVER_URL, LLM_SERVER_APIKEY, LLM_SERVER_MODEL, LLM_SERVER_ENABLED, LLM_SERVER_API_TYPE
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
                if LLM_SERVER_ENABLED:
                    app.logger.info(f"Configuration du serveur LLM chargée (Type: {LLM_SERVER_API_TYPE}).")
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
    files_with_secrets = 0
    
    for file_obj in sorted(uploaded_files, key=lambda f: f["path"]):
        relative_path = file_obj["path"]
        header_file = f"--- START FILE: {relative_path} ---\n"
        footer_file = f"--- END FILE: {relative_path} ---\n\n"
        lang = detect_language(relative_path)
        
        # Récupérer le contenu et appliquer le masquage des secrets
        content = file_obj["content"].rstrip()
        
        # Détecter et masquer les secrets si le masquage est activé
        redacted_content = content
        secrets_count = 0
        regex_secrets_count = 0
        
        if enable_masking:
            # Détecter et masquer les secrets avec detect-secrets
            redacted_content, secrets_count = detect_and_redact_secrets(content, relative_path, mask_mode)
            
            # Appliquer des règles supplémentaires basées sur regex pour les cas non détectés
            redacted_content, regex_secrets_count = detect_and_redact_with_regex(redacted_content, relative_path)
        
        # Mise à jour des statistiques de masquage
        total_masked = secrets_count + regex_secrets_count
        if total_masked > 0:
            app.logger.info(f"Masked {total_masked} secrets in {relative_path}")
            files_with_secrets += 1
            total_secrets_masked += total_masked
        
        # Utiliser le contenu masqué si des secrets ont été détectés
        content = redacted_content if total_masked > 0 else content
        
        # Formater avec le bloc de code approprié
        if lang:
            formatted_content = f"```{lang}\n{content}\n```\n"
        else:
            formatted_content = content + "\n"
        context_parts.append(header_file + formatted_content + footer_file)
    
    # Ajouter les instructions à la fin du contexte si elles sont fournies
    if instructions:
        instructions_part = "\n--- INSTRUCTIONS ---\n" + instructions + "\n--- END INSTRUCTIONS ---\n"
        context_parts.append(instructions_part)
    
    # Join all parts to form the context
    full_context = "".join(context_parts)
    
    # Calculate statistics for the summary to be returned separately
    char_count, estimated_tokens = estimate_tokens(full_context)
    model_compatibility = get_model_compatibility(estimated_tokens)
    
    # Generate the summary separately with information about masked secrets
    summary = {
        "files_count": len(uploaded_files),
        "char_count": char_count,
        "estimated_tokens": int(estimated_tokens),
        "model_compatibility": model_compatibility,
        "secrets_masked": total_secrets_masked,
        "files_with_secrets": files_with_secrets
    }
    
    # Return the context and the summary separately
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
        partial_path = '/'.join(parts[:i]) + '/'
        if spec.match_file(partial_path):
            app.logger.debug(f"File ignored (parent directory ignored): {path}, ignored portion: {partial_path}")
            return True
    
    # 3. Check specific patterns such as __pycache__
    if '__pycache__' in path:
        app.logger.debug(f"File ignored (pattern __pycache__): {path}")
        return True
    
    return False

# --- Application routes ---

@app.route('/')
def index():
    app.logger.info("Received request for '/' - Serving index.html")
    return render_template('index.html', 
                           instruction_text_1=INSTRUCTION_TEXT_1, 
                           instruction_text_2=INSTRUCTION_TEXT_2,
                           llm_feature_enabled=LLM_SERVER_ENABLED)

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
        '.gitignore'
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
        # Store patterns for debugging
        analysis_cache["ignored_patterns"] = all_patterns
    except Exception as e:
        app.logger.error(f"Error loading .gitignore: {e}")
        spec = pathspec.PathSpec([])
        analysis_cache["ignored_patterns"] = []

    # Filter files by excluding those that match the .gitignore rules (applied on the relative POSIX path)
    filtered_files = []
    ignored_files = []
    
    for file_obj in uploaded_files:
        path = file_obj["path"]
        if should_ignore_path(path, spec):
            ignored_files.append(path)
        else:
            filtered_files.append(file_obj)
    
    app.logger.info(f"Ignored files ({len(ignored_files)}): {', '.join(ignored_files[:10])}{'...' if len(ignored_files) > 10 else ''}")
    app.logger.info(f"Upload successful: {len(filtered_files)} files kept after applying .gitignore.")
    
    # Update the cache
    analysis_cache["uploaded_files"] = filtered_files

    # Prepare data for the client-side tree
    file_tree_data = []
    for file_obj in filtered_files:
        rel_path = file_obj["path"]
        file_tree_data.append({
            "path": rel_path
        })
    
    return jsonify({
        "success": True, 
        "files": file_tree_data,
        "debug": {
            "ignored_patterns": analysis_cache["ignored_patterns"],
            "ignored_files_count": len(ignored_files),
            "filtered_files_count": len(filtered_files)
        }
    })

@app.route('/generate', methods=['POST'])
def generate_context():
    """
    Endpoint to generate the Markdown context from the uploaded files.
    Expects a JSON of the form:
    {
       "selected_files": ["folder/file1.py", "folder/subfolder/file2.js", ...],
       "masking_options": {
           "enable_masking": true,
           "mask_mode": "mask"  // ou "remove" pour supprimer les lignes complètes
       },
       "instructions": "Ne fais rien, attends mes instructions."
    }
    Returns the Markdown context AND a separate summary with statistics.
    """
    if not request.is_json:
        return jsonify({"success": False, "error": "Invalid request format: JSON expected."}), 400
    data = request.get_json()
    if not data or "selected_files" not in data or not isinstance(data["selected_files"], list):
        return jsonify({"success": False, "error": "Missing or invalid selected files list."}), 400
    
    # Récupérer les options de masquage
    masking_options = data.get("masking_options", {})
    enable_masking = masking_options.get("enable_masking", True)  # Activé par défaut
    mask_mode = masking_options.get("mask_mode", "mask")  # 'mask' ou 'remove'
    
    # Récupérer les instructions personnalisées
    # Si les instructions envoyées sont une chaîne vide, les garder vides, sinon utiliser une chaîne vide par défaut.
    instructions = data.get("instructions") # Peut être None ou une chaîne vide
    if instructions is None: # Si la clé n'est pas là (ne devrait pas arriver si le front envoie toujours qqch)
        instructions = "" # Ou une autre valeur par défaut si vous préférez, mais vide est plus logique ici
    
    app.logger.info(f"Secret masking: {'enabled' if enable_masking else 'disabled'}, mode: {mask_mode}")
    app.logger.info(f"Instructions reçues: {instructions[:100]}...") # Log des instructions
    
    selected_paths = data["selected_files"]
    uploaded_files = analysis_cache.get("uploaded_files", [])
    if not uploaded_files:
        return jsonify({"success": False, "error": "No uploaded file found. Please re-upload the directory."}), 400
    
    # Filter uploaded files based on the selected paths
    selected_files = [f for f in uploaded_files if f["path"] in selected_paths]
    if not selected_files:
        return jsonify({"success": False, "error": "No valid file selected."}), 400
        
    # Passer les options de masquage à la fonction de génération de contexte
    
    # Generate the context and summary separately
    markdown_context, summary = build_uploaded_context_string(
        uploaded_files=selected_files,
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

# Route to debug .gitignore rules 
@app.route('/debug_gitignore', methods=['GET'])
def debug_gitignore():
    """Endpoint to debug the application of .gitignore rules"""
    return jsonify(analysis_cache["ignored_patterns"])

@app.route('/send_to_llm', methods=['POST'])
def send_to_llm():
    if not LLM_SERVER_ENABLED:
        return jsonify({"error": "LLM feature is not enabled in config.ini"}), 400

    # Vérifier si les paramètres essentiels sont là, en tenant compte qu'Ollama n'a pas besoin d'apikey
    if not LLM_SERVER_URL or not LLM_SERVER_MODEL or (LLM_SERVER_API_TYPE != "ollama" and not LLM_SERVER_APIKEY):
        app.logger.error(f"LLM server configuration incomplete. URL: {LLM_SERVER_URL}, Model: {LLM_SERVER_MODEL}, APIKey set: {bool(LLM_SERVER_APIKEY)}, Type: {LLM_SERVER_API_TYPE}")
        return jsonify({"error": "LLM server configuration is incomplete in config.ini"}), 400

    data = request.get_json()
    messages_history = data.get('messages')
    app.logger.info(f"Dans /send_to_llm, LLM_SERVER_API_TYPE = {LLM_SERVER_API_TYPE}")
    # Limiter la taille du log pour l'historique des messages
    if messages_history and len(messages_history) > 0:
        log_msg_content = messages_history[-1]['content'] # Log only last message content for brevity
        app.logger.info(f"Dernier message de l'historique ({messages_history[-1]['role']}): {log_msg_content[:200]}{'...' if len(log_msg_content)>200 else ''}")
    else:
        app.logger.warning("Aucun historique de messages reçu.")


    if not messages_history or not isinstance(messages_history, list) or len(messages_history) == 0:
        return jsonify({"error": "No messages provided"}), 400

    headers = {
        "Content-Type": "application/json"
    }
    if LLM_SERVER_APIKEY and LLM_SERVER_API_TYPE != "ollama":
        headers["Authorization"] = f"Bearer {LLM_SERVER_APIKEY}"

    payload = {
        "model": LLM_SERVER_MODEL,
        "messages": messages_history
    }
    if LLM_SERVER_API_TYPE == "ollama":
        payload["stream"] = False # Pour Ollama /api/chat, s'assurer que stream est false

    target_url = LLM_SERVER_URL
    if LLM_SERVER_API_TYPE == "ollama":
        # Normaliser l'URL en supprimant les slashes de fin potentiels
        normalized_url = target_url.rstrip('/')
        ollama_suffix = "api/chat"
        openai_compatible_suffix = "v1/chat/completions" # Pour Ollama en mode compatibilité OpenAI

        if normalized_url.endswith(ollama_suffix) or normalized_url.endswith(openai_compatible_suffix):
            target_url = normalized_url # L'URL est déjà complète avec un suffixe connu
        else:
            # Par défaut, ajouter /api/chat si aucun suffixe connu n'est présent et que l'URL ne semble pas déjà le contenir
            # Cela suppose que si l'URL ne se termine pas par ces suffixes, elle est une URL de base.
            target_url = f"{normalized_url}/{ollama_suffix}"
        app.logger.info(f"Appel à l'API Ollama sur l'URL: {target_url}")
    elif LLM_SERVER_API_TYPE == "openai":
        # Normaliser l'URL en supprimant les slashes de fin potentiels
        normalized_url = target_url.rstrip('/')
        openai_suffix = "v1/chat/completions"
        
        # Vérifier si l'URL normalisée se termine déjà par le suffixe OpenAI
        if normalized_url.endswith(openai_suffix):
            target_url = normalized_url
        # Gérer le cas où l'URL est juste le domaine de base d'OpenAI
        elif normalized_url == "https://api.openai.com":
             target_url = f"{normalized_url}/{openai_suffix}"
        # Si l'URL contient déjà "v1" mais pas le suffixe complet (par ex. proxy ou version custom)
        # ou si l'URL est une base différente qui a besoin du suffixe.
        # Cette logique assume que si l'URL ne se termine pas par le suffixe complet, et n'est pas le domaine nu,
        # alors le suffixe doit être ajouté.
        else:
            target_url = f"{normalized_url}/{openai_suffix}"
        app.logger.info(f"Appel à l'API OpenAI sur l'URL: {target_url}")

    try:
        response = requests.post(target_url, headers=headers, json=payload, timeout=180) # Timeout augmenté
        response.raise_for_status()
        llm_response = response.json()
        
        content_to_return = ""
        if LLM_SERVER_API_TYPE == "openai":
            choices = llm_response.get("choices")
            if choices and isinstance(choices, list) and len(choices) > 0:
                message = choices[0].get("message")
                if message and isinstance(message, dict):
                    content_to_return = message.get("content", "")
                else:
                    app.logger.error(f"Format de message inattendu dans la réponse OpenAI: {message}")
                    return jsonify({"error": "Unexpected message format in OpenAI API response", "details": llm_response}), 500
            else:
                app.logger.error(f"Tableau 'choices' manquant ou invalide dans la réponse OpenAI: {llm_response}")
                return jsonify({"error": "Missing or invalid 'choices' in OpenAI API response", "details": llm_response}), 500
        
        elif LLM_SERVER_API_TYPE == "ollama":
            if llm_response.get("message") and isinstance(llm_response["message"], dict) and "content" in llm_response["message"]:
                content_to_return = llm_response["message"].get("content", "")
            elif "error" in llm_response:
                app.logger.error(f"Erreur retournée par l'API Ollama: {llm_response['error']}")
                return jsonify({"error": f"Ollama API error: {llm_response['error']}", "details": llm_response}), 500
            else:
                app.logger.error(f"Réponse inattendue de l'API Ollama (/api/chat): {llm_response}")
                return jsonify({"error": "Unexpected response format from Ollama API (/api/chat)", "details": llm_response}), 500
        else:
            app.logger.error(f"Type d'API LLM non supporté: {LLM_SERVER_API_TYPE}")
            return jsonify({"error": f"Unsupported LLM API type: {LLM_SERVER_API_TYPE}"}), 400
        
        return jsonify({"response": content_to_return})

    except requests.exceptions.HTTPError as http_err:
        error_content = "No additional error content from server."
        try:
            error_content = http_err.response.json()
        except ValueError: 
            error_content = http_err.response.text
        app.logger.error(f"Erreur HTTP lors de l'appel à l'API LLM: {http_err}. Contenu: {error_content}")
        return jsonify({"error": f"HTTP error calling LLM API: {str(http_err)}", "details": error_content}), http_err.response.status_code
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Erreur lors de l'appel à l'API LLM: {e}")
        return jsonify({"error": f"Error calling LLM API: {str(e)}"}), 500

if __name__ == '__main__':
    # Récupérer le port depuis les arguments de la ligne de commande
    port = 5000 # Port par défaut
    host = '127.0.0.1' # Hôte par défaut
    if '--port' in sys.argv:
        try:
            port_index = sys.argv.index('--port') + 1
            if port_index < len(sys.argv):
                port = int(sys.argv[port_index])
            else:
                print("Erreur: --port nécessite un argument de numéro de port.", file=sys.stderr)
                sys.exit(1)
        except ValueError:
            print("Erreur: Le port doit être un entier.", file=sys.stderr)
            sys.exit(1)
        except IndexError:
            # Ce cas ne devrait pas arriver si --port est le dernier argument sans valeur
            print("Erreur: --port nécessite un argument de numéro de port.", file=sys.stderr)
            sys.exit(1)

    if '--host' in sys.argv:
        try:
            host_index = sys.argv.index('--host') + 1
            if host_index < len(sys.argv):
                host = sys.argv[host_index]
            else:
                print("Erreur: --host nécessite un argument d'adresse IP.", file=sys.stderr)
                sys.exit(1)
        except IndexError:
            print("Erreur: --host nécessite un argument d'adresse IP.", file=sys.stderr)
            sys.exit(1)
            
    app.run(host=host, port=port, debug=True)