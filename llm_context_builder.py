#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import argparse
import pathspec
from pathspec.patterns import GitWildMatchPattern
from pathlib import Path
import sys
from collections import defaultdict
import json # For potential future use or debugging
import logging
import re

# Import corrigé pour detect-secrets
try:
    from detect_secrets import SecretsCollection
    from detect_secrets.settings import default_settings
    from detect_secrets.plugins.base import BasePlugin
    from detect_secrets.core import baseline
    from detect_secrets.plugins import initialize
    HAS_DETECT_SECRETS = True
except ImportError:
    logging.warning("detect-secrets library not found. Secret masking will be disabled.")
    HAS_DETECT_SECRETS = False

# --- Configuration ---
MAX_BINARY_HEAD_SIZE = 1024

# --- Logging Setup ---
# Configure logging to output informational messages and above to stderr
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s', stream=sys.stderr)
# Set level to logging.DEBUG via --debug flag if needed

# --- Secret Detection and Masking Functions ---

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
        plugins_used = []
        all_plugins = list(initialize.from_parser_builder())
        for plugin in all_plugins:
            plugins_used.append(plugin)
        
        # Analyser le contenu pour détecter les secrets
        for plugin in plugins_used:
            secrets.scan_string_content(content, plugin, path=file_path)
        
        # Si aucun secret n'est détecté, retourner le contenu original
        if len(secrets.data) == 0:
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
        logging.error(f"Error using detect-secrets: {e}")
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
        'api_key': r'(?i)(api[_-]?key|apikey|api token)["\']?\s*[:=]\s*["\']?([0-9a-zA-Z]{16,64})["\']?',
        # Tokens divers (OAuth, JWT, etc.)
        'token': r'(?i)(access_token|auth_token|token)["\']?\s*[:=]\s*["\']?([0-9a-zA-Z._\-]{8,64})["\']?',
        # Clés AWS
        'aws_key': r'(?i)(AKIA[0-9A-Z]{16})',
        # URLs contenant username:password
        'url_auth': r'(?i)https?://[^:@/\s]+:[^:@/\s]+@[^/\s]+',
        # Clés privées
        'private_key': r'(?i)(-----BEGIN [A-Z]+ PRIVATE KEY-----)',
        # Documentation de credentials/variables sensibles avec valeurs
        'credentials_doc': r'(?i)# ?(password|secret|key|token|credential).*[=:] ?"[^"]{3,}"',
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

# --- Core Utility Functions ---

def load_gitignore(repo_path: Path) -> pathspec.PathSpec:
    """
    Loads rules from the .gitignore file at the given repository path.
    Returns a PathSpec object for matching files.
    Includes default patterns like .git/ and __pycache__/.
    """
    gitignore_path = repo_path.resolve() / '.gitignore' # Ensure resolved path
    gitignore_lines = []
    cleaned_lines = []
    logging.debug(f"Attempting to load .gitignore from: {gitignore_path}")

    if gitignore_path.is_file():
        try:
            # Read with utf-8, ignoring errors for maximum compatibility
            with open(gitignore_path, 'r', encoding='utf-8', errors='ignore') as f:
                gitignore_lines = f.readlines()
            logging.debug(f"Read {len(gitignore_lines)} lines from {gitignore_path}")
            # Clean lines: strip whitespace, ignore comments/empty lines
            cleaned_lines = [line.strip() for line in gitignore_lines if line.strip() and not line.strip().startswith('#')]
        except IOError as e:
            logging.warning(f"Could not read {gitignore_path}: {e}")
        except Exception as e:
            # Catch other potential errors during reading/processing
            logging.warning(f"Error reading/processing {gitignore_path}: {e}")
    else:
        logging.debug(f"File {gitignore_path} not found.")

    # Add default patterns that are almost always useful
    default_patterns = ['.git/', '__pycache__/', '.gitignore']
    # Combine rules from file (if any) and default rules
    all_lines = cleaned_lines + default_patterns
    logging.debug(f"Total rule lines for PathSpec processing: {len(all_lines)}")

    try:
        # Create PathSpec object using Git wildcard matching style
        spec = pathspec.PathSpec.from_lines(GitWildMatchPattern, all_lines)
        logging.debug(f"PathSpec created with {len(spec.patterns)} patterns.")
        return spec
    except Exception as e:
        # Log critical error if PathSpec creation fails, return an empty spec
        logging.critical(f"Critical error creating PathSpec from patterns: {e}")
        return pathspec.PathSpec([]) # Return empty spec (matches nothing)

