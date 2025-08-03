# services/file_utils.py
"""
Utilitaires pour la gestion des fichiers et du contenu
"""
import re
import json
import logging
from pathlib import Path
from collections import defaultdict

# Configuration du logger
logger = logging.getLogger(__name__)

# Constantes pour la détection binaire
TEXTCHARS = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)) - {0x7f})

def is_binary_string(bytes_to_check: bytes) -> bool:
    """Checks if a byte string appears to contain non-text characters."""
    return bool(bytes_to_check.translate(None, TEXTCHARS))

def detect_language(filename):
    """Détecte le langage d'un fichier basé sur son extension."""
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

def generate_tree_from_paths(relative_paths, root_name):
    """Génère une représentation arborescente à partir d'une liste de chemins."""
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

def compact_code(content: str) -> str:
    """Supprime les commentaires et lignes vides d'un bloc de code."""
    # Supprimer les commentaires sur une seule ligne (en gérant les # dans les chaînes de caractères)
    content = re.sub(r'(?m)^ *#.*\n?', '', content)
    # Supprimer les docstrings multilignes """..."""
    content = re.sub(r'""".*?"""', '', content, flags=re.DOTALL)
    # Supprimer les docstrings multilignes '''...'''
    content = re.sub(r"'''.*?'''", '', content, flags=re.DOTALL)
    # Supprimer les lignes vides résultantes
    lines = [line for line in content.splitlines() if line.strip()]
    return "\n".join(lines)