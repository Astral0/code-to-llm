// static/toolbox.js

document.addEventListener('DOMContentLoaded', () => {
    // Éléments DOM
    const importContextBtn = document.getElementById('importContextBtn');
    const contextStatus = document.getElementById('contextStatus');
    const promptButtonsContainer = document.getElementById('promptButtonsContainer');
    const gitDiffBtn = document.getElementById('gitDiffBtn');
    const chatDisplayArea = document.getElementById('chatDisplayArea');
    const chatMessageInput = document.getElementById('chatMessageInput');
    const sendChatMessageBtn = document.getElementById('sendChatMessageBtn');
    const clearChatBtn = document.getElementById('clearChatBtn');
    const exportChatBtn = document.getElementById('exportChatBtn');
    const llmErrorChat = document.getElementById('llm-error-chat');
    const llmChatSpinner = document.getElementById('llm-chat-spinner');
    const tokenCountSpan = document.getElementById('chat-token-count');

    // État de l'application
    let mainContext = '';
    let activePrompts = new Set();
    let chatHistory = [];
    let isStreamEnabled = false;
    let smartScrollController = null; // Contrôleur pour le défilement intelligent
    let conversationSummary = ''; // Stocke le résumé formaté du contexte
    
    // Fonction pour activer/désactiver les boutons selon le contexte
    function updateButtonStates() {
        const hasContext = mainContext && mainContext.trim() !== '';
        
        // Mettre à jour les boutons de prompts
        document.querySelectorAll('.prompt-button').forEach(button => {
            button.disabled = !hasContext;
            button.title = hasContext ? '' : "Veuillez d'abord importer le contexte du projet";
        });
        
        // Mettre à jour le bouton git diff
        if (gitDiffBtn) {
            gitDiffBtn.disabled = !hasContext;
            gitDiffBtn.title = hasContext ? '' : "Veuillez d'abord importer le contexte du projet";
        }
    }

    // Vérifier si le streaming est activé
    async function checkStreamingStatus() {
        if (window.pywebview && window.pywebview.api) {
            try {
                isStreamEnabled = await window.pywebview.api.get_stream_status();
                console.log('Streaming activé:', isStreamEnabled);
            } catch (error) {
                console.error('Erreur lors de la récupération du statut de streaming:', error);
                isStreamEnabled = false;
            }
        }
    }
    
    // Appeler la fonction au chargement
    checkStreamingStatus();

    // Initialiser le défilement intelligent
    if (chatDisplayArea && window.ChatUtils && window.ChatUtils.SmartScroll) {
        smartScrollController = window.ChatUtils.SmartScroll.init(chatDisplayArea, {
            tolerance: 50,
            debug: true // Activer les logs pour le debug
        });
    } else {
        console.warn('ChatUtils.SmartScroll non disponible ou chatDisplayArea non trouvé');
    }

    // Fonction wrapper pour la compatibilité
    function autoScrollToBottom() {
        if (smartScrollController) {
            smartScrollController.scrollToBottom();
        } else {
            // Fallback si le module n'est pas chargé
            chatDisplayArea.scrollTop = chatDisplayArea.scrollHeight;
        }
    }

    // Fonction pour afficher les erreurs
    function showError(element, message) {
        element.textContent = message;
        element.classList.remove('d-none');
    }

    // Fonction pour cacher les erreurs
    function hideError(element) {
        element.classList.add('d-none');
        element.textContent = '';
    }

    // Fonction pour ajouter un message au chat
    function appendMessageToChat(role, content, existingDiv = null, messageIndex = null) {
        if (existingDiv) {
            // Mise à jour d'un message existant (pour le streaming)
            const contentDiv = existingDiv.querySelector('.message-content');
            contentDiv.textContent = content;
            contentDiv.dataset.rawContent = content;
            contentDiv.dataset.markdownContent = marked.parse(content);
            autoScrollToBottom();
            return existingDiv;
        }

        const messageWrapper = document.createElement('div');
        messageWrapper.className = 'message-wrapper';
        
        const messageDiv = document.createElement('div');
        messageDiv.className = `message-bubble ${role}`;
        messageDiv.style.position = 'relative';
        
        // Créer un conteneur pour le contenu
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.style.whiteSpace = 'pre-wrap'; // Préserver les sauts de ligne
        contentDiv.style.wordBreak = 'break-word';
        
        // Stocker les deux versions du contenu
        contentDiv.dataset.rawContent = content;
        contentDiv.dataset.markdownContent = marked.parse(content);
        contentDiv.dataset.isMarkdown = 'true'; // Markdown par défaut
        
        // Afficher en markdown par défaut
        contentDiv.innerHTML = contentDiv.dataset.markdownContent;
        contentDiv.style.whiteSpace = 'normal';
        
        messageDiv.appendChild(contentDiv);
        
        // Stocker l'index du message si fourni
        if (messageIndex !== null && role === 'user') {
            messageDiv.dataset.messageIndex = messageIndex;
        }
        
        // Ajouter les boutons de contrôle pour user et assistant
        if (role === 'user' || role === 'assistant') {
            // Fonction pour créer un ensemble de boutons
            const createButtons = () => {
                const buttonsContainer = document.createElement('div');
                buttonsContainer.style.cssText = 'display: flex; gap: 5px;';
                
                // Pour les messages utilisateur, ajouter un bouton d'édition
                if (role === 'user') {
                    const editBtn = document.createElement('button');
                    editBtn.className = 'btn btn-sm btn-outline-secondary edit-btn';
                    editBtn.innerHTML = '<i class="fas fa-edit"></i>';
                    editBtn.title = 'Éditer ce message';
                    editBtn.style.cssText = 'opacity: 0.7; padding: 2px 6px; font-size: 12px;';
                    
                    editBtn.addEventListener('click', () => {
                        editUserMessage(messageDiv, contentDiv);
                    });
                    
                    buttonsContainer.appendChild(editBtn);
                }
                
                // Bouton toggle markdown
                const toggleBtn = document.createElement('button');
                toggleBtn.className = 'btn btn-sm btn-outline-secondary toggle-markdown-btn';
                toggleBtn.innerHTML = '<i class="fas fa-align-left"></i>'; // Icône initiale pour markdown
                toggleBtn.title = 'Afficher en texte brut';
                toggleBtn.style.cssText = 'opacity: 0.7; padding: 2px 6px; font-size: 12px;';
                
                toggleBtn.addEventListener('click', () => {
                    const isMarkdown = contentDiv.dataset.isMarkdown === 'true';
                    const allToggleBtns = messageDiv.querySelectorAll('.toggle-markdown-btn');
                    const allCopyBtns = messageDiv.querySelectorAll('.copy-btn');
                    
                    if (isMarkdown) {
                        // Passer en texte brut
                        contentDiv.textContent = contentDiv.dataset.rawContent;
                        contentDiv.style.whiteSpace = 'pre-wrap';
                        contentDiv.dataset.isMarkdown = 'false';
                        allToggleBtns.forEach(btn => {
                            btn.innerHTML = '<i class="fas fa-code"></i>';
                            btn.title = 'Afficher en Markdown';
                        });
                    } else {
                        // Passer en markdown
                        contentDiv.innerHTML = contentDiv.dataset.markdownContent;
                        contentDiv.style.whiteSpace = 'normal';
                        contentDiv.dataset.isMarkdown = 'true';
                        allToggleBtns.forEach(btn => {
                            btn.innerHTML = '<i class="fas fa-align-left"></i>';
                            btn.title = 'Afficher en texte brut';
                        });
                        // Ré-ajouter les boutons de copie après le changement en markdown
                        if (messageDiv.closest('.chat-assistant')) {
                            addCodeCopyButtons(contentDiv);
                        }
                    }
                });
                
                buttonsContainer.appendChild(toggleBtn);
                
                // Bouton de copie (pour tous maintenant)
                const copyBtn = document.createElement('button');
                copyBtn.className = 'btn btn-sm btn-outline-secondary copy-btn';
                copyBtn.innerHTML = '<i class="far fa-copy"></i>';
                copyBtn.title = 'Copier le contenu';
                copyBtn.style.cssText = 'opacity: 0.7; padding: 2px 6px; font-size: 12px;';
                
                copyBtn.addEventListener('click', () => {
                    // Copier selon le format actuel
                    const isMarkdown = contentDiv.dataset.isMarkdown === 'true';
                    let textToCopy;
                    
                    if (isMarkdown) {
                        // Copier le texte visible (HTML converti en texte)
                        const tempDiv = document.createElement('div');
                        tempDiv.innerHTML = contentDiv.innerHTML;
                        textToCopy = tempDiv.textContent || tempDiv.innerText || '';
                    } else {
                        // Copier le texte brut
                        textToCopy = contentDiv.dataset.rawContent;
                    }
                    
                    navigator.clipboard.writeText(textToCopy).then(() => {
                        const allCopyBtns = messageDiv.querySelectorAll('.copy-btn');
                        allCopyBtns.forEach(btn => {
                            btn.innerHTML = '<i class="fas fa-check"></i>';
                        });
                        setTimeout(() => {
                            allCopyBtns.forEach(btn => {
                                btn.innerHTML = '<i class="far fa-copy"></i>';
                            });
                        }, 2000);
                    }).catch(err => {
                        console.error('Erreur lors de la copie:', err);
                    });
                });
                
                buttonsContainer.appendChild(copyBtn);
                return buttonsContainer;
            };
            
            // Créer les boutons en bas seulement
            const buttonsBottom = createButtons();
            buttonsBottom.className = 'buttons-bottom';
            messageDiv.appendChild(buttonsBottom);
        } else {
            // Pour system et system-error, afficher en markdown par défaut
            contentDiv.innerHTML = contentDiv.dataset.markdownContent;
            contentDiv.dataset.isMarkdown = 'true';
        }
        
        messageWrapper.appendChild(messageDiv);
        chatDisplayArea.appendChild(messageWrapper);
        chatDisplayArea.scrollTop = chatDisplayArea.scrollHeight;
        
        // Ajouter les boutons de copie aux blocs de code si c'est un message assistant
        if (role === 'assistant') {
            addCodeCopyButtons(contentDiv);
        }
        
        return messageDiv;
    }

    // Fonction pour ajouter des boutons de copie à tous les blocs de code
    function addCodeCopyButtons(container) {
        // Trouver tous les éléments <pre> qui contiennent des blocs de code
        const codeBlocks = container.querySelectorAll('pre');
        
        codeBlocks.forEach((preElement, index) => {
            // Vérifier si un bouton n'a pas déjà été ajouté
            if (preElement.querySelector('.code-copy-btn')) {
                return;
            }
            
            // S'assurer que le pre a la position relative
            if (!preElement.style.position || preElement.style.position === 'static') {
                preElement.style.position = 'relative';
            }
            
            // Créer le bouton de copie
            const copyBtn = document.createElement('button');
            copyBtn.className = 'code-copy-btn';
            copyBtn.innerHTML = '<i class="far fa-copy"></i> Copier';
            copyBtn.title = 'Copier le code';
            
            // Gestionnaire de clic
            copyBtn.addEventListener('click', async () => {
                // Récupérer le texte du code
                const codeElement = preElement.querySelector('code') || preElement;
                const codeText = codeElement.textContent || codeElement.innerText;
                
                try {
                    await navigator.clipboard.writeText(codeText);
                    
                    // Feedback visuel
                    copyBtn.innerHTML = '<i class="fas fa-check"></i> Copié !';
                    copyBtn.classList.add('copied');
                    
                    // Restaurer après 2 secondes
                    setTimeout(() => {
                        copyBtn.innerHTML = '<i class="far fa-copy"></i> Copier';
                        copyBtn.classList.remove('copied');
                    }, 2000);
                } catch (err) {
                    console.error('Erreur lors de la copie:', err);
                    copyBtn.innerHTML = '<i class="fas fa-times"></i> Erreur';
                    setTimeout(() => {
                        copyBtn.innerHTML = '<i class="far fa-copy"></i> Copier';
                    }, 2000);
                }
            });
            
            // Ajouter le bouton au bloc de code
            preElement.appendChild(copyBtn);
        });
    }

    // Fonction pour éditer un message utilisateur
    function editUserMessage(messageDiv, contentDiv) {
        // Récupérer le contenu actuel
        const currentContent = contentDiv.dataset.rawContent;
        
        // Créer un textarea pour l'édition
        const editTextarea = document.createElement('textarea');
        editTextarea.className = 'form-control';
        editTextarea.value = currentContent;
        editTextarea.style.cssText = 'width: 100%; min-height: 100px; margin-bottom: 10px;';
        
        // Créer les boutons de validation/annulation
        const editControls = document.createElement('div');
        editControls.style.cssText = 'display: flex; gap: 10px; margin-bottom: 10px;';
        
        const saveBtn = document.createElement('button');
        saveBtn.className = 'btn btn-sm btn-success';
        saveBtn.innerHTML = '<i class="fas fa-check"></i> Valider';
        
        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'btn btn-sm btn-secondary';
        cancelBtn.innerHTML = '<i class="fas fa-times"></i> Annuler';
        
        editControls.appendChild(saveBtn);
        editControls.appendChild(cancelBtn);
        
        // Cacher le contenu actuel et les boutons
        contentDiv.style.display = 'none';
        const buttonsBottom = messageDiv.querySelector('.buttons-bottom');
        if (buttonsBottom) buttonsBottom.style.display = 'none';
        
        // Ajouter le textarea et les contrôles
        messageDiv.appendChild(editTextarea);
        messageDiv.appendChild(editControls);
        
        // Focus sur le textarea
        editTextarea.focus();
        adjustTextareaHeight(editTextarea);
        
        // Gestion de l'annulation
        cancelBtn.addEventListener('click', () => {
            editTextarea.remove();
            editControls.remove();
            contentDiv.style.display = '';
            if (buttonsBottom) buttonsBottom.style.display = '';
        });
        
        // Gestion de la sauvegarde
        saveBtn.addEventListener('click', () => {
            const newContent = editTextarea.value.trim();
            if (!newContent) {
                alert('Le message ne peut pas être vide');
                return;
            }
            
            // Trouver l'index du message dans l'historique
            const messageWrapper = messageDiv.closest('.message-wrapper');
            const allMessages = chatDisplayArea.querySelectorAll('.message-wrapper');
            let messageIndex = -1;
            
            for (let i = 0; i < allMessages.length; i++) {
                if (allMessages[i] === messageWrapper) {
                    // Compter uniquement les messages user et assistant avant celui-ci
                    let historyIndex = 0;
                    for (let j = 0; j < i; j++) {
                        const msgBubble = allMessages[j].querySelector('.message-bubble');
                        if (msgBubble && (msgBubble.classList.contains('user') || msgBubble.classList.contains('assistant'))) {
                            historyIndex++;
                        }
                    }
                    messageIndex = historyIndex;
                    break;
                }
            }
            
            if (messageIndex === -1) {
                alert('Erreur: impossible de trouver le message dans l\'historique');
                return;
            }
            
            // Supprimer tous les messages après celui-ci
            let nextMessage = messageWrapper.nextElementSibling;
            while (nextMessage) {
                const toRemove = nextMessage;
                nextMessage = nextMessage.nextElementSibling;
                toRemove.remove();
            }
            
            // Tronquer l'historique du chat
            chatHistory = chatHistory.slice(0, messageIndex + 1);
            
            // Mettre à jour le contenu du message dans l'historique
            chatHistory[messageIndex].content = newContent;
            
            // Pour l'affichage, on garde le nouveau contenu sans le contexte
            contentDiv.dataset.rawContent = newContent;
            contentDiv.dataset.markdownContent = marked.parse(newContent);
            
            // Restaurer l'affichage
            if (contentDiv.dataset.isMarkdown === 'true') {
                contentDiv.innerHTML = contentDiv.dataset.markdownContent;
            } else {
                contentDiv.textContent = newContent;
            }
            
            editTextarea.remove();
            editControls.remove();
            contentDiv.style.display = '';
            if (buttonsBottom) buttonsBottom.style.display = '';
            
            // Relancer automatiquement l'envoi au LLM
            setTimeout(() => {
                sendEditedMessage(newContent);
            }, 100);
        });
        
        // Ajuster la hauteur du textarea lors de la saisie
        editTextarea.addEventListener('input', () => adjustTextareaHeight(editTextarea));
    }
    
    // Fonction pour envoyer un message édité au LLM
    async function sendEditedMessage(editedContent) {
        hideError(llmErrorChat);
        
        // Afficher le spinner
        llmChatSpinner.classList.remove('d-none');
        
        try {
            // Préparer l'historique complet
            let historyToSend = [...chatHistory];
            
            // S'assurer que le contexte est inclus dans le premier message s'il existe
            if (historyToSend.length > 0 && mainContext) {
                const firstMessage = historyToSend[0].content;
                const contextPrefix = 'Voici le contexte du projet sur lequel je souhaite discuter:';
                
                // Toujours ajouter le contexte au premier message pour l'envoi
                historyToSend[0] = {
                    role: 'user',
                    content: `${contextPrefix}\n\n${mainContext}\n\n${firstMessage}`
                };
            }
            
            console.log('Envoi de l\'historique édité avec', historyToSend.length, 'messages');
            
            if (window.pywebview && window.pywebview.api) {
                if (isStreamEnabled) {
                    // Mode streaming
                    const callbackId = 'stream_' + Date.now();
                    let streamingDiv = null;
                    let streamContent = '';
                    
                    // Définir les callbacks pour le streaming
                    window.onStreamStart = (id) => {
                        if (id === callbackId) {
                            streamingDiv = appendMessageToChat('assistant', '', null, chatHistory.length);
                        }
                    };
                    
                    window.onStreamChunk = (id, chunk) => {
                        if (id === callbackId && streamingDiv) {
                            streamContent += chunk;
                            appendMessageToChat('assistant', streamContent, streamingDiv);
                        }
                    };
                    
                    window.onStreamEnd = (id, total_tokens) => {
                        if (id === callbackId) {
                            // Ajouter à l'historique
                            chatHistory.push({ role: 'assistant', content: streamContent });
                            
                            // Mettre à jour le compteur de tokens
                            if (total_tokens && tokenCountSpan) {
                                tokenCountSpan.textContent = total_tokens.toLocaleString();
                            }
                            
                            // Nettoyage
                            delete window.onStreamStart;
                            delete window.onStreamChunk;
                            delete window.onStreamEnd;
                            delete window.onStreamError;
                        }
                    };
                    
                    window.onStreamError = (id, error) => {
                        if (id === callbackId) {
                            showError(llmErrorChat, error);
                            appendMessageToChat('system-error', `Erreur: ${error}`);
                            // Nettoyage
                            delete window.onStreamStart;
                            delete window.onStreamChunk;
                            delete window.onStreamEnd;
                            delete window.onStreamError;
                        }
                    };
                    
                    // Lancer le streaming
                    const response = await window.pywebview.api.send_to_llm_stream(historyToSend, callbackId);
                    
                    if (response.error) {
                        showError(llmErrorChat, response.error);
                        appendMessageToChat('system-error', `Erreur: ${response.error}`);
                    }
                } else {
                    // Mode normal
                    const response = await window.pywebview.api.send_to_llm(historyToSend, false);
                    
                    if (response.error) {
                        showError(llmErrorChat, response.error);
                        appendMessageToChat('system-error', `Erreur: ${response.error}`);
                    } else if (response.response) {
                        chatHistory.push({ role: 'assistant', content: response.response });
                        appendMessageToChat('assistant', response.response, null, chatHistory.length - 1);
                        
                        // Mettre à jour le compteur de tokens
                        if (response.total_tokens && tokenCountSpan) {
                            tokenCountSpan.textContent = response.total_tokens.toLocaleString();
                        }
                    }
                }
            } else {
                showError(llmErrorChat, 'API non disponible.');
            }
        } catch (error) {
            console.error('Erreur lors de l\'envoi du message édité:', error);
            showError(llmErrorChat, 'Erreur lors de la communication avec l\'assistant.');
            appendMessageToChat('system-error', 'Erreur lors de la communication avec l\'assistant.');
        } finally {
            llmChatSpinner.classList.add('d-none');
        }
    }
    
    // Charger les prompts disponibles
    async function loadAvailablePrompts() {
        try {
            console.log('loadAvailablePrompts called');
            console.log('window.pywebview exists?', !!window.pywebview);
            console.log('window.pywebview.api exists?', !!(window.pywebview && window.pywebview.api));
            
            if (window.pywebview && window.pywebview.api) {
                console.log('Calling get_available_prompts...');
                const prompts = await window.pywebview.api.get_available_prompts();
                console.log('Prompts received:', prompts);
                
                promptButtonsContainer.innerHTML = '';
                
                prompts.forEach((prompt, index) => {
                    const button = document.createElement('button');
                    button.className = 'btn btn-outline-primary prompt-button';
                    button.dataset.promptFile = prompt.filename;
                    button.innerHTML = `<i class="fas fa-file-alt"></i> ${prompt.name}`;
                    
                    // Désactiver le bouton si pas de contexte
                    if (!mainContext || mainContext.trim() === '') {
                        button.disabled = true;
                        button.title = "Veuillez d'abord importer le contexte du projet";
                    }
                    
                    button.addEventListener('click', () => togglePrompt(button));
                    
                    promptButtonsContainer.appendChild(button);
                });
            } else {
                console.log('PyWebView API not available yet');
            }
        } catch (error) {
            console.error('Erreur lors du chargement des prompts:', error);
            showError(llmErrorChat, 'Erreur lors du chargement des prompts.');
        }
    }

    // Gérer le toggle des prompts
    async function togglePrompt(button) {
        const promptFile = button.dataset.promptFile;
        
        if (activePrompts.has(promptFile)) {
            // Désactiver le prompt
            activePrompts.delete(promptFile);
            button.classList.remove('active');
        } else {
            // Activer le prompt
            activePrompts.add(promptFile);
            button.classList.add('active');
            
            try {
                if (window.pywebview && window.pywebview.api) {
                    // Vérifier si c'est un prompt qui nécessite git diff
                    if (promptFile.endsWith('_diff.md')) {
                        // Exécuter git diff d'abord
                        console.log('Prompt nécessite git diff, exécution...');
                        const diffResult = await window.pywebview.api.run_git_diff();
                        
                        if (diffResult.error) {
                            showError(llmErrorChat, diffResult.error);
                            // Désactiver le bouton
                            activePrompts.delete(promptFile);
                            button.classList.remove('active');
                            return;
                        }
                        
                        if (!diffResult.diff || diffResult.diff.trim() === '') {
                            appendMessageToChat('system', 'Aucune modification détectée (git diff HEAD est vide).');
                            // Désactiver le bouton
                            activePrompts.delete(promptFile);
                            button.classList.remove('active');
                            return;
                        }
                        
                        // Charger le contenu du prompt
                        const promptContent = await window.pywebview.api.get_prompt_content(promptFile);
                        
                        // Pour revue_de_diff, mettre le prompt APRÈS le diff
                        const fullMessage = `## Diff des modifications :\n\n\`\`\`diff\n${diffResult.diff}\n\`\`\`\n\n---\n\n${promptContent}`;
                        
                        chatMessageInput.value = fullMessage;
                    } else {
                        // Prompt normal sans git diff
                        const content = await window.pywebview.api.get_prompt_content(promptFile);
                        const currentText = chatMessageInput.value;
                        
                        // Ajouter le prompt avec une séparation claire
                        if (currentText.trim()) {
                            chatMessageInput.value = currentText + '\n\n---\n\n' + content;
                        } else {
                            chatMessageInput.value = content;
                        }
                    }
                    
                    adjustTextareaHeight(chatMessageInput);
                    
                    // Scroll à la fin du textarea
                    chatMessageInput.scrollTop = chatMessageInput.scrollHeight;
                    chatMessageInput.focus();
                    chatMessageInput.setSelectionRange(chatMessageInput.value.length, chatMessageInput.value.length);
                }
            } catch (error) {
                console.error('Erreur lors du chargement du prompt:', error);
                showError(llmErrorChat, 'Erreur lors du chargement du prompt.');
            }
        }
    }

    // Importer le contexte du projet principal
    importContextBtn.addEventListener('click', async () => {
        try {
            if (window.pywebview && window.pywebview.api) {
                mainContext = await window.pywebview.api.get_main_context();
                
                if (mainContext && mainContext.trim()) {
                    contextStatus.classList.remove('no-context');
                    contextStatus.innerHTML = '<i class="fas fa-check-circle text-success"></i> Contexte importé avec succès';
                    
                    // Afficher un aperçu du contexte
                    const contextLength = mainContext.length;
                    const contextLines = mainContext.split('\n').length;
                    const contextPreview = mainContext.substring(0, 200) + '...';
                    
                    // Créer et stocker le résumé formaté
                    conversationSummary = `## Contexte du Projet

**Statistiques :**
- Taille : ${contextLength.toLocaleString()} caractères
- Lignes : ${contextLines.toLocaleString()}

**Aperçu :**
\`\`\`
${contextPreview}
\`\`\`

Le contexte contient le code source et la structure du projet pour permettre l'analyse et les modifications.`;
                    
                    // Ajouter un message système dans le chat
                    appendMessageToChat('system', `Le contexte du projet a été importé avec succès !\n\n${conversationSummary}\n\nLe contexte est maintenant disponible pour l'analyse. Vous pouvez utiliser les prompts ou poser vos questions.`);
                    
                    // Activer les boutons maintenant que le contexte est chargé
                    updateButtonStates();
                } else {
                    showError(llmErrorChat, 'Aucun contexte disponible. Veuillez d\'abord générer un contexte depuis la fenêtre principale.');
                }
            }
        } catch (error) {
            console.error('Erreur lors de l\'import du contexte:', error);
            showError(llmErrorChat, 'Erreur lors de l\'import du contexte.');
        }
    });

    // Gérer l'analyse git diff
    gitDiffBtn.addEventListener('click', async () => {
        try {
            hideError(llmErrorChat);
            
            if (window.pywebview && window.pywebview.api) {
                const diffResult = await window.pywebview.api.run_git_diff();
                
                if (diffResult.error) {
                    showError(llmErrorChat, diffResult.error);
                    return;
                }
                
                if (!diffResult.diff || diffResult.diff.trim() === '') {
                    appendMessageToChat('system', 'Aucune modification détectée (git diff HEAD est vide).');
                    return;
                }
                
                // Charger automatiquement le prompt de revue de diff
                try {
                    const reviewPromptContent = await window.pywebview.api.get_prompt_content('04_revue_de_diff.md');
                    
                    // Construire le message avec le diff
                    const fullMessage = `${reviewPromptContent}\n\n## Diff des modifications :\n\n\`\`\`diff\n${diffResult.diff}\n\`\`\``;
                    
                    chatMessageInput.value = fullMessage;
                    adjustTextareaHeight(chatMessageInput);
                    
                    // Marquer le bouton de prompt comme actif s'il existe
                    const reviewButton = document.querySelector('[data-prompt-file="04_revue_de_diff.md"]');
                    if (reviewButton) {
                        reviewButton.classList.add('active');
                        activePrompts.add('04_revue_de_diff.md');
                    }
                    
                    appendMessageToChat('system', 'Les modifications ont été chargées avec le prompt de revue. Vous pouvez maintenant envoyer le message pour obtenir une analyse.');
                } catch (error) {
                    // Si le prompt n'est pas trouvé, ajouter simplement le diff
                    chatMessageInput.value = `Voici mes dernières modifications (git diff) :\n\n\`\`\`diff\n${diffResult.diff}\n\`\`\``;
                    adjustTextareaHeight(chatMessageInput);
                    appendMessageToChat('system', 'Les modifications ont été chargées. Ajoutez vos questions ou demandes d\'analyse.');
                }
            }
        } catch (error) {
            console.error('Erreur lors de l\'exécution de git diff:', error);
            showError(llmErrorChat, 'Erreur lors de l\'exécution de git diff.');
        }
    });

    // Ajuster la hauteur du textarea
    function adjustTextareaHeight(textarea) {
        textarea.style.height = 'auto';
        textarea.style.height = (textarea.scrollHeight) + 'px';
    }

    // Gérer l'envoi de messages
    async function sendMessage() {
        const userMessage = chatMessageInput.value.trim();
        if (!userMessage) return;

        if (!mainContext && !userMessage.includes('git diff')) {
            showError(llmErrorChat, 'Veuillez d\'abord importer le contexte du projet.');
            return;
        }

        hideError(llmErrorChat);
        
        // Vérifier à nouveau le statut du streaming avant l'envoi
        await checkStreamingStatus();
        
        // Ajouter le message de l'utilisateur
        chatHistory.push({ role: 'user', content: userMessage });
        appendMessageToChat('user', userMessage, null, chatHistory.length - 1);
        
        // Réinitialiser l'interface
        chatMessageInput.value = '';
        adjustTextareaHeight(chatMessageInput);
        sendChatMessageBtn.disabled = true;
        chatMessageInput.disabled = true;
        llmChatSpinner.classList.remove('d-none');
        if (smartScrollController) {
            smartScrollController.reset(); // Réactiver le défilement automatique pour la nouvelle réponse
        }
        
        console.log('isStreamEnabled avant envoi:', isStreamEnabled, typeof isStreamEnabled);

        // Désactiver tous les boutons de prompts actifs
        document.querySelectorAll('.prompt-button.active').forEach(button => {
            button.classList.remove('active');
        });
        activePrompts.clear();

        try {
            // Préparer l'historique complet
            let historyToSend = [...chatHistory];
            
            // S'assurer que le contexte est inclus dans le premier message s'il existe
            if (historyToSend.length > 0 && mainContext) {
                const firstUserMessage = historyToSend[0].content;
                const contextPrefix = 'Voici le contexte du projet sur lequel je souhaite discuter:';
                
                // Ajouter le contexte au premier message pour l'envoi
                historyToSend[0] = {
                    role: 'user',
                    content: `${contextPrefix}\n\n${mainContext}\n\n${firstUserMessage}`
                };
            }

            if (window.pywebview && window.pywebview.api) {
                if (isStreamEnabled) {
                    // Mode streaming
                    console.log('Mode streaming activé');
                    const callbackId = 'stream_' + Date.now();
                    let streamingDiv = null;
                    let streamContent = '';
                    
                    // Créer immédiatement la bulle de réponse avec un indicateur de chargement
                    streamingDiv = appendMessageToChat('assistant', '⏳ En cours de rédaction...', null, chatHistory.length);
                    console.log('Bulle de streaming créée:', streamingDiv);
                    
                    // Définir les callbacks pour le streaming
                    window.onStreamStart = (id) => {
                        console.log('Stream start:', id);
                        if (id === callbackId) {
                            // La bulle est déjà créée
                        }
                    };
                    
                    window.onStreamChunk = (id, chunk) => {
                        console.log('Stream chunk:', id, chunk);
                        if (id === callbackId && streamingDiv) {
                            streamContent += chunk;
                            // Mettre à jour le contenu existant
                            const contentDiv = streamingDiv.querySelector('.message-content');
                            if (contentDiv) {
                                contentDiv.dataset.rawContent = streamContent;
                                contentDiv.dataset.markdownContent = marked.parse(streamContent);
                                if (contentDiv.dataset.isMarkdown === 'true') {
                                    contentDiv.innerHTML = contentDiv.dataset.markdownContent;
                                    // Ajouter les boutons de copie pendant le streaming
                                    addCodeCopyButtons(contentDiv);
                                } else {
                                    contentDiv.textContent = streamContent;
                                }
                                autoScrollToBottom();
                            }
                        }
                    };
                    
                    window.onStreamEnd = (id, total_tokens) => {
                        console.log('Stream end:', id, 'tokens:', total_tokens);
                        if (id === callbackId) {
                            // Ajouter à l'historique
                            chatHistory.push({ role: 'assistant', content: streamContent });
                            
                            // Mettre à jour le compteur de tokens
                            if (total_tokens && tokenCountSpan) {
                                tokenCountSpan.textContent = total_tokens.toLocaleString();
                            }
                            
                            // Nettoyage
                            delete window.onStreamStart;
                            delete window.onStreamChunk;
                            delete window.onStreamEnd;
                            delete window.onStreamError;
                        }
                    };
                    
                    window.onStreamError = (id, error) => {
                        console.log('Stream error:', id, error);
                        if (id === callbackId) {
                            showError(llmErrorChat, error);
                            if (streamingDiv) {
                                streamingDiv.remove();
                            }
                            appendMessageToChat('system-error', `Erreur: ${error}`);
                            // Nettoyage
                            delete window.onStreamStart;
                            delete window.onStreamChunk;
                            delete window.onStreamEnd;
                            delete window.onStreamError;
                        }
                    };
                    
                    // Lancer le streaming
                    console.log('Appel de send_to_llm_stream avec callbackId:', callbackId);
                    const response = await window.pywebview.api.send_to_llm_stream(historyToSend, callbackId);
                    
                    if (response.error) {
                        showError(llmErrorChat, response.error);
                        if (streamingDiv) {
                            streamingDiv.remove();
                        }
                        appendMessageToChat('system-error', `Erreur: ${response.error}`);
                    }
                } else {
                    // Mode normal
                    console.log('Mode normal (pas de streaming)');
                    const response = await window.pywebview.api.send_to_llm(historyToSend, false);
                    
                    if (response.error) {
                        showError(llmErrorChat, response.error);
                        appendMessageToChat('system-error', `Erreur: ${response.error}`);
                    } else if (response.response) {
                        chatHistory.push({ role: 'assistant', content: response.response });
                        appendMessageToChat('assistant', response.response, null, chatHistory.length - 1);
                        
                        // Mettre à jour le compteur de tokens
                        if (response.total_tokens && tokenCountSpan) {
                            tokenCountSpan.textContent = response.total_tokens.toLocaleString();
                        }
                    }
                }
            } else {
                showError(llmErrorChat, 'API non disponible.');
            }
        } catch (error) {
            console.error('Erreur lors de l\'envoi du message:', error);
            showError(llmErrorChat, 'Erreur lors de la communication avec l\'assistant.');
            appendMessageToChat('system-error', 'Erreur lors de la communication avec l\'assistant.');
        } finally {
            llmChatSpinner.classList.add('d-none');
            sendChatMessageBtn.disabled = false;
            chatMessageInput.disabled = false;
            chatMessageInput.focus();
        }
    }

    // Événements
    sendChatMessageBtn.addEventListener('click', sendMessage);
    
    chatMessageInput.addEventListener('keypress', (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            sendMessage();
        }
    });
    
    chatMessageInput.addEventListener('input', () => adjustTextareaHeight(chatMessageInput));

    clearChatBtn.addEventListener('click', () => {
        if (confirm('Êtes-vous sûr de vouloir effacer la conversation ?')) {
            chatHistory = [];
            chatDisplayArea.innerHTML = '';
            if (smartScrollController) {
                smartScrollController.reset(); // Réinitialiser le défilement automatique
            }
            appendMessageToChat('system', 'Conversation effacée. Le contexte du projet reste importé.');
            
            // Réinitialiser le compteur de tokens
            if (tokenCountSpan) {
                tokenCountSpan.textContent = '0';
            }
        }
    });

    // Initialisation
    loadAvailablePrompts();
    adjustTextareaHeight(chatMessageInput);
    updateButtonStates(); // Désactiver les boutons au démarrage
    
    // Gestionnaire pour le bouton d'export
    if (exportChatBtn) {
        exportChatBtn.addEventListener('click', async () => {
            // Désactiver le bouton pendant l'export
            exportChatBtn.disabled = true;
            const originalContent = exportChatBtn.innerHTML;
            exportChatBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Export en cours...';
            
            try {
                // Préparer les données de la conversation
                const chatData = {
                    summary: conversationSummary,
                    history: chatHistory
                };
                
                // Appeler l'API pour ouvrir la boîte de dialogue et exporter
                if (window.pywebview && window.pywebview.api) {
                    const result = await window.pywebview.api.save_conversation_dialog(chatData);
                    
                    if (result.success) {
                        // Afficher une notification de succès
                        const successMessage = `Conversation exportée avec succès !\nFichier : ${result.path.split(/[\\/]/).pop()}`;
                        appendMessageToChat('system', successMessage);
                        
                        // Feedback visuel temporaire
                        exportChatBtn.classList.remove('btn-outline-success');
                        exportChatBtn.classList.add('btn-success');
                        exportChatBtn.innerHTML = '<i class="fas fa-check"></i> Exporté !';
                        
                        setTimeout(() => {
                            exportChatBtn.classList.remove('btn-success');
                            exportChatBtn.classList.add('btn-outline-success');
                            exportChatBtn.innerHTML = originalContent;
                        }, 2000);
                    } else if (result.cancelled) {
                        // L'utilisateur a annulé - ne rien faire
                        exportChatBtn.innerHTML = originalContent;
                    } else {
                        // Erreur
                        showError(llmErrorChat, `Erreur lors de l'export : ${result.error || 'Erreur inconnue'}`);
                        exportChatBtn.innerHTML = originalContent;
                    }
                } else {
                    showError(llmErrorChat, 'API non disponible pour l\'export');
                    exportChatBtn.innerHTML = originalContent;
                }
            } catch (error) {
                console.error('Erreur lors de l\'export:', error);
                showError(llmErrorChat, `Erreur lors de l'export : ${error.message}`);
                exportChatBtn.innerHTML = originalContent;
            } finally {
                // Réactiver le bouton
                exportChatBtn.disabled = false;
            }
        });
    }
    
    // Réessayer après un délai si l'API n'était pas prête
    setTimeout(() => {
        if (promptButtonsContainer.children.length === 0) {
            console.log('Retrying to load prompts after delay...');
            loadAvailablePrompts();
        }
        // Mettre à jour l'état des boutons après le rechargement
        updateButtonStates();
    }, 1000);
});