def get_files_from_directory(directory_to_scan: Path, spec: pathspec.PathSpec, output_file_path: Path = None) -> list[str]:
    """
    Recursively finds files in `directory_to_scan` that are NOT ignored by the `spec`.
    Excludes the `output_file_path` itself (relevant for CLI mode).
    Returns a sorted list of unique relative POSIX path strings (relative to `directory_to_scan`).
    """
    scan_root = directory_to_scan.resolve()
    included_files_relative = set() # Use a set for efficient deduplication
    logging.debug(f"Starting directory walk in: {scan_root}")

    if not spec:
        spec = pathspec.PathSpec([]) # Ensure spec is never None

    # Resolve output path for accurate comparison
    abs_output_file_path = output_file_path.resolve() if output_file_path else None

    # Use rglob for recursive walking
    for item_path in scan_root.rglob('*'):
        # Basic check: ensure it's a file
        if item_path.is_file():
            abs_item_path = item_path.resolve()

            # Check 1: Exclude the output file itself
            if abs_output_file_path and abs_item_path == abs_output_file_path:
                logging.info(f"Ignoring specified output file during walk: {item_path.relative_to(scan_root)}")
                continue

            # Check 2: Match against gitignore rules
            try:
                # Get path relative to the scanned root for matching
                relative_path = abs_item_path.relative_to(scan_root)
                # Convert to POSIX format (forward slashes) for pathspec
                relative_path_str = relative_path.as_posix()

                # Perform the match
                is_ignored = spec.match_file(relative_path_str)
                logging.debug(f"Checking file: '{relative_path_str}', Ignored: {is_ignored}")

                if not is_ignored:
                    # Store the relative path string if not ignored
                    included_files_relative.add(relative_path_str)
            except ValueError:
                # Handle cases where file might be outside the scan_root (e.g., weird symlinks)
                logging.warning(f"Cannot determine relative path for {abs_item_path} regarding {scan_root}. Ignoring file.")
                continue
            except Exception as e:
                 # Catch unexpected errors during path processing or matching
                 logging.warning(f"Error processing path {item_path}: {e}")
                 continue
        # else: # Optional: Log directories being skipped or processed if needed
        #     if item_path.is_dir(): logging.debug(f"Processing directory: {item_path.relative_to(scan_root)}")

    # Return a sorted list of the unique relative paths found
    return sorted(list(included_files_relative))

def generate_tree(relative_file_paths: list[str], repo_root_name: str) -> str:
    """
    Generates a textual representation of the file tree from a list of relative paths.
    Uses standard tree drawing characters (├──, └──, │, etc.).
    """
    if not relative_file_paths:
        return "[NO FILES SELECTED FOR TREE]\n"

    # Use defaultdict for easily building nested dictionary structure
    tree = defaultdict(dict)

    # Populate the tree structure from the list of relative paths
    for rel_path_str in relative_file_paths:
        # Use pathlib to handle path components correctly
        parts = Path(rel_path_str).parts
        current_level = tree
        for i, part in enumerate(parts):
            is_last_part = (i == len(parts) - 1)
            if is_last_part:
                # Mark the end node (file)
                current_level[part] = True
            else:
                # Ensure the node exists as a dictionary (folder)
                # If a file had the same name as a later folder, folder structure takes precedence
                if part not in current_level or not isinstance(current_level[part], (dict, defaultdict)):
                    current_level[part] = defaultdict(dict)
                # Move down to the next level
                current_level = current_level[part]

    # List to store the formatted lines of the tree
    tree_lines = [f"{repo_root_name}/"] # Start with the root name

    # Internal recursive function to format each level of the tree
    def format_level(level_dict: dict, prefix: str = ""):
        # Sort items: folders first (dictionaries), then files (booleans), then alphabetically
        items = sorted(level_dict.keys(), key=lambda k: (not isinstance(level_dict[k], (dict, defaultdict)), k.lower()))

        for i, name in enumerate(items):
            is_last_item_in_level = (i == len(items) - 1)
            # Choose the appropriate connector
            connector = "└── " if is_last_item_in_level else "├── "
            tree_lines.append(f"{prefix}{connector}{name}")

            # If it's a non-empty subdirectory (represented by a dict/defaultdict)
            if isinstance(level_dict[name], (dict, defaultdict)) and level_dict[name]:
                # Calculate the prefix for the next level
                new_prefix = prefix + ("    " if is_last_item_in_level else "│   ")
                format_level(level_dict[name], new_prefix)

    # Start the recursive formatting from the root level
    format_level(tree)
    # Join all lines with newline characters
    return "\n".join(tree_lines) + "\n"


