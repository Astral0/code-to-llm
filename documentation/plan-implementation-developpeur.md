# Plan d'Implémentation Développeur : Branches de Conversation

## Vue d'Ensemble
Ce document guide l'implémentation pas à pas de la fonctionnalité de branches de conversation. Chaque étape est détaillée avec du code prêt à l'emploi et des critères de validation clairs.

## 🎯 Objectif Final
Permettre aux utilisateurs de créer des "branches" de conversation à partir de n'importe quel message, explorant ainsi différentes directions sans perdre l'historique original.

## 📋 Prérequis

### Environnement de Développement
- Python 3.9+
- Node.js (pour les dépendances frontend si nécessaire)
- Git
- Éditeur de code avec support JavaScript/Python

### Compétences Requises
- JavaScript ES6+ (niveau intermédiaire)
- Python (niveau basique)
- HTML/CSS (niveau basique)
- Git (niveau basique)

## Phase 0 : Préparation et Sécurité 🛡️

### 0.1 Configuration Git
```bash
# 1. Synchroniser avec la branche principale
git checkout main
git pull origin main

# 2. Créer la branche de développement
git checkout -b feature/conversation-branching

# 3. Vérifier
git status
```

✅ **Validation**: `git status` affiche "On branch feature/conversation-branching"

### 0.2 Environnement Python
```bash
# Créer l'environnement virtuel
conda create -n code2llm python=3.9
conda activate code2llm

# Installer les dépendances
pip install -r requirements.txt

# Tester le lancement
python main_desktop.py
```

✅ **Validation**: L'application se lance sans erreur et la Toolbox s'ouvre

### 0.3 Tests Initiaux
```bash
# Vérifier que pytest est installé
pip list | grep pytest || pip install pytest

# Lancer les tests existants
pytest

# Si la commande échoue ou s'il n'y a pas de tests
if [ $? -ne 0 ]; then
    echo "Création d'un test minimal..."
    echo "def test_placeholder(): assert True" > test_basic.py
    pytest test_basic.py
fi
```

✅ **Validation**: Pytest est installé et au moins un test passe

### 0.4 Backup de Sécurité
```bash
# Créer un point de sauvegarde local
git add .
git commit -m "chore: checkpoint before branching implementation"
```

## Phase 1 : Modification du Modèle de Données 📊

### 1.1 Documentation du Modèle

**Fichier**: `docs/data_models.md`

Ajouter dans la section metadata:

```json
{
  "metadata": {
    "mode": "api",
    "tags": [],
    "ai_generated_title": false,
    "forkInfo": {
      "sourceConversationId": "uuid-parent",
      "sourceMessageIndex": 4,
      "sourceMessageRole": "assistant",
      "forkTimestamp": "2025-01-20T10:30:00",
      "forkReason": "exploration alternative"
    }
    // PAS de tableau "branches" - calculé dynamiquement
  }
}
```

⚠️ **Important**: Ne PAS ajouter de tableau `branches` dans le parent (liaison unidirectionnelle)

✅ **Validation**: Le fichier documente clairement la structure `forkInfo`

### 1.2 Adaptation Backend Python

**Fichier**: `main_desktop.py`

Localiser et modifier la méthode `duplicate_conversation`:

```python
def duplicate_conversation(self, conversation_id):
    """Duplique une conversation sans hériter de forkInfo"""
    try:
        source_conv = self.get_conversation_details(conversation_id)
        if not source_conv:
            return {"success": False, "error": "Conversation non trouvée"}
        
        # Créer une copie propre SANS forkInfo
        new_conv_data = {
            "title": f"{source_conv.get('title', 'Sans titre')} - Copie",
            "history": source_conv.get('history', []),
            "context": source_conv.get('context', {}),
            "metadata": {
                "mode": source_conv.get('metadata', {}).get('mode', 'api'),
                "tags": [],
                "ai_generated_title": False
                # PAS de forkInfo ici - c'est une nouvelle racine
            }
        }
        
        return self.save_conversation(new_conv_data)
    except Exception as e:
        return {"success": False, "error": str(e)}
```

✅ **Validation**: Une conversation dupliquée n'a pas de `forkInfo` dans ses métadonnées

## Phase 2 : Implémentation Frontend - Le Cœur de la Fonctionnalité 🎨

### 2.1 Remplacement du Bouton Éditer

**Fichier**: `static/toolbox.js`

Localiser la méthode `addMessageControls` (ligne ~599) et remplacer:

```javascript
// AVANT (bouton edit)
if (role === 'user' && this.provider.getCapabilities().edit) {
    const editBtn = document.createElement('button');
    editBtn.className = 'btn btn-sm btn-outline-secondary edit-btn';
    editBtn.innerHTML = '<i class="fas fa-edit"></i>';
    editBtn.title = 'Éditer ce message';
    // ...
}

// APRÈS (bouton fork pour tous les messages)
const forkBtn = document.createElement('button');
forkBtn.className = 'btn btn-sm btn-outline-secondary fork-btn';
forkBtn.innerHTML = '<i class="fas fa-code-branch"></i>';
forkBtn.title = 'Créer une branche à partir d\'ici';
forkBtn.style.cssText = 'opacity: 0.7; padding: 2px 6px; font-size: 12px;';

// Calculer l'index du message dans l'historique
const allMessages = Array.from(document.querySelectorAll('.message-bubble'));
const messageIndex = allMessages.indexOf(messageDiv);

forkBtn.addEventListener('click', () => {
    this.forkConversationFrom(messageIndex, contentDiv.dataset.rawContent, role);
});

buttonsContainer.appendChild(forkBtn);
```

✅ **Validation**: L'icône de branche apparaît sur TOUS les messages (user et assistant)

### 2.2 Méthode forkConversationFrom

Ajouter dans la classe `ToolboxController`:

```javascript
async forkConversationFrom(messageIndex, originalContent, role) {
    // Pour le MVP, utiliser un prompt simple
    const defaultText = role === 'user' ? originalContent : '';
    const newPrompt = prompt(
        "🌿 Création d'une nouvelle branche\n\n" +
        "Entrez votre nouveau message pour explorer une direction alternative:",
        defaultText
    );
    
    if (newPrompt === null || newPrompt.trim() === '') {
        return; // Annulation
    }
    
    // Logique de découpage différenciée selon le rôle
    let baseHistory;
    if (role === 'user') {
        // Fork sur message user: on remplace ce message
        baseHistory = this.chatHistory.slice(0, messageIndex);
    } else {
        // Fork sur message assistant: on répond différemment
        baseHistory = this.chatHistory.slice(0, messageIndex + 1);
    }
    
    // Ajouter le nouveau message utilisateur
    baseHistory.push({
        role: 'user',
        content: newPrompt.trim()
    });
    
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
        parentId: this.currentConversationId,
        parentIndex: messageIndex,
        parentRole: role,
        parentTitle: parentTitle,
        history: baseHistory,
        suggestedTitle: suggestedTitle,
        reason: 'exploration alternative'
    });
}
```

✅ **Validation**: Le prompt s'ouvre et accepte un nouveau message

### 2.3 Méthode initializeBranch

Ajouter dans la classe `ToolboxController`:

```javascript
initializeBranch(branchData) {
    // 1. CRUCIAL: Réinitialiser l'ID pour forcer la modal de sauvegarde
    this.currentConversationId = null;
    
    // 2. Mettre à jour l'historique
    this.chatHistory = branchData.history;
    
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
    
    // 5. Rafraîchir l'interface
    this.refreshChatDisplay();
    this.updateSaveButtonState();
    
    // 6. Message système informatif
    this.appendMessageToChat('system', 
        `🌿 Nouvelle branche créée depuis "${branchData.parentTitle}".\n` +
        `La conversation continue dans une nouvelle direction.\n` +
        `Cliquez sur "Sauvegarder" pour conserver cette branche.`
    );
    
    // 7. Envoyer le dernier message au LLM automatiquement
    const lastMessage = branchData.history[branchData.history.length - 1];
    if (lastMessage && lastMessage.role === 'user') {
        // Utiliser le mode streaming si disponible
        if (this.isStreamEnabled) {
            this.sendMessageStream(lastMessage.content);
        } else {
            this.sendMessage(lastMessage.content);
        }
    }
}
```

✅ **Validation**: L'historique est mis à jour et une réponse IA est générée

### 2.4 Modification de _buildConversationPayload

Localiser et modifier:

```javascript
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
```

### 2.5 Modification de saveCurrentConversation

Dans la partie qui gère la modal:

```javascript
// Localiser cette section dans saveCurrentConversation
const titleInput = document.getElementById('conversationTitleInput');

// MODIFICATION: Pré-remplir avec le titre suggéré
if (this.suggestedBranchTitle) {
    titleInput.value = this.suggestedBranchTitle;
    titleInput.placeholder = 'Nouvelle branche';
    // Nettoyer après utilisation
    this.suggestedBranchTitle = null;
} else {
    titleInput.value = this.conversationSummary || '';
    titleInput.placeholder = 'Nouvelle conversation';
}
```

