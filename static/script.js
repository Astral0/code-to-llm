// static/script.js

document.addEventListener('DOMContentLoaded', () => {
    // Lire l'état du streaming depuis l'attribut data du body
    const isLlmStreamEnabled = document.body.dataset.llmStreamEnabled === 'true';
    
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

    const fileSelectionSection = document.getElementById('file-selection-section');
    const fileListDiv = document.getElementById('fileList');
    const selectAllBtn = document.getElementById('selectAllBtn');
    const deselectAllBtn = document.getElementById('deselectAllBtn');

    const generationSection = document.getElementById('generation-section');
    const generateBtn = document.getElementById('generateBtn');
    const generateSpinner = document.getElementById('generate-spinner');
    const generateError = document.getElementById('generate-error');
    const enableSecretMaskingCheckbox = document.getElementById('enableSecretMasking');

    const resultAndChatArea = document.getElementById('resultAndChatArea');
    const markdownOutput = document.getElementById('markdownOutput');
    const summaryContainer = document.getElementById('summaryContainer');
    const copyBtn = document.getElementById('copyBtn');

    const llmErrorChat = document.getElementById('llm-error-chat');
    const llmChatSpinner = document.getElementById('llm-chat-spinner');

    // --- State variables ---
    let currentFilesData = []; // Will store uploaded files (object with name, full relative path and content)
    let includedFilePaths = []; // Will store only the included file paths (not ignored by gitignore)
    let selectionToPreserveForRegeneration = new Set();
    let isRegeneratingFlowActive = false;

    let chatHistory = []; // Stocke l'historique : [{role: 'user'/'assistant', content: '...'}, ...]
    let currentAssistantMessageDiv = null; // Pour le streaming

    // --- Utility functions ---
    function showElement(element) { element?.classList.remove('visually-hidden'); }
    function hideElement(element) { element?.classList.add('visually-hidden'); }
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

    // --- Directory analysis (upload of selected files) ---
    analyzeBtn.addEventListener('click', async () => {
        const files = directoryPicker.files;
        if (!files || files.length === 0) {
            showError(analyzeError, "Please select a directory.", analyzeStatusContainer);
            return;
        }
        hideError(analyzeError);
        showSpinner(analyzeSpinner);
        hideElement(fileSelectionSection);
        hideElement(generationSection);
        hideElement(resultAndChatArea);
        fileListDiv.innerHTML = '<p class="text-muted text-center placeholder-message">Analyzing...</p>';
        currentFilesData = [];
        includedFilePaths = [];

        // Réinitialiser l'état des boutons de génération/régénération
        showElement(generateBtn);
        hideElement(regenerateBtn);

        // Read all files using FileReader and retrieve their full relative path
        const readFilePromises = [];
        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            readFilePromises.push(new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => {
                    resolve({
                        name: file.name,
                        // webkitRelativePath contains the full relative path from the selected directory
                        path: file.webkitRelativePath || file.name,
                        content: reader.result
                    });
                };
                reader.onerror = () => {
                    console.log(`[DEBUG] FileReader.onerror triggered for ${file.name}`);
                    console.error(`FileReader error for ${file.name}:`, reader.error);
                    reject(new Error(`Error reading file ${file.name}. See console for details.`));
                };
                reader.readAsText(file);
            }));
        }

        try {
            const uploadedFiles = await Promise.all(readFilePromises);
            currentFilesData = uploadedFiles;
            // Send the uploaded data to the server to build the file tree and apply .gitignore rules
            const response = await fetch('/upload', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
                body: JSON.stringify({ files: uploadedFiles })
            });
            const data = await response.json();
            if (!response.ok || !data.success) {
                throw new Error(data.error || `Error ${response.status}`);
            }
            
            // Store the list of included file paths (not ignored)
            includedFilePaths = data.files.map(f => f.path);
            
            // Render the file tree
            renderFileList(data.files);
            
            hideError(analyzeError); // Clear any instruction/error message from analyze step

            if (isRegeneratingFlowActive) {
                // Re-apply preserved selection
                fileListDiv.querySelectorAll('.form-check-input').forEach(checkbox => {
                    if (selectionToPreserveForRegeneration.has(checkbox.value)) {
                        checkbox.checked = true;
                    } else {
                        checkbox.checked = false; // Ensure others are unchecked
                    }
                });
                selectionToPreserveForRegeneration = new Set(); // Clear after use
                isRegeneratingFlowActive = false; // Reset flag

                showElement(fileSelectionSection);
                showElement(generationSection);
                await executeActualGeneration(); // Automatically generate context
            } else {
                // Normal analysis flow: select all by default (or existing logic)
                // Ensure all files are checked by default in the new tree
                selectAllBtn.click(); // Simulate click to check all new files
                showElement(fileSelectionSection);
                showElement(generationSection);
            }

            // Faire défiler vers la section de génération une fois l'analyse terminée
            if (generationSection.classList.contains('visually-hidden') === false) {
                generationSection.scrollIntoView({ behavior: 'smooth' });
            }
        } catch (error) {
            console.error("Analysis error:", error);
            showError(analyzeError, `Analysis error: ${error.message}`, analyzeStatusContainer);
            fileListDiv.innerHTML = '<p class="text-danger text-center placeholder-message">Analysis failed.</p>';
            showElement(fileSelectionSection);
        } finally {
            hideSpinner(analyzeSpinner);
        }
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
            if (parentLi && parentLi.classList.contains('folder')) {
                const childCheckboxes = parentLi.querySelectorAll('ul .form-check-input');
                childCheckboxes.forEach(child => {
                    child.checked = isChecked;
                });
            }
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
            "Estimated tokens (approximate)": summary.total_tokens
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

    // --- Generate context ---
    async function executeActualGeneration() {
        const selectedCheckboxes = fileListDiv.querySelectorAll('.form-check-input:checked');
        const selectedFiles = Array.from(selectedCheckboxes).map(cb => cb.value);

        if (selectedFiles.length === 0) {
            showError(generateError, "No files selected for context generation.", generationSection);
            return;
        }
        hideError(generateError);
        showSpinner(generateSpinner);
        hideElement(resultAndChatArea);

        // Préserver la sélection pour une éventuelle régénération
        selectionToPreserveForRegeneration = new Set(selectedFiles);

        // Récupérer les options de masquage
        const enableMasking = enableSecretMaskingCheckbox.checked;
        // Pour l'instant, on ne propose pas de changer le mask_mode via UI, donc on utilise le défaut du serveur.
        const maskingOptions = { enable_masking: enableMasking, mask_mode: "mask" }; 

        // Récupérer les instructions
        const instructions = instructionsTextarea.value;

        try {
            const response = await fetch('/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    selected_files: selectedFiles, 
                    masking_options: maskingOptions,
                    instructions: instructions
                })
            });
            const result = await response.json();
            if (!response.ok || !result.success) {
                throw new Error(result.error || `Error ${response.status}`);
            }
            markdownOutput.value = result.markdown;
            displaySummary(result.summary);
            displaySecretsAlert(result.summary.secrets_masked, result.summary.files_with_secrets); 
            
            showElement(resultAndChatArea);
            showElement(regenerateBtn);
            hideElement(generateBtn);

            // Logique pour afficher/cacher les éléments de chat après génération
            // Ces éléments sont définis dans index.html, mais nous les contrôlons ici aussi
            const llmInteractionContainer = document.getElementById('llmInteractionContainer');
            const startLlmChatBtn = document.getElementById('startLlmChatBtn');
            const chatUiContainer = document.getElementById('chatUiContainer');

            if (llmInteractionContainer) showElement(llmInteractionContainer);
            if (startLlmChatBtn) showElement(startLlmChatBtn);
            if (chatUiContainer) hideElement(chatUiContainer); // Cacher l'UI de chat si on (re)génère
            
            // Scroll to the result area
            resultAndChatArea.scrollIntoView({ behavior: 'smooth' });

        } catch (error) {
            console.error("Generation error:", error);
            showError(generateError, `Generation error: ${error.message}`, generationSection);
        } finally {
            hideSpinner(generateSpinner);
        }
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

}); // Fin de DOMContentLoaded