def format_file_content_for_llm(absolute_filepath: Path, repo_root: Path) -> str:
    """
    Reads a single file, handles binary detection, decodes text, normalizes line endings,
    detects language, and formats the content with headers/footers and Markdown code blocks.
    Uses the absolute path for reading but calculates relative path for display.
    """
    try:
        # Calculate relative path for display in headers/footers
        relative_path_str = absolute_filepath.relative_to(repo_root).as_posix()
    except ValueError:
        # Fallback if file is somehow outside the effective repo root
        relative_path_str = absolute_filepath.name
        logging.warning(f"File {absolute_filepath} seems outside effective root {repo_root}. Using filename only.")

    # Define standard headers and footers
    header = f"--- START FILE: {relative_path_str} ---\n"
    footer = f"--- END FILE: {relative_path_str} ---\n\n" # Two newlines for separation

    content = ""
    try:
        # Read in binary mode first to detect binary content reliably
        with open(absolute_filepath, 'rb') as f:
            # Read a small chunk from the beginning
            file_head = f.read(MAX_BINARY_HEAD_SIZE)
            # Check if the initial chunk contains non-text bytes
            if is_binary_string(file_head):
                file_size = absolute_filepath.stat().st_size
                logging.info(f"Detected binary content in: {relative_path_str} ({file_size} bytes)")
                content = f"[BINARY CONTENT DETECTED - {file_size} bytes]\n"
                # Return immediately for binary files
                return header + content.strip() + "\n" + footer
            else:
                # If it looks like text, rewind and read the whole file
                f.seek(0)
                raw_content = f.read()
                # Attempt to decode as UTF-8 first (most common)
                try:
                    content = raw_content.decode('utf-8')
                except UnicodeDecodeError:
                    # Fallback to Latin-1 if UTF-8 fails, replacing errors
                    logging.warning(f"UTF-8 decode failed for {relative_path_str}. Trying Latin-1 fallback.")
                    content = raw_content.decode('latin-1', errors='replace')
                except Exception as e:
                     # Catch other potential decoding errors
                     logging.warning(f"Read/decode error in {relative_path_str}: {e}")
                     content = f"[READ/DECODE ERROR: {e}]\n"
    except IOError as e:
        # Handle file reading errors (permissions, etc.)
        logging.warning(f"Cannot read file {absolute_filepath}: {e}")
        content = f"[READ ERROR: {e}]\n"
    except Exception as e:
        # Catch unexpected errors during file handling
        logging.warning(f"Unexpected error reading {absolute_filepath}: {e}")
        content = f"[UNEXPECTED READ ERROR]\n"

    # Process content only if it's not an error message or binary placeholder
    if content and not content.startswith(("[READ", "[BINARY", "[UNEXPECTED")):
        try:
            # Normalize line endings to LF (\n)
            lines = content.splitlines()
            normalized_content = "\n".join(lines)
        except Exception as e:
             # Fallback if line normalization fails for some reason
             logging.warning(f"Error normalizing line endings for {relative_path_str}: {e}")
             normalized_content = content
    else:
        # Pass through error messages or binary placeholders directly
        normalized_content = content 

    # Appliquer la détection et le masquage des secrets
    redacted_content, secrets_count = detect_and_redact_secrets(normalized_content, relative_path_str)
    
    # Utiliser les règles regex pour les cas non détectés par detect-secrets
    redacted_content, regex_secrets_count = detect_and_redact_with_regex(redacted_content, relative_path_str)
    
    total_secrets = secrets_count + regex_secrets_count
    if total_secrets > 0:
        logging.info(f"Masked {total_secrets} secrets in {relative_path_str}")
        normalized_content = redacted_content
    else:
        normalized_content = content

    # Remove trailing whitespace/blank lines from the *end* of the content
    content_processed = normalized_content.rstrip()

    # --- Language Detection based on file extension ---
    lang = ""
    ext = absolute_filepath.suffix.lower()
    # Extensive map of common extensions to Markdown language identifiers
    lang_map = {
        # Python
        ".py": "python", ".pyw": "python", ".pyi": "python", ".python": "python",
        # JavaScript & TypeScript
        ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
        ".ts": "typescript", ".tsx": "typescript", ".mts": "typescript", ".cts": "typescript",
        # Web Frontend
        ".html": "html", ".htm": "html",
        ".css": "css", ".scss": "scss", ".sass": "sass", ".less": "less",
        # Data Formats
        ".json": "json", ".jsonc": "json", ".geojson": "json",
        ".yaml": "yaml", ".yml": "yaml",
        ".xml": "xml", ".xsd": "xml", ".xsl": "xml", ".xslt": "xml", ".svg": "xml",
        ".toml": "toml",
        ".csv": "csv", ".tsv": "tsv",
        # Shell & Scripting
        ".sh": "bash", ".bash": "bash", ".zsh": "bash", ".fish": "fish", ".ksh": "bash",
        ".ps1": "powershell", ".psm1": "powershell", ".psd1": "powershell",
        ".bat": "batch", ".cmd": "batch",
        ".php": "php", ".php4": "php", ".php5": "php", ".phtml": "php",
        ".pl": "perl", ".pm": "perl",
        ".rb": "ruby", ".rbw": "ruby",
        ".lua": "lua",
        # Compiled Languages & Headers
        ".java": "java",
        ".kt": "kotlin", ".kts": "kotlin",
        ".c": "c", ".h": "c",
        ".cpp": "cpp", ".hpp": "cpp", ".cxx": "cpp", ".hxx": "cpp", ".cc": "cpp", ".hh": "cpp",
        ".cs": "csharp",
        ".go": "go",
        ".rs": "rust",
        ".swift": "swift",
        ".scala": "scala",
        ".dart": "dart",
        ".pas": "pascal", ".pp": "pascal",
        ".f": "fortran", ".f90": "fortran", ".f95": "fortran", ".f03": "fortran",
        # DevOps & Config
        "dockerfile": "dockerfile", ".dockerfile": "dockerfile",
        ".tf": "terraform", ".tfvars": "terraform",
        ".conf": "ini", ".ini": "ini", ".cfg": "ini", ".properties": "ini",
        ".sql": "sql",
        # Documents & Markup
        ".md": "markdown", ".markdown": "markdown", ".rst": "rst",
        ".tex": "latex",
        ". R": "r", ".r": "r", # Statistics
        # Others (add as needed)
        ".vb": "vbnet",
        ".vbs": "vbscript",
        ".asm": "assembly",
        ".m": "objectivec", # Can also be MATLAB
        ".mm": "objectivec",
    }
    lang = lang_map.get(ext, "")
    # Handle special filenames like 'Dockerfile'
    if not lang and absolute_filepath.name.lower() == 'dockerfile':
        lang = 'dockerfile'
    elif not lang and absolute_filepath.name.lower() == 'makefile':
         lang = 'makefile'
    # Add more special filename checks if necessary

    # Format with Markdown code blocks if language was detected
    if lang:
        # Ensure trailing newline within the code block before the closing ```
        formatted_content = f"```{lang}\n{content_processed}\n```\n"
    else:
        # For unknown file types, just include the content without specific language tag
        # Option: Wrap in generic ```text block?
        # formatted_content = f"```text\n{content_processed}\n```\n"
        formatted_content = content_processed + "\n" # Ensure newline after raw content

    # Combine header, formatted content, and footer
    return header + formatted_content + footer

