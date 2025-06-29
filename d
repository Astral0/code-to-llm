diff --git a/README.md b/README.md
index ebc4477..983c0a1 100644
--- a/README.md
+++ b/README.md
@@ -241,3 +241,38 @@ Pour lancer l'application en mode bureau, suivez ces instructions :
 1.  Lancez l'application de bureau en exécutant la commande `python main_desktop.py`.
 2.  Cela ouvrira une fenêtre d'application native affichant l'interface.
 3.  Le bouton "Démarrer la discussion avec le LLM" ouvrira une seconde fenêtre de navigateur pour l'automatisation.
+
+## Usage
+
+### Desktop Mode (Recommended for large projects)
+
+The desktop mode avoids file upload issues with large projects (React, Node.js with node_modules, etc.) by reading files directly from disk:
+
+```bash
+python main_desktop.py
+```
+
+**Features:**
+- 🚀 **No file upload limit** - reads directly from disk
+- 📁 **Native directory picker** - system dialog for folder selection  
+- ⚡ **Pre-filtered scanning** - applies .gitignore rules before reading files
+- 💾 **Memory efficient** - processes files on-demand
+- 🔄 **Hybrid interface** - combines desktop APIs with web UI
+
+**Perfect for:**
+- Large React/Angular projects with node_modules
+- Monorepos with multiple packages
+- Projects with extensive build artifacts
+- Any project where file count > 10,000
+
+### Web Interface
+
+```bash
+python web_server.py # Default port 5000
+# or specify a custom port, e.g., 8080
+python web_server.py --port 8080
+```
+
+Then open http://127.0.0.1:5000 (or your custom port) in your browser.
+
+**Note:** Web mode has file upload limitations on large projects.
diff --git a/main_desktop.py b/main_desktop.py
index 9e79615..0150ab6 100644
--- a/main_desktop.py
+++ b/main_desktop.py
@@ -9,6 +9,9 @@ import logging
 from selenium.webdriver.common.by import By
 from pywebview_driver import PywebviewDriver
 from web_server import app
+import pathspec
+from pathspec.patterns import GitWildMatchPattern
+from pathlib import Path
 
 # Définir le chemin de stockage des données persistantes
 DATA_DIR = appdirs.user_data_dir('WebAutomationDesktop', 'WebAutomationTools')
@@ -50,6 +53,8 @@ class Api:
         self._main_window = None
         self._browser_window = None
         self.driver = None
+        self.current_directory = None
+        self.file_cache = []
     
     def set_main_window(self, window):
         """Définit la référence à la fenêtre principale"""
@@ -287,6 +292,256 @@ class Api:
             error_message = f"Erreur lors de l'interaction avec la page : {e}"
             logging.error(error_message)
             return {'success': False, 'error': error_message}
