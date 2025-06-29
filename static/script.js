// static/script.js

const socket = io(); // Initialise la connexion Socket.IO

document.addEventListener('DOMContentLoaded', () => {
    // Lire l'état du streaming depuis l'attribut data du body
    const isLlmStreamEnabled = document.body.dataset.llmStreamEnabled === 'true';

    // --- Détection du mode pywebview au démarrage ---
    console.log("DEBUG: window.pywebview existe?", !!window.pywebview);
    
    // Fonction pour activer le mode pywebview
    function enablePywebviewMode() {
        const launchPywebviewBtn = document.getElementById('launchPywebviewBtn');
        if (launchPywebviewBtn) {
            launchPywebviewBtn.style.display = 'inline-block';
        }
        
        // Indicateur visuel pour confirmer la détection
        document.title = "Bureau Mode (PyWebView Détecté)";
        
        // Ajouter un badge visible
        const header = document.querySelector('header h1');
        if (header) {
            const badge = document.createElement('span');
            badge.className = 'badge bg-success ms-2';
            badge.textContent = 'Mode Desktop';
            header.appendChild(badge);
        }
    }
    
    // Essayer la détection immédiate
    if (window.pywebview) {
        console.log("Mode pywebview détecté immédiatement");
        enablePywebviewMode();
    } else {
        // Attendre que pywebview soit injecté (peut prendre du temps)
        let attempts = 0;
        const maxAttempts = 10;
        const checkInterval = setInterval(() => {
            attempts++;
            if (window.pywebview) {
                console.log("Mode pywebview détecté après", attempts, "tentatives");
                clearInterval(checkInterval);
                enablePywebviewMode();
            } else if (attempts >= maxAttempts) {
                console.log("Mode web classique - pywebview non détecté après", maxAttempts, "tentatives");
                clearInterval(checkInterval);
                // Activer quand même si on est dans main_desktop.py
                enablePywebviewMode(); // Puisque nous savons que nous sommes en mode desktop
            }
        }, 500);
    }
    
    // --- DOM element references ---
    const directoryPicker = document.getElementById('directoryPicker');
    const analyzeBtn = document.getElementById('analyzeBtn');
    const analyzeSpinner = document.getElementById('analyze-spinner');
    const analyzeError = document.getElementById('analyze-error');
    const analyzeStatusContainer = document.getElementById('analyze-status');
    const instructionsTextarea = document.getElementById('instructionsTextarea');
    const insertInstructionBtn1 = document.getElementById('insertInstructionBtn1');
    const insertInstructionBtn2 = document.getElementById('insertInstructionBtn2');
    const regenerateBtn = document.getElementById('regenerateBtn');

    // NOUVEAU: Références pour les options de compression
    const compressionOptionsBtn = document.getElementById('compressionOptionsBtn');
    const compressionLabel = document.getElementById('compressionLabel');
    const compressionValue = document.getElementById('compressionValue');
    const compressionMenu = document.querySelector('.dropdown-menu[aria-labelledby="compressionOptionsBtn"]');
    const summarizerOptionsDiv = document.getElementById('summarizer-options');
    const summarizerModelSelect = document.getElementById('summarizerModelSelect');
    const summarizerWorkersSelect = document.getElementById('summarizerWorkersSelect');
// NOUVEAU: Gestionnaire d'événements pour les options de compression
    if (compressionMenu) {
        compressionMenu.addEventListener('click', (event) => {
            // S'assurer qu'on a cliqué sur un élément du menu
            const target = event.target;
            if (target.classList.contains('dropdown-item')) {
                // Empêcher le comportement par défaut du lien (remonter en haut de page)
                event.preventDefault();

                // Récupérer la valeur et le texte
                const selectedValue = target.dataset.value;
                const selectedText = target.textContent.split('(')[0].trim(); // "Aucune (Défaut)" -> "Aucune"

                // Mettre à jour les éléments de l'interface
                if (compressionValue) {
                    compressionValue.value = selectedValue;
                }
                if (compressionLabel) {
                    compressionLabel.textContent = selectedText;
                }
                
                // Show/hide summarizer options based on selection
                if (selectedValue === 'summarize') {
                    summarizerOptionsDiv?.classList.remove('d-none');
                } else {
                    summarizerOptionsDiv?.classList.add('d-none');
                }
            }
        });
    }

    const fileSelectionSection = document.getElementById('file-selection-section');
    const fileListDiv = document.getElementById('fileList');
    const selectAllBtn = document.getElementById('selectAllBtn');
    const deselectAllBtn = document.getElementById('deselectAllBtn');
    const selectMdCheckbox = document.getElementById('selectMdCheckbox');
    const selectDevCheckbox = document.getElementById('selectDevCheckbox');

    const generationSection = document.getElementById('generation-section');
    const generateBtn = document.getElementById('generateBtn');
    const generateSpinner = document.getElementById('generate-spinner');
    const generateError = document.getElementById('generate-error');
    const enableSecretMaskingCheckbox = document.getElementById('enableSecretMasking');

    const resultAndChatArea = document.getElementById('resultAndChatArea');
    const markdownOutput = document.getElementById('markdownOutput');
    const summaryContainer = document.getElementById('summaryContainer');
    const copyBtn = document.getElementById('copyBtn');
    // Chat UI elements for LLM
    const startLlmChatBtn = document.getElementById('startLlmChatBtn');
    const chatUiContainer = document.getElementById('chatUiContainer');
    const sendChatMessageBtn = document.getElementById('sendChatMessageBtn');
    const chatMessageInput = document.getElementById('chatMessageInput');

    const llmErrorChat = document.getElementById('llm-error-chat');
    const llmChatSpinner = document.getElementById('llm-chat-spinner');
    const appendPatchToChatBtn = document.getElementById('appendPatchToChatBtn');

    // --- State variables ---
    let currentFilesData = []; // Will store uploaded files (object with name, full relative path and content)
    let includedFilePaths = []; // Will store only the included file paths (not ignored by gitignore)
    let selectionToPreserveForRegeneration = new Set();
    let isRegeneratingFlowActive = false;
    let isDesktopMode = false; // Mode actuel (desktop vs web)
    let currentSelectedDirectory = null; // Répertoire sélectionné en mode desktop

    let chatHistory = []; // Stocke l'historique : [{role: 'user'/'assistant', content: '...'}, ...]
    let currentAssistantMessageDiv = null; // Pour le streaming

    // --- Utility functions ---
    function showElement(element) { element?.classList.remove('d-none'); }
    function hideElement(element) { element?.classList.add('d-none'); }
    function showError(errorElement, message, statusContainer, isHtml = false) {
        if (errorElement) { 
            if (isHtml) {
                errorElement.innerHTML = message;
            } else {
                errorElement.textContent = message;
            }
            showElement(errorElement); 
        }
        hideElement(statusContainer?.querySelector('.spinner-border'));
    }
    function hideError(errorElement) { hideElement(errorElement); if (errorElement) errorElement.textContent = ''; }
    function showSpinner(spinnerElement) { showElement(spinnerElement); }
    function hideSpinner(spinnerElement) { hideElement(spinnerElement); }

    function escapeHtml(unsafe) {
        return unsafe
             .replace(/&/g, "&amp;")
             .replace(/</g, "&lt;")
             .replace(/>/g, "&gt;")
             .replace(/"/g, "&quot;")
             .replace(/'/g, "&#039;");
    }

    function appendMessageToChat(role, content, existingDiv = null) {
        const messageWrapper = existingDiv ? existingDiv.closest('.chat-message-wrapper') : document.createElement('div');
        if (!existingDiv) {
            messageWrapper.classList.add('chat-message-wrapper', `chat-${role}`);
        }

        const messageDiv = existingDiv || document.createElement('div');
        if (!existingDiv) {
            messageDiv.classList.add('chat-bubble');
        }
        
        let processedContent = "";
        if (content) {
            if (role === 'assistant') {
                // Utiliser Marked.js pour le contenu de l'assistant
                // Assurez-vous que Marked.js est chargé (par exemple, via CDN dans index.html)
                if (typeof marked !== 'undefined') {
                    processedContent = marked.parse(content);
                } else {
                    console.warn("Marked.js n'est pas chargé. Affichage du Markdown brut.");
                    processedContent = escapeHtml(content).replace(/\\n/g, '<br>'); // Fallback simple
                }
            } else if (role === 'user') {
                // Pour les messages utilisateur, échapper le HTML et convertir les sauts de ligne
                processedContent = escapeHtml(content).replace(/\\n/g, '<br>');
            } else { // system-error ou autres
                processedContent = escapeHtml(content).replace(/\\n/g, '<br>');
            }
        }
        
        messageDiv.innerHTML = processedContent;

        // Le bouton copier doit toujours utiliser le contenu brut (non-HTML) pour l'assistant
        let rawContentForCopy = content; 

        if (role === 'assistant' && !existingDiv) {
            const copyBtnElement = document.createElement('button');
            copyBtnElement.innerHTML = '<i class="far fa-copy"></i>';
            copyBtnElement.classList.add('btn', 'btn-sm', 'btn-outline-secondary', 'copy-chat-btn');
            copyBtnElement.title = 'Copier ce message';
            
            copyBtnElement.onclick = () => {
                // S'assurer de copier le contenu final brut si streamé
                const finalContent = messageDiv.dataset.finalRawContent || rawContentForCopy; 
                navigator.clipboard.writeText(finalContent).then(() => {
                    const originalIcon = copyBtnElement.innerHTML;
                    copyBtnElement.innerHTML = '<i class="fas fa-check text-success"></i>';
                    setTimeout(() => { copyBtnElement.innerHTML = originalIcon; }, 1500);
                }).catch(err => {
                    console.error('Erreur de copie:', err);
                    alert("Impossible de copier le message.")
                });
            };
            messageWrapper.appendChild(copyBtnElement);
        }
        
        if (!existingDiv) {
            messageWrapper.insertBefore(messageDiv, messageWrapper.firstChild);
            chatDisplayArea.appendChild(messageWrapper);
        }
        chatDisplayArea.scrollTop = chatDisplayArea.scrollHeight;
        return messageDiv; // Retourner l'élément pour le streaming
    }

    // --- Fonction pour sauvegarder le dernier répertoire ---
    function saveLastDirectory(files) {
        if (files && files.length > 0) {
            // Récupérer le chemin du premier fichier pour identifier le répertoire
            const firstFilePath = files[0].webkitRelativePath || files[0].name;
            const directoryName = firstFilePath.split('/')[0];
            localStorage.setItem('lastSelectedDirectory', directoryName);
            console.log("Répertoire sauvegardé:", directoryName);
        }
    }

    // --- Fonction pour restaurer le focus sur le dernier répertoire ---
    function restoreLastDirectory() {
        const lastDir = localStorage.getItem('lastSelectedDirectory');
        if (lastDir) {
            // Ajouter un indicateur visuel pour montrer le dernier répertoire utilisé
            const directoryLabel = document.querySelector('label[for="directoryPicker"]');
            if (directoryLabel) {
                directoryLabel.innerHTML = `Select a directory on your PC: <small class="text-muted">(Dernier: ${lastDir})</small>`;
            }
        }
    }

    // Restaurer l'indicateur du dernier répertoire au chargement
    restoreLastDirectory();

    // --- Persistance du choix de LLM ---
    function saveLastLlmChoice() {
        const llmSelector = document.getElementById('llm-destination-selector');
        if (llmSelector) {
            localStorage.setItem('lastSelectedLLM', llmSelector.value);
        }
    }

    function restoreLastLlmChoice() {
        const lastLlm = localStorage.getItem('lastSelectedLLM');
        const llmSelector = document.getElementById('llm-destination-selector');
        if (lastLlm && llmSelector) {
            llmSelector.value = lastLlm;
        }
    }

    // Restaurer le choix de LLM au chargement
    setTimeout(restoreLastLlmChoice, 500); // Attendre que l'élément soit disponible

    // Sauvegarder le choix de LLM quand il change
    const llmSelector = document.getElementById('llm-destination-selector');
    if (llmSelector) {
        llmSelector.addEventListener('change', saveLastLlmChoice);
    }

    // --- Nouveaux éléments pour le mode desktop ---
    const selectDirectoryBtn = document.getElementById('selectDirectoryBtn');
    const scanDirectoryBtn = document.getElementById('scanDirectoryBtn');
    const selectedDirectoryPath = document.getElementById('selected-directory-path');
    
    // --- Mode Desktop : Sélection de répertoire ---
    if (selectDirectoryBtn) {
        selectDirectoryBtn.addEventListener('click', async () => {
            try {
                console.log("Demande de sélection de répertoire...");
                const result = await pywebview.api.select_directory_dialog();
                
                if (result.success) {
                    currentSelectedDirectory = result.directory;
                    selectedDirectoryPath.textContent = result.directory;
                    scanDirectoryBtn.classList.remove('d-none');
                    console.log("Répertoire sélectionné:", result.directory);
                } else {
                    console.error("Erreur lors de la sélection:", result.error);
                    showError(analyzeError, result.error, analyzeStatusContainer);
                }
            } catch (error) {
                console.error("Erreur lors de l'appel à l'API:", error);
                showError(analyzeError, "Erreur lors de la sélection du répertoire", analyzeStatusContainer);
            }
        });
    }

    // --- Mode Desktop : Scanner le répertoire ---
    if (scanDirectoryBtn) {
        scanDirectoryBtn.addEventListener('click', async () => {
            if (!currentSelectedDirectory) {
                showError(analyzeError, "Aucun répertoire sélectionné", analyzeStatusContainer);
                return;
            }

            console.log("Début du scan du répertoire:", currentSelectedDirectory);
            isDesktopMode = true;
            
            // Interface utilisateur
            hideError(analyzeError);
            showSpinner(analyzeSpinner);
            scanDirectoryBtn.disabled = true;
            hideElement(fileSelectionSection);
            hideElement(generationSection);
            hideElement(resultAndChatArea);
            fileListDiv.innerHTML = '<p class="text-muted text-center placeholder-message">Scanning directory...</p>';
            
            // Réinitialiser l'état
            currentFilesData = [];
            includedFilePaths = [];
            
            try {
                const result = await pywebview.api.scan_local_directory(currentSelectedDirectory);
                
                if (result.success) {
                    console.log("Scan terminé:", result);
                    
                    // Préparer les données pour l'affichage
                    includedFilePaths = result.files.map(f => f.path);
                    currentFilesData = result.files; // Stocker pour utilisation ultérieure
                    
                    renderFileList(result.files);
                    hideError(analyzeError);
                    
                    // Sélectionner tous les fichiers par défaut sauf les fichiers de dev
                    selectAllBtn.click();
                    fileListDiv.querySelectorAll('.form-check-input').forEach(checkbox => {
                        // On décoche uniquement la case du fichier "dev" lui-même
                        if (isDevFile(checkbox.value)) {
                            checkbox.checked = false;
                        }
                    });
                    
                    // Mettre à jour les états des parents
                    fileListDiv.querySelectorAll('li.file .form-check-input').forEach(updateParentCheckboxes);
                    
                    showElement(fileSelectionSection);
                    showElement(generationSection);
                    
                    // Afficher les statistiques
                    const noteDiv = document.createElement('div');
                    noteDiv.className = 'alert alert-success mt-3';
                    noteDiv.innerHTML = `
                        <div class="d-flex align-items-center">
                            <i class="fas fa-check-circle me-2"></i>
                            <div>
                                <strong>Scan local terminé</strong><br>
                                <small>
                                    ${result.total_files} fichiers trouvés • 
                                    ${result.debug.gitignore_patterns_count} règles .gitignore appliquées
                                </small>
                            </div>
                        </div>
                    `;
                    fileListDiv.appendChild(noteDiv);
                    
                    generationSection.scrollIntoView({ behavior: 'smooth' });
                    
                } else {
                    console.error("Erreur de scan:", result.error);
                    showError(analyzeError, `Erreur de scan: ${result.error}`, analyzeStatusContainer);
                    fileListDiv.innerHTML = '<p class="text-danger text-center placeholder-message">Scan failed.</p>';
                    showElement(fileSelectionSection);
                }
                
            } catch (error) {
                console.error("Erreur lors du scan:", error);
                showError(analyzeError, `Erreur lors du scan: ${error.message}`, analyzeStatusContainer);
                fileListDiv.innerHTML = '<p class="text-danger text-center placeholder-message">Scan failed.</p>';
                showElement(fileSelectionSection);
            } finally {
                hideSpinner(analyzeSpinner);
                scanDirectoryBtn.disabled = false;
            }
        });
    }

    // --- Mode Web existant (analyse) ---
    analyzeBtn.addEventListener('click', () => {
        console.log("Analyze button clicked (Web mode).");
        const files = directoryPicker.files;
        if (!files || files.length === 0) {
            showError(analyzeError, "Please select a directory.", analyzeStatusContainer);
            console.error("No directory selected or no files found in selected directory.");
            return;
        }

        isDesktopMode = false;
        
        // Sauvegarder le répertoire sélectionné
        saveLastDirectory(files);

        // --- Partie 1: Mises à jour immédiates de l'interface utilisateur ---
        hideError(analyzeError);
        showSpinner(analyzeSpinner);
        analyzeBtn.disabled = true; // Désactiver le bouton pour éviter les doubles clics
        hideElement(fileSelectionSection);
        hideElement(generationSection);
        hideElement(resultAndChatArea);
        fileListDiv.innerHTML = '<p class="text-muted text-center placeholder-message">Analyzing...</p>';
        currentFilesData = [];
        includedFilePaths = [];

        // Réinitialiser les cases à cocher de sélection rapide
        if (selectMdCheckbox) selectMdCheckbox.checked = false;
        if (selectDevCheckbox) selectDevCheckbox.checked = false;

        // Réinitialiser l'état des boutons de génération/régénération
        showElement(generateBtn);
        hideElement(regenerateBtn);


        // --- Partie 2: Logique principale différée pour permettre le rafraîchissement de l'interface ---
        setTimeout(async () => {
            try {
                // Read all files using FileReader and retrieve their full relative path
                const readFilePromises = [];
                for (let i = 0; i < files.length; i++) {
                    const file = files[i];
                    readFilePromises.push(new Promise((resolve, reject) => {
                        const reader = new FileReader();
                        reader.onload = () => {
                            resolve({
                                name: file.name,
                                path: file.webkitRelativePath || file.name,
                                content: reader.result
                            });
                        };
                        reader.onerror = () => {
                            console.error(`FileReader error for ${file.name}:`, reader.error);
                            reject(new Error(`Error reading file ${file.name}.`));
                        };
                        reader.readAsText(file);
                    }));
                }

                const uploadedFiles = await Promise.all(readFilePromises);
                currentFilesData = uploadedFiles;
                
                // Send the uploaded data to the server
                const response = await fetch('/upload', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
                    body: JSON.stringify({ files: uploadedFiles })
                });
                const data = await response.json();
                if (!response.ok || !data.success) {
                    throw new Error(data.error || `Error ${response.status}`);
                }
                
                includedFilePaths = data.files.map(f => f.path);
                renderFileList(data.files);
                hideError(analyzeError);

                if (isRegeneratingFlowActive) {
                    // Re-apply preserved selection
                    fileListDiv.querySelectorAll('.form-check-input').forEach(checkbox => {
                        checkbox.checked = selectionToPreserveForRegeneration.has(checkbox.value);
                    });
                    selectionToPreserveForRegeneration.clear();
                    isRegeneratingFlowActive = false;

                    showElement(fileSelectionSection);
                    showElement(generationSection);
                    
                    // await executeActualGeneration(); // Automatically generate context
                } else {
                    // Normal flow
                    selectAllBtn.click();
                    fileListDiv.querySelectorAll('.form-check-input').forEach(checkbox => {
                        // On décoche uniquement la case du fichier "dev" lui-même
                        if (isDevFile(checkbox.value)) {
                            checkbox.checked = false;
                        }
                    });
                    // La fonction suivante s'occupera de mettre à jour l'état des dossiers parents
                    fileListDiv.querySelectorAll('li.file .form-check-input').forEach(updateParentCheckboxes);
                    showElement(fileSelectionSection);
                    showElement(generationSection);
                }

                if (!generationSection.classList.contains('d-none')) {
                    generationSection.scrollIntoView({ behavior: 'smooth' });
                }

            } catch (error) {
                console.error("Analysis error:", error);
                showError(analyzeError, `Analysis error: ${error.message}`, analyzeStatusContainer);
                fileListDiv.innerHTML = '<p class="text-danger text-center placeholder-message">Analysis failed.</p>';
                showElement(fileSelectionSection);
            } finally {
                hideSpinner(analyzeSpinner);
                analyzeBtn.disabled = false; // Réactiver le bouton
            }
        }, 0); // Le délai de 0 permet au navigateur de redessiner l'interface
    });

    // --- Render file tree ---
    function renderFileList(files) {
        fileListDiv.innerHTML = '';
        if (files.length === 0) {
            fileListDiv.innerHTML = '<p class="text-muted text-center placeholder-message">No non-ignored files found.</p>';
            return;
        }
        
        // Build tree structure from paths (files already contains only non-ignored files)
        const paths = files.map(f => f.path);
        const tree = buildTreeStructure(paths);
        
        // Create the DOM element for the tree
        const ul = createTreeElement(tree, "");
        fileListDiv.appendChild(ul);
        
        // Add an explanatory note for the user
        const noteDiv = document.createElement('div');
        noteDiv.className = 'alert alert-info mt-3';
        noteDiv.innerHTML = '<small><i class="fas fa-info-circle"></i> Note: Only files not ignored by .gitignore rules are displayed and selected.</small>';
        fileListDiv.appendChild(noteDiv);
    }

    // Construct a tree structure from relative paths
    function buildTreeStructure(paths) {
        const tree = {};
        paths.forEach(path => {
            let currentLevel = tree;
            const parts = path.split('/');
            parts.forEach((part, index) => {
                if (!part) return;
                const isLastPart = (index === parts.length - 1);
                if (!currentLevel[part]) {
                    // If not the last part, create an object to contain children
                    currentLevel[part] = isLastPart ? true : { _children: {} };
                }
                if (!isLastPart && typeof currentLevel[part] === 'object') {
                    currentLevel = currentLevel[part]._children;
                }
            });
        });
        return tree;
    }

    // --- Create the tree structure while preserving full path and selecting by default ---
    function createTreeElement(node, basePath) {
        const ul = document.createElement('ul');
        const keys = Object.keys(node).sort();
        keys.forEach(key => {
            // Calculate the full path for the current node
            const fullPath = basePath ? `${basePath}/${key}` : key;
            const li = document.createElement('li');
            const div = document.createElement('div');
            div.classList.add('form-check');

            const input = document.createElement('input');
            input.type = 'checkbox';
            input.classList.add('form-check-input');
            // Using the full path as the value (e.g., "static/script.js")
            input.value = fullPath;
            // Select by default only files that are in the included file paths list
            // For folders, always select by default
            input.checked = true;

            const label = document.createElement('label');
            label.classList.add('form-check-label');
            label.textContent = key;

            div.appendChild(input);
            div.appendChild(label);
            li.appendChild(div);

            if (node[key] && typeof node[key] === 'object' && node[key]._children && Object.keys(node[key]._children).length > 0) {
                li.classList.add('folder');
                // Recursive call passing the fullPath to accumulate the full path
                const childrenUl = createTreeElement(node[key]._children, fullPath);
                li.appendChild(childrenUl);
            } else {
                li.classList.add('file');
            }
            ul.appendChild(li);
        });
        return ul;
    }

    // --- Handling selection via checkboxes ---
    fileListDiv.addEventListener('change', (event) => {
        if (event.target.matches('.form-check-input')) {
            const checkbox = event.target;
            const isChecked = checkbox.checked;
            const parentLi = checkbox.closest('li');

            // Propagate change downwards to children if it's a folder
            if (parentLi && parentLi.classList.contains('folder')) {
                const childCheckboxes = parentLi.querySelectorAll('ul .form-check-input');
                childCheckboxes.forEach(child => {
                    child.checked = isChecked;
                    child.indeterminate = false; // When parent is clicked, children are not indeterminate
                });
            }

            // Propagate change upwards to parents
            updateParentCheckboxes(checkbox);
        }
    });

    selectAllBtn.addEventListener('click', () => {
        fileListDiv.querySelectorAll('.form-check-input').forEach(cb => {
            cb.checked = true;
        });
    });
    deselectAllBtn.addEventListener('click', () => {
        fileListDiv.querySelectorAll('.form-check-input').forEach(cb => {
            cb.checked = false;
        });
    });

    function updateParentCheckboxes(element) {
        const parentLi = element.closest('li');
        if (!parentLi) return;

        const parentUl = parentLi.parentElement;
        if (!parentUl) return;

        const folderLi = parentUl.closest('li.folder');
        if (!folderLi) return; // Reached the root

        const folderCheckbox = folderLi.querySelector(':scope > .form-check > .form-check-input');
        if (!folderCheckbox) return;

        const childCheckboxes = Array.from(parentUl.querySelectorAll(':scope > li > .form-check > .form-check-input'));
        if (childCheckboxes.length === 0) return;

        const totalChildren = childCheckboxes.length;
        const checkedChildren = childCheckboxes.filter(cb => cb.checked).length;
        const indeterminateChildren = childCheckboxes.filter(cb => cb.indeterminate).length;

        if (checkedChildren === 0 && indeterminateChildren === 0) {
            folderCheckbox.checked = false;
            folderCheckbox.indeterminate = false;
        } else if (checkedChildren === totalChildren && indeterminateChildren === 0) {
            folderCheckbox.checked = true;
            folderCheckbox.indeterminate = false;
        } else {
            folderCheckbox.checked = false;
            folderCheckbox.indeterminate = true;
        }

        // Recurse up the tree
        updateParentCheckboxes(folderCheckbox);
    }

    // --- Logique pour les nouvelles cases à cocher de sélection rapide ---

    function isDevFile(filePath) {
        const devPatterns = [
            // Fichiers de dépendances et config
            'requirements.txt', 'requirements-dev.txt', 'pyproject.toml', 'package.json', 'pnpm-lock.yaml',
            // Fichiers de config
            '.gitignore', '.dockerignore', '.editorconfig', 'config.ini', 'config.ini.template',
            // Scripts
            '.sh', '.bat', '.ps1',
            // CI/CD
            'Dockerfile', 'docker-compose.yml', '.github/', '.gitlab-ci.yml',
            // Documentation et licence
            '.md', 'LICENSE', 'CONTRIBUTING', 'docs/',
            // Tests
            'tests/', 'tests_e2e/',
            // Templates
            '.template'
        ];

        // Vérifie les extensions et noms de fichiers exacts
        if (devPatterns.some(pattern => pattern.startsWith('.') && filePath.endsWith(pattern))) {
            return true;
        }
        // Vérifie les noms de fichiers exacts
        if (devPatterns.some(pattern => !pattern.startsWith('.') && !pattern.endsWith('/') && filePath.endsWith(pattern))) {
            return true;
        }
        // Vérifie les répertoires
        if (devPatterns.some(pattern => pattern.endsWith('/') && filePath.startsWith(pattern))) {
            return true;
        }
        return false;
    }

    if (selectDevCheckbox) {
        selectDevCheckbox.addEventListener('change', (event) => {
            const isChecked = event.target.checked;
            fileListDiv.querySelectorAll('.form-check-input').forEach(checkbox => {
                if (isDevFile(checkbox.value)) {
                    checkbox.checked = isChecked;
                }
            });
            // After changing, update all parent folder states
            fileListDiv.querySelectorAll('li.file .form-check-input').forEach(fileCheckbox => {
                updateParentCheckboxes(fileCheckbox);
            });
        });
    }

    if (selectMdCheckbox) {
        selectMdCheckbox.addEventListener('change', (event) => {
            const isChecked = event.target.checked;
            fileListDiv.querySelectorAll('.form-check-input').forEach(checkbox => {
                if (checkbox.value.endsWith('.md')) {
                    checkbox.checked = isChecked;
                }
            });
            // After changing, update all parent folder states
            fileListDiv.querySelectorAll('li.file .form-check-input').forEach(fileCheckbox => {
                updateParentCheckboxes(fileCheckbox);
            });
        });
    }

    // Function to format numbers with thousands separators
    function formatNumber(num) {
        return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ");
    }

    function displaySummary(summary) {
        const summaryContainer = document.getElementById('summaryContainer');
        if (!summaryContainer) return;

        summaryContainer.innerHTML = ''; // Clear previous summary

        if (!summary) {
            summaryContainer.innerHTML = '<p class="text-muted">No summary data available.</p>';
            return;
        }

        const title = document.createElement('h5');
        title.innerHTML = '<i class="fas fa-list-alt text-muted"></i> Generation Summary:';
        summaryContainer.appendChild(title);

        const list = document.createElement('ul');
        list.classList.add('list-group', 'list-group-flush', 'small');

        const items = {
            "Total files processed": summary.total_files,
            "Total files included": summary.included_files_count,
            "Total files excluded (by .gitignore or rules)": summary.excluded_files_count,
            "Total lines of code included": summary.total_lines,
            "Total characters included": summary.total_chars,
            "Estimated tokens (approximate)": summary.estimated_tokens
        };

        for (const [key, value] of Object.entries(items)) {
            if (value !== undefined && value !== null) {
                const listItem = document.createElement('li');
                listItem.classList.add('list-group-item', 'd-flex', 'justify-content-between', 'align-items-center', 'p-1');
                listItem.innerHTML = `${key}: <span class="badge bg-primary rounded-pill">${formatNumber(value)}</span>`;
                list.appendChild(listItem);
            }
        }
        summaryContainer.appendChild(list);
    }

    function displaySecretsAlert(secrets_masked_count, files_with_secrets) {
        const secretsAlertDiv = document.getElementById('secretsMaskedAlert');
        const secretsDetailsUl = document.getElementById('secretsMaskedDetails');

        if (!secretsAlertDiv || !secretsDetailsUl) return;

        secretsDetailsUl.innerHTML = ''; // Clear previous details

        if (secrets_masked_count > 0 && files_with_secrets && files_with_secrets.length > 0) {
            secretsAlertDiv.classList.remove('d-none');
            
            files_with_secrets.forEach(filePath => {
                const li = document.createElement('li');
                li.textContent = filePath;
                secretsDetailsUl.appendChild(li);
            });
        } else {
            secretsAlertDiv.classList.add('d-none');
        }
    }

    // --- Génération de contexte adaptée aux deux modes ---
    async function executeActualGeneration() {
        const selectedCheckboxes = fileListDiv.querySelectorAll('.form-check-input:checked');
        const selectedFiles = Array.from(selectedCheckboxes).map(cb => cb.value).filter(path => {
            const li = fileListDiv.querySelector(`input[value="${path}"]`)?.closest('li');
            return li && li.classList.contains('file');
        });

        if (selectedFiles.length === 0) {
            showError(generateError, "No files selected for context generation.", generationSection);
            return;
        }
        
        hideError(generateError);
        hideElement(resultAndChatArea);
        selectionToPreserveForRegeneration = new Set(selectedFiles);

        const enableMasking = enableSecretMaskingCheckbox.checked;
        const maskingOptions = { enable_masking: enableMasking, mask_mode: "mask" };
        const instructions = instructionsTextarea.value;
        const selectedCompression = compressionValue.value;

        if (isDesktopMode) {
            // Mode Desktop : génération locale
            console.log("Génération en mode Desktop avec fichiers:", selectedFiles);
            showSpinner(generateSpinner);
            
            try {
                const result = await pywebview.api.generate_context_from_selection(selectedFiles, instructions);
                
                if (result.success) {
                    displayResults(result.context, result.stats);
                    showElement(resultAndChatArea);
                    
                    if (!resultAndChatArea.classList.contains('d-none')) {
                        resultAndChatArea.scrollIntoView({ behavior: 'smooth' });
                    }
                } else {
                    console.error("Erreur de génération:", result.error);
                    showError(generateError, `Erreur de génération: ${result.error}`, generationSection);
                }
                
            } catch (error) {
                console.error("Erreur lors de la génération:", error);
                showError(generateError, `Erreur lors de la génération: ${error.message}`, generationSection);
            } finally {
                hideSpinner(generateSpinner);
                showElement(generateBtn);
            }
            
        } else {
            // Mode Web : génération via serveur (logique existante)
            if (selectedCompression === 'summarize') {
                const progressContainer = document.getElementById('summarizer-progress-container');
                const progressBar = document.getElementById('summarizer-progress-bar');
                const progressText = document.getElementById('summarizer-progress-text');

                showElement(progressContainer);
                progressBar.style.width = '0%';
                progressBar.setAttribute('aria-valuenow', 0);
                progressText.textContent = 'Starting...';
                hideSpinner(generateSpinner);

                try {
                    const initialResponse = await fetch('/generate', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            selected_files: selectedFiles,
                            masking_options: maskingOptions,
                            instructions: instructions,
                            compression_mode: selectedCompression,
                            summarizer_model: summarizerModelSelect ? summarizerModelSelect.value : null,
                            summarizer_max_workers: summarizerWorkersSelect ? summarizerWorkersSelect.value : null
                        })
                    });

                    const initialResult = await initialResponse.json();
                    if (!initialResponse.ok || !initialResult.success || !initialResult.task_id) {
                        throw new Error(initialResult.error || `Failed to start summarization task.`);
                    }

                    const taskId = initialResult.task_id;
                    const eventSource = new EventSource(`/summarize_progress?task_id=${taskId}`);

                    eventSource.onmessage = (event) => {
                        const data = JSON.parse(event.data);
                        if (data.status === 'running') {
                            const percent = data.total > 0 ? (data.completed / data.total) * 100 : 0;
                            progressBar.style.width = `${percent}%`;
                            progressBar.setAttribute('aria-valuenow', percent);
                            progressText.textContent = `${data.completed} / ${data.total}`;
                        } else if (data.status === 'error') {
                            showError(generateError, `Summarization error: ${data.message}`, generationSection);
                            eventSource.close();
                            hideElement(progressContainer);
                            showElement(generateBtn);
                        }
                    };

                    eventSource.addEventListener('done', (event) => {
                        eventSource.close();
                        hideElement(progressContainer);

                        const finalResult = JSON.parse(event.data);
                        if (finalResult.status === 'complete' && finalResult.result && finalResult.result.summary) {
                            const { markdown, summary } = finalResult.result;
                            markdownOutput.value = markdown;
                            displaySummary(summary);
                            displaySecretsAlert(summary.secrets_masked, summary.files_with_secrets);
                            showElement(resultAndChatArea);
                            const llmInteractionContainer = document.getElementById('llmInteractionContainer');
                            if (llmInteractionContainer) showElement(llmInteractionContainer);
                            resultAndChatArea.scrollIntoView({ behavior: 'smooth' });
                        } else {
                            const errorMessage = finalResult.result ? finalResult.result.error : 'Invalid data structure received on completion.';
                            throw new Error(errorMessage || 'Summarization completed but returned an invalid result.');
                        }
                    });

                    eventSource.onerror = (err) => {
                        eventSource.close();
                        console.error("EventSource failed:", err);
                        showError(generateError, "Connection to progress stream failed. Please try again.", generationSection);
                        hideElement(progressContainer);
                        showElement(generateBtn);
                    };

                } catch (error) {
                    console.error("Summarization error:", error);
                    showError(generateError, `Summarization error: ${error.message}`, generationSection);
                    hideElement(document.getElementById('summarizer-progress-container'));
                    showElement(generateBtn);
                }

            } else {
                showSpinner(generateSpinner);
                try {
                    const response = await fetch('/generate', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            selected_files: selectedFiles,
                            masking_options: maskingOptions,
                            instructions: instructions,
                            compression_mode: selectedCompression,
                            summarizer_model: summarizerModelSelect ? summarizerModelSelect.value : null,
                            summarizer_max_workers: summarizerWorkersSelect ? summarizerWorkersSelect.value : null
                        })
                    });
                    const data = await response.json();
                    
                    if (!response.ok || !data.success) {
                        throw new Error(data.error || `Error ${response.status}`);
                    }
                    
                    displayResults(data.context, data.summary);
                    showElement(resultAndChatArea);
                    
                    if (!resultAndChatArea.classList.contains('d-none')) {
                        resultAndChatArea.scrollIntoView({ behavior: 'smooth' });
                    }
                    
                } catch (error) {
                    console.error("Generation error:", error);
                    showError(generateError, `Generation error: ${error.message}`, generationSection);
                } finally {
                    hideSpinner(generateSpinner);
                    showElement(generateBtn);
                }
            }
        }
    }

    // --- Fonction d'affichage des résultats ---
    function displayResults(contextContent, stats) {
        const markdownOutput = document.getElementById('markdownOutput');
        const summaryContainer = document.getElementById('summaryContainer');
        
        if (markdownOutput) {
            markdownOutput.textContent = contextContent;
        }
        
        if (summaryContainer && stats) {
            displaySummary(stats);
        }
        
        // Mettre à jour les boutons
        hideElement(generateBtn);
        showElement(regenerateBtn);
    }

    generateBtn.addEventListener('click', executeActualGeneration);
    regenerateBtn.addEventListener('click', () => {
        isRegeneratingFlowActive = true;
        analyzeBtn.click(); // Relancer le flux d'analyse, qui réappliquera la sélection
    });

    // --- Copy the generated context to the clipboard ---
    copyBtn.addEventListener('click', async () => {
        if (!markdownOutput.value) return;
        try {
            await navigator.clipboard.writeText(markdownOutput.value);
            copyBtn.innerHTML = '<i class="fas fa-check"></i> Copied!';
            copyBtn.classList.add('copied-feedback');
            copyBtn.disabled = true;
            setTimeout(() => {
                copyBtn.innerHTML = '<i class="far fa-copy"></i> Copy';
                copyBtn.classList.remove('copied-feedback');
                copyBtn.disabled = false;
            }, 1500);
        } catch (err) {
            console.error('Copy error:', err);
            alert('Error: Unable to copy to clipboard.');
        }
    });

    // --- Gestion des boutons d'instructions prédéfinies ---
    if (insertInstructionBtn1) {
        insertInstructionBtn1.addEventListener('click', () => {
            const newInstructionText = insertInstructionBtn1.dataset.instruction;
            const currentFullText = instructionsTextarea.value;
            const instruction1Data = insertInstructionBtn1.dataset.instruction;
            const instruction2Data = insertInstructionBtn2 ? insertInstructionBtn2.dataset.instruction : null;

            const textToInsert = "\n" + newInstructionText;

            if (currentFullText.trim() === "") {
                // Si vide, insérer simplement
                instructionsTextarea.value = textToInsert;
            } else if (instruction2Data && currentFullText.endsWith("\n" + instruction2Data)) {
                // Si le texte se termine par l'instruction 2, la remplacer par l'instruction 1
                const baseText = currentFullText.substring(0, currentFullText.length - ( "\n" + instruction2Data).length);
                instructionsTextarea.value = baseText + textToInsert;
            } else if (currentFullText.endsWith("\n" + instruction1Data)) {
                // Si le texte se termine déjà par l'instruction 1, la remplacer (pas de changement visible, mais correct)
                const baseText = currentFullText.substring(0, currentFullText.length - ( "\n" + instruction1Data).length);
                instructionsTextarea.value = baseText + textToInsert;
            } else {
                // Sinon, on ajoute
                instructionsTextarea.value += textToInsert;
            }
        });
    }

    if (insertInstructionBtn2) {
        insertInstructionBtn2.addEventListener('click', () => {
            const newInstructionText = insertInstructionBtn2.dataset.instruction;
            const currentFullText = instructionsTextarea.value;
            const instruction1Data = insertInstructionBtn1 ? insertInstructionBtn1.dataset.instruction : null;
            const instruction2Data = insertInstructionBtn2.dataset.instruction;

            const textToInsert = "\n" + newInstructionText;

            if (currentFullText.trim() === "") {
                // Si vide, insérer simplement
                instructionsTextarea.value = textToInsert;
            } else if (instruction1Data && currentFullText.endsWith("\n" + instruction1Data)) {
                // Si le texte se termine par l'instruction 1, la remplacer par l'instruction 2
                const baseText = currentFullText.substring(0, currentFullText.length - ( "\n" + instruction1Data).length);
                instructionsTextarea.value = baseText + textToInsert;
            } else if (currentFullText.endsWith("\n" + instruction2Data)) {
                // Si le texte se termine déjà par l'instruction 2, la remplacer (pas de changement visible, mais correct)
                const baseText = currentFullText.substring(0, currentFullText.length - ( "\n" + instruction2Data).length);
                instructionsTextarea.value = baseText + textToInsert;
            } else {
                // Sinon, on ajoute
                instructionsTextarea.value += textToInsert;
            }
        });
    }

    async function sendChatHistoryToLlm() {
        llmChatSpinner.classList.remove('visually-hidden');
        sendChatMessageBtn.disabled = true;
        chatMessageInput.disabled = true;
        chatMessageInput.style.backgroundColor = '#e9ecef';
        llmErrorChat.classList.add('visually-hidden');
        currentAssistantMessageDiv = null; // Réinitialiser pour le streaming

        try {
            const response = await fetch('/send_to_llm', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ messages: chatHistory }),
            });

            if (!response.ok) {
                // Gérer les erreurs HTTP non-2xx avant de tenter de lire le corps
                const errorData = await response.json().catch(() => ({ error: "Failed to parse error response", details: response.statusText }));
                const errorMsg = (errorData.error || "Unknown error") + 
                                 (errorData.details ? ` Détails: ${typeof errorData.details === 'object' ? JSON.stringify(errorData.details) : errorData.details}` : '');
                appendMessageToChat('system-error', `Erreur de l'assistant: ${errorMsg}`);
                llmErrorChat.textContent = errorMsg;
                llmErrorChat.classList.remove('visually-hidden');
                return; // Sortir après avoir géré l'erreur
            }
            
            if (isLlmStreamEnabled && response.headers.get("content-type")?.includes("text/event-stream")) {
                // Gestion du streaming
                currentAssistantMessageDiv = appendMessageToChat('assistant', ''); // Créer une bulle vide
                let accumulatedContent = "";

                const reader = response.body.getReader();
                const decoder = new TextDecoder();

                while (true) {
                    const { value, done } = await reader.read();
                    if (done) {
                        chatHistory.push({ role: 'assistant', content: accumulatedContent });
                        if (currentAssistantMessageDiv) {
                             // Stocker le contenu final brut pour le bouton copier
                            currentAssistantMessageDiv.dataset.finalRawContent = accumulatedContent;
                            // La mise à jour de innerHTML avec marked.parse se fera à chaque chunk
                        }
                        break;
                    }

                    const chunk = decoder.decode(value, { stream: true });
                    const lines = chunk.split('\\n\\n');
                    for (const line of lines) {
                        if (line.startsWith("data: ")) {
                            const jsonData = line.substring(5).trim();
                            if (jsonData) {
                                try {
                                    const parsedData = JSON.parse(jsonData);
                                    if (parsedData.type === 'content' && parsedData.content) {
                                        accumulatedContent += parsedData.content;
                                        // Mettre à jour la bulle avec le contenu Markdown parsé
                                        appendMessageToChat('assistant', accumulatedContent, currentAssistantMessageDiv);
                                    } else if (parsedData.type === 'done') {
                                        console.log("Stream: Done event received from server.");
                                        // La boucle while(true) sera rompue par le reader.read() done.
                                    } else if (parsedData.type === 'error') {
                                        console.error("Stream: Error event received:", parsedData.content);
                                        appendMessageToChat('system-error', `Erreur streamée: ${parsedData.content}`);
                                        // Peut-être arrêter le traitement ici ou afficher dans llmErrorChat aussi
                                    }
                                } catch (e) {
                                    console.error("Error parsing streamed JSON:", jsonData, e);
                                }
                            }
                        }
                    }
                }
            } else {
                // Gestion non-streamée (existante)
                const result = await response.json();
                if (result.response) { 
                    chatHistory.push({ role: 'assistant', content: result.response });
                    appendMessageToChat('assistant', result.response);
                } else if (result.error) { 
                    const errorMsg = result.error + (result.details ? ` Détails: ${typeof result.details === 'object' ? JSON.stringify(result.details) : result.details}` : '');
                    appendMessageToChat('system-error', `Erreur de l'assistant: ${errorMsg}`);
                    llmErrorChat.textContent = errorMsg;
                    llmErrorChat.classList.remove('visually-hidden');
                } else { // Réponse non-streamée inattendue
                    appendMessageToChat('system-error', `Réponse inattendue du serveur.`);
                    llmErrorChat.textContent = "Réponse inattendue du serveur.";
                    llmErrorChat.classList.remove('visually-hidden');
                }
            }

        } catch (error) {
            console.error("Error sending chat history to LLM:", error);
            appendMessageToChat('system-error', `Erreur lors de la communication avec l'assistant: ${error.message}`);
            llmErrorChat.textContent = "Erreur lors de la communication avec l'assistant. Veuillez réessayer plus tard.";
            llmErrorChat.classList.remove('visually-hidden');
        } finally {
            llmChatSpinner.classList.add('visually-hidden');
            sendChatMessageBtn.disabled = false;
            chatMessageInput.disabled = false;
            chatMessageInput.style.backgroundColor = '';
            currentAssistantMessageDiv = null; // Nettoyer après usage
        }
    }

    // --- Gestion des événements du Chat --- 

    function adjustTextareaHeight(textarea) {
        textarea.style.height = 'auto'; // Réinitialiser la hauteur
        textarea.style.height = (textarea.scrollHeight) + 'px'; // Ajuster à la hauteur du contenu
    }

    if (startLlmChatBtn) {
        startLlmChatBtn.addEventListener('click', async () => {
            if (window.pywebview) {
                // Mode Bureau
                console.log("Mode Bureau détecté. Appel de pywebview.api.launch_browser()");
                window.pywebview.api.launch_browser();
            } else {
                // Mode Web
                const initialContext = markdownOutput.value;
                const customInstructions = instructionsTextarea.value;

                if (!initialContext.trim()) {
                    // Utiliser showError pour une meilleure intégration UI
                    showError(llmErrorChat, "Le contexte Markdown est vide. Veuillez d'abord générer un contexte.", llmChatSpinner);
                    // alert('Le contexte Markdown est vide. Veuillez d'abord générer un contexte.');
                    return;
                }

                chatHistory = [];
                chatDisplayArea.innerHTML = '';
                hideError(llmErrorChat); // Cacher les erreurs précédentes

                let firstUserMessageContent = "Voici le contexte du projet sur lequel je souhaite discuter:\n\n" + initialContext;
                if (customInstructions.trim()) {
                    firstUserMessageContent += "\n\nInstructions spécifiques pour cette discussion:\n" + customInstructions;
                }

                chatHistory.push({ role: 'user', content: firstUserMessageContent });
                appendMessageToChat('user', "Contexte du projet et instructions initiales envoyés au LLM.");

                chatUiContainer.classList.remove('visually-hidden');
                startLlmChatBtn.classList.add('visually-hidden');

                await sendChatHistoryToLlm();
            }
        });
    }

    if (sendChatMessageBtn && chatMessageInput) {
        sendChatMessageBtn.addEventListener('click', () => {
            const userMessage = chatMessageInput.value.trim();
            if (userMessage) {
                chatHistory.push({ role: 'user', content: userMessage });
                appendMessageToChat('user', userMessage);
                chatMessageInput.value = '';
                adjustTextareaHeight(chatMessageInput);
                sendChatHistoryToLlm();
            }
        });

        chatMessageInput.addEventListener('keypress', (event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault(); 
                sendChatMessageBtn.click();
            }
        });
        
        chatMessageInput.addEventListener('input', () => adjustTextareaHeight(chatMessageInput));
        adjustTextareaHeight(chatMessageInput); // Ajuster initialement si du texte est déjà présent (peu probable ici)
    }

    // --- Logique pour le bouton "Ajouter Instruction Patch" ---
    if (appendPatchToChatBtn && chatMessageInput) {
        appendPatchToChatBtn.addEventListener('click', () => {
            const patchInstruction = appendPatchToChatBtn.dataset.instruction;
            if (patchInstruction) {
                const currentMessage = chatMessageInput.value;
                // Ajouter un saut de ligne si le message n'est pas vide et ne se termine pas déjà par un saut de ligne
                const prefix = currentMessage.trim() !== '' && !currentMessage.endsWith('\n') ? '\n' : '';
                chatMessageInput.value = currentMessage + prefix + patchInstruction;
                adjustTextareaHeight(chatMessageInput);
                chatMessageInput.focus(); // Remettre le focus sur le textarea
            }
        });
    }
    
    // Assurer que les références DOM pour le chat sont bien définies au début de DOMContentLoaded
    // const markdownOutput = document.getElementById('markdownOutput');
    // const instructionsTextarea = document.getElementById('instructionsTextarea');
    // const chatDisplayArea = document.getElementById('chatDisplayArea');
    // const chatMessageInput = document.getElementById('chatMessageInput');
    // const sendChatMessageBtn = document.getElementById('sendChatMessageBtn');
    // const startLlmChatBtn = document.getElementById('startLlmChatBtn');
    // const chatUiContainer = document.getElementById('chatUiContainer');
    // const llmErrorChat = document.getElementById('llm-error-chat'); // Déjà défini plus haut
    // const llmChatSpinner = document.getElementById('llm-chat-spinner'); // Déjà défini plus haut

    // --- Logique pour le pilotage du navigateur ---
    const launchSeleniumBtn = document.getElementById('launchSeleniumBtn');
    const launchPywebviewBtn = document.getElementById('launchPywebviewBtn');
    const attachBrowserBtn = document.getElementById('attachBrowserBtn');
    const sendContextBtn = document.getElementById('sendContextBtn');
    const llmDestinationSelector = document.getElementById('llm-destination-selector');
    const browserStatus = document.getElementById('browser-status');

    // Socket.IO listener pour les logs du navigateur
    socket.on('browser_log', (data) => {
        console.log(`[Browser Log] ${data.message}`);
        // Optionnellement, afficher dans une zone de log dédiée
    });

    // Gestionnaire pour le bouton Selenium (ancien launchBrowserBtn)
    if (launchSeleniumBtn) {
        launchSeleniumBtn.addEventListener('click', async () => {
            const llmType = llmDestinationSelector.value;
            try {
                const response = await fetch('/browser/launch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ llm_type: llmType })
                });
                const result = await response.json();
                console.log(result.message || result.error);
                if (response.ok) {
                    browserStatus.textContent = 'Launched, awaiting attachment';
                    browserStatus.className = 'badge bg-warning';
                }
            } catch (e) {
                console.error("Erreur lancement navigateur:", e);
            }
        });
    }

    // Gestionnaire pour le bouton pywebview
    if (launchPywebviewBtn) {
        launchPywebviewBtn.addEventListener('click', async () => {
            console.log("Lancement pywebview browser...");
            try {
                // Appeler la fonction Python pywebview
                if (window.pywebview && window.pywebview.api && window.pywebview.api.launch_pywebview_browser) {
                    await window.pywebview.api.launch_pywebview_browser();
                    
                    // Griser le bouton "Attach to browser" et mettre le statut à "Lancement en cours..."
                    if (attachBrowserBtn) attachBrowserBtn.disabled = true;
                    if (browserStatus) {
                        browserStatus.textContent = 'Lancement en cours...';
                        browserStatus.className = 'badge bg-info';
                    }
                } else {
                    console.error("API pywebview non disponible");
                    alert("Erreur : API pywebview non disponible");
                }
            } catch (e) {
                console.error("Erreur lancement pywebview:", e);
                alert("Erreur lors du lancement de pywebview : " + e.message);
            }
        });
    }

    attachBrowserBtn.addEventListener('click', async () => {
        try {
            const response = await fetch('/browser/attach', { method: 'POST' });
            const result = await response.json();
            console.log(result.message || result.error);
            if (response.ok) {
                browserStatus.textContent = 'Connected';
                browserStatus.className = 'badge bg-success';
                if (markdownOutput.value.trim() !== '') {
                    sendContextBtn.disabled = false;
                }
            } else {
                // Message d'erreur amélioré
                browserStatus.textContent = 'Connection failed';
                browserStatus.className = 'badge bg-danger';
                alert("Connection failed. Please ensure Chrome is running in debug mode on port 9222. You can use the 'Launch Browser' button to start it correctly.");
            }
        } catch (e) {
            console.error("Erreur attachement navigateur:", e);
            browserStatus.textContent = 'Communication error';
            browserStatus.className = 'badge bg-danger';
            alert("Communication error with the server while trying to attach.");
        }
    });

    // Mettre à jour la logique de génération pour activer le bouton d'envoi si le navigateur est déjà attaché
    // Dans la fonction `executeActualGeneration`, à la fin du `try` où le contexte est généré avec succès :
    // if (browserStatus.textContent === 'Connecté') {
    //     sendContextBtn.disabled = false;
    // }
    // Pour l'instant, nous le ferons manuellement via la console de test, mais c'est l'idée.

    sendContextBtn.addEventListener('click', async () => {
        const context = markdownOutput.value;
        if (!context.trim()) {
            alert("Le contexte est vide.");
            return;
        }

        
        console.log("Envoi du contexte au navigateur...");

        try {
            if (window.pywebview && window.pywebview.api && window.pywebview.api.send_context) {
                // Mode pywebview - appeler directement l'API Python
                const result = await window.pywebview.api.send_context(context);
                if (result && result.error) {
                    alert("Erreur : " + result.error);
                } else {
                    console.log("Contexte envoyé avec succès via pywebview");
                }
            } else {
                // Mode web classique - utiliser l'API REST
                const llmType = llmDestinationSelector.value;
                const response = await fetch('/browser/send_context', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ context: context, llm_type: llmType })
                });
                const result = await response.json();
                console.log(result.message || result.error);
                if (result.error) {
                    alert("Erreur : " + result.error);
                }
            }
        } catch (e) {
            console.error("Erreur lors de l'envoi du contexte:", e);
            alert("Erreur lors de l'envoi du contexte : " + e.message);
        } finally {
            // On le laisse désactivé pour éviter les double-clics,
            // l'utilisateur peut le réactiver en relançant si besoin.
            // Pour une meilleure UX, on pourrait le réactiver après un délai.
        }
    });

}); // Fin de DOMContentLoaded

// --- Fonction de callback globale pour pywebview ---
window.onBrowserConnected = function() {
    console.log("Callback onBrowserConnected appelée depuis Python");
    const browserStatus = document.getElementById('browser-status');
    const launchSeleniumBtn = document.getElementById('launchSeleniumBtn');
    const launchPywebviewBtn = document.getElementById('launchPywebviewBtn');
    const sendContextBtn = document.getElementById('sendContextBtn');
    const markdownOutput = document.getElementById('markdownOutput');
    
    if (browserStatus) {
        browserStatus.textContent = 'Connecté (pywebview)';
        browserStatus.className = 'badge bg-success';
    }
    
    // Griser les deux boutons de lancement pour éviter les lancements multiples
    if (launchSeleniumBtn) launchSeleniumBtn.disabled = true;
    if (launchPywebviewBtn) launchPywebviewBtn.disabled = true;
    
    // Activer le bouton Send Context si du contexte est disponible
    if (sendContextBtn && markdownOutput && markdownOutput.value.trim() !== '') {
        sendContextBtn.disabled = false;
    }
};