def build_llm_context_string(absolute_file_paths: list[Path], repo_root: Path) -> str:
    """
    Constructs the final Markdown string for the LLM, including a header,
    the directory tree, and the formatted content of all specified files.
    """
    llm_context_parts = [] # List to hold all parts of the final string
    repo_root_name = repo_root.name if repo_root else "Selected_Files"
    logging.info(f"Building context string with effective root: {repo_root}")

    # --- Convert absolute paths to relative for tree generation ---
    relative_paths_for_tree = []
    for abs_path in absolute_file_paths:
        try:
            # Attempt to get path relative to the determined repo root
            relative_paths_for_tree.append(abs_path.relative_to(repo_root).as_posix())
        except ValueError:
             # Fallback if a file is outside the root (should be rare with proper filtering)
             relative_paths_for_tree.append(abs_path.name)

    # --- Generate the Directory Tree ---
    tree_string = generate_tree(relative_paths_for_tree, repo_root_name)

    # --- Add Standard Header ---
    # Describes the structure and purpose of the generated context
    llm_context_parts.append(
        "--- START CONTEXT ---\n"
        "Objective: Provide the complete context of a project to enable an LLM to understand the code and apply user-requested modifications.\n"
        "Structure: First, the project's directory tree is presented, followed by the full content of each relevant file.\n" 
        "Security Note: Sensitive information such as API keys, tokens, passwords, and credentials have been automatically masked in this context.\n"
        "File Identification: Each file begins with `--- START FILE: [relative/path/to/file] ---` and ends with `--- END FILE: [relative/path/to/file] ---`. The relative path is essential for identifying files to modify.\n"
        "Code Format: Source code content is generally enclosed in Markdown code blocks with the language specified (e.g., ```python).\n"
        "Interaction: After analyzing this context, the LLM should be ready to receive instructions to modify the code in the specified files.\n"
        f"Considered project root: {repo_root.resolve().as_posix() if repo_root else 'N/A'}\n"
        f"Total files included: {len(absolute_file_paths)}\n"
        "--- END HEADER ---\n\n"
    )

    # --- Add Directory Tree ---
    llm_context_parts.append( "--- START DIRECTORY TREE ---\n" + f"{tree_string.strip()}\n" + "--- END DIRECTORY TREE ---\n\n" )

    # --- Add Formatted File Contents ---
    if not absolute_file_paths:
        logging.warning("No files selected to include in the context string.")
        llm_context_parts.append("[INFO] No files were selected or found to include in the context.\n")
    else:
        # Sort paths for consistent output order
        for abs_filepath in sorted(absolute_file_paths):
            logging.debug(f"Formatting file for context: {abs_filepath}")
            # Pass the effective repo_root for calculating relative paths inside format function
            llm_context_parts.append(format_file_content_for_llm(abs_filepath, repo_root))

    # --- Combine all parts ---
    return "".join(llm_context_parts)

