# web_server.py
from flask import Flask, request, jsonify, render_template
import sys
import os
import logging
from pathlib import Path
from collections import defaultdict
import pathspec
from pathspec.patterns import GitWildMatchPattern  # Explicit import

app = Flask(__name__, template_folder='templates', static_folder='static')

# Configure logging
logging.basicConfig(level=logging.INFO)

# --- In-memory cache for uploaded files ---
# Each uploaded file is a dictionary with keys: "name", "path", "content"
analysis_cache = {
    "uploaded_files": [],
    "ignored_patterns": []  # Store ignored patterns for debugging
}

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
        # Add other extensions as needed
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

def build_uploaded_context_string(uploaded_files, root_name="Uploaded_Directory"):
    # Generate the tree from relative paths
    relative_paths = [f["path"] for f in uploaded_files]
    tree_string = generate_tree_from_paths(relative_paths, root_name)
    
    context_parts = []
    # Standard header
    header = (
        "--- START CONTEXT ---\n"
        "Objective: Provide the complete context of a project to enable an LLM to understand the code and apply user-requested modifications.\n"
        "Structure: First, the project's directory tree is presented, followed by the full content of each relevant file.\n"
        "File Identification: Each file begins with `--- START FILE: [relative/path/to/file] ---` and ends with `--- END FILE: [relative/path/to/file] ---`.\n"
        "Code Format: Source code content is generally enclosed in Markdown code blocks with the language specified (e.g., ```python).\n"
        f"Considered project directory: {root_name}\n"
        f"Total files included: {len(uploaded_files)}\n"
        "--- END HEADER ---\n\n"
    )
    context_parts.append(header)
    context_parts.append("--- START DIRECTORY TREE ---\n" + tree_string + "\n--- END DIRECTORY TREE ---\n\n")
    
    # For each file, add the formatted content
    for file_obj in sorted(uploaded_files, key=lambda f: f["path"]):
        relative_path = file_obj["path"]
        header_file = f"--- START FILE: {relative_path} ---\n"
        footer_file = f"--- END FILE: {relative_path} ---\n\n"
        lang = detect_language(relative_path)
        content = file_obj["content"].rstrip()
        if lang:
            formatted_content = f"```{lang}\n{content}\n```\n"
        else:
            formatted_content = content + "\n"
        context_parts.append(header_file + formatted_content + footer_file)
    
    # Join all parts to form the context
    full_context = "".join(context_parts)
    
    # Calculate statistics for the summary to be returned separately
    char_count, estimated_tokens = estimate_tokens(full_context)
    model_compatibility = get_model_compatibility(estimated_tokens)
    
    # Generate the summary separately
    summary = {
        "files_count": len(uploaded_files),
        "char_count": char_count,
        "estimated_tokens": int(estimated_tokens),
        "model_compatibility": model_compatibility
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
    return render_template('index.html')

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
       "selected_files": ["folder/file1.py", "folder/subfolder/file2.js", ...]
    }
    Returns the Markdown context AND a separate summary with statistics.
    """
    if not request.is_json:
        return jsonify({"success": False, "error": "Invalid request format: JSON expected."}), 400
    data = request.get_json()
    if not data or "selected_files" not in data or not isinstance(data["selected_files"], list):
        return jsonify({"success": False, "error": "Missing or invalid selected files list."}), 400
    selected_paths = data["selected_files"]
    uploaded_files = analysis_cache.get("uploaded_files", [])
    if not uploaded_files:
        return jsonify({"success": False, "error": "No uploaded file found. Please re-upload the directory."}), 400
    # Filter uploaded files based on the selected paths
    selected_files = [f for f in uploaded_files if f["path"] in selected_paths]
    if not selected_files:
        return jsonify({"success": False, "error": "No valid file selected."}), 400
    
    # Generate the context and summary separately
    markdown_context, summary = build_uploaded_context_string(selected_files)
    
    return jsonify({
        "success": True, 
        "markdown": markdown_context,
        "summary": summary
    })

# Route to debug .gitignore rules 
@app.route('/debug_gitignore', methods=['GET'])
def debug_gitignore():
    """Endpoint to debug the application of .gitignore rules"""
    return jsonify({
        "ignored_patterns": analysis_cache.get("ignored_patterns", []),
        "filtered_files_count": len(analysis_cache.get("uploaded_files", [])),
    })

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)
