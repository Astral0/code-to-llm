# Architecture

System architecture:

The project consists of a Python backend and a web-based frontend. The backend is built using Flask and is responsible for scanning and formatting code projects, generating context optimized for LLMs, and providing an API for the frontend. The frontend is built using HTML, CSS, and JavaScript and provides an interactive "Developer Toolbox" for analyzing, designing, and reviewing code with AI. The pywebview library is used to create a desktop application.

Source Code paths:

- `web_server.py`: Flask backend application
- `llm_context_builder.py`: Code for scanning and formatting code projects
- `services/`: Directory containing various services used by the backend
- `prompts/`: Directory containing prompts used by the LLM
- `static/`: Directory containing static files for the frontend (CSS, JavaScript, images)
- `templates/`: Directory containing HTML templates for the frontend
- `pywebview_driver.py`: Code for creating the desktop application using pywebview
- `main_desktop.py`: Main entry point for the desktop application

Key technical decisions:

- Choice of Flask for the backend
- Choice of pywebview for the desktop application
- Overall structure of the project