def find_project_root_and_spec(input_paths: list[Path], specified_root: Path | None = None) -> tuple[Path | None, pathspec.PathSpec | None, Path | None]:
    """
    Attempts to determine the project root (often containing .git or .gitignore),
    load the .gitignore specification from that root, and determine the
    'effective root' used for calculating relative paths of input files.

    Returns:
        tuple[Path | None, pathspec.PathSpec | None, Path | None]:
            - detected_root: The best guess for the actual project root (where .git/.gitignore lives).
            - pathspec_object: The loaded PathSpec object (or empty if none found/loaded).
            - effective_root_for_paths: The directory used as the base for relative paths.
    """
    repo_root_path: Path | None = None # Where .git/.gitignore is likely found
    spec: pathspec.PathSpec | None = None # The loaded ignore rules
    effective_repo_root: Path | None = None # Base for relative path calculations

    # Resolve all input paths to absolute paths first
    try:
        resolved_paths = [p.resolve() for p in input_paths]
    except Exception as e:
        logging.error(f"Error resolving input paths: {e}")
        return None, pathspec.PathSpec([]), Path.cwd() # Return defaults on error

    # --- Strategy 1: Explicit Root Provided ---
    if specified_root:
        repo_root_path = specified_root.resolve()
        if not repo_root_path.is_dir():
            logging.error(f"--repo-root provided is not a valid directory: {specified_root}")
            # Cannot proceed reliably if specified root is invalid
            return None, pathspec.PathSpec([]), None
        logging.info(f"Using explicitly provided --repo-root: {repo_root_path}. Loading .gitignore...")
        spec = load_gitignore(repo_root_path)
        # When root is specified, it's both the detected and effective root
        effective_repo_root = repo_root_path

    # --- Strategy 2: Single Directory Input ---
    elif len(resolved_paths) == 1 and resolved_paths[0].is_dir():
        repo_root_path = resolved_paths[0]
        logging.info(f"Single directory provided. Using {repo_root_path} as root. Loading .gitignore...")
        spec = load_gitignore(repo_root_path)
        # Single directory input is also treated as both detected and effective root
        effective_repo_root = repo_root_path

    # --- Strategy 3: Multiple Inputs or Single File (Auto-Detection) ---
    else:
        logging.info("Multiple paths or single file specified. Attempting auto-detection of project root...")
        try:
            # Determine the common ancestor directory of all inputs
            # Consider parent directory if an input is a file
            paths_for_commonpath = [p.parent if p.is_file() else p for p in resolved_paths]
            if not paths_for_commonpath:
                raise ValueError("No valid paths provided to determine common ancestor.")

            common_ancestor = Path(os.path.commonpath(paths_for_commonpath))
            # Ensure the ancestor is treated as a directory
            if common_ancestor.is_file():
                common_ancestor = common_ancestor.parent
            logging.debug(f"Common ancestor of inputs: {common_ancestor}")

            # Search upwards from the common ancestor for .git or .gitignore
            potential_root = common_ancestor
            found_git_indicator = False
            # Loop until we hit the filesystem root (parent of root is root itself)
            while potential_root != potential_root.parent:
                gitignore_path = potential_root / '.gitignore'
                git_dir_path = potential_root / '.git'
                if gitignore_path.is_file() or git_dir_path.is_dir():
                    # Found a likely project root
                    repo_root_path = potential_root
                    logging.info(f"Found potential project root marker (.git or .gitignore) at: {repo_root_path}. Loading .gitignore...")
                    spec = load_gitignore(repo_root_path)
                    found_git_indicator = True
                    break # Stop searching upwards
                # Move to the parent directory
                potential_root = potential_root.parent

            # If no marker found, use the common ancestor as the best guess for effective root
            if not found_git_indicator:
                logging.info(f"No .git or .gitignore found in ancestor paths. Using common ancestor {common_ancestor} as effective root.")
                repo_root_path = common_ancestor # May not contain .gitignore
                # Attempt to load .gitignore from this common ancestor anyway
                if (repo_root_path / '.gitignore').is_file():
                    logging.debug(f"Found .gitignore at common ancestor. Loading spec from: {repo_root_path}")
                    spec = load_gitignore(repo_root_path)
                else:
                     logging.debug(f"No .gitignore found at common ancestor {repo_root_path}.")

            # In auto-detect mode, the effective root is usually the determined/ancestor root
            effective_repo_root = repo_root_path

        except ValueError as e:
            # If common path calculation fails (e.g., different drives on Windows)
            logging.warning(f"Cannot determine common root path ({e}). Falling back to Current Working Directory as effective root.")
            # Use CWD as a last resort for the effective root
            effective_repo_root = Path.cwd()
            # Attempt to load .gitignore from CWD
            if (effective_repo_root / '.gitignore').is_file():
                  logging.debug(f"Loading .gitignore from CWD: {effective_repo_root}")
                  spec = load_gitignore(effective_repo_root)
        except Exception as e:
             logging.error(f"Unexpected error during root auto-detection: {e}")
             effective_repo_root = Path.cwd() # Fallback

    # --- Final Checks ---
    # Ensure spec is always a PathSpec object, even if empty
    if spec is None:
        logging.debug("No .gitignore specification loaded, using empty PathSpec (will ignore nothing).")
        spec = pathspec.PathSpec([])

    # Ensure effective_repo_root is always set (should default to CWD if all else failed)
    if effective_repo_root is None:
        logging.warning("Effective root could not be determined, defaulting to Current Working Directory.")
        effective_repo_root = Path.cwd()

    return repo_root_path, spec, effective_repo_root


