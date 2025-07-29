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
    const llmErrorChat = document.getElementById('llm-error-chat');
    const llmChatSpinner = document.getElementById('llm-chat-spinner');

    // État de l'application
    let mainContext = '';
    let activePrompts = new Set();
    let chatHistory = [];
    let isStreamEnabled = false;

    // Vérifier si le streaming est activé
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.get_stream_status().then(status => {
            isStreamEnabled = status;
        });
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
    function appendMessageToChat(role, content, existingDiv = null) {
        if (existingDiv) {
            // Mise à jour d'un message existant (pour le streaming)
            existingDiv.innerHTML = marked.parse(content);
            chatDisplayArea.scrollTop = chatDisplayArea.scrollHeight;
            return existingDiv;
        }

        const messageDiv = document.createElement('div');
        messageDiv.className = `message-bubble ${role}`;
        
        if (role === 'user') {
            messageDiv.textContent = content;
        } else if (role === 'assistant' || role === 'system' || role === 'system-error') {
            messageDiv.innerHTML = marked.parse(content);
        } else {
            messageDiv.textContent = content;
        }

        chatDisplayArea.appendChild(messageDiv);
        chatDisplayArea.scrollTop = chatDisplayArea.scrollHeight;
        return messageDiv;
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
            
            // Charger et ajouter le contenu du prompt au textarea
            try {
                if (window.pywebview && window.pywebview.api) {
                    const content = await window.pywebview.api.get_prompt_content(promptFile);
                    const currentText = chatMessageInput.value;
                    
                    // Ajouter le prompt avec une séparation claire
                    if (currentText.trim()) {
                        chatMessageInput.value = currentText + '\n\n---\n\n' + content;
                    } else {
                        chatMessageInput.value = content;
                    }
                    
                    adjustTextareaHeight(chatMessageInput);
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
                    
                    // Ajouter un message système dans le chat avec des détails
                    appendMessageToChat('system', `Le contexte du projet a été importé avec succès !\n\n**Statistiques :**\n- Taille : ${contextLength.toLocaleString()} caractères\n- Lignes : ${contextLines.toLocaleString()}\n\n**Aperçu :**\n\`\`\`\n${contextPreview}\n\`\`\`\n\nLe contexte est maintenant disponible pour l'analyse. Vous pouvez utiliser les prompts ou poser vos questions.`);
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
        
        // Ajouter le message de l'utilisateur
        chatHistory.push({ role: 'user', content: userMessage });
        appendMessageToChat('user', userMessage);
        
        // Réinitialiser l'interface
        chatMessageInput.value = '';
        adjustTextareaHeight(chatMessageInput);
        sendChatMessageBtn.disabled = true;
        chatMessageInput.disabled = true;
        llmChatSpinner.classList.remove('d-none');

        // Désactiver tous les boutons de prompts actifs
        document.querySelectorAll('.prompt-button.active').forEach(button => {
            button.classList.remove('active');
        });
        activePrompts.clear();

        try {
            // Préparer l'historique complet avec le contexte si c'est le premier message
            let historyToSend = [...chatHistory];
            if (chatHistory.length === 1 && mainContext) {
                // Premier message, ajouter le contexte au début
                historyToSend = [
                    { 
                        role: 'user', 
                        content: `Voici le contexte du projet sur lequel je souhaite discuter:\n\n${mainContext}\n\n${userMessage}`
                    }
                ];
                // Mettre à jour l'historique local pour refléter cela
                chatHistory[0].content = historyToSend[0].content;
            }

            if (window.pywebview && window.pywebview.api) {
                const response = await window.pywebview.api.send_to_llm(historyToSend, isStreamEnabled);
                
                if (response.error) {
                    showError(llmErrorChat, response.error);
                    appendMessageToChat('system-error', `Erreur: ${response.error}`);
                } else if (response.response) {
                    chatHistory.push({ role: 'assistant', content: response.response });
                    appendMessageToChat('assistant', response.response);
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
            appendMessageToChat('system', 'Conversation effacée. Le contexte du projet reste importé.');
        }
    });

    // Initialisation
    loadAvailablePrompts();
    adjustTextareaHeight(chatMessageInput);
    
    // Réessayer après un délai si l'API n'était pas prête
    setTimeout(() => {
        if (promptButtonsContainer.children.length === 0) {
            console.log('Retrying to load prompts after delay...');
            loadAvailablePrompts();
        }
    }, 1000);
});