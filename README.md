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


![image](https://github.com/user-attachments/assets/e2816992-9967-403a-b8d6-3df66e618a0e)


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

## 📋 Usage

### Web Interface

```bash
python web_server.py
```

Then open http://127.0.0.1:5000 in your browser.

### Command Line

```bash
python llm_context_builder.py cli path/to/your/project -o output.md
```

### Advanced Options

```bash
# Specify a custom repository root
python llm_context_builder.py cli path/to/your/project --repo-root /custom/root -o output.md

# Enable debug logging
python llm_context_builder.py cli path/to/your/project -o output.md --debug

# Start web server on a specific port
python llm_context_builder.py serve --port 8080 --host 0.0.0.0
```

## 🛡️ Security Features

### Sensitive Data Protection

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

> **Note**: This masking helps prevent accidental leakage of sensitive information when sharing code context with LLMs. You can enable or disable this feature in the web interface.

### Detection Methods

The security scanning uses two complementary approaches:

1. **detect-secrets library**: Uses a variety of detectors for different types of secrets
2. **Custom regex patterns**: Additional patterns for common credential formats

## 🔄 Output Format

The generated context includes:

1. A header with project information
2. A directory tree visualization
3. The content of each file with language-specific formatting

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
--- END FILE: src/main.py ---

```
## 💡 Tips for Using with LLMs

- **Prompt Structure**: Provide the context followed by clear instructions about what modifications you need
- **File References**: Refer to files using their exact paths as shown in the context
- **Token Management**: For large projects, select only relevant files to stay within LLM context limits
- **Security Check**: Always verify that sensitive data has been properly masked before sharing

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.