+    
+    def scan_local_directory(self, directory_path):
+        """Scanne un répertoire local et applique les règles .gitignore sans upload"""
+        try:
+            if not directory_path or not os.path.exists(directory_path):
+                error_msg = f"Répertoire invalide: {directory_path}"
+                logging.error(error_msg)
+                return {'success': False, 'error': error_msg}
+            
+            self.current_directory = directory_path
+            logging.info(f"Début du scan local du répertoire: {directory_path}")
+            
+            # Charger les règles .gitignore
+            gitignore_spec = self._load_gitignore_spec(directory_path)
+            
+            # Scanner les fichiers
+            scanned_files = self._scan_files_with_gitignore(directory_path, gitignore_spec)
+            
+            # Filtrer les fichiers binaires
+            filtered_files = self._filter_binary_files(scanned_files)
+            
+            # Mettre en cache les fichiers pour un accès rapide
+            self.file_cache = filtered_files
+            
+            # Préparer la structure pour l'affichage
+            file_tree_data = [{"path": f["relative_path"], "size": f["size"]} for f in filtered_files]
+            
+            logging.info(f"Scan terminé: {len(filtered_files)} fichiers trouvés")
+            
+            return {
+                'success': True,
+                'files': file_tree_data,
+                'directory': directory_path,
+                'total_files': len(filtered_files),
+                'debug': {
+                    'gitignore_patterns_count': len(gitignore_spec.patterns) if gitignore_spec else 0
+                }
+            }
+            
+        except Exception as e:
+            error_msg = f"Erreur lors du scan du répertoire: {str(e)}"
+            logging.error(error_msg)
+            return {'success': False, 'error': error_msg}
+    
+    def _load_gitignore_spec(self, directory_path):
+        """Charge les règles .gitignore depuis le répertoire"""
+        try:
+            gitignore_path = os.path.join(directory_path, '.gitignore')
+            patterns = ['.git/', '__pycache__/', 'node_modules/', '.vscode/', '.idea/']
+            
+            if os.path.exists(gitignore_path):
+                with open(gitignore_path, 'r', encoding='utf-8', errors='ignore') as f:
+                    lines = f.readlines()
+                    
+                # Nettoyer les lignes
+                cleaned_lines = [
+                    line.strip() for line in lines 
+                    if line.strip() and not line.strip().startswith('#')
+                ]
+                patterns.extend(cleaned_lines)
+                logging.info(f"Chargé {len(cleaned_lines)} règles depuis .gitignore")
+            else:
+                logging.info("Aucun .gitignore trouvé, utilisation des règles par défaut")
+            
+            return pathspec.PathSpec.from_lines(GitWildMatchPattern, patterns)
+            
+        except Exception as e:
+            logging.warning(f"Erreur lors du chargement de .gitignore: {e}")
+            # Retourner un spec avec seulement les règles par défaut
+            default_patterns = ['.git/', '__pycache__/', 'node_modules/', '.vscode/', '.idea/']
+            return pathspec.PathSpec.from_lines(GitWildMatchPattern, default_patterns)
+    
+    def _scan_files_with_gitignore(self, directory_path, gitignore_spec):
+        """Scanne récursivement les fichiers en appliquant les règles gitignore"""
+        scanned_files = []
+        directory_path = Path(directory_path)
+        
+        try:
+            for file_path in directory_path.rglob('*'):
+                if file_path.is_file():
+                    try:
+                        # Calculer le chemin relatif
+                        relative_path = file_path.relative_to(directory_path).as_posix()
+                        
+                        # Vérifier si le fichier est ignoré
+                        if not gitignore_spec.match_file(relative_path):
+                            file_size = file_path.stat().st_size
+                            scanned_files.append({
+                                'absolute_path': str(file_path),
+                                'relative_path': relative_path,
+                                'name': file_path.name,
+                                'size': file_size
+                            })
+                            
+                            if CONFIG['debug'] and len(scanned_files) % 1000 == 0:
+                                logging.debug(f"Scanné {len(scanned_files)} fichiers...")
+                                
+                    except Exception as file_error:
+                        logging.warning(f"Erreur lors du traitement de {file_path}: {file_error}")
+                        continue
+                        
+        except Exception as e:
+            logging.error(f"Erreur lors du scan récursif: {e}")
+            
+        return scanned_files
+    
+    def _filter_binary_files(self, files):
+        """Filtre les fichiers binaires basé sur l'extension et le contenu"""
+        filtered_files = []
+        binary_extensions = {
+            '.exe', '.dll', '.so', '.dylib', '.bin', '.img', '.iso',
+            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.ico',
+            '.mp3', '.mp4', '.avi', '.mov', '.wav', '.zip', '.rar',
+            '.7z', '.tar', '.gz', '.pdf', '.doc', '.docx', '.xls',
+            '.xlsx', '.ppt', '.pptx', '.woff', '.woff2', '.ttf', '.eot'
+        }
+        
+        for file_info in files:
+            file_path = Path(file_info['absolute_path'])
+            
+            # Filtrer par extension
+            if file_path.suffix.lower() in binary_extensions:
+                if CONFIG['debug']:
+                    logging.debug(f"Ignoré (binaire par extension): {file_info['relative_path']}")
+                continue
+            
+            # Vérifier le contenu pour les petits fichiers
+            try:
+                if file_info['size'] < 1024 * 1024:  # Moins de 1MB
+                    with open(file_path, 'rb') as f:
+                        sample = f.read(1024)
+                        # Si plus de 30% de bytes non-ASCII, considérer comme binaire
+                        non_ascii_count = sum(1 for b in sample if b > 127 or (b < 32 and b not in [9, 10, 13]))
+                        if len(sample) > 0 and (non_ascii_count / len(sample)) > 0.3:
+                            if CONFIG['debug']:
+                                logging.debug(f"Ignoré (binaire par contenu): {file_info['relative_path']}")
+                            continue
+            except Exception:
+                # En cas d'erreur de lecture, ignorer le fichier
+                if CONFIG['debug']:
+                    logging.debug(f"Ignoré (erreur de lecture): {file_info['relative_path']}")
+                continue
+                
+            filtered_files.append(file_info)
+        
+        return filtered_files
+    
+    def get_file_content(self, relative_path):
+        """Récupère le contenu d'un fichier depuis le cache local"""
+        try:
+            if not self.current_directory:
+                return {'success': False, 'error': 'Aucun répertoire scanné'}
+            
+            # Trouver le fichier dans le cache
+            file_info = next((f for f in self.file_cache if f['relative_path'] == relative_path), None)
+            
+            if not file_info:
+                return {'success': False, 'error': f'Fichier non trouvé: {relative_path}'}
+            
+            # Lire le contenu
+            with open(file_info['absolute_path'], 'r', encoding='utf-8', errors='ignore') as f:
+                content = f.read()
+            
+            return {
+                'success': True,
+                'content': content,
+                'path': relative_path,
+                'size': file_info['size']
+            }
+            
+        except Exception as e:
+            error_msg = f"Erreur lors de la lecture du fichier {relative_path}: {str(e)}"
+            logging.error(error_msg)
+            return {'success': False, 'error': error_msg}
+    
+    def generate_context_from_selection(self, selected_files):
+        """Génère le contexte depuis une sélection de fichiers locaux"""
+        try:
+            if not selected_files:
+                return {'success': False, 'error': 'Aucun fichier sélectionné'}
+            
+            context_parts = []
+            total_chars = 0
+            successful_files = 0
+            
+            # En-tête du contexte
+            context_parts.append(f"# Contexte du projet - {os.path.basename(self.current_directory)}")
+            context_parts.append(f"Répertoire: {self.current_directory}")
+            context_parts.append(f"Fichiers inclus: {len(selected_files)}")
+            context_parts.append("")
+            
+            # Générer l'arbre des fichiers
+            tree_lines = self._generate_file_tree(selected_files)
+            context_parts.extend(tree_lines)
+            context_parts.append("")
+            
+            # Ajouter le contenu de chaque fichier
+            for file_path in selected_files:
+                file_result = self.get_file_content(file_path)
+                if file_result['success']:
+                    context_parts.append(f"--- {file_path} ---")
+                    context_parts.append(file_result['content'])
+                    context_parts.append(f"--- FIN {file_path} ---")
+                    context_parts.append("")
+                    total_chars += len(file_result['content'])
+                    successful_files += 1
+                else:
+                    logging.warning(f"Échec lecture fichier: {file_path}")
+            
+            context = "\n".join(context_parts)
+            
+            return {
+                'success': True,
+                'context': context,
+                'stats': {
+                    'total_files': successful_files,
+                    'total_chars': total_chars,
+                    'estimated_tokens': total_chars // 4  # Estimation approximative
+                }
+            }
+            
+        except Exception as e:
+            error_msg = f"Erreur lors de la génération du contexte: {str(e)}"
+            logging.error(error_msg)
+            return {'success': False, 'error': error_msg}
+    
+    def _generate_file_tree(self, selected_files):
+        """Génère un arbre visuel des fichiers sélectionnés"""
+        if not selected_files:
+            return ["## Arbre des fichiers", "Aucun fichier sélectionné"]
+        
+        tree_lines = ["## Arbre des fichiers", "```"]
+        tree_lines.append(f"{os.path.basename(self.current_directory)}/")
+        
+        # Trier les fichiers pour un affichage cohérent
+        sorted_files = sorted(selected_files)
+        
+        # Construire l'arbre
+        for i, file_path in enumerate(sorted_files):
+            is_last = (i == len(sorted_files) - 1)
+            parts = file_path.split('/')
+            
+            # Construire l'indentation
+            prefix = "└── " if is_last else "├── "
+            indent = "    " * (len(parts) - 1)
+            
+            tree_lines.append(f"{indent}{prefix}{parts[-1]}")
+        
+        tree_lines.append("```")
+        return tree_lines
 
 def run_flask():
     app.run(port=5000, debug=False)