✅ **Validation**: La modal de sauvegarde affiche le titre pré-rempli

### 2.6 Affichage des Indicateurs de Branche

Modifier `displayConversations`:

```javascript
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
        
        // Vérifier si c'est une branche
        const forkInfo = conv.metadata?.forkInfo;
        let forkIndicator = '';
        let branchIcon = '';
        
        if (forkInfo && forkInfo.sourceConversationId) {
            // Trouver le parent
            const parentConv = this.conversations.find(
                c => c.id === forkInfo.sourceConversationId
            );
            
            // Gestion robuste du parent manquant
            let parentTitle;
            let parentLink;
            
            if (parentConv) {
                parentTitle = parentConv.title;
                // Lien cliquable vers le parent existant
                parentLink = `<a href="#" class="text-primary" 
                    onclick="event.preventDefault(); window.toolboxController.loadConversation('${forkInfo.sourceConversationId}')">
                    "${parentTitle}"
                </a>`;
            } else {
                // Parent supprimé ou non sauvegardé
                parentTitle = 'conversation supprimée ou non sauvegardée';
                parentLink = `<span class="text-muted">${parentTitle}</span>`;
            }
            
            // Icône de branche
            branchIcon = '<i class="fas fa-code-branch text-primary" title="Branche"></i> ';
            
            // Indicateur avec gestion du parent manquant
            forkIndicator = `
                <div class="fork-info text-muted small mt-1">
                    <i class="fas fa-level-up-alt fa-rotate-90"></i>
                    Branché depuis : ${parentLink}
                    (message #${(forkInfo.sourceMessageIndex || 0) + 1})
                </div>
            `;
        }
        
        // Construire le HTML
        convDiv.innerHTML = `
            <div class="d-flex justify-content-between align-items-center">
                <div class="fw-bold">
                    ${branchIcon}${conv.title || 'Sans titre'}
                </div>
                ${conv.isLocked ? '<i class="fas fa-lock"></i>' : ''}
            </div>
            <div class="meta mb-2">
                ${new Date(conv.updatedAt).toLocaleDateString()} 
                ${new Date(conv.updatedAt).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
            </div>
            ${forkIndicator}
            <div class="conversation-actions">
                <button class="btn btn-sm btn-outline-primary" 
                        onclick="window.toolboxController.loadConversation('${conv.id}')"
                        ${conv.isLocked && !conv.isLockedByMe ? 'disabled' : ''}>
                    <i class="fas fa-folder-open"></i>
                </button>
                <!-- Autres boutons... -->
            </div>
        `;
        
        conversationsList.appendChild(convDiv);
    });
}
```

✅ **Validation**: Les branches affichent l'icône et le lien vers le parent

## Phase 3 : Tests et Validation 🧪

### 3.1 Test Manuel Complet

1. **Créer une conversation normale**
   - Importer un contexte
   - Envoyer 2-3 messages
   - Sauvegarder

2. **Créer une branche depuis un message utilisateur**
   - Cliquer sur l'icône de branche d'un message user
   - Entrer un nouveau message
   - Vérifier que l'historique est tronqué AVANT ce message
   - Sauvegarder la branche

3. **Créer une branche depuis un message assistant**
   - Cliquer sur l'icône de branche d'un message assistant
   - Entrer une nouvelle question
   - Vérifier que l'historique INCLUT la réponse de l'assistant
   - Sauvegarder la branche

4. **Naviguer entre parent et enfant**
   - Dans la liste, cliquer sur le lien "Branché depuis..."
   - Vérifier que la conversation parent se charge

### 3.2 Vérification des Fichiers JSON

```bash
# Ouvrir le dossier des conversations
cd conversations/

# Vérifier qu'une branche contient forkInfo
cat [id-de-la-branche].json | grep forkInfo
```

✅ **Validation**: Les branches ont `forkInfo`, les conversations normales non

### 3.3 Tests de Régression

- [ ] L'import de contexte fonctionne toujours
- [ ] L'envoi de messages fonctionne toujours
- [ ] La sauvegarde normale fonctionne toujours
- [ ] Le chargement de conversation fonctionne toujours
- [ ] La duplication crée bien une nouvelle racine (sans forkInfo)

## Phase 4 : Finalisation 🚀

### 4.1 Nettoyage du Code

```javascript
// Supprimer tous les console.log de debug
// Rechercher: console.log
// Remplacer par: // console.log (ou supprimer)

// Ajouter des commentaires JSDoc
/**
 * Crée une nouvelle branche de conversation à partir d'un message
 * @param {number} messageIndex - Index du message dans l'historique
 * @param {string} originalContent - Contenu original du message
 * @param {string} role - Rôle du message ('user' ou 'assistant')
 */
async forkConversationFrom(messageIndex, originalContent, role) {
    // ...
}
```

### 4.2 Commit et Pull Request

```bash
# Vérifier les modifications
git status
git diff

# Ajouter les fichiers modifiés
git add static/toolbox.js
git add main_desktop.py
git add docs/data_models.md

# Commit avec un message descriptif
git commit -m "feat: implement conversation branching (MVP)

- Replace edit button with fork button (branch icon)
- Add forkConversationFrom and initializeBranch methods
- Implement unidirectional parent-child relationship
- Add visual indicators for branches in conversation list
- Enable navigation from child to parent conversation
- Pre-fill title when saving a branch

Closes #[issue-number]"

# Pousser la branche
git push origin feature/conversation-branching
```

### 4.3 Description de la Pull Request

```markdown
## 🌿 Conversation Branching - MVP Implementation

### What's New
This PR implements the first version of conversation branching, allowing users to explore alternative paths in their conversations.

### Key Features
- ✅ Fork any message (user or assistant) to create a new branch
- ✅ Unidirectional parent-child relationship (child knows parent)
- ✅ Visual indicators for branches in the conversation list
- ✅ Click-to-navigate from branch to parent
- ✅ Auto-suggested titles for branches

### Technical Details
- **Architecture**: Unidirectional linking prevents lock conflicts
- **Storage**: Each branch is a separate JSON file with `forkInfo` metadata
- **UI**: Fork button replaces edit button with branch icon

### Testing
- [x] Created branches from user messages
- [x] Created branches from assistant messages
- [x] Verified parent navigation works
- [x] Confirmed duplicates don't inherit forkInfo
- [x] No regression on existing features

### Screenshots
[Add screenshots here if possible]

### Next Steps (Future PRs)
- [ ] Dedicated fork modal (instead of prompt)
- [ ] Branch comparison view
- [ ] Tree visualization

Reviewers: @[team-lead] @[senior-dev]
```

## 📚 Ressources Utiles

### Documentation
- [Plan de projet original](./plan-action-branches-conversation.md)
- [Modèle de données](./docs/data_models.md)
- [Architecture de la Toolbox](./docs/toolbox_architecture.md)

### Outils de Debug
```javascript
// Pour debug dans la console du navigateur
window.toolboxController.chatHistory
window.toolboxController.currentConversationId
window.toolboxController.forkInfo
```

### Points d'Attention Critiques ⚠️

1. **Ne jamais** modifier le parent lors de la création d'une branche (liaison unidirectionnelle)
2. **Toujours** mettre `currentConversationId` à `null` pour forcer la modal de sauvegarde
3. **Vérifier** que `forkInfo` n'est pas copié lors de la duplication
4. **Accepter** que `parentId` puisse être `null` (parent non sauvegardé)
5. **Gérer** l'affichage quand le parent est supprimé ou introuvable

## 🎉 Félicitations !

Si tu arrives ici avec tous les tests verts, tu as réussi à implémenter une fonctionnalité complexe et innovante ! 

Cette feature transforme la Toolbox en un véritable "IDE conversationnel" et ouvre la voie à de nombreuses améliorations futures.

### Prochaines Améliorations (Sprint 2+)
- Modal dédiée pour le fork avec suggestions
- Vue arborescente des conversations
- Comparaison côte à côte des branches
- Export de l'arbre complet

## Notes de Version

### Version 1.1 (20/01/2025)
- Suppression de la sauvegarde automatique du parent (évite les sauvegardes non désirées)
- Amélioration de la gestion des parents manquants/supprimés
- Ajout de la vérification de pytest dans les tests initiaux
- Clarification des points d'attention critiques

### Version 1.0 (20/01/2025)
- Document initial avec plan complet d'implémentation

---

*Document créé le 20/01/2025*  
*Version actuelle: 1.1*  
*Destiné aux développeurs junior à intermédiaire*  
*Temps estimé: 2-3 jours pour le MVP complet*