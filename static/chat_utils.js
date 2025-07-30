// static/chat_utils.js
// Module utilitaire pour les fonctionnalités de chat partagées

/**
 * Module de gestion du défilement intelligent pour les zones de chat
 * Permet de désactiver le défilement automatique quand l'utilisateur fait défiler manuellement
 */
const SmartScroll = {
    // État du module
    state: {
        userHasScrolled: false,
        isAutoScrolling: false
    },
    
    /**
     * Initialise la gestion du défilement intelligent pour un élément
     * @param {HTMLElement} scrollElement - L'élément à gérer (ex: chatDisplayArea)
     * @param {Object} options - Options de configuration
     * @returns {Object} - Objet avec méthodes pour contrôler le défilement
     */
    init(scrollElement, options = {}) {
        if (!scrollElement) {
            console.warn('SmartScroll.init: scrollElement est null ou undefined');
            return null;
        }
        
        // Options par défaut
        const config = {
            tolerance: options.tolerance || 50,  // Tolérance en pixels pour considérer qu'on est "en bas"
            debug: options.debug || false,       // Activer les logs de debug
            ...options
        };
        
        // État local pour cette instance
        const localState = {
            userHasScrolled: false,
            isAutoScrolling: false
        };
        
        // Fonction pour faire défiler automatiquement
        const autoScrollToBottom = () => {
            if (!localState.userHasScrolled && scrollElement) {
                localState.isAutoScrolling = true;
                scrollElement.scrollTop = scrollElement.scrollHeight;
                // Reset le flag après un court délai
                setTimeout(() => { 
                    localState.isAutoScrolling = false; 
                }, 100);
            }
        };
        
        // Fonction pour réinitialiser l'état
        const resetScrollState = () => {
            localState.userHasScrolled = false;
            if (config.debug) {
                console.log("SmartScroll: État réinitialisé - auto-scroll réactivé");
            }
        };
        
        // Détecter quand l'utilisateur fait défiler manuellement
        scrollElement.addEventListener('scroll', () => {
            // Ignorer si c'est un scroll automatique
            if (localState.isAutoScrolling) return;
            
            // Vérifier si on est proche du bas
            const isAtBottom = scrollElement.scrollHeight - scrollElement.scrollTop - scrollElement.clientHeight < config.tolerance;
            
            // Si l'utilisateur a fait défiler vers le haut
            if (!isAtBottom) {
                localState.userHasScrolled = true;
                if (config.debug) {
                    console.log("SmartScroll: Défilement manuel détecté - auto-scroll désactivé");
                }
            } else {
                // Si on est de retour en bas, réactiver le défilement automatique
                localState.userHasScrolled = false;
                if (config.debug) {
                    console.log("SmartScroll: Retour en bas - auto-scroll réactivé");
                }
            }
        });
        
        // Détecter l'utilisation de la molette de souris
        scrollElement.addEventListener('wheel', (event) => {
            // Si la molette est utilisée pour remonter (deltaY négatif)
            if (event.deltaY < 0) {
                localState.userHasScrolled = true;
                if (config.debug) {
                    console.log("SmartScroll: Molette vers le haut détectée - auto-scroll désactivé");
                }
            }
        }, { passive: true });
        
        // Détecter le toucher sur mobile
        let touchStartY = 0;
        scrollElement.addEventListener('touchstart', (e) => {
            touchStartY = e.touches[0].clientY;
        }, { passive: true });
        
        scrollElement.addEventListener('touchmove', (e) => {
            const touchY = e.touches[0].clientY;
            const deltaY = touchY - touchStartY;
            
            // Si on fait glisser vers le bas (deltaY positif), on remonte dans le contenu
            if (deltaY > 10) {
                localState.userHasScrolled = true;
                if (config.debug) {
                    console.log("SmartScroll: Glissement tactile vers le haut détecté - auto-scroll désactivé");
                }
            }
        }, { passive: true });
        
        // Retourner l'API publique
        return {
            scrollToBottom: autoScrollToBottom,
            reset: resetScrollState,
            isUserScrolling: () => localState.userHasScrolled,
            forceScroll: () => {
                localState.userHasScrolled = false;
                autoScrollToBottom();
            }
        };
    }
};

// Export pour utilisation dans d'autres fichiers
window.ChatUtils = window.ChatUtils || {};
window.ChatUtils.SmartScroll = SmartScroll;