diff --git a/static/script.js b/static/script.js
index bc1086a..84b4b2e 100644
--- a/static/script.js
+++ b/static/script.js
@@ -134,6 +134,8 @@ document.addEventListener('DOMContentLoaded', () => {
     let includedFilePaths = []; // Will store only the included file paths (not ignored by gitignore)
     let selectionToPreserveForRegeneration = new Set();
     let isRegeneratingFlowActive = false;
+    let isDesktopMode = false; // Mode actuel (desktop vs web)
+    let currentSelectedDirectory = null; // Répertoire sélectionné en mode desktop
 
     let chatHistory = []; // Stocke l'historique : [{role: 'user'/'assistant', content: '...'}, ...]
     let currentAssistantMessageDiv = null; // Pour le streaming
@@ -280,9 +282,130 @@ document.addEventListener('DOMContentLoaded', () => {
         llmSelector.addEventListener('change', saveLastLlmChoice);
     }
 
-    // --- Directory analysis (upload of selected files) ---
+    // --- Nouveaux éléments pour le mode desktop ---
+    const selectDirectoryBtn = document.getElementById('selectDirectoryBtn');
+    const scanDirectoryBtn = document.getElementById('scanDirectoryBtn');
+    const selectedDirectoryPath = document.getElementById('selected-directory-path');
+    
+    // --- Mode Desktop : Sélection de répertoire ---
+    if (selectDirectoryBtn) {
+        selectDirectoryBtn.addEventListener('click', async () => {
+            try {
+                console.log("Demande de sélection de répertoire...");
+                const result = await pywebview.api.select_directory_dialog();
+                
+                if (result.success) {
+                    currentSelectedDirectory = result.directory;
+                    selectedDirectoryPath.textContent = result.directory;
+                    scanDirectoryBtn.classList.remove('d-none');
+                    console.log("Répertoire sélectionné:", result.directory);
+                } else {
+                    console.error("Erreur lors de la sélection:", result.error);
+                    showError(analyzeError, result.error, analyzeStatusContainer);
+                }
+            } catch (error) {
+                console.error("Erreur lors de l'appel à l'API:", error);
+                showError(analyzeError, "Erreur lors de la sélection du répertoire", analyzeStatusContainer);
+            }
+        });
+    }
+
+    // --- Mode Desktop : Scanner le répertoire ---
+    if (scanDirectoryBtn) {
+        scanDirectoryBtn.addEventListener('click', async () => {
+            if (!currentSelectedDirectory) {
+                showError(analyzeError, "Aucun répertoire sélectionné", analyzeStatusContainer);
+                return;
+            }
+
+            console.log("Début du scan du répertoire:", currentSelectedDirectory);
+            isDesktopMode = true;
+            
+            // Interface utilisateur
+            hideError(analyzeError);
+            showSpinner(analyzeSpinner);
+            scanDirectoryBtn.disabled = true;
+            hideElement(fileSelectionSection);
+            hideElement(generationSection);
+            hideElement(resultAndChatArea);
+            fileListDiv.innerHTML = '<p class="text-muted text-center placeholder-message">Scanning directory...</p>';
+            
+            // Réinitialiser l'état
+            currentFilesData = [];
+            includedFilePaths = [];
+            
+            try {
+                const result = await pywebview.api.scan_local_directory(currentSelectedDirectory);
+                
+                if (result.success) {
+                    console.log("Scan terminé:", result);
+                    
+                    // Préparer les données pour l'affichage
+                    includedFilePaths = result.files.map(f => f.path);
+                    currentFilesData = result.files; // Stocker pour utilisation ultérieure
+                    
+                    renderFileList(result.files);
+                    hideError(analyzeError);
+                    
+                    // Sélectionner tous les fichiers par défaut sauf les fichiers de dev
+                    selectAllBtn.click();
+                    fileListDiv.querySelectorAll('.form-check-input').forEach(checkbox => {
+                        if (isDevFile(checkbox.value)) {
+                            checkbox.checked = false;
+                            const parentLi = checkbox.closest('li.folder');
+                            if (parentLi) {
+                                parentLi.querySelectorAll('ul .form-check-input').forEach(child => child.checked = false);
+                            }
+                        }
+                    });
+                    
+                    // Mettre à jour les états des parents
+                    fileListDiv.querySelectorAll('li.file .form-check-input').forEach(updateParentCheckboxes);
+                    
+                    showElement(fileSelectionSection);
+                    showElement(generationSection);
+                    
+                    // Afficher les statistiques
+                    const noteDiv = document.createElement('div');
+                    noteDiv.className = 'alert alert-success mt-3';
+                    noteDiv.innerHTML = `
+                        <div class="d-flex align-items-center">
+                            <i class="fas fa-check-circle me-2"></i>
+                            <div>
+                                <strong>Scan local terminé</strong><br>
+                                <small>
+                                    ${result.total_files} fichiers trouvés • 
+                                    ${result.debug.gitignore_patterns_count} règles .gitignore appliquées
+                                </small>
+                            </div>
+                        </div>
+                    `;
+                    fileListDiv.appendChild(noteDiv);
+                    
+                    generationSection.scrollIntoView({ behavior: 'smooth' });
+                    
+                } else {
+                    console.error("Erreur de scan:", result.error);
+                    showError(analyzeError, `Erreur de scan: ${result.error}`, analyzeStatusContainer);
+                    fileListDiv.innerHTML = '<p class="text-danger text-center placeholder-message">Scan failed.</p>';
+                    showElement(fileSelectionSection);
+                }
+                
+            } catch (error) {
+                console.error("Erreur lors du scan:", error);
+                showError(analyzeError, `Erreur lors du scan: ${error.message}`, analyzeStatusContainer);
+                fileListDiv.innerHTML = '<p class="text-danger text-center placeholder-message">Scan failed.</p>';
+                showElement(fileSelectionSection);
+            } finally {
+                hideSpinner(analyzeSpinner);
+                scanDirectoryBtn.disabled = false;
+            }
+        });
+    }
+
+    // --- Mode Web existant (analyse) ---
     analyzeBtn.addEventListener('click', () => {
-        console.log("Analyze button clicked.");
+        console.log("Analyze button clicked (Web mode).");
         const files = directoryPicker.files;
         if (!files || files.length === 0) {
             showError(analyzeError, "Please select a directory.", analyzeStatusContainer);
@@ -290,6 +413,8 @@ document.addEventListener('DOMContentLoaded', () => {
             return;
         }
 
+        isDesktopMode = false;
+        
         // Sauvegarder le répertoire sélectionné
         saveLastDirectory(files);
 
@@ -681,7 +806,7 @@ document.addEventListener('DOMContentLoaded', () => {
         }
     }
 
-    // --- Generate context ---
+    // --- Génération de contexte adaptée aux deux modes ---
     async function executeActualGeneration() {
         const selectedCheckboxes = fileListDiv.querySelectorAll('.form-check-input:checked');
         const selectedFiles = Array.from(selectedCheckboxes).map(cb => cb.value).filter(path => {
@@ -693,146 +818,186 @@ document.addEventListener('DOMContentLoaded', () => {
             showError(generateError, "No files selected for context generation.", generationSection);
             return;
         }
+        
         hideError(generateError);
         hideElement(resultAndChatArea);
-
         selectionToPreserveForRegeneration = new Set(selectedFiles);
 
         const enableMasking = enableSecretMaskingCheckbox.checked;
         const maskingOptions = { enable_masking: enableMasking, mask_mode: "mask" };
         const instructions = instructionsTextarea.value;
         const selectedCompression = compressionValue.value;
-        const summarizerModel = summarizerModelSelect ? summarizerModelSelect.value : null;
-        const summarizerMaxWorkers = summarizerWorkersSelect ? summarizerWorkersSelect.value : null;
 
-        if (selectedCompression === 'summarize') {
-            const progressContainer = document.getElementById('summarizer-progress-container');
-            const progressBar = document.getElementById('summarizer-progress-bar');
-            const progressText = document.getElementById('summarizer-progress-text');
+        if (isDesktopMode) {
+            // Mode Desktop : génération locale
+            console.log("Génération en mode Desktop avec fichiers:", selectedFiles);
+            showSpinner(generateSpinner);
+            
+            try {
+                const result = await pywebview.api.generate_context_from_selection(selectedFiles);
+                
+                if (result.success) {
+                    displayResults(result.context, result.stats);
+                    showElement(resultAndChatArea);
+                    
+                    if (!resultAndChatArea.classList.contains('d-none')) {
+                        resultAndChatArea.scrollIntoView({ behavior: 'smooth' });
+                    }
+                } else {
+                    console.error("Erreur de génération:", result.error);
+                    showError(generateError, `Erreur de génération: ${result.error}`, generationSection);
+                }
+                
+            } catch (error) {
+                console.error("Erreur lors de la génération:", error);
+                showError(generateError, `Erreur lors de la génération: ${error.message}`, generationSection);
+            } finally {
+                hideSpinner(generateSpinner);
+                showElement(generateBtn);
+            }
+            
+        } else {
+            // Mode Web : génération via serveur (logique existante)
+            if (selectedCompression === 'summarize') {
+                const progressContainer = document.getElementById('summarizer-progress-container');
+                const progressBar = document.getElementById('summarizer-progress-bar');
+                const progressText = document.getElementById('summarizer-progress-text');
+
+                showElement(progressContainer);
+                progressBar.style.width = '0%';
+                progressBar.setAttribute('aria-valuenow', 0);
+                progressText.textContent = 'Starting...';
+                hideSpinner(generateSpinner);
 
-            showElement(progressContainer);
-            progressBar.style.width = '0%';
-            progressBar.setAttribute('aria-valuenow', 0);
-            progressText.textContent = 'Starting...';
-            hideSpinner(generateSpinner);
+                try {
+                    const initialResponse = await fetch('/generate', {
+                        method: 'POST',
+                        headers: { 'Content-Type': 'application/json' },
+                        body: JSON.stringify({
+                            selected_files: selectedFiles,
+                            masking_options: maskingOptions,
+                            instructions: instructions,
+                            compression_mode: selectedCompression,
+                            summarizer_model: summarizerModelSelect ? summarizerModelSelect.value : null,
+                            summarizer_max_workers: summarizerWorkersSelect ? summarizerWorkersSelect.value : null
+                        })
+                    });
 
-            try {
-                const initialResponse = await fetch('/generate', {
-                    method: 'POST',
-                    headers: { 'Content-Type': 'application/json' },
-                    body: JSON.stringify({
-                        selected_files: selectedFiles,
-                        masking_options: maskingOptions,
-                        instructions: instructions,
-                        compression_mode: selectedCompression,
-                        summarizer_model: summarizerModel,
-                        summarizer_max_workers: summarizerMaxWorkers
-                    })
-                });
+                    const initialResult = await initialResponse.json();
+                    if (!initialResponse.ok || !initialResult.success || !initialResult.task_id) {
+                        throw new Error(initialResult.error || `Failed to start summarization task.`);
+                    }
 
-                const initialResult = await initialResponse.json();
-                if (!initialResponse.ok || !initialResult.success || !initialResult.task_id) {
-                    throw new Error(initialResult.error || `Failed to start summarization task.`);
-                }
+                    const taskId = initialResult.task_id;
+                    const eventSource = new EventSource(`/summarize_progress?task_id=${taskId}`);
+
+                    eventSource.onmessage = (event) => {
+                        const data = JSON.parse(event.data);
+                        if (data.status === 'running') {
+                            const percent = data.total > 0 ? (data.completed / data.total) * 100 : 0;
+                            progressBar.style.width = `${percent}%`;
+                            progressBar.setAttribute('aria-valuenow', percent);
+                            progressText.textContent = `${data.completed} / ${data.total}`;
+                        } else if (data.status === 'error') {
+                            showError(generateError, `Summarization error: ${data.message}`, generationSection);
+                            eventSource.close();
+                            hideElement(progressContainer);
+                            showElement(generateBtn);
+                        }
+                    };
 
-                const taskId = initialResult.task_id;
-                const eventSource = new EventSource(`/summarize_progress?task_id=${taskId}`);
-
-                eventSource.onmessage = (event) => {
-                    const data = JSON.parse(event.data);
-                    if (data.status === 'running') {
-                        const percent = data.total > 0 ? (data.completed / data.total) * 100 : 0;
-                        progressBar.style.width = `${percent}%`;
-                        progressBar.setAttribute('aria-valuenow', percent);
-                        progressText.textContent = `${data.completed} / ${data.total}`;
-                    } else if (data.status === 'error') {
-                        showError(generateError, `Summarization error: ${data.message}`, generationSection);
+                    eventSource.addEventListener('done', (event) => {
                         eventSource.close();
                         hideElement(progressContainer);
-                        showElement(generateBtn);
-                    }
-                };
-
-                eventSource.addEventListener('done', (event) => {
-                    eventSource.close();
-                    hideElement(progressContainer);
-
-                    const finalResult = JSON.parse(event.data);
-                    if (finalResult.status === 'complete' && finalResult.result && finalResult.result.summary) {
-                        const { markdown, summary } = finalResult.result;
-                        markdownOutput.value = markdown;
-                        displaySummary(summary);
-                        displaySecretsAlert(summary.secrets_masked, summary.files_with_secrets);
-                        showElement(resultAndChatArea);
-                        const llmInteractionContainer = document.getElementById('llmInteractionContainer');
-                        if (llmInteractionContainer) showElement(llmInteractionContainer);
-                        resultAndChatArea.scrollIntoView({ behavior: 'smooth' });
-                    } else {
-                        const errorMessage = finalResult.result ? finalResult.result.error : 'Invalid data structure received on completion.';
-                        throw new Error(errorMessage || 'Summarization completed but returned an invalid result.');
-                    }
-                });
 
-                eventSource.onerror = (err) => {
-                    eventSource.close();
-                    console.error("EventSource failed:", err);
-                    showError(generateError, "Connection to progress stream failed. Please try again.", generationSection);
-                    hideElement(progressContainer);
-                    showElement(generateBtn);
-                };
+                        const finalResult = JSON.parse(event.data);
+                        if (finalResult.status === 'complete' && finalResult.result && finalResult.result.summary) {
+                            const { markdown, summary } = finalResult.result;
+                            markdownOutput.value = markdown;
+                            displaySummary(summary);
+                            displaySecretsAlert(summary.secrets_masked, summary.files_with_secrets);
+                            showElement(resultAndChatArea);
+                            const llmInteractionContainer = document.getElementById('llmInteractionContainer');
+                            if (llmInteractionContainer) showElement(llmInteractionContainer);
+                            resultAndChatArea.scrollIntoView({ behavior: 'smooth' });
+                        } else {
+                            const errorMessage = finalResult.result ? finalResult.result.error : 'Invalid data structure received on completion.';
+                            throw new Error(errorMessage || 'Summarization completed but returned an invalid result.');
+                        }
+                    });
 
-            } catch (error) {
-                console.error("Summarization error:", error);
-                showError(generateError, `Summarization error: ${error.message}`, generationSection);
-                hideElement(document.getElementById('summarizer-progress-container'));
-                showElement(generateBtn);
-            }
+                    eventSource.onerror = (err) => {
+                        eventSource.close();
+                        console.error("EventSource failed:", err);
+                        showError(generateError, "Connection to progress stream failed. Please try again.", generationSection);
+                        hideElement(progressContainer);
+                        showElement(generateBtn);
+                    };
 
-        } else {
-            showSpinner(generateSpinner);
-            try {
-                const response = await fetch('/generate', {
-                    method: 'POST',
-                    headers: { 'Content-Type': 'application/json' },
-                    body: JSON.stringify({
-                        selected_files: selectedFiles,
-                        masking_options: maskingOptions,
-                        instructions: instructions,
-                        compression_mode: selectedCompression,
-                        summarizer_model: summarizerModel,
-                        summarizer_max_workers: summarizerMaxWorkers
-                    })
-                });
-                const result = await response.json();
-                if (!response.ok || !result.success) {
-                    throw new Error(result.error || `Error ${response.status}`);
+                } catch (error) {
+                    console.error("Summarization error:", error);
+                    showError(generateError, `Summarization error: ${error.message}`, generationSection);
+                    hideElement(document.getElementById('summarizer-progress-container'));
+                    showElement(generateBtn);
                 }
-                markdownOutput.value = result.markdown;
-                displaySummary(result.summary);
-                displaySecretsAlert(result.summary.secrets_masked, result.summary.files_with_secrets);
 
-                showElement(resultAndChatArea);
-                
-                // Active le bouton du chat interne s'il existe
-                if (llmInteractionContainer) showElement(llmInteractionContainer);
-                if (startLlmChatBtn) showElement(startLlmChatBtn);
-                if (chatUiContainer) hideElement(chatUiContainer); // Réinitialise la vue du chat
-                
-                // Active le bouton d'envoi au navigateur si celui-ci est déjà connecté
-                if (browserStatus.textContent === 'Connecté') {
-                    sendContextBtn.disabled = false;
+            } else {
+                showSpinner(generateSpinner);
+                try {
+                    const response = await fetch('/generate', {
+                        method: 'POST',
+                        headers: { 'Content-Type': 'application/json' },
+                        body: JSON.stringify({
+                            selected_files: selectedFiles,
+                            masking_options: maskingOptions,
+                            instructions: instructions,
+                            compression_mode: selectedCompression,
+                            summarizer_model: summarizerModelSelect ? summarizerModelSelect.value : null,
+                            summarizer_max_workers: summarizerWorkersSelect ? summarizerWorkersSelect.value : null
+                        })
+                    });
+                    const data = await response.json();
+                    
+                    if (!response.ok || !data.success) {
+                        throw new Error(data.error || `Error ${response.status}`);
+                    }
+                    
+                    displayResults(data.context, data.summary);
+                    showElement(resultAndChatArea);
+                    
+                    if (!resultAndChatArea.classList.contains('d-none')) {
+                        resultAndChatArea.scrollIntoView({ behavior: 'smooth' });
+                    }
+                    
+                } catch (error) {
+                    console.error("Generation error:", error);
+                    showError(generateError, `Generation error: ${error.message}`, generationSection);
+                } finally {
+                    hideSpinner(generateSpinner);
+                    showElement(generateBtn);
                 }
-
-                resultAndChatArea.scrollIntoView({ behavior: 'smooth' });
-            } catch (error) {
-                console.error("Generation error:", error);
-                showError(generateError, `Generation error: ${error.message}`, generationSection);
-            } finally {
-                hideSpinner(generateSpinner);
             }
         }
     }
 
+    // --- Fonction d'affichage des résultats ---
+    function displayResults(contextContent, stats) {
+        const markdownOutput = document.getElementById('markdownOutput');
+        const summaryContainer = document.getElementById('summaryContainer');
+        
+        if (markdownOutput) {
+            markdownOutput.textContent = contextContent;
+        }
+        
+        if (summaryContainer && stats) {
+            displaySummary(stats);
+        }
+        
+        // Mettre à jour les boutons
+        hideElement(generateBtn);
+        showElement(regenerateBtn);
+    }
+
     generateBtn.addEventListener('click', executeActualGeneration);
     regenerateBtn.addEventListener('click', () => {
         isRegeneratingFlowActive = true;
diff --git a/templates/index.html b/templates/index.html
index 4831266..5e8ea4e 100644
--- a/templates/index.html
+++ b/templates/index.html
@@ -21,16 +21,40 @@
         <i class="fas fa-folder-open"></i> Step 1: Select a local directory
       </div>
       <div class="card-body">
-        <div class="mb-3">
-          <label for="directoryPicker" class="form-label">Select a directory on your PC:</label>
+        <!-- Mode Desktop avec scan local -->
+        <div id="desktop-mode" class="mb-3">
+          <label class="form-label">Mode Desktop - Sélection locale :</label>
+          <div class="d-flex gap-2 align-items-center">
+            <button class="btn btn-outline-primary" type="button" id="selectDirectoryBtn">
+              <i class="fas fa-folder-open"></i> Sélectionner un répertoire
+            </button>
+            <span id="selected-directory-path" class="text-muted"></span>
+          </div>
+          <div class="form-text">
+            Utilise la boîte de dialogue native pour sélectionner un répertoire. Les fichiers seront lus directement depuis le disque.
+          </div>
+          <button class="btn btn-success mt-2 d-none" type="button" id="scanDirectoryBtn">
+            <i class="fas fa-search"></i> Scanner le répertoire
+          </button>
+        </div>
+        
+        <!-- Séparateur -->
+        <div class="text-center my-3">
+          <span class="badge bg-secondary">OU</span>
+        </div>
+        
+        <!-- Mode Web classique -->
+        <div id="web-mode" class="mb-3">
+          <label for="directoryPicker" class="form-label">Mode Web - Upload de fichiers :</label>
           <div class="input-group">
-            <span class="input-group-text"><i class="fas fa-folder"></i></span>
+            <span class="input-group-text"><i class="fas fa-upload"></i></span>
             <input type="file" class="form-control" id="directoryPicker" webkitdirectory directory multiple>
           </div>
           <div class="form-text">
-            Use the selector to choose a local directory. The selected files and folders will be uploaded to generate the context.
+            Sélectionne un répertoire local. Les fichiers seront uploadés pour analyse.
           </div>
         </div>
+        
         <div id="analyze-status" class="mt-2 d-flex align-items-center" style="min-height: 24px;">
           <div id="analyze-spinner" class="spinner-border spinner-border-sm text-primary me-2 d-none" role="status">
             <span class="visually-hidden">Analyzing...</span>
@@ -38,7 +62,7 @@
           <div id="analyze-error" class="alert alert-danger p-1 mb-0 d-none" role="alert" style="font-size: 0.9em;"></div>
         </div>
         <button class="btn btn-primary mt-3" type="button" id="analyzeBtn" title="Analyze directory">
-          <i class="fas fa-search"></i> Analyze directory
+          <i class="fas fa-search"></i> Analyser le répertoire (Upload)
         </button>
       </div>
     </section>