def estimate_size(text: str):
    """Calculates character count and provides a rough token estimate."""
    char_count = len(text)
    # Simple heuristic: average 4 chars per token (highly variable)
    estimated_tokens = char_count / 4

    logging.info("\n--- Size Estimation (Approximate) ---")
    logging.info(f"Total characters in generated context: {char_count:,}")
    logging.info(f"Approximate token estimate (~4 chars/token): {estimated_tokens:,.0f} tokens")
    logging.warning("Disclaimer: This token estimate is very rough and may differ significantly from the LLM's actual count, especially for code. Does not include your prompt.")

    # General guidance based on estimated size
    size_guidance = {
        3500: "-> Likely compatible with most models (~4k+ context).",
        7000: "-> Likely compatible with standard models (~8k+ context).",
        14000: "-> Likely compatible with ~16k+ context models.",
        28000: "-> Likely compatible with ~32k+ context models.",
        100000: "-> Likely compatible with large ~128k+ context models.",
        180000: "-> Likely compatible with very large ~200k+ context models."
    }
    guidance_msg = "-> Very large size (>180k tokens), requires specific models or context reduction."
    for limit, msg in size_guidance.items():
        if estimated_tokens < limit:
            guidance_msg = msg
            break
    logging.info(guidance_msg)
    logging.info("Tip: Use dedicated tokenizers (like 'tiktoken' library or online tools) for accurate counts.")
    logging.info("--- End Estimation ---")


