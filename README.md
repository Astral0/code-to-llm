# 🔍 LLM Context Builder

A tool for preparing code repositories for LLM analysis and modification. Create concise, properly formatted context from your projects that can be easily shared with LLMs.

> 🛡️ **Security Feature**: Automatically detects and masks sensitive information like API keys, credentials, and tokens to prevent them from being shared with LLMs.

## 🚀 Features

- **Smart Repository Scanning**: Recursively scans directories, automatically respects .gitignore rules
- **Proper Formatting**: Creates neatly formatted code blocks with language detection
- **Directory Tree Visualization**: Generates a visual tree structure of your project
- **Web Interface**: Simple browser UI for selecting files and generating context
- **CLI Support**: Command-line interface for automation and scripts
- **Sensitive Data Protection**: Detects and masks API keys, passwords, tokens and other credentials
- **Token Estimation**: Provides approximate token count for LLM context windows
- **Developer Toolbox** (Desktop Mode): Advanced AI-powered development assistant with prompt library

### Web Interface Features

![image](https://github.com/user-attachments/assets/e2816992-9967-403a-b8d6-3df66e618a0e)

- **File Selection**: Interactively select files and folders from your chosen directory.
- **.gitignore Integration**: Automatically respects `.gitignore` rules to exclude irrelevant files.
- **Custom Instructions**: Add specific instructions to be appended to the end of the generated context, guiding the LLM on subsequent tasks.
  - Includes buttons for quickly inserting predefined, configurable instruction templates.
  - Smart insertion logic: appends to existing custom text, or replaces the last predefined instruction if one was just inserted.
- **Context Regeneration**: Easily regenerate the context. If files have been modified, you'll be guided to re-select the directory to ensure all changes are captured, while your previous file selection is preserved.
- **Secret Masking Toggle**: Enable or disable sensitive data masking directly from the UI.
- **Copy to Clipboard**: Quickly copy the generated Markdown context.
- **LLM Integration (Configurable)**:
  - Send the generated context directly to a configured LLM API (OpenAI compatible or Ollama).
  - View the LLM's response directly in the interface.
  - Chat with the LLM with conversation history.
  - LLM responses are rendered as Markdown in the chat.
  - Quickly append predefined instructions (e.g., for generating patches) to your chat messages.
  - Copy the LLM's response to the clipboard.
  - Configuration via `config.ini` for API endpoint, key, model, API type, and streaming.

## ⚙️ Installation

### Requirements

- Python 3.8+
- Flask
- pathspec
- detect-secrets

### Setup

```bash
git clone https://github.com/Astral0/code-to-llm.git
cd code-to-llm
pip install -r requirements.txt
```

The web interface allows for configuration of predefined instruction templates and LLM server settings via a `config.ini` file at the root of the project. 
Create `config.ini` from `config.ini.template` and customize it:

```ini
[Instructions]
instruction1_text = Your first predefined instruction.
instruction2_text = Your second predefined instruction.

[LLMServer]
url = YOUR_LLM_API_URL_HERE # e.g., https://api.openai.com/v1/chat/completions or http://localhost:11434
                             # For OpenAI, can be base 'https://api.openai.com' or full '.../v1/chat/completions'.
                             # For Ollama, can be base 'http://host:port' or include '/api/chat' or '/v1/chat/completions'.
apikey = YOUR_LLM_API_KEY_HERE # Optional for local Ollama, required for OpenAI
model = YOUR_LLM_MODEL_HERE   # e.g., gpt-3.5-turbo or llama3
api_type = openai             # 'openai' or 'ollama'
enabled = false               # Set to true to enable LLM interaction features
stream_response = false       # Set to true to enable streaming responses from the LLM

[Tokens]

[Git]
# Path to git executable (optional - leave empty to use git from PATH)
executable_path = 
```

### Web Interface

```bash
python web_server.py # Default port 5000
# or specify a custom port, e.g., 8080
python web_server.py --port 8080
```

Then open http://127.0.0.1:5000 (or your custom port) in your browser.

### Desktop Mode with Developer Toolbox

The Desktop Mode provides an enhanced experience with native file system access and the Developer Toolbox:

```bash
python main_desktop.py
```

Features:
- **Native Directory Selection**: Direct file system access without uploads
- **Developer Toolbox**: AI-powered assistant for code analysis and development
- **Prompt Library**: Pre-configured prompts for common development tasks
- **Git Integration**: Analyze your recent changes with `git diff`

### Command Line

```bash
python llm_context_builder.py cli path/to/your/project -o output.md
```

### CLI Options

```bash
# General
python llm_context_builder.py cli <paths_to_scan...>

# Output Configuration
  -o, --output-file <file>    Specify the output file for the context. (Default: stdout)
  --no-tree                   Disable the generation of the directory tree visualization.
  --no-header                 Disable the standard context header.
  --no-footer                 Disable the standard file footers (--- END FILE ---).

# Content Filtering & Handling
  --repo-root <path>          Specify the project root if different from the scanned path.
                              Used for more accurate relative paths in the context.
  --exclude <pattern>         Specify additional glob patterns to exclude files/directories.
                              Can be used multiple times. (e.g., --exclude "*.log" --exclude "temp/")
  --include-binary            Include a short header of binary files instead of skipping them.
  --max-size <size>           Maximum size for individual files (e.g., 1M, 500K). Files exceeding this
                              will be truncated or skipped (behavior may vary).
  --encoding <enc>            Specify encoding for reading files (e.g., utf-8, latin-1).
                              (Default: utf-8 with error handling)

# Security & Masking
  --no-masking                Disable all sensitive data masking.
  --masking-mode <mode>       Set masking mode: 'mask' (replace with placeholder, default) 
                              or 'remove' (remove the line containing the secret).

# Instructions
  --instructions "<text>"   Add custom instructions to the end of the generated context.

# Other
  --debug                     Enable debug logging for verbose output.
  --no-progress               Disable the progress bar during file processing.
```

### Advanced Options

```bash
# Specify a custom repository root
python llm_context_builder.py cli path/to/your/project -o output.md --repo-root /custom/root --debug

# Start web server on a specific port
python llm_context_builder.py serve --port 8080 --host 0.0.0.0
```

## 🛡️ Security Features

### Sensitive Data Masking

The tool automatically detects and masks sensitive information in your code, including:

- API keys and tokens
- Passwords and credentials
- Private keys and certificates
- Connection strings with embedded credentials
- AWS keys and other cloud provider credentials

When sensitive data is detected, it will be replaced with a masked indicator such as:

```
[LINE CONTAINING SENSITIVE DATA: ArtifactoryDetector]
```

Or, depending on the detection method and file type:
```
[LINE REMOVED DUE TO DETECTED SECRET]
```
Or sometimes simply, for very sensitive lines:
```
[LINE CONTAINING SENSITIVE DATA: some_pattern_name]
```

> **Note**: This masking helps prevent accidental leakage of sensitive information when sharing code context with LLMs. You can enable or disable this feature in the web interface.

### Detection Methods

The security scanning uses two complementary approaches:

1. **detect-secrets library**: Uses a variety of detectors for different types of secrets
2. **Custom regex patterns**: Additional patterns for common credential formats

## 🧰 Developer Toolbox (Desktop Mode Only)

The Developer Toolbox is an advanced AI-powered assistant integrated into the Desktop Mode. It provides a comprehensive set of tools for code analysis, development planning, and code review.

### Available Prompts

The toolbox includes pre-configured prompts in the `prompts/` directory:

1. **General Analysis** (`01_analyse_generale.md`): Comprehensive project architecture review
   - Architecture and structure analysis
   - Identification of strengths and improvement areas
   - Technical stack summary

2. **Security Analysis** (`02_analyse_securite.md`): Security-focused code audit
   - Vulnerability detection
   - Risk assessment (Critical/High/Medium/Low)
   - Security recommendations

3. **Feature Planning** (`03_plan_action_fonctionnalite.md`): Detailed implementation planning
   - Step-by-step action plans
   - File modifications needed
   - Testing strategy

4. **Code Review** (`04_revue_de_diff.md`): Review of recent changes
   - Automatic git diff integration
   - Quality assessment
   - Improvement suggestions

### Using the Toolbox

1. **Open the Toolbox**: Click "Open Developer Toolbox" button in Desktop Mode
2. **Import Project Context**: Import the context from your main window
3. **Select Prompts**: Choose from the prompt library or write custom queries
4. **Git Integration**: Use "Analyze my recent changes" to review uncommitted work

### Customizing Prompts

You can add your own prompts by creating new `.md` files in the `prompts/` directory:

```markdown
# prompts/05_custom_analysis.md
Your custom prompt content here...
```

The toolbox will automatically detect and display new prompts.

## 🔄 Output Format

The generated context includes:

1. A header with project information
2. A directory tree visualization
3. The content of each file with language-specific formatting
4. Custom instructions, if provided by the user

```
--- START CONTEXT ---
Objective: Provide the complete context of a project to enable an LLM to understand the code and apply user-requested modifications.
Structure: First, the project's directory tree is presented, followed by the full content of each relevant file.
Security Note: Sensitive information such as API keys, tokens, passwords, and credentials have been automatically masked in this context.
...

--- START DIRECTORY TREE ---
Project_Root/
├── src/
│   ├── main.py
│   └── utils.py
├── tests/
│   └── test_main.py
└── README.md
--- END DIRECTORY TREE ---

--- START FILE: src/main.py ---
```python
# Main application code
...
```
--- END FILE: src/main.py ---

...
--- INSTRUCTIONS ---
Refactor the main_function to improve readability.
--- END INSTRUCTIONS ---

## 💡 Tips for Using with LLMs

- **Prompt Structure**: Provide the context followed by clear instructions about what modifications you need
- **File References**: Refer to files using their exact paths as shown in the context
- **Token Management**: For large projects, select only relevant files to stay within LLM context limits
- **Security Check**: Always verify that sensitive data has been properly masked before sharing

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## Mode d'Emploi de l'Application

### Mode Web (pour un environnement standard)

Pour lancer l'application en mode web, suivez ces instructions :

1.  Lancez le serveur Flask en exécutant la commande `python web_server.py`.
2.  Ouvrez un navigateur web à l'adresse `http://127.0.0.1:5000`.
3.  Le pilotage du navigateur externe se fait via des scripts Selenium séparés, comme dans le fonctionnement original.

### Mode Bureau (pour un environnement restreint)

Pour lancer l'application en mode bureau, suivez ces instructions :

1.  Lancez l'application de bureau en exécutant le script `run_desktop.bat`.
2.  Cela ouvrira une fenêtre d'application native affichant l'interface.
3.  Le bouton "Démarrer la discussion avec le LLM" ouvrira une seconde fenêtre de navigateur pour l'automatisation.

## Usage

### Desktop Mode (Recommended for large projects)

The desktop mode avoids file upload issues with large projects (React, Node.js with node_modules, etc.) by reading files directly from disk:

```bash
python main_desktop.py
```

**Features:**
- 🚀 **No file upload limit** - reads directly from disk
- 📁 **Native directory picker** - system dialog for folder selection  
- ⚡ **Pre-filtered scanning** - applies .gitignore rules before reading files
- 💾 **Memory efficient** - processes files on-demand
- 🔄 **Hybrid interface** - combines desktop APIs with web UI

**Perfect for:**
- Large React/Angular projects with node_modules
- Monorepos with multiple packages
- Projects with extensive build artifacts
- Any project where file count > 10,000

### Web Interface

```bash
python web_server.py # Default port 5000
# or specify a custom port, e.g., 8080
python web_server.py --port 8080
```

Then open http://127.0.0.1:5000 (or your custom port) in your browser.

**Note:** Web mode has file upload limitations on large projects.
