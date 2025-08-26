// static/toolbox.js

// Classes Provider pour gérer les différents modes
class ApiProvider {
    constructor() {
        this.chatHistory = [];
        this.mainContext = '';
    }
    
    getCapabilities() {
        return {
            export: true,
            clear: true,
            edit: true,
            tokens: true,
            streaming: true,
            history: true
        };
    }
    
    async importContext(context) {
        this.mainContext = context;
        return { success: true };
    }
    
    async sendMessage(message, chatHistory, mainContext) {
        // Préparer l'historique avec le contexte
        let historyToSend = [...chatHistory];
        
        if (historyToSend.length > 0 && mainContext) {
            const firstMessage = historyToSend[0].content;
            const contextPrefix = 'Voici le contexte du projet sur lequel je souhaite discuter:';
            historyToSend[0] = {
                role: 'user',
                content: `${contextPrefix}\n\n${mainContext}\n\n${firstMessage}`
            };
        }
        
        // Récupérer le modèle sélectionné
        const llmSelector = document.getElementById('llmSelector');
        const selectedLlmId = llmSelector ? llmSelector.value : null;
        
        // Utiliser l'API existante avec le modèle sélectionné
        if (window.pywebview && window.pywebview.api) {
            return await window.pywebview.api.send_to_llm(historyToSend, false, selectedLlmId);
        }
        return { error: 'API non disponible' };
    }
    
    async sendMessageStream(message, chatHistory, mainContext, callbackId) {
        // Préparer l'historique avec le contexte
        let historyToSend = [...chatHistory];
        
        if (historyToSend.length > 0 && mainContext) {
            const firstMessage = historyToSend[0].content;
            const contextPrefix = 'Voici le contexte du projet sur lequel je souhaite discuter:';
            historyToSend[0] = {
                role: 'user',
                content: `${contextPrefix}\n\n${mainContext}\n\n${firstMessage}`
            };
        }
        
        // Récupérer le modèle sélectionné
        const llmSelector = document.getElementById('llmSelector');
        const selectedLlmId = llmSelector ? llmSelector.value : null;
        
        // Utiliser l'API de streaming avec le modèle sélectionné
        if (window.pywebview && window.pywebview.api) {
            return await window.pywebview.api.send_to_llm_stream(historyToSend, callbackId, selectedLlmId);
        }
        return { error: 'API non disponible' };
    }
}

class BrowserProvider {
    constructor(target) {
        this.target = target;
        this.contextImported = false;
    }
    
    getCapabilities() {
        return {
            export: false,
            clear: false,
            edit: false,
            tokens: false,
            streaming: false,
            history: false
        };
    }
    
    async checkStatus() {
        if (window.pywebview && window.pywebview.api) {
            return await window.pywebview.api.check_browser_status();
        }
        return { active: false, error: 'API non disponible' };
    }
    
    async importContext(context) {
        const status = await this.checkStatus();
        if (!status.active) {
            return { success: false, error: status.error };
        }
        
        // Utiliser la méthode existante qui fonctionne déjà bien
        if (window.pywebview && window.pywebview.api) {
            const result = await window.pywebview.api.send_context(context);
            if (result.success) {
                this.contextImported = true;
            }
            return result;
        }
        return { success: false, error: 'API non disponible' };
    }
    
    async sendMessage(message) {
        console.log('BrowserProvider.sendMessage appelé avec message de longueur:', message.length);
        
        const status = await this.checkStatus();
        console.log('Statut du navigateur:', status);
        
        if (!status.active) {
            return { error: 'La fenêtre du navigateur a été fermée. Veuillez relancer la Toolbox.' };
        }
        
        // Injecter le message dans le chatbot en utilisant send_context
        if (window.pywebview && window.pywebview.api) {
            console.log('Appel de send_context...');
            const result = await window.pywebview.api.send_context(message);
            console.log('Résultat de send_context:', result);
            return result;
        }
        return { error: 'API non disponible' };
    }
}

// Contrôleur principal de la Toolbox
class ToolboxController {
    constructor() {
        this.mode = window.toolboxMode || 'api';
        this.target = window.toolboxTarget || '';
        this.provider = null;
        this.mainContext = '';
        this.chatHistory = [];
        this.activePrompts = new Set();
        this.isStreamEnabled = false;
        this.smartScrollController = null;
        this.conversationSummary = '';
        this.currentConversationId = null;
        this.conversations = [];
        
        // Centralisation des sélecteurs CSS pour faciliter la maintenance
        this.selectors = {
            MESSAGE_WRAPPER: '.message-wrapper',
            MESSAGE_BUBBLE: '.message-bubble',
            MESSAGE_HEADER: '.message-header',
            MESSAGE_BODY: '.message-body',
            MESSAGE_CONTENT: '.message-content',
            MESSAGE_PREVIEW: '.message-preview',
            COLLAPSE_ICON: '.collapse-icon',
            COLLAPSED_CLASS: 'collapsed',
            HIGHLIGHT_CLASS: 'highlight',
            CHAT_DISPLAY: '#chatDisplayArea',
            COLLAPSE_ALL_BTN: '#collapseAllBtn',
            EXPAND_ALL_BTN: '#expandAllBtn',
            NAV_JUMP: '.nav-jump'
        };
        
        // Initialiser le provider selon le mode
        this.initializeProvider();
        
        // Initialiser l'interface
        this.initializeUI();
        
        // Vérifier le streaming
        this.checkStreamingStatus();
        
        // Charger la liste des conversations
        this.loadConversations();
    }
    
    initializeProvider() {
        if (this.mode === 'api') {
            this.provider = new ApiProvider();
        } else {
            this.provider = new BrowserProvider(this.target);
        }
    }
    
    initializeUI() {
        // Définir le mode sur le body
        document.body.setAttribute('data-mode', this.mode);
        
        // Initialiser les contrôles de navigation
        this.setupNavigationControls();
        this.currentMessageIndex = { user: -1, assistant: -1 };
        
        // Charger les modèles LLM disponibles (mode API uniquement)
        if (this.mode === 'api') {
            this.loadAvailableLlmModels();
        }
        
        // Afficher le mode actuel
        if (this.mode === 'browser') {
            // Afficher la notification du mode navigateur
            const notification = document.getElementById('browserModeNotification');
            if (notification) {
                notification.classList.remove('d-none');
                const urlSpan = document.getElementById('browserUrl');
                if (urlSpan) {
                    urlSpan.textContent = this.target ? `(${this.target})` : '';
                }
            }
            
            // Vérifier périodiquement le statut du navigateur
            setInterval(() => this.checkBrowserStatus(), 5000);
        }
        
        // Initialiser le défilement intelligent pour le mode API
        if (this.mode === 'api') {
            const chatDisplayArea = document.getElementById('chatDisplayArea');
            if (chatDisplayArea && window.ChatUtils && window.ChatUtils.SmartScroll) {
                this.smartScrollController = window.ChatUtils.SmartScroll.init(chatDisplayArea, {
                    tolerance: 50,
                    debug: true
                });
            }
        }
        
        // Mettre à jour l'état initial des boutons
        this.updateButtonStates();
        this.updateSaveButtonState();
    }
    
    async checkStreamingStatus() {
        if (this.mode === 'api' && window.pywebview && window.pywebview.api) {
            try {
                this.isStreamEnabled = await window.pywebview.api.get_stream_status();
                console.log('Streaming activé:', this.isStreamEnabled);
            } catch (error) {
                console.error('Erreur lors de la récupération du statut de streaming:', error);
                this.isStreamEnabled = false;
            }
        }
    }
    
    async checkBrowserStatus() {
        if (this.mode === 'browser') {
            const status = await this.provider.checkStatus();
            const indicator = document.getElementById('browserStatusIndicator');
            if (indicator) {
                const badge = indicator.querySelector('.badge');
                if (status.active) {
                    badge.className = 'badge bg-success';
                    badge.innerHTML = '<i class="fas fa-link"></i> Connecté';
                } else {
                    badge.className = 'badge bg-danger';
                    badge.innerHTML = '<i class="fas fa-unlink"></i> Déconnecté';
                }
            }
        }
    }
    
    showError(message) {
        console.error('Erreur affichée:', message);
        
        if (this.mode === 'browser') {
            // En mode browser, utiliser la zone d'erreur spécifique
            const errorDiv = document.getElementById('llm-error-browser');
            if (errorDiv) {
                errorDiv.textContent = message;
                errorDiv.classList.remove('d-none');
            }
        } else {
            // En mode API, utiliser la zone d'erreur du chat
            const llmErrorChat = document.getElementById('llm-error-chat');
            if (llmErrorChat) {
                llmErrorChat.textContent = message;
                llmErrorChat.classList.remove('d-none');
            }
        }
    }
    
    hideError() {
        const llmErrorChat = document.getElementById('llm-error-chat');
        const llmErrorBrowser = document.getElementById('llm-error-browser');
        
        if (llmErrorChat) {
            llmErrorChat.classList.add('d-none');
            llmErrorChat.textContent = '';
        }
        if (llmErrorBrowser) {
            llmErrorBrowser.classList.add('d-none');
            llmErrorBrowser.textContent = '';
        }
    }
    
    appendSystemMessage(message) {
        if (this.mode === 'api') {
            this.appendMessageToChat('system', message);
        } else {
            // En mode browser, on peut afficher dans la zone de notification
            const notification = document.getElementById('browserModeNotification');
            if (notification) {
                const alert = notification.querySelector('.alert');
                const p = document.createElement('p');
                p.className = 'mb-0 text-success';
                p.innerHTML = `<i class="fas fa-check"></i> ${message}`;
                alert.appendChild(p);
            }
        }
    }
    
    autoScrollToBottom() {
        if (this.smartScrollController) {
            this.smartScrollController.scrollToBottom();
        } else {
            const chatDisplayArea = document.getElementById('chatDisplayArea');
            if (chatDisplayArea) {
                chatDisplayArea.scrollTop = chatDisplayArea.scrollHeight;
            }
        }
    }
    
    updateSaveButtonState() {
        const saveBtn = document.getElementById('saveConversationBtn');
        if (saveBtn) {
            if (this.chatHistory.length === 0) {
                saveBtn.disabled = true;
                saveBtn.title = 'Commencez une conversation pour pouvoir la sauvegarder';
            } else {
                saveBtn.disabled = false;
                saveBtn.title = 'Sauvegarder la conversation actuelle';
            }
        }
    }
    
    updateButtonStates() {
        const hasContext = this.mainContext && this.mainContext.trim() !== '';
        
        // Mettre à jour les boutons de prompts
        document.querySelectorAll('.prompt-button').forEach(button => {
            button.disabled = !hasContext;
            button.title = hasContext ? '' : "Veuillez d'abord importer le contexte du projet";
        });
        
        // Mettre à jour le bouton git diff
        const gitDiffBtn = document.getElementById('gitDiffBtn');
        if (gitDiffBtn) {
            gitDiffBtn.disabled = !hasContext;
            gitDiffBtn.title = hasContext ? '' : "Veuillez d'abord importer le contexte du projet";
        }
    }
    