# --- CLI Mode Logic ---
def run_cli_mode(args):
    """Handles the complete process for the command-line interface mode."""
    logging.info("Running in Command-Line Interface (CLI) mode.")
    try:
        # Resolve and validate output file path early
        output_file_path = Path(args.output).resolve()
        logging.info(f"Output file target: {output_file_path}")
        # Ensure parent directory exists (create if needed)
        output_file_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logging.error(f"Invalid or inaccessible output path '{args.output}': {e}")
        sys.exit(1)

    # Prepare input paths and specified root from arguments
    try:
        input_paths = [Path(p) for p in args.paths]
    except Exception as e:
         logging.error(f"Error processing input paths: {e}")
         sys.exit(1)
    specified_root = Path(args.repo_root).resolve() if args.repo_root else None

    # --- Determine Roots and Gitignore Spec ---
    detected_root, spec, effective_repo_root = find_project_root_and_spec(input_paths, specified_root)

    # We need an effective root to proceed reliably for relative paths
    if effective_repo_root is None:
        logging.error("Could not determine an effective root directory for processing relative paths. Exiting.")
        sys.exit(1)
    logging.info(f"Using effective root for path context: {effective_repo_root}")
    if detected_root:
        logging.info(f"Detected project root (for .gitignore): {detected_root}")
    else:
         logging.info("No specific project root (e.g., .git/.gitignore marker) detected.")


    # --- Collect Files ---
    # Use a set to automatically handle duplicates if paths overlap
    files_to_process_absolute = set()
    for path_obj in input_paths:
        # Resolve each input path robustly
        try:
            path = path_obj.resolve()
        except Exception as e:
             logging.warning(f"Could not resolve input path '{path_obj}': {e}. Skipping.")
             continue

        # Skip if the input path is the output file
        if path == output_file_path:
            logging.info(f"Input path '{path_obj}' matches the output file. Skipping.")
            continue

        # Process if it's a directory
        if path.is_dir():
            logging.info(f"Processing directory input: {path}")
            # Use the directory itself as the scan base, but apply the spec loaded from detected_root
            relative_files = get_files_from_directory(path, spec, output_file_path)
            # Reconstruct absolute paths relative to the scanned directory
            for rel_f in relative_files:
                files_to_process_absolute.add(path / rel_f) # path is already absolute here
        # Process if it's a file
        elif path.is_file():
            logging.info(f"Processing file input: {path}")
            # Check individual file against spec, relative to the effective_repo_root
            should_add = True
            try:
                # Calculate path relative to where .gitignore rules apply (effective_repo_root)
                relative_path_str = path.relative_to(effective_repo_root).as_posix()
                if spec.match_file(relative_path_str):
                    should_add = False
                    logging.info(f"Ignoring single file '{path.name}' due to gitignore match: '{relative_path_str}'")
            except ValueError:
                 # File is outside the effective root, cannot reliably apply global spec
                 logging.warning(f"Single file '{path.name}' is outside effective root {effective_repo_root}. Cannot check global .gitignore rules. Including file.")
                 # Keep should_add = True in this case
            except Exception as e:
                 logging.warning(f"Error checking ignore status for file {path}: {e}. Assuming not ignored.")
                 # Keep should_add = True

            if should_add:
                files_to_process_absolute.add(path)
        # Warn if it's neither a file nor a directory
        else:
             logging.warning(f"Input path '{path_obj}' is not a valid file or directory. Skipping.")


    # Convert the set of absolute paths to a sorted list
    unique_files_absolute = sorted(list(files_to_process_absolute))

    # --- Generate Context String ---
    if not unique_files_absolute:
        logging.warning("No files found to include after processing inputs and ignoring files.")
        # Generate context string even if empty (will contain headers/empty tree)
        final_context = build_llm_context_string([], effective_repo_root)
    else:
        logging.info(f"Generating context for {len(unique_files_absolute)} files...")
        final_context = build_llm_context_string(unique_files_absolute, effective_repo_root)


    # --- Write Output File & Estimate Size ---
    try:
        # Parent directory already created/checked earlier
        with open(output_file_path, 'w', encoding='utf-8') as f:
            f.write(final_context)
        logging.info(f"\nSuccess! LLM context written to: {output_file_path}")
        logging.info(f"Number of files included in context: {len(unique_files_absolute)}")
    except IOError as e:
        # Handle potential write errors
        logging.error(f"\nError writing output file '{args.output}': {e}")
        sys.exit(1)
    except Exception as e:
        # Catch other unexpected errors during writing
        logging.error(f"\nUnexpected error writing output file: {e}")
        sys.exit(1)

    # Provide size estimation based on the generated content
    estimate_size(final_context)


