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
        
        // Utiliser l'API existante
        if (window.pywebview && window.pywebview.api) {
            return await window.pywebview.api.send_to_llm(historyToSend, false);
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
        
        // Utiliser l'API de streaming
        if (window.pywebview && window.pywebview.api) {
            return await window.pywebview.api.send_to_llm_stream(historyToSend, callbackId);
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
        
        // Initialiser le provider selon le mode
        this.initializeProvider();
        
        // Initialiser l'interface
        this.initializeUI();
        
        // Vérifier le streaming
        this.checkStreamingStatus();
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
                    } else {
                        this.showError(result.error || 'Erreur lors de l\'import du contexte');
                    }
                } else {
                    this.showError('Aucun contexte disponible. Veuillez d\'abord générer un contexte depuis la fenêtre principale.');
                }
            }
        } catch (error) {
            console.error('Erreur lors de l\'import du contexte:', error);
            this.showError('Erreur lors de l\'import du contexte.');
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
    
    // Méthode pour ajouter un message au chat (mode API uniquement)
    appendMessageToChat(role, content, existingDiv = null, messageIndex = null) {
        if (this.mode !== 'api') return null;
        
        const chatDisplayArea = document.getElementById('chatDisplayArea');
        if (!chatDisplayArea) return null;
        
        if (existingDiv) {
            // Mise à jour d'un message existant (pour le streaming)
            const contentDiv = existingDiv.querySelector('.message-content');
            contentDiv.textContent = content;
            contentDiv.dataset.rawContent = content;
            contentDiv.dataset.markdownContent = marked.parse(content);
            this.autoScrollToBottom();
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
        contentDiv.style.whiteSpace = 'pre-wrap';
        contentDiv.style.wordBreak = 'break-word';
        
        // Stocker les deux versions du contenu
        contentDiv.dataset.rawContent = content;
        contentDiv.dataset.markdownContent = marked.parse(content);
        contentDiv.dataset.isMarkdown = 'true'; // Markdown par défaut
        
        // Afficher en markdown par défaut
        contentDiv.innerHTML = contentDiv.dataset.markdownContent;
        contentDiv.style.whiteSpace = 'normal';
        
        messageDiv.appendChild(contentDiv);
        
        // Ajouter les boutons de contrôle pour user et assistant
        if (role === 'user' || role === 'assistant') {
            this.addMessageControls(messageDiv, role, contentDiv);
        }
        
        messageWrapper.appendChild(messageDiv);
        chatDisplayArea.appendChild(messageWrapper);
        this.autoScrollToBottom();
        
        // Ajouter les boutons de copie aux blocs de code si c'est un message assistant
        if (role === 'assistant') {
            this.addCodeCopyButtons(contentDiv);
        }
        
        return messageDiv;
    }
    
    addMessageControls(messageDiv, role, contentDiv) {
        // Créer les boutons
        const buttonsContainer = document.createElement('div');
        buttonsContainer.className = 'buttons-bottom';
        buttonsContainer.style.cssText = 'display: flex; gap: 5px;';
        
        // Pour les messages utilisateur, ajouter un bouton d'édition
        if (role === 'user' && this.provider.getCapabilities().edit) {
            const editBtn = document.createElement('button');
            editBtn.className = 'btn btn-sm btn-outline-secondary edit-btn';
            editBtn.innerHTML = '<i class="fas fa-edit"></i>';
            editBtn.title = 'Éditer ce message';
            editBtn.style.cssText = 'opacity: 0.7; padding: 2px 6px; font-size: 12px;';
            
            editBtn.addEventListener('click', () => {
                this.editUserMessage(messageDiv, contentDiv);
            });
            
            buttonsContainer.appendChild(editBtn);
        }
        
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
        messageDiv.appendChild(buttonsContainer);
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
        // ... (logique d'édition existante)
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
        }
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
};

// Initialisation au chargement du DOM
document.addEventListener('DOMContentLoaded', () => {
    // Si le mode est déjà défini, initialiser le contrôleur
    if (window.toolboxMode) {
        toolboxController = new ToolboxController();
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