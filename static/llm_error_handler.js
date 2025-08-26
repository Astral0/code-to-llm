/**
 * Gestionnaire d'erreurs LLM avec notifications visuelles
 */

class LLMErrorHandler {
    constructor() {
        this.currentNotification = null;
        this.errorHistory = [];
        this.maxHistorySize = 50;
        
        // Créer le conteneur de notifications s'il n'existe pas
        this.createNotificationContainer();
        
        // Enregistrer le handler global
        window.handleLLMError = this.handleError.bind(this);
    }
    
    createNotificationContainer() {
        if (!document.getElementById('llm-notification-container')) {
            const container = document.createElement('div');
            container.id = 'llm-notification-container';
            container.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 10000;
                max-width: 400px;
                pointer-events: none;
            `;
            document.body.appendChild(container);
        }
    }
    
    handleError(errorData) {
        // Ajouter à l'historique
        this.errorHistory.push({
            ...errorData,
            timestamp: new Date(errorData.timestamp * 1000)
        });
        
        // Limiter la taille de l'historique
        if (this.errorHistory.length > this.maxHistorySize) {
            this.errorHistory.shift();
        }
        
        // Afficher la notification
        this.showNotification(errorData);
        
        // Émettre un événement personnalisé
        window.dispatchEvent(new CustomEvent('llm-error', { detail: errorData }));
    }
    
    showNotification(errorData) {
        const container = document.getElementById('llm-notification-container');
        
        // Supprimer l'ancienne notification si elle existe
        if (this.currentNotification) {
            this.currentNotification.remove();
        }
        
        // Créer la nouvelle notification
        const notification = document.createElement('div');
        notification.className = 'llm-error-notification';
        
        // Déterminer le type et la couleur
        const isRetrying = errorData.attempt > 0 && errorData.wait_time > 0;
        const isCritical = errorData.message.includes('critique') || errorData.attempt === -1;
        const isBasculement = errorData.message.includes('Basculement');
        
        let bgColor = '#ff6b6b'; // Rouge pour les erreurs
        let icon = '⚠️';
        
        if (isRetrying) {
            bgColor = '#ffd93d'; // Jaune pour les retry
            icon = '🔄';
        } else if (isBasculement) {
            bgColor = '#4ecdc4'; // Turquoise pour le basculement
            icon = '🔀';
        } else if (isCritical) {
            bgColor = '#e74c3c'; // Rouge foncé pour le critique
            icon = '❌';
        }
        
        notification.style.cssText = `
            background: ${bgColor};
            color: white;
            padding: 15px 20px;
            border-radius: 8px;
            margin-bottom: 10px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            animation: slideIn 0.3s ease-out;
            pointer-events: auto;
            cursor: pointer;
            transition: opacity 0.3s ease;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        `;
        
        // Contenu de la notification
        let content = `
            <div style="display: flex; align-items: start; gap: 12px;">
                <span style="font-size: 20px;">${icon}</span>
                <div style="flex: 1;">
                    <div style="font-weight: 600; margin-bottom: 4px;">
                        ${this.getTitle(errorData)}
                    </div>
                    <div style="font-size: 14px; opacity: 0.95;">
                        ${errorData.message}
                    </div>
        `;
        
        // Ajouter une barre de progression si c'est un retry
        if (isRetrying && errorData.wait_time > 0) {
            content += `
                    <div style="margin-top: 8px;">
                        <div style="background: rgba(255,255,255,0.3); height: 4px; border-radius: 2px; overflow: hidden;">
                            <div class="retry-progress" style="background: white; height: 100%; width: 100%; 
                                animation: progress ${errorData.wait_time}s linear;">
                            </div>
                        </div>
                        <div style="font-size: 12px; margin-top: 4px; opacity: 0.9;">
                            Nouvelle tentative dans ${errorData.wait_time.toFixed(1)}s
                        </div>
                    </div>
            `;
        }
        
        content += `
                </div>
                <button onclick="this.parentElement.parentElement.style.opacity='0'; 
                    setTimeout(() => this.parentElement.parentElement.remove(), 300);" 
                    style="background: none; border: none; color: white; cursor: pointer; 
                    font-size: 20px; padding: 0; opacity: 0.7; transition: opacity 0.2s;"
                    onmouseover="this.style.opacity='1'" 
                    onmouseout="this.style.opacity='0.7'">
                    ×
                </button>
            </div>
        `;
        
        notification.innerHTML = content;
        container.appendChild(notification);
        this.currentNotification = notification;
        
        // Auto-suppression après un délai
        const autoRemoveDelay = isRetrying ? (errorData.wait_time + 1) * 1000 : 8000;
        setTimeout(() => {
            if (notification.parentElement) {
                notification.style.opacity = '0';
                setTimeout(() => notification.remove(), 300);
            }
        }, autoRemoveDelay);
    }
    
    getTitle(errorData) {
        if (errorData.message.includes('Basculement')) {
            return 'Changement de serveur';
        } else if (errorData.attempt === -1) {
            return 'Erreur critique';
        } else if (errorData.attempt > 0) {
            return `Tentative ${errorData.attempt}`;
        } else {
            return 'Notification LLM';
        }
    }
    
    getErrorHistory() {
        return this.errorHistory;
    }
    
    clearHistory() {
        this.errorHistory = [];
    }
    
    showHealthStatus(healthData) {
        // Afficher un panneau avec le statut de santé des endpoints
        const container = document.getElementById('llm-notification-container');
        
        const statusPanel = document.createElement('div');
        statusPanel.className = 'llm-health-status';
        statusPanel.style.cssText = `
            background: white;
            color: #333;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            animation: slideIn 0.3s ease-out;
            pointer-events: auto;
            margin-bottom: 10px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        `;
        
        let content = '<h4 style="margin: 0 0 10px 0;">Statut des serveurs LLM</h4>';
        content += '<div style="font-size: 14px;">';
        
        for (const [endpoint, health] of Object.entries(healthData)) {
            const statusIcon = this.getStatusIcon(health.state);
            const successRate = (health.success_rate * 100).toFixed(1);
            
            content += `
                <div style="display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid #eee;">
                    <span>${statusIcon} ${endpoint}</span>
                    <span style="color: ${this.getStatusColor(health.state)}">
                        ${successRate}% (${health.total_requests} requêtes)
                    </span>
                </div>
            `;
        }
        
        content += '</div>';
        statusPanel.innerHTML = content;
        
        // Supprimer après 10 secondes
        container.appendChild(statusPanel);
        setTimeout(() => {
            statusPanel.style.opacity = '0';
            setTimeout(() => statusPanel.remove(), 300);
        }, 10000);
    }
    
    getStatusIcon(state) {
        switch(state) {
            case 'healthy': return '✅';
            case 'degraded': return '⚠️';
            case 'circuit_open': return '❌';
            default: return '❓';
        }
    }
    
    getStatusColor(state) {
        switch(state) {
            case 'healthy': return '#27ae60';
            case 'degraded': return '#f39c12';
            case 'circuit_open': return '#e74c3c';
            default: return '#95a5a6';
        }
    }
}

// Ajouter les styles CSS
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes progress {
        from {
            transform: translateX(-100%);
        }
        to {
            transform: translateX(0);
        }
    }
    
    .llm-error-notification:hover {
        transform: scale(1.02);
        box-shadow: 0 6px 16px rgba(0,0,0,0.2) !important;
    }
`;
document.head.appendChild(style);

// Initialiser le handler
const llmErrorHandler = new LLMErrorHandler();

// Exposer l'API globale
window.LLMErrorHandler = llmErrorHandler;