# --- Main Execution Logic ---
def main():
    # Setup argument parser
    parser = argparse.ArgumentParser(
        description="Builds a text file OR starts a web server for preparing project context for LLMs.",
        formatter_class=argparse.RawDescriptionHelpFormatter # Preserve formatting in help text
    )
    # Use subparsers to handle different modes (cli, serve)
    subparsers = parser.add_subparsers(
        dest='mode',
        help='Run mode: "cli" (default, generates file) or "serve" (starts web UI)',
        required=False # Make mode optional, will default later
    )
    parser.set_defaults(mode='cli') # Default mode if none is specified

    # --- CLI Mode Arguments ---
    parser_cli = subparsers.add_parser('cli', help='Run in command-line mode to generate an output file.')
    parser_cli.add_argument(
        'paths',
        metavar='PATH',
        type=str,
        nargs='+', # Require one or more paths
        help="One or more paths to project directories or specific files."
    )
    parser_cli.add_argument(
        '-o', '--output',
        metavar='OUTPUT_FILE',
        type=str,
        required=True, # Output file is mandatory for CLI mode
        help="Path to the output file where the context will be written."
    )
    parser_cli.add_argument(
        '--repo-root',
        metavar='REPO_ROOT',
        type=str,
        default=None, # Optional
        help="Specify the repository root path (locates .gitignore). Auto-detected otherwise."
    )
    parser_cli.add_argument(
        '--debug',
        action='store_true', # Flag, doesn't take a value
        help="Enable verbose debug logging to stderr."
    )
    # Associate the run_cli_mode function with this subparser
    parser_cli.set_defaults(func=run_cli_mode)


    # --- Serve Mode Arguments ---
    parser_serve = subparsers.add_parser('serve', help='Run a web server interface.')
    parser_serve.add_argument(
        '--host',
        type=str,
        default='127.0.0.1', # Default to localhost
        help='Host address for the web server (default: 127.0.0.1).'
    )
    parser_serve.add_argument(
        '--port',
        type=int,
        default=5000, # Default port
        help='Port number for the web server (default: 5000).'
    )
    parser_serve.add_argument(
        '--debug',
        action='store_true', # Flag
        help="Enable Flask debug mode (auto-reload, interactive debugger in browser)."
    )
    # Define the function to run for 'serve' mode inline or import
    def run_serve_mode(args):
        """Imports and runs the Flask web server."""
        logging.info("Running in Web Server mode.")
        try:
            # Import Flask app only when needed for serve mode
            # This avoids Flask dependency if only using CLI
            from web_server import app
            logging.info(f"Starting web server on http://{args.host}:{args.port}")
            # Pass Flask's debug flag based on the --debug argument
            # Use use_reloader=False if watchdog causes issues, but debug implies reloader
            app.run(host=args.host, port=args.port, debug=args.debug)
        except ImportError:
             # Guide user if Flask or web_server is missing
             logging.error("Failed to import web_server. Ensure Flask is installed (`pip install Flask`) and web_server.py exists in the same directory.")
             sys.exit(1)
        except Exception as e:
            # Catch other potential errors during server startup
            logging.error(f"Failed to start web server: {e}", exc_info=True) # Log traceback if possible
            sys.exit(1)
    # Associate the run_serve_mode function with this subparser
    parser_serve.set_defaults(func=run_serve_mode)

    # --- Parse Arguments ---
    args = parser.parse_args()

    # --- Set Logging Level based on --debug flag ---
    # Check if the 'debug' attribute exists and is True
    if hasattr(args, 'debug') and args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug("Debug logging enabled.")
    else:
         # Default to INFO level if --debug is not present or not True
         logging.getLogger().setLevel(logging.INFO)

    # --- Execute the Function Associated with the Chosen Mode ---
    # The `func` attribute was set by `set_defaults` for the chosen subparser
    if hasattr(args, 'func'):
        args.func(args)
    else:
        # If no mode was specified (e.g., just `python script.py`), default to CLI help
        # Note: With set_defaults(mode='cli'), this case might be less likely unless nargs='?' used somewhere
        logging.warning("No command mode specified (e.g., 'cli' or 'serve'). Defaulting to showing CLI help.")
        parser_cli.print_help()
        # Alternatively, show general help: parser.print_help()


# Standard Python entry point check
if __name__ == "__main__":
    main()