    async importContext() {
        try {
            if (window.pywebview && window.pywebview.api) {
                const context = await window.pywebview.api.get_main_context();
                
                if (context && context.trim()) {
                    this.mainContext = context;
                    
                    // Utiliser le provider pour importer le contexte
                    const result = await this.provider.importContext(context);
                    
                    if (result.success !== false) {
                        // Mise à jour de l'interface
                        const contextStatus = document.getElementById('contextStatus');
                        contextStatus.classList.remove('no-context');
                        contextStatus.innerHTML = '<i class="fas fa-check-circle text-success"></i> Contexte importé avec succès';
                        
                        // Créer le résumé
                        const contextLength = context.length;
                        const contextLines = context.split('\n').length;
                        const contextPreview = context.substring(0, 200) + '...';
                        
                        this.conversationSummary = `## Contexte du Projet\n\n**Statistiques :**\n- Taille : ${contextLength.toLocaleString()} caractères\n- Lignes : ${contextLines.toLocaleString()}\n\n**Aperçu :**\n\`\`\`\n${contextPreview}\n\`\`\`\n\nLe contexte contient le code source et la structure du projet pour permettre l'analyse et les modifications.`;
                        
                        // Message système selon le mode
                        if (this.mode === 'api') {
                            this.appendSystemMessage(`Le contexte du projet a été importé avec succès !\n\n${this.conversationSummary}\n\nLe contexte est maintenant disponible pour l'analyse. Vous pouvez utiliser les prompts ou poser vos questions.`);
                        } else {
                            this.appendSystemMessage('Le contexte a été envoyé à la fenêtre du chatbot.');
                        }
                        
                        // Activer les boutons
                        this.updateButtonStates();
                        this.updateSaveButtonState();
                    } else {
                        this.showError(result.error || 'Erreur lors de l\'import du contexte');
                    }
                } else {
                    // NE PLUS AFFICHER D'ERREUR, METTRE L'UI A JOUR
                    const contextStatus = document.getElementById('contextStatus');
                    if (contextStatus) {
                        contextStatus.classList.add('no-context');
                        contextStatus.innerHTML = '<i class="fas fa-info-circle text-warning"></i> Aucun contexte importé. Scannez un projet ou chargez une conversation.';
                    }
                    // S'assurer que les boutons sont bien désactivés
                    this.updateButtonStates();
                }
            }
        } catch (error) {
            console.error('Erreur lors de l\'import du contexte:', error);
            this.showError('Erreur lors de l\'import du contexte.');
        }
    }
    
    async loadAvailableLlmModels() {
        try {
            const models = await window.pywebview.api.get_available_llms();
            const selector = document.getElementById('llmSelector');
            
            if (!selector || !models || models.length === 0) {
                console.warn('Aucun modèle LLM disponible ou sélecteur non trouvé');
                return;
            }
            
            // Vider le sélecteur
            selector.innerHTML = '';
            
            // Récupérer le modèle précédemment sélectionné depuis le localStorage
            const savedModelId = localStorage.getItem('selectedLlmModel');
            let defaultFound = false;
            
            // Ajouter les options
            models.forEach(model => {
                const option = document.createElement('option');
                option.value = model.id;
                option.textContent = model.name;
                
                // Sélectionner le modèle par défaut ou le modèle sauvegardé
                if (savedModelId && model.id === savedModelId) {
                    option.selected = true;
                    defaultFound = true;
                } else if (!savedModelId && model.default) {
                    option.selected = true;
                    defaultFound = true;
                }
                
                selector.appendChild(option);
            });
            
            // Si aucun modèle n'est sélectionné, sélectionner le premier
            if (!defaultFound && models.length > 0) {
                selector.selectedIndex = 0;
            }
            
            // Sauvegarder le choix lors du changement
            selector.addEventListener('change', () => {
                localStorage.setItem('selectedLlmModel', selector.value);
                console.log('Modèle LLM sélectionné:', selector.value);
            });
            
            // Sauvegarder le choix initial
            if (selector.value) {
                localStorage.setItem('selectedLlmModel', selector.value);
            }
            
            console.log('Modèles LLM chargés:', models.length);
        } catch (error) {
            console.error('Erreur lors du chargement des modèles LLM:', error);
        }
    }
    
    async sendMessage(message) {
        if (!message || !message.trim()) return;
        
        // Vérifier le contexte en mode API
        if (this.mode === 'api' && !this.mainContext && !message.includes('git diff')) {
            this.showError('Veuillez d\'abord importer le contexte du projet.');
            return;
        }
        
        this.hideError();
        
        // Désactiver l'interface
        const sendBtn = document.getElementById('sendChatMessageBtn');
        const input = document.getElementById('chatMessageInput');
        
        this.updateSaveButtonState();
        if (sendBtn) sendBtn.disabled = true;
        if (input) input.disabled = true;
        
        const spinner = document.getElementById('llm-chat-spinner');
        if (spinner) spinner.classList.remove('d-none');
        
        try {
            if (this.mode === 'api') {
                // Mode API : gérer l'historique et l'affichage
                this.chatHistory.push({ role: 'user', content: message });
                this.appendMessageToChat('user', message);
                
                // Réinitialiser le défilement
                if (this.smartScrollController) {
                    this.smartScrollController.reset();
                }
                
                // Envoyer selon le mode (streaming ou normal)
                if (this.isStreamEnabled) {
                    await this.sendMessageStream(message);
                } else {
                    const response = await this.provider.sendMessage(message, this.chatHistory, this.mainContext);
                    
                    if (response.error) {
                        this.showError(response.error);
                        this.appendMessageToChat('system-error', `Erreur: ${response.error}`);
                    } else if (response.response) {
                        this.chatHistory.push({ role: 'assistant', content: response.response });
                        this.appendMessageToChat('assistant', response.response);
                        
                        // Mettre à jour le compteur de tokens
                        if (response.total_tokens) {
                            const tokenSpan = document.getElementById('chat-token-count');
                            if (tokenSpan) tokenSpan.textContent = response.total_tokens.toLocaleString();
                        }
                    }
                }
            } else {
                // Mode Browser : simplement injecter le message
                const response = await this.provider.sendMessage(message);
                
                if (response.error) {
                    this.showError(response.error);
                } else {
                    this.appendSystemMessage('Message envoyé au chatbot.');
                }
            }
        } catch (error) {
            console.error('Erreur lors de l\'envoi du message:', error);
            this.showError('Erreur lors de la communication.');
            if (this.mode === 'api') {
                this.appendMessageToChat('system-error', 'Erreur lors de la communication.');
            }
        } finally {
            if (spinner) spinner.classList.add('d-none');
            if (sendBtn) sendBtn.disabled = false;
            if (input) {
                input.disabled = false;
                input.value = '';
                input.focus();
            }
        }
    }
    
    async sendMessageStream(message) {
        const callbackId = 'stream_' + Date.now();
        let streamingDiv = null;
        let streamContent = '';
        
        // Créer immédiatement la bulle de réponse
        streamingDiv = this.appendMessageToChat('assistant', '⏳ En cours de rédaction...', null, this.chatHistory.length);
        
        // Définir les callbacks pour le streaming
        window.onStreamStart = (id) => {
            if (id === callbackId) {
                // La bulle est déjà créée
            }
        };
        
        window.onStreamChunk = (id, chunk) => {
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
                        this.addCodeCopyButtons(contentDiv);
                    } else {
                        contentDiv.textContent = streamContent;
                    }
                    this.autoScrollToBottom();
                }
            }
        };
        
        window.onStreamEnd = (id, total_tokens) => {
            if (id === callbackId) {
                // Ajouter à l'historique
                this.chatHistory.push({ role: 'assistant', content: streamContent });
                
                // Mettre à jour le compteur de tokens
                if (total_tokens) {
                    const tokenSpan = document.getElementById('chat-token-count');
                    if (tokenSpan) tokenSpan.textContent = total_tokens.toLocaleString();
                }
                
                // Réactiver le bouton de sauvegarde après une réponse
                this.updateSaveButtonState();
                
                // Nettoyage
                delete window.onStreamStart;
                delete window.onStreamChunk;
                delete window.onStreamEnd;
                delete window.onStreamError;
            }
        };
        
        window.onStreamError = (id, error) => {
            if (id === callbackId) {
                this.showError(error);
                if (streamingDiv) {
                    streamingDiv.remove();
                }
                // Ré-évaluer l'état du bouton de sauvegarde même en cas d'erreur
                this.updateSaveButtonState();
                this.appendMessageToChat('system-error', `Erreur: ${error}`);
                // Nettoyage
                delete window.onStreamStart;
                delete window.onStreamChunk;
                delete window.onStreamEnd;
                delete window.onStreamError;
            }
        };
        
        // Lancer le streaming
        const response = await this.provider.sendMessageStream(message, this.chatHistory, this.mainContext, callbackId);
        
        if (response.error) {
            this.showError(response.error);
            if (streamingDiv) {
                streamingDiv.remove();
            }
            this.appendMessageToChat('system-error', `Erreur: ${response.error}`);
        }
    }
    
    /**
     * Obtient l'icône FontAwesome correspondante au rôle du message
     * @private
     * @param {string} role - Le rôle du message (user, assistant, system, system-error)
     * @returns {string} La classe CSS de l'icône FontAwesome
     */
    _getRoleIcon(role) {
        const icons = {
            'user': 'fas fa-user',
            'assistant': 'fas fa-robot',
            'system': 'fas fa-info-circle',
            'system-error': 'fas fa-exclamation-triangle'
        };
        return icons[role] || 'fas fa-comment';
    }

    /**
     * Obtient le label localisé pour un rôle de message
     * @private
     * @param {string} role - Le rôle du message
     * @returns {string} Le label en français du rôle
     */
    _getRoleLabel(role) {
        const labels = {
            'user': 'Utilisateur',
            'assistant': 'Assistant',
            'system': 'Système',
            'system-error': 'Erreur'
        };
        return labels[role] || role;
    }

    /**
     * Met à jour l'aperçu textuel d'un message lorsqu'il est plié/déplié
     * @private
     * @param {HTMLElement} wrapper - L'élément .message-wrapper à mettre à jour
     */
    _updateMessagePreview(wrapper) {
        const preview = wrapper.querySelector(this.selectors.MESSAGE_PREVIEW);
        const content = wrapper.querySelector(this.selectors.MESSAGE_CONTENT);
        
        if (!preview || !content) return;
        
        if (wrapper.classList.contains('collapsed')) {
            // Générer l'aperçu seulement au moment du pliage
            const text = content.textContent.trim();
            preview.textContent = text.substring(0, 100) + (text.length > 100 ? '...' : '');
            preview.style.display = 'inline';
        } else {
            preview.textContent = '';
            preview.style.display = 'none';
        }
    }

    /**
     * Ajoute ou met à jour un message dans l'interface de chat
     * @param {string} role - Le rôle du message (user, assistant, system, system-error)
     * @param {string} content - Le contenu du message
     * @param {HTMLElement|null} existingDiv - Élément existant à mettre à jour (pour le streaming)
     * @param {number|null} messageIndex - Index explicite du message dans chatHistory
     * @returns {HTMLElement|null} L'élément div du message créé ou mis à jour
     */
    appendMessageToChat(role, content, existingDiv = null, messageIndex = null) {
        if (this.mode !== 'api') return null;
        
        const chatDisplayArea = document.querySelector(this.selectors.CHAT_DISPLAY);
        if (!chatDisplayArea) return null;
        
        if (existingDiv) {
            // Mise à jour d'un message existant (pour le streaming)
            const contentDiv = existingDiv.querySelector(this.selectors.MESSAGE_CONTENT);
            contentDiv.textContent = content;
            contentDiv.dataset.rawContent = content;
            contentDiv.dataset.markdownContent = marked.parse(content);
            this.autoScrollToBottom();
            return existingDiv;
        }
        
        const messageWrapper = document.createElement('div');
        messageWrapper.className = 'message-wrapper';
        // Utiliser l'index fourni, sinon calculer en fonction du rôle
        if (messageIndex !== null && messageIndex !== undefined) {
            messageWrapper.dataset.messageIndex = messageIndex;
        } else {
            // Pour les messages système, ne pas utiliser l'index car ils ne sont pas dans chatHistory
            if (role !== 'system' && role !== 'system-error') {
                // Pour les messages non-streamés, le .push() dans sendMessage a déjà été fait.
                // L'index du nouvel élément est donc simplement le dernier du tableau.
                // C'est plus simple et plus performant (O(1)) que de rechercher.
                messageWrapper.dataset.messageIndex = this.chatHistory.length - 1;
            }
        }
        
        // Créer l'en-tête du message
        const messageHeader = document.createElement('div');
        messageHeader.className = 'message-header';
        messageHeader.innerHTML = `
            <span class="message-role">
                <i class="${this._getRoleIcon(role)}"></i>
                ${this._getRoleLabel(role)}
            </span>
            <span class="message-preview" style="display: none;"></span>
            <i class="fas fa-chevron-down collapse-icon"></i>
        `;
        
        // Ajouter l'événement de pliage/dépliage
        messageHeader.addEventListener('click', (e) => {
            // Important : éviter le pliage lors du clic sur les boutons d'action
            if (!e.target.closest('.message-actions')) {
                messageWrapper.classList.toggle('collapsed');
                this._updateMessagePreview(messageWrapper);
                this.saveNavigationState();
            }
        });
        
        const messageDiv = document.createElement('div');
        messageDiv.className = `message-bubble ${role}`;
        messageDiv.style.position = 'relative';
        
        // Créer le corps du message qui contiendra le contenu
        const messageBody = document.createElement('div');
        messageBody.className = 'message-body';
        
        // Créer un conteneur pour le contenu
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.style.whiteSpace = 'pre-wrap';
        contentDiv.style.wordBreak = 'break-word';
        
        // Stocker les deux versions du contenu
        contentDiv.dataset.rawContent = content;
        contentDiv.dataset.markdownContent = marked.parse(content);
        contentDiv.dataset.isMarkdown = 'true'; // Markdown par défaut
        
        // Afficher en markdown par défaut
        contentDiv.innerHTML = contentDiv.dataset.markdownContent;
        contentDiv.style.whiteSpace = 'normal';
        
        messageBody.appendChild(contentDiv);
        
        // Ajouter les boutons de contrôle pour user et assistant
        if (role === 'user' || role === 'assistant') {
            this.addMessageControls(messageBody, role, contentDiv);
        }
        
        messageDiv.appendChild(messageHeader);
        messageDiv.appendChild(messageBody);
        messageWrapper.appendChild(messageDiv);
        chatDisplayArea.appendChild(messageWrapper);
        this.autoScrollToBottom();
        
        // Ajouter les boutons de copie aux blocs de code si c'est un message assistant
        if (role === 'assistant') {
            this.addCodeCopyButtons(contentDiv);
        }
        
        return messageDiv;
    }
    
    /**
     * Ajoute les boutons de contrôle à un message (Fork, Copier, Relancer, Éditer)
     * @param {HTMLElement} messageBody - Le conteneur du corps du message
     * @param {string} role - Le rôle du message (user ou assistant)
     * @param {HTMLElement} contentDiv - Le div contenant le contenu du message
     */
    addMessageControls(messageBody, role, contentDiv) {
        // Créer les boutons
        const buttonsContainer = document.createElement('div');
        buttonsContainer.className = 'buttons-bottom';
        buttonsContainer.style.cssText = 'display: flex; gap: 5px;';
        
        // Bouton Fork pour tous les messages (user et assistant)
        const forkBtn = document.createElement('button');
        forkBtn.className = 'btn btn-sm btn-outline-secondary fork-btn';
        forkBtn.innerHTML = '<i class="fas fa-code-branch"></i>';
        forkBtn.title = 'Créer une branche à partir d\'ici';
        forkBtn.style.cssText = 'opacity: 0.7; padding: 2px 6px; font-size: 12px;';
        
        // Utiliser le data-message-index pour trouver l'index dans chatHistory
        forkBtn.addEventListener('click', () => {
            // Récupérer l'index depuis le wrapper parent au moment du clic
            const messageWrapper = messageBody.closest('.message-wrapper');
            const messageIndex = messageWrapper ? parseInt(messageWrapper.dataset.messageIndex) : -1;
            
            if (messageIndex >= 0 && messageIndex < this.chatHistory.length) {
                this.forkConversationFrom(messageIndex, contentDiv.dataset.rawContent, role);
            } else {
                console.error('Fork - Index invalide:', messageIndex, 'sur', this.chatHistory.length);
                this.showError('Impossible de créer une branche depuis ce message');
            }
        });
        
        buttonsContainer.appendChild(forkBtn);
        
        // Bouton toggle markdown
        const toggleBtn = document.createElement('button');
        toggleBtn.className = 'btn btn-sm btn-outline-secondary toggle-markdown-btn';
        toggleBtn.innerHTML = '<i class="fas fa-align-left"></i>';
        toggleBtn.title = 'Afficher en texte brut';
        toggleBtn.style.cssText = 'opacity: 0.7; padding: 2px 6px; font-size: 12px;';
        
        toggleBtn.addEventListener('click', () => {
            const isMarkdown = contentDiv.dataset.isMarkdown === 'true';
            
            if (isMarkdown) {
                contentDiv.textContent = contentDiv.dataset.rawContent;
                contentDiv.style.whiteSpace = 'pre-wrap';
                contentDiv.dataset.isMarkdown = 'false';
                toggleBtn.innerHTML = '<i class="fas fa-code"></i>';
                toggleBtn.title = 'Afficher en Markdown';
            } else {
                contentDiv.innerHTML = contentDiv.dataset.markdownContent;
                contentDiv.style.whiteSpace = 'normal';
                contentDiv.dataset.isMarkdown = 'true';
                toggleBtn.innerHTML = '<i class="fas fa-align-left"></i>';
                toggleBtn.title = 'Afficher en texte brut';
                
                if (role === 'assistant') {
                    this.addCodeCopyButtons(contentDiv);
                }
            }
        });
        
        buttonsContainer.appendChild(toggleBtn);
        
        // Bouton de copie
        const copyBtn = document.createElement('button');
        copyBtn.className = 'btn btn-sm btn-outline-secondary copy-btn';
        copyBtn.innerHTML = '<i class="far fa-copy"></i>';
        copyBtn.title = 'Copier le contenu';
        copyBtn.style.cssText = 'opacity: 0.7; padding: 2px 6px; font-size: 12px;';
        
        copyBtn.addEventListener('click', () => {
            const isMarkdown = contentDiv.dataset.isMarkdown === 'true';
            let textToCopy;
            
            if (isMarkdown) {
                const tempDiv = document.createElement('div');
                tempDiv.innerHTML = contentDiv.innerHTML;
                textToCopy = tempDiv.textContent || tempDiv.innerText || '';
            } else {
                textToCopy = contentDiv.dataset.rawContent;
            }
            
            navigator.clipboard.writeText(textToCopy).then(() => {
                copyBtn.innerHTML = '<i class="fas fa-check"></i>';
                setTimeout(() => {
                    copyBtn.innerHTML = '<i class="far fa-copy"></i>';
                }, 2000);
            }).catch(err => {
                console.error('Erreur lors de la copie:', err);
            });
        });
        
        buttonsContainer.appendChild(copyBtn);
        
        // Boutons pour les messages utilisateur seulement
        if (role === 'user') {
            // Bouton Relancer (renvoyer le message)
            const retryBtn = document.createElement('button');
            retryBtn.className = 'btn btn-sm btn-outline-secondary retry-btn';
            retryBtn.innerHTML = '<i class="fas fa-redo"></i>';
            retryBtn.title = 'Relancer ce message';
            retryBtn.style.cssText = 'opacity: 0.7; padding: 2px 6px; font-size: 12px;';
            
            retryBtn.addEventListener('click', async () => {
                // Récupérer l'index depuis le wrapper parent au moment du clic
                const messageWrapper = messageBody.closest('.message-wrapper');
                const realIndex = messageWrapper ? parseInt(messageWrapper.dataset.messageIndex) : -1;
                
                if (realIndex >= 0) {
                    // Supprimer tous les messages après celui-ci (garder jusqu'à ce message inclus)
                    this.chatHistory = this.chatHistory.slice(0, realIndex);
                    
                    // Rafraîchir l'affichage
                    this.refreshChatDisplay();
                    
                    // Message système pour indiquer le relancement
                    this.appendMessageToChat('system', '🔄 Relancement du message...');
                    
                    // Renvoyer le message (il sera rajouté à l'historique par sendMessage)
                    const messageContent = contentDiv.dataset.rawContent;
                    await this.sendMessage(messageContent);
                }
            });
            
            buttonsContainer.appendChild(retryBtn);
            
            // Bouton Éditer
            const editBtn = document.createElement('button');
            editBtn.className = 'btn btn-sm btn-outline-secondary edit-btn';
            editBtn.innerHTML = '<i class="fas fa-edit"></i>';
            editBtn.title = 'Éditer et régénérer';
            editBtn.style.cssText = 'opacity: 0.7; padding: 2px 6px; font-size: 12px;';
            
            editBtn.addEventListener('click', () => {
                // Récupérer l'index depuis le wrapper parent au moment du clic
                const messageWrapper = messageBody.closest('.message-wrapper');
                const realIndex = messageWrapper ? parseInt(messageWrapper.dataset.messageIndex) : -1;
                
                if (realIndex >= 0) {
                    this.editUserMessage(realIndex, contentDiv.dataset.rawContent);
                }
            });
            
            buttonsContainer.appendChild(editBtn);
        }
        
        messageBody.appendChild(buttonsContainer);
    }
    
    addCodeCopyButtons(container) {
        const codeBlocks = container.querySelectorAll('pre');
        
        codeBlocks.forEach((preElement) => {
            if (preElement.querySelector('.code-copy-btn')) {
                return;
            }
            
            if (!preElement.style.position || preElement.style.position === 'static') {
                preElement.style.position = 'relative';
            }
            
            const copyBtn = document.createElement('button');
            copyBtn.className = 'code-copy-btn';
            copyBtn.innerHTML = '<i class="far fa-copy"></i> Copier';
            copyBtn.title = 'Copier le code';
            
            copyBtn.addEventListener('click', async () => {
                const codeElement = preElement.querySelector('code') || preElement;
                const codeText = codeElement.textContent || codeElement.innerText;
                
                try {
                    await navigator.clipboard.writeText(codeText);
                    copyBtn.innerHTML = '<i class="fas fa-check"></i> Copié !';
                    copyBtn.classList.add('copied');
                    
                    setTimeout(() => {
                        copyBtn.innerHTML = '<i class="far fa-copy"></i> Copier';
                        copyBtn.classList.remove('copied');
                    }, 2000);
                } catch (err) {
                    console.error('Erreur lors de la copie:', err);
                }
            });
            
            preElement.appendChild(copyBtn);
        });
    }
    
    editUserMessage(messageDiv, contentDiv) {
        // Implémentation de l'édition de message (mode API seulement)
        if (this.mode !== 'api') return;
        
        // Récupérer le contenu actuel
        const currentContent = contentDiv.dataset.rawContent || contentDiv.textContent;
        
        // Créer une zone de texte pour l'édition
        const textarea = document.createElement('textarea');
        textarea.className = 'form-control';
        textarea.value = currentContent;
        textarea.style.width = '100%';
        textarea.style.minHeight = '100px';
        textarea.style.resize = 'vertical';
        
        // Créer les boutons de contrôle
        const buttonsDiv = document.createElement('div');
        buttonsDiv.className = 'mt-2';
        buttonsDiv.style.display = 'flex';
        buttonsDiv.style.gap = '10px';
        
        const saveBtn = document.createElement('button');
        saveBtn.className = 'btn btn-sm btn-success';
        saveBtn.innerHTML = '<i class="fas fa-check"></i> Valider';
        
        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'btn btn-sm btn-secondary';
        cancelBtn.innerHTML = '<i class="fas fa-times"></i> Annuler';
        
        buttonsDiv.appendChild(saveBtn);
        buttonsDiv.appendChild(cancelBtn);
        
        // Remplacer le contenu par la zone d'édition
        const originalContent = contentDiv.innerHTML;
        const originalDisplay = contentDiv.style.display;
        contentDiv.style.display = 'none';
        
        // Créer un conteneur temporaire pour l'édition
        const editContainer = document.createElement('div');
        editContainer.className = 'edit-container';
        editContainer.appendChild(textarea);
        editContainer.appendChild(buttonsDiv);
        
        messageDiv.insertBefore(editContainer, contentDiv);
        
        // Focus sur le textarea
        textarea.focus();
        textarea.select();
        
        // Ajuster automatiquement la hauteur
        const adjustHeight = () => {
            textarea.style.height = 'auto';
            textarea.style.height = textarea.scrollHeight + 'px';
        };
        adjustHeight();
        textarea.addEventListener('input', adjustHeight);
        
        // Fonction pour sauvegarder les modifications
        const saveEdit = () => {
            const newContent = textarea.value.trim();
            
            if (!newContent) {
                alert('Le message ne peut pas être vide');
                return;
            }
            
            // Trouver l'index du message dans l'historique
            const messageIndex = Array.from(document.querySelectorAll('.message-bubble.user')).indexOf(messageDiv);
            
            if (messageIndex >= 0) {
                // Mettre à jour l'historique du chat
                let userMessageIndex = -1;
                let currentIndex = 0;
                
                for (let i = 0; i < this.chatHistory.length; i++) {
                    if (this.chatHistory[i].role === 'user') {
                        if (currentIndex === messageIndex) {
                            userMessageIndex = i;
                            break;
                        }
                        currentIndex++;
                    }
                }
                
                if (userMessageIndex >= 0) {
                    // Mettre à jour le message dans l'historique
                    this.chatHistory[userMessageIndex].content = newContent;
                    
                    // Mettre à jour l'affichage
                    contentDiv.dataset.rawContent = newContent;
                    contentDiv.dataset.markdownContent = marked.parse(newContent);
                    
                    if (contentDiv.dataset.isMarkdown === 'true') {
                        contentDiv.innerHTML = contentDiv.dataset.markdownContent;
                    } else {
                        contentDiv.textContent = newContent;
                    }
                    
                    // Ajouter un indicateur visuel de modification
                    const editedIndicator = messageDiv.querySelector('.edited-indicator');
                    if (!editedIndicator) {
                        const indicator = document.createElement('span');
                        indicator.className = 'edited-indicator text-muted small';
                        indicator.style.marginLeft = '10px';
                        indicator.innerHTML = '<i class="fas fa-edit"></i> Modifié';
                        
                        const buttonsContainer = messageDiv.querySelector('.buttons-bottom');
                        if (buttonsContainer) {
                            buttonsContainer.appendChild(indicator);
                        }
                    }
                    
                    // Afficher un message système
                    this.appendMessageToChat('system', 'Message utilisateur modifié. L\'historique de la conversation a été mis à jour.');
                }
            }
            
            // Restaurer l'affichage normal
            editContainer.remove();
            contentDiv.style.display = originalDisplay;
        };
        
        // Fonction pour annuler l'édition
        const cancelEdit = () => {
            editContainer.remove();
            contentDiv.style.display = originalDisplay;
        };
        
        // Attacher les événements
        saveBtn.addEventListener('click', saveEdit);
        cancelBtn.addEventListener('click', cancelEdit);
        
        // Permettre Ctrl+Enter pour sauvegarder
        textarea.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && e.ctrlKey) {
                e.preventDefault();
                saveEdit();
            } else if (e.key === 'Escape') {
                e.preventDefault();
                cancelEdit();
            }
        });
    }
    
    editUserMessage(messageIndex, originalContent) {
        // Vérifier que Bootstrap est disponible
        if (!window.bootstrap) {
            console.error('Bootstrap non disponible');
            return;
        }
        
        const modalElement = document.getElementById('editMessageModal');
        if (!modalElement) {
            console.error('Modal editMessageModal non trouvé');
            return;
        }
        
        const modal = new bootstrap.Modal(modalElement);
        const textarea = document.getElementById('editMessageTextarea');
        const confirmBtn = document.getElementById('confirmEditBtn');
        
        // Pré-remplir avec le contenu actuel
        textarea.value = originalContent;
        
        // Retirer l'ancien listener s'il existe
        const newConfirmBtn = confirmBtn.cloneNode(true);
        confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);
        
        // Ajouter le nouveau listener
        newConfirmBtn.addEventListener('click', () => {
            const newContent = textarea.value.trim();
            
            if (newContent === '') {
                alert('Le message ne peut pas être vide');
                return;
            }
            
            // Tronquer l'historique jusqu'à ce message (exclu)
            this.chatHistory = this.chatHistory.slice(0, messageIndex);
            
            // Ajouter le nouveau message modifié
            this.chatHistory.push({
                role: 'user',
                content: newContent
            });
            
            // Rafraîchir l'affichage
            this.refreshChatDisplay();
            
            // Fermer le modal
            modal.hide();
            
            // Envoyer le message modifié au LLM pour obtenir une nouvelle réponse
            if (this.isStreamEnabled) {
                this.sendMessageStream(newContent);
            } else {
                this.sendMessage(newContent);
            }
            
            // Message système pour indiquer l'édition
            this.appendMessageToChat('system', 
                '✏️ Message édité et historique tronqué. Nouvelle réponse en cours de génération...'
            );
        });
        
        // Afficher le modal
        modal.show();
    }
    
    async forkConversationFrom(messageIndex, originalContent, role) {
        // Confirmation simple pour créer une nouvelle discussion
        const confirmMessage = role === 'user' 
            ? `Créer une nouvelle discussion à partir de ce message ?\n\nL'historique sera conservé jusqu'à AVANT ce message (il sera exclu et remplacé par votre nouveau message).`
            : `Créer une nouvelle discussion à partir de cette réponse ?\n\nL'historique sera conservé jusqu'à cette réponse incluse.`;
        
        if (!confirm(confirmMessage)) {
            return; // Annulation
        }
        
        // CORRECTION: S'assurer que l'index est correct
        // Si c'est -1, c'est qu'il y a un problème
        if (messageIndex === -1) {
            console.error('Erreur: impossible de trouver l\'index du message');
            this.showError('Erreur lors de la création de la branche');
            return;
        }
        
        // Logique de découpage différenciée selon le rôle
        let baseHistory;
        if (role === 'user') {
            // Fork sur message user: on prend l'historique AVANT ce message
            // IMPORTANT: on exclut ce message car il sera remplacé
            baseHistory = this.chatHistory.slice(0, messageIndex);
        } else {
            // Fork sur message assistant: on prend l'historique AVEC cette réponse
            baseHistory = this.chatHistory.slice(0, messageIndex + 1);
        }
        
        console.log(`Fork: ${baseHistory.length} messages conservés sur ${this.chatHistory.length}`);
        console.log('Dernier message conservé:', baseHistory[baseHistory.length - 1]);
        
        // Préparer les données pour la branche
        // Note: parentId peut être null si le parent n'est pas sauvegardé
        // C'est volontaire pour éviter de créer des sauvegardes non désirées
        const parentId = this.currentConversationId; // Peut être null, c'est OK
        const parentTitle = this.conversationSummary || 'Conversation non sauvegardée';
        const timestamp = new Date().toLocaleTimeString('fr-FR', {
            hour: '2-digit',
            minute: '2-digit'
        });
        const suggestedTitle = `${parentTitle} - Branche ${timestamp}`;
        
        // PAS de sauvegarde automatique du parent
        // L'utilisateur décidera explicitement s'il veut sauvegarder
        
        // Initialiser la branche
        this.initializeBranch({
            parentId: parentId,
            parentIndex: messageIndex,
            parentRole: role,
            parentTitle: parentTitle,
            history: baseHistory,
            suggestedTitle: suggestedTitle,
            reason: 'exploration alternative'
        });
    }
    
    initializeBranch(branchData) {
        // 1. CRUCIAL: Réinitialiser l'ID pour forcer la modal de sauvegarde
        this.currentConversationId = null;
        
        // 2. Mettre à jour l'historique avec l'historique tronqué
        this.chatHistory = [...branchData.history]; // Copie pour éviter les références
        
        // 3. Stocker les métadonnées de fork
        this.forkInfo = {
            sourceConversationId: branchData.parentId,
            sourceMessageIndex: branchData.parentIndex,
            sourceMessageRole: branchData.parentRole,
            forkTimestamp: new Date().toISOString(),
            forkReason: branchData.reason || 'exploration alternative'
        };
        
        // 4. Stocker le titre suggéré
        this.suggestedBranchTitle = branchData.suggestedTitle;
        
        // 5. Effacer complètement l'affichage et le reconstruire
        const chatDisplayArea = document.getElementById('chatDisplayArea');
        if (chatDisplayArea) {
            chatDisplayArea.innerHTML = '';
        }
        
        // 6. Afficher d'abord un message indiquant que le contexte est chargé (si présent)
        if (this.mainContext) {
            this.appendMessageToChat('system', 
                `📚 Contexte du projet chargé (${this.estimateTokens(this.mainContext)} tokens estimés)`
            );
        }
        
        // 7. Afficher l'historique conservé avec les index corrects
        this.chatHistory.forEach((msg, index) => {
            this.appendMessageToChat(msg.role, msg.content, null, index);
        });
        
        this.updateSaveButtonState();
        
        // 8. Message système avec séparateur visuel
        this.appendMessageToChat('system', 
            `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n` +
            `🌿 NOUVELLE BRANCHE CRÉÉE\n` +
            `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n` +
            `L'historique ci-dessus a été conservé.\n` +
            `Vous pouvez maintenant explorer une nouvelle direction.\n` +
            `N'oubliez pas de sauvegarder cette nouvelle discussion.`
        );
        
        // 9. Focus sur le champ de saisie pour que l'utilisateur puisse directement taper
        const chatInput = document.getElementById('chatMessageInput');
        if (chatInput) {
            chatInput.focus();
            chatInput.placeholder = 'Tapez votre message pour explorer une nouvelle direction...';
            // Réinitialiser le placeholder après un délai
            setTimeout(() => {
                chatInput.placeholder = 'Tapez votre message ici...';
            }, 5000);
        }
    }
    
    async clearChat() {
        if (this.mode === 'api' && confirm('Êtes-vous sûr de vouloir effacer la conversation ?')) {
            this.chatHistory = [];
            const chatDisplayArea = document.getElementById('chatDisplayArea');
            if (chatDisplayArea) {
                chatDisplayArea.innerHTML = '';
            }
            if (this.smartScrollController) {
                this.smartScrollController.reset();
            }
            this.appendMessageToChat('system', 'Conversation effacée. Le contexte du projet reste importé.');
            
            const tokenSpan = document.getElementById('chat-token-count');
            if (tokenSpan) {
                tokenSpan.textContent = '0';
            }
            
            // Réinitialiser l'index de navigation
            this.currentMessageIndex = { user: -1, assistant: -1 };
            
            this.updateSaveButtonState();
        }
    }
    
    /**
     * Configure les contrôles de navigation globaux et les raccourcis clavier
     */
    setupNavigationControls() {
        // Tout plier/déplier
        document.querySelector(this.selectors.COLLAPSE_ALL_BTN)?.addEventListener('click', () => {
            document.querySelectorAll(this.selectors.MESSAGE_WRAPPER).forEach(w => {
                w.classList.add(this.selectors.COLLAPSED_CLASS);
                this._updateMessagePreview(w);
            });
            this.saveNavigationState();
        });
        
        document.querySelector(this.selectors.EXPAND_ALL_BTN)?.addEventListener('click', () => {
            document.querySelectorAll(this.selectors.MESSAGE_WRAPPER).forEach(w => {
                w.classList.remove(this.selectors.COLLAPSED_CLASS);
                this._updateMessagePreview(w);
            });
            this.saveNavigationState();
        });
        
        // Navigation par rôle
        document.querySelectorAll(this.selectors.NAV_JUMP).forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const role = e.currentTarget.dataset.role;
                const direction = e.currentTarget.dataset.direction;
                this.navigateToMessage(role, direction);
            });
        });
        
        // Raccourcis clavier
        document.addEventListener('keydown', (e) => {
            // CRUCIAL : Ne pas interférer avec la saisie de texte
            if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT') return;
            
            switch(e.key) {
                case 'e':
                    if (e.ctrlKey) {
                        e.preventDefault();
                        document.getElementById('expandAllBtn')?.click();
                    }
                    break;
                case 'c':
                    if (e.ctrlKey && e.shiftKey) {
                        e.preventDefault();
                        document.getElementById('collapseAllBtn')?.click();
                    }
                    break;
                case 'ArrowUp':
                    if (e.altKey) {
                        e.preventDefault();
                        this.navigateToMessage(e.shiftKey ? 'assistant' : 'user', 'prev');
                    }
                    break;
                case 'ArrowDown':
                    if (e.altKey) {
                        e.preventDefault();
                        this.navigateToMessage(e.shiftKey ? 'assistant' : 'user', 'next');
                    }
                    break;
            }
        });
    }
    
    /**
     * Navigation intelligente entre les messages par rôle
     * @param {string} role - 'user' ou 'assistant'
     * @param {string} direction - 'prev' ou 'next'
     * 
     * Note : Array.from() est nécessaire pour convertir la NodeList en Array
     * et pouvoir utiliser .map(). La logique de boucle avec l'opérateur modulo
     * assure une navigation circulaire fluide.
     */
    navigateToMessage(role, direction) {
        // Conversion NodeList -> Array pour utiliser .map()
        const messages = Array.from(document.querySelectorAll(`${this.selectors.MESSAGE_BUBBLE}.${role}`))
            .map(el => el.closest(this.selectors.MESSAGE_WRAPPER))
            .filter(Boolean);
        
        if (messages.length === 0) return;
        
        let index = this.currentMessageIndex[role];
        
        if (direction === 'next') {
            // Modulo pour boucler à 0 après le dernier message
            index = (index + 1) % messages.length;
        } else { // prev
            // Si index <= 0, on revient au dernier message
            index = index <= 0 ? messages.length - 1 : index - 1;
        }
        
        const target = messages[index];
        if (target) {
            // Déplier si nécessaire pour voir le contenu
            target.classList.remove(this.selectors.COLLAPSED_CLASS);
            this._updateMessagePreview(target);
            
            // Scroll avec highlight visuel
            target.scrollIntoView({ behavior: 'smooth', block: 'center' });
            target.classList.add(this.selectors.HIGHLIGHT_CLASS);
            setTimeout(() => target.classList.remove(this.selectors.HIGHLIGHT_CLASS), 2000);
            
            this.currentMessageIndex[role] = index;
        }
    }
    
    /**
     * Sauvegarde l'état actuel de la navigation dans localStorage
     * Inclut les messages pliés, l'index de navigation et l'ID de conversation
     */
    saveNavigationState() {
        const state = {
            collapsed: Array.from(document.querySelectorAll(`${this.selectors.MESSAGE_WRAPPER}.${this.selectors.COLLAPSED_CLASS}`))
                .map(w => parseInt(w.dataset.messageIndex))
                .filter(index => !isNaN(index)),
            currentIndex: this.currentMessageIndex,
            conversationId: this.currentConversationId // Pour invalider si conversation change
        };
        localStorage.setItem('chat-navigation-state', JSON.stringify(state));
    }
    
    /**
     * Restaure l'état de navigation depuis localStorage
     * Vérifie que l'état correspond à la conversation actuelle avant de l'appliquer
     */
    restoreNavigationState() {
        const saved = localStorage.getItem('chat-navigation-state');
        if (saved) {
            try {
                const state = JSON.parse(saved);
                
                // Vérifier que c'est la même conversation
                if (state.conversationId !== this.currentConversationId) {
                    localStorage.removeItem('chat-navigation-state');
                    return;
                }
                
                // Restaurer les messages pliés
                state.collapsed?.forEach(index => {
                    const wrapper = document.querySelector(`[data-message-index="${index}"]`);
                    if (wrapper) {
                        wrapper.classList.add(this.selectors.COLLAPSED_CLASS);
                        this._updateMessagePreview(wrapper);
                    }
                });
                
                // Restaurer la position de navigation
                this.currentMessageIndex = state.currentIndex || { user: -1, assistant: -1 };
            } catch (e) {
                console.warn('Impossible de restaurer l\'état de navigation:', e);
                localStorage.removeItem('chat-navigation-state');
            }
        }
    }
    
    /**
     * Efface l'état de navigation sauvegardé et réinitialise les index
     */
    clearNavigationState() {
        localStorage.removeItem('chat-navigation-state');
        this.currentMessageIndex = { user: -1, assistant: -1 };
    }
    
    async exportChat() {
        if (this.mode === 'api' && window.pywebview && window.pywebview.api) {
            const chatData = {
                summary: this.conversationSummary,
                history: this.chatHistory
            };
            
            const result = await window.pywebview.api.save_conversation_dialog(chatData);
            
            if (result.success) {
                const successMessage = `Conversation exportée avec succès !\nFichier : ${result.path.split(/[\\/]/).pop()}`;
                this.appendMessageToChat('system', successMessage);
            } else if (!result.cancelled) {
                this.showError(`Erreur lors de l'export : ${result.error || 'Erreur inconnue'}`);
            }
        }
    }
    
    async loadConversations() {
        console.log('Loading conversations...');
        if (this.mode === 'api' && window.pywebview && window.pywebview.api) {
            try {
                const conversations = await window.pywebview.api.get_conversations();
                console.log('Conversations loaded:', conversations);
                this.conversations = conversations;
                this.displayConversations();
            } catch (error) {
                console.error('Erreur lors du chargement des conversations:', error);
            }
        } else {
            console.log('Conditions not met for loading conversations:', {
                mode: this.mode,
                pywebview: !!window.pywebview,
                api: !!(window.pywebview && window.pywebview.api)
            });
        }
    }
    
    displayConversations() {
        const conversationsList = document.getElementById('conversationsList');
        if (!conversationsList) return;
        
        conversationsList.innerHTML = '';
        
        if (this.conversations.length === 0) {
            conversationsList.innerHTML = '<div class="text-muted small">Aucune conversation sauvegardée</div>';
            return;
        }
        
        this.conversations.forEach(conv => {
            const convDiv = document.createElement('div');
            convDiv.className = 'conversation-item';
            if (conv.id === this.currentConversationId) {
                convDiv.classList.add('active');
            }
            
            // Icône de verrouillage interactive
            let lockIcon = '';
            if (conv.isLockedByMe) {
                lockIcon = '<i class="fas fa-lock-open lock-icon locked-by-me" title="Verrouillée par vous"></i>';
            } else if (conv.isLocked) {
                lockIcon = `<button class="btn btn-sm btn-link p-0 lock-icon-btn" 
                                onclick="window.toolboxController.forceReleaseLock('${conv.id}')" 
                                title="Verrouillée par ${conv.lockInfo}. Cliquez pour forcer le déverrouillage.">
                                <i class="fas fa-lock lock-icon locked-by-other"></i>
                            </button>`;
            }
            
            // Vérifier si c'est une branche - indicateur discret
            const forkInfo = conv.metadata?.forkInfo;
            let branchIcon = '';
            
            if (forkInfo) {
                // Simple icône de branche avec tooltip informatif
                const parentConv = this.conversations.find(
                    c => c.id === forkInfo.sourceConversationId
                );
                const parentTitle = parentConv ? parentConv.title : 'conversation non sauvegardée';
                
                // Icône discrète avec tooltip
                branchIcon = `<i class="fas fa-code-branch text-muted me-1" 
                    style="font-size: 0.85em;" 
                    title="Branche créée depuis: ${parentTitle}"></i> `;
            }
            
            // Formater la date
            const date = new Date(conv.updatedAt);
            const dateStr = date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
            
            convDiv.innerHTML = `
                <div class="d-flex justify-content-between align-items-center">
                    <div class="fw-bold">
                        ${branchIcon}${conv.title || 'Sans titre'}
                    </div>
                    ${lockIcon}
                </div>
                <div class="meta mb-2">${dateStr}</div>
                <div class="conversation-actions">
                    <button class="btn btn-sm btn-outline-primary load-btn" 
                        data-conv-id="${conv.id}"
                        title="${conv.isLocked && !conv.isLockedByMe ? 'Verrouillée par ' + conv.lockInfo : 'Charger'}">
                        <i class="fas fa-folder-open"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-secondary rename-btn" 
                        data-conv-id="${conv.id}"
                        title="${conv.isLocked && !conv.isLockedByMe ? 'Verrouillée par ' + conv.lockInfo : 'Renommer'}">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-info duplicate-btn" 
                        data-conv-id="${conv.id}"
                        title="Dupliquer (toujours disponible)">
                        <i class="fas fa-copy"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger delete-btn" 
                        data-conv-id="${conv.id}"
                        title="${conv.isLocked && !conv.isLockedByMe ? 'Verrouillée par ' + conv.lockInfo : 'Supprimer'}">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            `;
            
            // Attacher les événements aux boutons
            const loadBtn = convDiv.querySelector('.load-btn');
            if (loadBtn) {
                loadBtn.addEventListener('click', () => {
                    if (conv.isLocked && !conv.isLockedByMe) {
                        this.showLockedModal(conv);
                        return;
                    }
                    this.loadConversation(conv.id);
                });
            }
            
            const renameBtn = convDiv.querySelector('.rename-btn');
            if (renameBtn) {
                renameBtn.addEventListener('click', () => {
                    if (conv.isLocked && !conv.isLockedByMe) {
                        this.showLockedModal(conv);
                        return;
                    }
                    this.renameConversation(conv.id);
                });
            }
            
            const duplicateBtn = convDiv.querySelector('.duplicate-btn');
            if (duplicateBtn) {
                duplicateBtn.addEventListener('click', () => {
                    this.duplicateConversation(conv.id);
                });
            }
            
            const deleteBtn = convDiv.querySelector('.delete-btn');
            if (deleteBtn) {
                deleteBtn.addEventListener('click', () => {
                    if (conv.isLocked && !conv.isLockedByMe) {
                        this.showLockedModal(conv);
                        return;
                    }
                    this.deleteConversation(conv.id);
                });
            }
            
            conversationsList.appendChild(convDiv);
        });
    }
    
    _buildConversationPayload(title, isAiGenerated = false) {
        const cleanTitle = title.replace(/[\r\n]+/g, ' ').trim().substring(0, 100);

        const payload = {
            id: this.currentConversationId,
            title: cleanTitle,
            history: this.chatHistory,
            context: {
                fullContext: this.mainContext,
                metadata: {
                    projectPath: window.toolboxProjectPath || '',
                    filesIncluded: 0,
                    estimatedTokens: this.estimateTokens(this.mainContext)
                }
            },
            metadata: {
                mode: 'api',
                tags: [],
                ai_generated_title: isAiGenerated
            }
        };
        
        // AJOUT: Inclure forkInfo si présent
        if (this.forkInfo) {
            payload.metadata.forkInfo = this.forkInfo;
            // Nettoyer après utilisation
            this.forkInfo = null;
        }
        
        return payload;
    }
    
    async saveCurrentConversation() {
        // La garde est maintenant gérée par l'état du bouton (disabled)
        if (this.mode !== 'api' || !window.pywebview || !window.pywebview.api) return;

        const saveBtn = document.getElementById('saveConversationBtn');
        if (!saveBtn) return;

        // Sauvegarde rapide si la conversation a déjà un ID
        if (this.currentConversationId) {
            const originalContent = saveBtn.innerHTML;
            saveBtn.disabled = true;
            saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Sauvegarde...';

            try {
                const conversationData = this._buildConversationPayload(this.conversationSummary, false);
                const result = await window.pywebview.api.save_conversation(conversationData);

                if (result.success) {
                    this.appendMessageToChat('system', `Conversation sauvegardée: ${result.title}`);
                    await this.loadConversations();
                } else {
                    this.showError(`Erreur lors de la sauvegarde: ${result.error}`);
                }
            } catch (error) {
                this.showError(`Erreur lors de la sauvegarde: ${error}`);
            } finally {
                saveBtn.disabled = false;
                saveBtn.innerHTML = originalContent;
            }
            return;
        }

        // Première sauvegarde - ouvrir la modale
        const modalElement = document.getElementById('saveConversationModal');
        const modal = new bootstrap.Modal(modalElement);
        const titleInput = document.getElementById('conversationTitleInput');
        const suggestBtn = document.getElementById('suggestTitleBtn');
        const spinner = document.getElementById('title-suggestion-spinner');
        const confirmSaveBtn = document.getElementById('confirmSaveBtn');
        const charCountSpan = document.getElementById('titleCharCount');

        // Variable pour traquer si le titre a été généré par IA
        let titleGeneratedByAI = false;

        // Réinitialiser la modale
        // MODIFICATION: Pré-remplir avec le titre suggéré pour les branches
        if (this.suggestedBranchTitle) {
            titleInput.value = this.suggestedBranchTitle;
            titleInput.placeholder = 'Nouvelle branche';
            // Nettoyer après utilisation
            this.suggestedBranchTitle = null;
        } else {
            titleInput.value = this.conversationSummary || '';
            titleInput.placeholder = 'Nouvelle conversation';
        }
        titleInput.disabled = false;
        suggestBtn.classList.remove('d-none');
        spinner.classList.add('d-none');
        confirmSaveBtn.disabled = false;
        
        // Mettre à jour le compteur de caractères
        if (charCountSpan) {
            const updateCharCount = () => {
                const length = titleInput.value.length;
                charCountSpan.textContent = `${length} / 100 caractères`;
                if (length > 90) {
                    charCountSpan.classList.add('text-warning');
                } else {
                    charCountSpan.classList.remove('text-warning');
                }
                // Si l'utilisateur modifie le titre, ce n'est plus généré par IA
                titleGeneratedByAI = false;
            };
            updateCharCount();
            titleInput.addEventListener('input', updateCharCount);
        }
        
        modal.show();
        titleInput.focus();
        titleInput.select();

        // Gérer le bouton de suggestion IA
        const handleSuggest = async () => {
            // Afficher le spinner et désactiver les contrôles
            suggestBtn.classList.add('d-none');
            spinner.classList.remove('d-none');
            titleInput.disabled = true;
            confirmSaveBtn.disabled = true;

            try {
                const titleResult = await window.pywebview.api.generate_conversation_title(
                    this.chatHistory,
                    this.mainContext  // Passer le contexte principal
                );
                if (titleResult.success && titleResult.title) {
                    titleInput.value = titleResult.title;
                    titleGeneratedByAI = true; // Marquer que le titre vient de l'IA
                    // Mettre à jour le compteur
                    if (charCountSpan) {
                        const length = titleInput.value.length;
                        charCountSpan.textContent = `${length} / 100 caractères`;
                        if (length > 90) {
                            charCountSpan.classList.add('text-warning');
                        } else {
                            charCountSpan.classList.remove('text-warning');
                        }
                    }
                } else {
                    // Gérer le cas où la suggestion échoue
                    this.showError('Impossible de générer un titre. Veuillez saisir manuellement.');
                    titleInput.placeholder = "Saisissez un titre...";
                }
            } catch (error) {
                console.error('Erreur lors de la génération du titre:', error);
                this.showError(`Erreur de génération: ${error.message || error}`);
            } finally {
                // Toujours réactiver les contrôles à la fin
                spinner.classList.add('d-none');
                suggestBtn.classList.remove('d-none');
                titleInput.disabled = false;
                confirmSaveBtn.disabled = false;
                titleInput.focus();
                titleInput.select();
            }
        };

        suggestBtn.onclick = handleSuggest;

        // Gérer le clic sur le bouton de sauvegarde final
        const handleSave = async () => {
            const finalTitle = titleInput.value.trim() || titleInput.placeholder;

            // Nettoyer le titre : enlever les sauts de ligne et limiter la longueur
            const cleanTitle = finalTitle.replace(/[\r\n]+/g, ' ').trim().substring(0, 100);

            if (!cleanTitle) {
                alert('Le titre ne peut pas être vide');
                return;
            }

            const conversationData = this._buildConversationPayload(cleanTitle, titleGeneratedByAI);

            try {
                const result = await window.pywebview.api.save_conversation(conversationData);
                if (result.success) {
                    this.currentConversationId = result.id;
                    this.conversationSummary = result.title; // Mettre à jour le titre pour les sauvegardes rapides futures
                    this.appendMessageToChat('system', `Conversation sauvegardée: ${result.title}`);
                    await this.loadConversations();
                    modal.hide();
                } else {
                    this.showError(`Erreur lors de la sauvegarde: ${result.error}`);
                }
            } catch (error) {
                this.showError(`Erreur lors de la sauvegarde: ${error}`);
            }
        };

        // Attacher le gestionnaire d'événements
        confirmSaveBtn.onclick = handleSave;
        
        // Permettre la sauvegarde avec Enter
        titleInput.onkeypress = (e) => {
            if (e.key === 'Enter' && !confirmSaveBtn.disabled) {
                handleSave();
            }
        };
        
        // Nettoyer les gestionnaires lors de la fermeture
        modalElement.addEventListener('hidden.bs.modal', () => {
            suggestBtn.onclick = null;
            confirmSaveBtn.onclick = null;
            titleInput.onkeypress = null;
            titleInput.removeEventListener('input', titleInput.oninput);
        }, { once: true });
    }
    
    async loadConversation(conversationId) {
        if (this.mode !== 'api' || !window.pywebview || !window.pywebview.api) return;
        
        try {
            const conversation = await window.pywebview.api.get_conversation_details(conversationId);
            if (conversation) {
                // Sauvegarder la conversation actuelle si elle a des modifications
                if (this.currentConversationId && this.chatHistory.length > 0) {
                    if (confirm('Voulez-vous sauvegarder la conversation actuelle avant de charger une nouvelle ?')) {
                        await this.saveCurrentConversation();
                    }
                }
                
                // Charger la nouvelle conversation
                this.currentConversationId = conversationId;
                this.chatHistory = conversation.history || [];
                this.mainContext = conversation.context?.fullContext || '';
                this.conversationSummary = conversation.title || '';
                
                // Mettre à jour l'affichage
                this.refreshChatDisplay();
                this.updateContextStatus(!!this.mainContext);
                this.updateSaveButtonState();
                this.displayConversations();
                
                // Restaurer l'état de navigation après le chargement
                setTimeout(() => {
                    this.restoreNavigationState();
                }, 150);
                
                // Message système après le rafraîchissement
                setTimeout(() => {
                    this.appendMessageToChat('system', `Conversation "${conversation.title}" chargée`);
                }, 100);
            }
        } catch (error) {
            this.showError(`Erreur lors du chargement: ${error}`);
        }
    }
    
    showLockedModal(conv) {
        // Vérifier que Bootstrap est disponible
        if (!window.bootstrap) {
            console.error('Bootstrap non disponible');
            return;
        }
        
        const modalElement = document.getElementById('lockedConversationModal');
        if (!modalElement) {
            console.error('Modal lockedConversationModal non trouvé');
            return;
        }
        
        const modal = new bootstrap.Modal(modalElement);
        
        // Mettre à jour les informations du verrou
        const lockOwnerInfo = document.getElementById('lockOwnerInfo');
        if (lockOwnerInfo && conv.lockInfo) {
            lockOwnerInfo.textContent = conv.lockInfo;
        }
        
        // Configurer le bouton Dupliquer
        const duplicateBtn = document.getElementById('duplicateFromLockModal');
        if (duplicateBtn) {
            // Retirer l'ancien listener s'il existe
            const newDuplicateBtn = duplicateBtn.cloneNode(true);
            duplicateBtn.parentNode.replaceChild(newDuplicateBtn, duplicateBtn);
            
            // Ajouter le nouveau listener
            newDuplicateBtn.addEventListener('click', () => {
                modal.hide();
                this.duplicateConversation(conv.id);
            });
        }
        
        // Afficher le modal
        modal.show();
    }
    
    async duplicateConversation(conversationId) {
        if (this.mode !== 'api' || !window.pywebview || !window.pywebview.api) return;
        
        try {
            const result = await window.pywebview.api.duplicate_conversation(conversationId);
            if (result.success) {
                this.appendMessageToChat('system', `Conversation dupliquée: ${result.title}`);
                await this.loadConversations();
            } else {
                this.showError(`Erreur lors de la duplication: ${result.error}`);
            }
        } catch (error) {
            this.showError(`Erreur lors de la duplication: ${error}`);
        }
    }
    
    async renameConversation(conversationId) {
        if (this.mode !== 'api' || !window.pywebview || !window.pywebview.api) return;
        
        // Trouver la conversation dans la liste
        const conversation = this.conversations.find(c => c.id === conversationId);
        if (!conversation) {
            this.showError('Conversation non trouvée');
            return;
        }
        
        const modalElement = document.getElementById('saveConversationModal');
        const modal = new bootstrap.Modal(modalElement);
        const titleInput = document.getElementById('conversationTitleInput');
        const suggestBtn = document.getElementById('suggestTitleBtn');
        const spinner = document.getElementById('title-suggestion-spinner');
        const confirmSaveBtn = document.getElementById('confirmSaveBtn');
        const charCountSpan = document.getElementById('titleCharCount');
        const modalTitle = document.getElementById('saveConversationModalLabel');
        
        // Adapter le titre de la modale
        modalTitle.innerHTML = '<i class="fas fa-edit"></i> Renommer la conversation';
        
        // Variables pour le suivi
        let titleGeneratedByAI = false;
        const originalTitle = conversation.title;
        
        // Charger les détails de la conversation pour la baguette magique
        let conversationDetails = null;
        try {
            conversationDetails = await window.pywebview.api.get_conversation_details(conversationId);
        } catch (error) {
            console.error('Impossible de charger les détails de la conversation:', error);
        }
        
        // Initialiser la modale avec le titre actuel
        titleInput.value = originalTitle;
        titleInput.placeholder = 'Titre de la conversation';
        titleInput.disabled = false;
        suggestBtn.classList.remove('d-none');
        spinner.classList.add('d-none');
        confirmSaveBtn.disabled = false;
        
        // Mettre à jour le compteur de caractères
        const updateCharCount = () => {
            const length = titleInput.value.length;
            charCountSpan.textContent = `${length} / 100 caractères`;
            charCountSpan.classList.toggle('text-warning', length > 90);
            titleGeneratedByAI = false;
        };
        updateCharCount();
        titleInput.addEventListener('input', updateCharCount);
        
        modal.show();
        titleInput.focus();
        titleInput.select();
        
        // Gérer la suggestion IA
        const handleSuggest = async () => {
            suggestBtn.classList.add('d-none');
            spinner.classList.remove('d-none');
            titleInput.disabled = true;
            confirmSaveBtn.disabled = true;
            
            try {
                if (conversationDetails) {
                    const titleResult = await window.pywebview.api.generate_conversation_title(
                        conversationDetails.history || [],
                        conversationDetails.context?.fullContext || ''
                    );
                    if (titleResult.success && titleResult.title) {
                        titleInput.value = titleResult.title;
                        titleGeneratedByAI = true;
                        updateCharCount();
                    } else {
                        this.showError('Impossible de générer un titre');
                    }
                } else {
                    this.showError('Détails de la conversation non disponibles');
                }
            } catch (error) {
                this.showError(`Erreur: ${error.message || error}`);
            } finally {
                spinner.classList.add('d-none');
                suggestBtn.classList.remove('d-none');
                titleInput.disabled = false;
                confirmSaveBtn.disabled = false;
                titleInput.focus();
            }
        };
        
        suggestBtn.onclick = handleSuggest;
        
        // Gérer la confirmation du renommage
        const handleRename = async () => {
            const newTitle = titleInput.value.trim();
            
            if (!newTitle) {
                alert('Le titre ne peut pas être vide');
                return;
            }
            
            if (newTitle === originalTitle) {
                modal.hide();
                return;
            }
            
            try {
                const result = await window.pywebview.api.update_conversation_title(conversationId, newTitle);
                if (result.success) {
                    // Mettre à jour le titre local si c'est la conversation courante
                    if (this.currentConversationId === conversationId) {
                        this.conversationSummary = result.title;
                    }
                    this.appendMessageToChat('system', `Conversation renommée: ${result.title}`);
                    await this.loadConversations();
                    modal.hide();
                } else {
                    this.showError(`Erreur: ${result.error}`);
                }
            } catch (error) {
                this.showError(`Erreur: ${error}`);
            }
        };
        
        confirmSaveBtn.onclick = handleRename;
        
        titleInput.onkeypress = (e) => {
            if (e.key === 'Enter' && !confirmSaveBtn.disabled) {
                handleRename();
            }
        };
        
        // Nettoyer lors de la fermeture
        modalElement.addEventListener('hidden.bs.modal', () => {
            // Restaurer le titre original de la modale
            modalTitle.innerHTML = '<i class="fas fa-save"></i> Sauvegarder la conversation';
            suggestBtn.onclick = null;
            confirmSaveBtn.onclick = null;
            titleInput.onkeypress = null;
            titleInput.removeEventListener('input', updateCharCount);
        }, { once: true });
    }
    
    async deleteConversation(conversationId) {
        if (this.mode !== 'api' || !window.pywebview || !window.pywebview.api) return;
        
        if (!confirm('Êtes-vous sûr de vouloir supprimer cette conversation ?')) return;
        
        try {
            const result = await window.pywebview.api.delete_conversation(conversationId);
            if (result.success) {
                if (conversationId === this.currentConversationId) {
                    this.currentConversationId = null;
                    this.clearChat();
                }
                this.appendMessageToChat('system', 'Conversation supprimée');
                await this.loadConversations();
            } else {
                this.showError(`Erreur lors de la suppression: ${result.error}`);
            }
        } catch (error) {
            this.showError(`Erreur lors de la suppression: ${error}`);
        }
    }
    
    async forceReleaseLock(conversationId) {
        if (!confirm('Êtes-vous sûr de vouloir forcer le déverrouillage de cette conversation ?')) return;

        try {
            if (window.pywebview && window.pywebview.api) {
                const result = await window.pywebview.api.force_release_lock(conversationId);
                if (result.success) {
                    this.appendMessageToChat('system', `Verrou libéré pour la conversation.`);
                    await this.loadConversations();
                } else {
                    this.showError(`Erreur: ${result.error}`);
                }
            }
        } catch (error) {
            this.showError(`Erreur lors du déverrouillage: ${error.message}`);
        }
    }
    
    /**
     * Rafraîchit l'affichage complet du chat en recréant tous les messages
     */
    refreshChatDisplay() {
        const chatDisplayArea = document.querySelector(this.selectors.CHAT_DISPLAY);
        if (!chatDisplayArea) return;
        
        chatDisplayArea.innerHTML = '';
        
        // Afficher tous les messages de l'historique avec leur index correct
        this.chatHistory.forEach((msg, index) => {
            // Passer l'index explicite pour chaque message
            this.appendMessageToChat(msg.role, msg.content, null, index);
        });
        
        // Mettre à jour le compteur de tokens
        this.updateTokenCount();
        
        // Scroller vers le bas pour voir les derniers messages
        this.autoScrollToBottom();
    }
    
    estimateTokens(text) {
        // Estimation simple: ~4 caractères par token
        return Math.ceil(text.length / 4);
    }
    
    updateTokenCount() {
        // Calculer le nombre total de tokens dans l'historique
        let totalTokens = 0;
        this.chatHistory.forEach(msg => {
            totalTokens += this.estimateTokens(msg.content);
        });
        
        // Mettre à jour l'affichage
        const tokenSpan = document.getElementById('chat-token-count');
        if (tokenSpan) {
            tokenSpan.textContent = totalTokens.toLocaleString();
        }
    }
    
    updateContextStatus(hasContext) {
        const contextStatus = document.getElementById('contextStatus');
        if (contextStatus) {
            if (hasContext) {
                contextStatus.classList.remove('no-context');
                contextStatus.innerHTML = '<i class="fas fa-check-circle text-success"></i> Contexte importé';
            } else {
                contextStatus.classList.add('no-context');
                contextStatus.innerHTML = '<i class="fas fa-exclamation-circle text-warning"></i> Aucun contexte importé';
            }
        }
        
        // Mettre à jour l'état des boutons
        this.updateButtonStates();
    }
    
    async closeToolbox() {
        console.log('Fermeture de la Toolbox...');
        
        // Demander confirmation si des modifications non sauvegardées
        if (this.chatHistory.length > 0 && !this.currentConversationId) {
            if (!confirm('Vous avez une conversation non sauvegardée. Voulez-vous vraiment fermer ?')) {
                return;
            }
        }
        
        try {
            // Libérer le verrou de la conversation active
            if (this.currentConversationId) {
                console.log(`Libération du verrou pour la conversation ${this.currentConversationId}`);
                await window.pywebview.api.release_conversation_lock(this.currentConversationId);
            }
            
            // Fermer la fenêtre
            await window.pywebview.api.close_toolbox_window();
        } catch (error) {
            console.error('Erreur lors de la fermeture:', error);
            // Essayer de fermer quand même
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.close_toolbox_window();
            }
        }
    }
    
    async releaseAllLocks() {
        if (this.mode !== 'api' || !window.pywebview || !window.pywebview.api) return;
        
        if (!confirm('Voulez-vous libérer tous vos verrous actifs ?\n\nCela permettra aux autres instances d\'accéder aux conversations que vous avez verrouillées.')) {
            return;
        }
        
        try {
            const result = await window.pywebview.api.release_all_instance_locks();
            if (result.success) {
                this.appendMessageToChat('system', result.message);
                // Rafraîchir la liste des conversations
                await this.loadConversations();
                
                // Si la conversation courante était verrouillée, réinitialiser
                if (result.count > 0 && this.currentConversationId) {
                    this.currentConversationId = null;
                }
            } else {
                this.showError(`Erreur: ${result.error}`);
            }
        } catch (error) {
            this.showError(`Erreur lors de la libération des verrous: ${error}`);
        }
    }
    
    async loadPrompts() {
        try {
            if (window.pywebview && window.pywebview.api) {
                const prompts = await window.pywebview.api.get_available_prompts();
                const container = document.getElementById('promptButtonsContainer');
                if (!container) return;
                
                container.innerHTML = '';
                
                prompts.forEach((prompt) => {
                    const button = document.createElement('button');
                    button.className = 'btn btn-outline-primary prompt-button';
                    button.dataset.promptFile = prompt.filename;
                    
                    // En mode browser, ajouter une icône d'envoi pour clarifier l'action
                    if (this.mode === 'browser') {
                        button.innerHTML = `<i class="fas fa-paper-plane"></i> ${prompt.name}`;
                        button.title = "Cliquer pour envoyer ce prompt au chatbot";
                    } else {
                        button.innerHTML = `<i class="fas fa-file-alt"></i> ${prompt.name}`;
                        button.title = "Cliquer pour ajouter/retirer ce prompt";
                    }
                    
                    // Désactiver si pas de contexte
                    if (!this.mainContext || this.mainContext.trim() === '') {
                        button.disabled = true;
                        button.title = "Veuillez d'abord importer le contexte du projet";
                    }
                    
                    button.addEventListener('click', () => this.togglePrompt(button));
                    
                    container.appendChild(button);
                });
            }
        } catch (error) {
            console.error('Erreur lors du chargement des prompts:', error);
            this.showError('Erreur lors du chargement des prompts.');
        }
    }
    
    async togglePrompt(button) {
        const promptFile = button.dataset.promptFile;
        console.log(`togglePrompt appelé - fichier: ${promptFile}, mode: ${this.mode}`);
        
        // En mode browser, on ne fait pas de toggle, on envoie directement
        if (this.mode === 'browser') {
            console.log('Mode browser détecté - envoi direct du prompt');
            
            // Désactiver temporairement le bouton pour éviter les double-clics
            button.disabled = true;
            button.classList.add('active');
            
            try {
                if (window.pywebview && window.pywebview.api) {
                    let messageToSend = '';
                    
                    if (promptFile.endsWith('_diff.md')) {
                        console.log('Prompt avec git diff détecté');
                        // Prompt nécessitant git diff
                        const diffResult = await window.pywebview.api.run_git_diff();
                        console.log('Résultat de run_git_diff:', diffResult);
                        
                        if (diffResult.error) {
                            console.error('Erreur git diff:', diffResult.error);
                            this.showError(diffResult.error);
                            button.classList.remove('active');
                            button.disabled = false;
                            return;
                        }
                        
                        console.log('Diff brut:', diffResult.diff);
                        console.log('Longueur du diff:', diffResult.diff ? diffResult.diff.length : 0);
                        console.log('Diff vide?', !diffResult.diff || diffResult.diff.trim() === '');
                        
                        if (!diffResult.diff || diffResult.diff.trim() === '') {
                            this.appendSystemMessage('Aucune modification détectée (git diff --staged est vide).');
                            button.classList.remove('active');
                            button.disabled = false;
                            return;
                        }
                        
                        const promptContent = await window.pywebview.api.get_prompt_content(promptFile);
                        messageToSend = `## Diff des modifications :\n\n\`\`\`diff\n${diffResult.diff}\n\`\`\`\n\n---\n\n${promptContent}`;
                    } else {
                        // Prompt normal
                        console.log('Chargement du contenu du prompt...');
                        messageToSend = await window.pywebview.api.get_prompt_content(promptFile);
                        console.log(`Contenu du prompt chargé, taille: ${messageToSend.length} caractères`);
                    }
                    
                    // En mode browser, envoyer directement au chatbot
                    console.log('Envoi du message au provider browser...');
                    const response = await this.provider.sendMessage(messageToSend);
                    console.log('Réponse du provider:', response);
                    
                    if (response.error) {
                        this.showError(response.error);
                    } else {
                        this.appendSystemMessage(`Prompt "${button.textContent.trim()}" envoyé au chatbot.`);
                    }
                    
                    // Réactiver le bouton et retirer la classe active
                    button.classList.remove('active');
                    button.disabled = false;
                }
            } catch (error) {
                console.error('Erreur lors du traitement du prompt:', error);
                this.showError(`Erreur lors du chargement du prompt: ${error.message}`);
                button.classList.remove('active');
                button.disabled = false;
            }
            
        } else {
            // Mode API - comportement toggle existant
            if (this.activePrompts.has(promptFile)) {
                // Désactiver le prompt
                this.activePrompts.delete(promptFile);
                button.classList.remove('active');
            } else {
                // Activer le prompt
                this.activePrompts.add(promptFile);
                button.classList.add('active');
                
                try {
                    if (window.pywebview && window.pywebview.api) {
                        let messageToSend = '';
                        
                        if (promptFile.endsWith('_diff.md')) {
                            // Prompt nécessitant git diff
                            const diffResult = await window.pywebview.api.run_git_diff();
                            
                            if (diffResult.error) {
                                this.showError(diffResult.error);
                                this.activePrompts.delete(promptFile);
                                button.classList.remove('active');
                                return;
                            }
                            
                            if (!diffResult.diff || diffResult.diff.trim() === '') {
                                this.appendSystemMessage('Aucune modification détectée (git diff --staged est vide).');
                                this.activePrompts.delete(promptFile);
                                button.classList.remove('active');
                                return;
                            }
                            
                            const promptContent = await window.pywebview.api.get_prompt_content(promptFile);
                            messageToSend = `## Diff des modifications :\n\n\`\`\`diff\n${diffResult.diff}\n\`\`\`\n\n---\n\n${promptContent}`;
                        } else {
                            // Prompt normal
                            messageToSend = await window.pywebview.api.get_prompt_content(promptFile);
                        }
                        
                        // En mode API, mettre dans le textarea
                        const input = document.getElementById('chatMessageInput');
                        if (input) {
                            const currentText = input.value;
                            if (currentText.trim()) {
                                input.value = currentText + '\n\n---\n\n' + messageToSend;
                            } else {
                                input.value = messageToSend;
                            }
                            // Ajuster la hauteur du textarea
                            input.style.height = 'auto';
                            input.style.height = (input.scrollHeight) + 'px';
                            input.focus();
                        }
                    }
                } catch (error) {
                    console.error('Erreur lors du chargement du prompt:', error);
                    this.showError('Erreur lors du chargement du prompt.');
                }
            }
        }
    }
    
    async handleGitDiff() {
        try {
            this.hideError();
            
            if (window.pywebview && window.pywebview.api) {
                console.log('Appel de run_git_diff...');
                const diffResult = await window.pywebview.api.run_git_diff();
                console.log('Résultat complet de run_git_diff:', JSON.stringify(diffResult));
                
                if (diffResult.error) {
                    console.error('Erreur git diff:', diffResult.error);
                    this.showError(diffResult.error);
                    return;
                }
                
                console.log('Diff brut:', diffResult.diff);
                console.log('Longueur du diff:', diffResult.diff ? diffResult.diff.length : 0);
                
                if (!diffResult.diff || diffResult.diff.trim() === '') {
                    this.appendSystemMessage('Aucune modification détectée (git diff --staged est vide).');
                    return;
                }
                
                let messageToSend = '';
                
                try {
                    const reviewPromptContent = await window.pywebview.api.get_prompt_content('04_revue_de_diff.md');
                    messageToSend = `${reviewPromptContent}\n\n## Diff des modifications :\n\n\`\`\`diff\n${diffResult.diff}\n\`\`\``;
                } catch (error) {
                    messageToSend = `Voici mes dernières modifications (git diff) :\n\n\`\`\`diff\n${diffResult.diff}\n\`\`\``;
                }
                
                if (this.mode === 'api') {
                    // Mode API : mettre dans le textarea
                    const input = document.getElementById('chatMessageInput');
                    if (input) {
                        input.value = messageToSend;
                        input.style.height = 'auto';
                        input.style.height = (input.scrollHeight) + 'px';
                        
                        const reviewButton = document.querySelector('[data-prompt-file="04_revue_de_diff.md"]');
                        if (reviewButton) {
                            reviewButton.classList.add('active');
                            this.activePrompts.add('04_revue_de_diff.md');
                        }
                        
                        this.appendSystemMessage('Les modifications ont été chargées avec le prompt de revue. Vous pouvez maintenant envoyer le message pour obtenir une analyse.');
                    }
                } else {
                    // Mode browser : envoyer directement au chatbot
                    console.log('Mode browser : envoi du git diff au chatbot');
                    const response = await this.provider.sendMessage(messageToSend);
                    
                    if (response.error) {
                        this.showError(response.error);
                    } else {
                        this.appendSystemMessage('Les modifications (git diff) ont été envoyées au chatbot pour analyse.');
                    }
                }
            }
        } catch (error) {
            console.error('Erreur lors de l\'exécution de git diff:', error);
            this.showError('Erreur lors de l\'exécution de git diff.');
        }
    }
}

// Variable globale pour le contrôleur
let toolboxController = null;

// Fonction d'initialisation appelée par Python
window.initializeToolboxMode = function() {
    console.log('Initialisation du mode Toolbox:', window.toolboxMode);
    toolboxController = new ToolboxController();
    // Exposer l'instance à la fenêtre pour les boutons HTML
    window.toolboxController = toolboxController;
};

// Initialisation au chargement du DOM
document.addEventListener('DOMContentLoaded', () => {
    // Si le mode est déjà défini, initialiser le contrôleur
    if (window.toolboxMode) {
        toolboxController = new ToolboxController();
        // Exposer l'instance à la fenêtre pour les boutons HTML
        window.toolboxController = toolboxController;
    }
    
    // Gestionnaires d'événements
    const importContextBtn = document.getElementById('importContextBtn');
    if (importContextBtn) {
        importContextBtn.addEventListener('click', () => {
            if (toolboxController) {
                toolboxController.importContext();
            }
        });
    }
    
    const sendChatMessageBtn = document.getElementById('sendChatMessageBtn');
    const chatMessageInput = document.getElementById('chatMessageInput');
    
    if (sendChatMessageBtn) {
        sendChatMessageBtn.addEventListener('click', () => {
            if (toolboxController && chatMessageInput) {
                const message = chatMessageInput.value.trim();
                if (message) {
                    toolboxController.sendMessage(message);
                    chatMessageInput.value = '';
                }
            }
        });
    }
    
    if (chatMessageInput) {
        chatMessageInput.addEventListener('keypress', (event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                if (toolboxController) {
                    const message = chatMessageInput.value.trim();
                    if (message) {
                        toolboxController.sendMessage(message);
                        chatMessageInput.value = '';
                    }
                }
            }
        });
        
        chatMessageInput.addEventListener('input', () => {
            chatMessageInput.style.height = 'auto';
            chatMessageInput.style.height = (chatMessageInput.scrollHeight) + 'px';
        });
    }
    
    const clearChatBtn = document.getElementById('clearChatBtn');
    if (clearChatBtn) {
        clearChatBtn.addEventListener('click', () => {
            if (toolboxController) {
                toolboxController.clearChat();
            }
        });
    }
    
    const exportChatBtn = document.getElementById('exportChatBtn');
    if (exportChatBtn) {
        exportChatBtn.addEventListener('click', async () => {
            if (toolboxController) {
                exportChatBtn.disabled = true;
                const originalContent = exportChatBtn.innerHTML;
                exportChatBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Export en cours...';
                
                await toolboxController.exportChat();
                
                exportChatBtn.disabled = false;
                exportChatBtn.innerHTML = originalContent;
            }
        });
    }
    
    const gitDiffBtn = document.getElementById('gitDiffBtn');
    if (gitDiffBtn) {
        gitDiffBtn.addEventListener('click', () => {
            if (toolboxController) {
                toolboxController.handleGitDiff();
            }
        });
    }
    
    // Gestionnaires pour les conversations
    const saveConversationBtn = document.getElementById('saveConversationBtn');
    if (saveConversationBtn) {
        saveConversationBtn.addEventListener('click', async () => {
            if (toolboxController) {
                await toolboxController.saveCurrentConversation();
            }
        });
    }
    
    const refreshConversationsBtn = document.getElementById('refreshConversationsBtn');
    if (refreshConversationsBtn) {
        refreshConversationsBtn.addEventListener('click', async () => {
            if (toolboxController) {
                refreshConversationsBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
                await toolboxController.loadConversations();
                refreshConversationsBtn.innerHTML = '<i class="fas fa-sync-alt"></i>';
            }
        });
    }
    
    // Gestionnaire pour le bouton Libérer mes verrous
    const releaseLocksBtn = document.getElementById('releaseLocksBtn');
    if (releaseLocksBtn) {
        releaseLocksBtn.addEventListener('click', async () => {
            if (toolboxController) {
                await toolboxController.releaseAllLocks();
            }
        });
    }
    
    // Gestionnaire pour le bouton Fermer
    const closeToolboxBtn = document.getElementById('closeToolboxBtn');
    if (closeToolboxBtn) {
        closeToolboxBtn.addEventListener('click', async () => {
            if (toolboxController) {
                await toolboxController.closeToolbox();
            }
        });
    }
    
    
    // Charger les prompts après un délai
    setTimeout(() => {
        if (toolboxController) {
            toolboxController.loadPrompts();
        }
    }, 100);
    
    // Réessayer si l'API n'était pas prête
    setTimeout(() => {
        const promptButtonsContainer = document.getElementById('promptButtonsContainer');
        if (promptButtonsContainer && promptButtonsContainer.children.length === 0 && toolboxController) {
            console.log('Retrying to load prompts after delay...');
            toolboxController.loadPrompts();
        }
    }, 1000);
});