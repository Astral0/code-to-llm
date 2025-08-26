# Plan d'Action : Gestion des Branches de Conversation

## Résumé Exécutif

Transformation de la Toolbox d'un système de conversation linéaire vers un système de **branches de conversation** permettant l'exploration non-linéaire des idées, similaire au concept de branches dans Git.

## Vision du Projet

### Problématique Actuelle
- Les conversations sont strictement linéaires
- Le bouton "Éditer" actuel ne permet que de modifier un message existant
- Impossible d'explorer plusieurs directions à partir d'un même point
- Perte d'opportunités d'exploration créative

### Solution Proposée
Créer un système de **"fork" conversationnel** où chaque message peut devenir le point de départ d'une nouvelle branche de réflexion.

## Architecture Technique

### 1. Modèle de Données Enrichi

#### Structure JSON Étendue - Liaison Unidirectionnelle
```json
{
  "id": "uuid-conversation",
  "title": "Titre de la conversation",
  "history": [...],
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
    // Pas de tableau "branches" - calculé dynamiquement
  }
}
```

**Principe architectural clé**: Liaison **unidirectionnelle** - seul l'enfant connaît son parent. Cela évite:
- Les conflits de verrouillage lors de la création de branches
- La modification de deux fichiers simultanément
- La complexité de synchronisation

Les branches enfants sont retrouvées dynamiquement:
```javascript
function getChildrenOf(parentId, allConversations) {
    return allConversations.filter(conv => 
        conv.metadata?.forkInfo?.sourceConversationId === parentId
    );
}
```

### 2. Modifications Frontend

#### Phase 1: Remplacement du Bouton Éditer (Sprint 1)
- **Icône**: `fa-code-branch` au lieu de `fa-edit`
- **Tooltip**: "Créer une branche à partir d'ici"
- **Position**: Sur tous les messages (user et assistant)

#### Phase 2: Interface de Fork (Sprint 1)
```javascript
// Nouvelle méthode dans ToolboxController
async forkConversationFrom(messageIndex, originalContent, role) {
    // Modal améliorée au lieu d'un simple prompt
    const modal = this.showForkModal({
        originalContent,
        messageRole: role,
        suggestions: [
            "Explorer une approche alternative",
            "Reformuler la question",
            "Approfondir ce point spécifique"
        ]
    });
    
    const result = await modal.getResult();
    if (!result) return;
    
    // Logique différenciée selon le rôle du message source
    let baseHistory;
    if (role === 'user') {
        // Cas A: Fork sur message utilisateur - on remplace ce message
        // L'historique s'arrête AVANT le message utilisateur
        baseHistory = this.chatHistory.slice(0, messageIndex);
    } else { // 'assistant' ou 'system'
        // Cas B: Fork sur message assistant - on répond différemment
        // L'historique inclut le message de l'assistant
        baseHistory = this.chatHistory.slice(0, messageIndex + 1);
    }
    
    // Ajout du nouveau message utilisateur
    if (result.newMessage) {
        baseHistory.push({
            role: 'user',
            content: result.newMessage
        });
    }
    
    // Sauvegarde automatique de la conversation parente si non sauvegardée
    if (!this.currentConversationId) {
        await this.quickSaveCurrentConversation();
    }
    
    // Génération du titre pré-rempli pour la branche
    const parentTitle = this.conversationSummary || 'Conversation';
    const suggestedTitle = `${parentTitle} - Branche ${new Date().toLocaleTimeString()}`;
    
    // Initialisation de la nouvelle branche
    this.initializeBranch({
        parentId: this.currentConversationId,
        parentIndex: messageIndex,
        parentRole: role,
        history: baseHistory,
        reason: result.reason,
        suggestedTitle: suggestedTitle
    });
}
```

#### Phase 3: Visualisation des Branches (Sprint 2)

##### Option A: Indicateur Simple avec Navigation Active
```html
<!-- Dans la liste des conversations -->
<div class="conversation-item">
    <div class="conversation-header">
        <i class="fas fa-code-branch text-primary"></i>
        <span class="title">Ma branche de conversation</span>
    </div>
    <div class="fork-info">
        <small class="text-muted">
            Branché depuis: 
            <a href="#" class="fork-parent-link" 
               onclick="window.toolboxController.loadConversation('${forkInfo.sourceConversationId}')">
                "${parentTitle}" (message #${forkInfo.sourceMessageIndex + 1})
            </a>
        </small>
    </div>
</div>
```

##### Option B: Arbre Visuel (Sprint 3)
```html
<!-- Vue arborescente optionnelle -->
<div class="conversation-tree">
    <div class="tree-node root">
        📄 Conversation principale
        <div class="branch-line"></div>
        <div class="tree-node branch">
            🌿 Branche: Approche technique
        </div>
        <div class="tree-node branch">
            🌿 Branche: Approche créative
            <div class="branch-line"></div>
            <div class="tree-node sub-branch">
                🍃 Sous-branche: Détails UI
            </div>
        </div>
    </div>
</div>
```

### 3. Fonctionnalités Avancées (Sprint 3+)

#### Combinaison de Conversations (plutôt que "Merge")
```javascript
async combineConversations(branch1Id, branch2Id) {
    // Création d'une nouvelle conversation combinant les insights
    // Note: Ce n'est pas un vrai "merge" sémantique mais une concaténation intelligente
    const branch1 = await this.loadConversation(branch1Id);
    const branch2 = await this.loadConversation(branch2Id);
    
    const combinedHistory = [
        ...branch1.history,
        { role: 'system', content: '--- Insights de la branche alternative ---' },
        ...branch2.history.slice(this.findDivergencePoint(branch1, branch2))
    ];
    
    return this.createConversation({
        title: `Combinaison: ${branch1.title} + ${branch2.title}`,
        history: combinedHistory,
        metadata: {
            combinationInfo: {
                sources: [branch1Id, branch2Id],
                combinationDate: new Date().toISOString()
            }
        }
    });
}
```

#### Comparaison de Branches
```javascript
async compareBranches(branch1Id, branch2Id) {
    // Affichage côte à côte des deux branches
    // Utilisation recommandée: bibliothèque diff-match-patch de Google
    const comparison = {
        divergencePoint: this.findDivergencePoint(branch1, branch2),
        differences: this.highlightDifferences(branch1, branch2), // Via diff-match-patch
        insights: await this.generateComparisonInsights(branch1, branch2)
    };
    
    this.showComparisonModal(comparison);
}
```

#### Méthode initializeBranch Détaillée
```javascript
// Dans ToolboxController - Méthode centrale pour initialiser une branche
initializeBranch(branchData) {
    // 1. Réinitialiser l'ID - Clé pour forcer la modal de sauvegarde
    this.currentConversationId = null;

    // 2. Mettre à jour l'historique avec celui de la branche
    this.chatHistory = branchData.history;

    // 3. Stocker les métadonnées de fork pour la sauvegarde
    this.forkInfo = {
        sourceConversationId: branchData.parentId,
        sourceMessageIndex: branchData.parentIndex,
        sourceMessageRole: branchData.parentRole,
        forkTimestamp: new Date().toISOString(),
        forkReason: branchData.reason
    };
    
    // 4. Rafraîchir l'interface
    this.refreshChatDisplay();
    this.updateSaveButtonState();
    
    // 5. Pré-remplir le titre suggéré (sera utilisé lors de la sauvegarde)
    this.suggestedBranchTitle = branchData.suggestedTitle;
    
    // 6. Message système informatif
    this.appendMessageToChat('system', 
        `🌿 Nouvelle branche créée depuis "${branchData.parentTitle}". ` +
        `La conversation continue dans une nouvelle direction.`
    );
    
    // 7. Envoyer automatiquement le dernier message au LLM si c'est un message user
    const lastMessage = branchData.history[branchData.history.length - 1];
    if (lastMessage && lastMessage.role === 'user') {
        this.sendMessageStream(lastMessage.content);
    }
}
```

## Plan d'Implémentation

### Sprint 1 (1 semaine) - MVP
- [ ] Modifier le modèle de données pour supporter `forkInfo` (liaison unidirectionnelle uniquement)
- [ ] Remplacer le bouton "Éditer" par "Fork" avec icône `fa-code-branch`
- [ ] Implémenter la logique de création de branche avec distinction user/assistant
- [ ] Ajouter le calcul dynamique des branches enfants
- [ ] Pré-remplir le titre lors de la sauvegarde de branche
- [ ] Ajouter l'indicateur visuel simple dans la liste
- [ ] Tests et validation

### Sprint 2 (1 semaine) - Amélioration UX
- [ ] Créer une modal dédiée pour le fork (au lieu du prompt)
- [ ] Ajouter des suggestions contextuelles
- [ ] Implémenter la sauvegarde automatique du parent
- [ ] Améliorer les indicateurs visuels
- [ ] Ajouter la navigation parent-enfant

### Sprint 3 (2 semaines) - Fonctionnalités Avancées
- [ ] Vue arborescente des conversations
- [ ] Fonction de combinaison de conversations (concaténation intelligente)
- [ ] Comparaison côte à côte des branches (prioritaire - avec diff-match-patch)
- [ ] Export de l'arbre complet
- [ ] Tags automatiques pour les branches
- [ ] Indicateurs de divergence et points communs
- [ ] Navigation bidirectionnelle parent-enfant

### Sprint 4 (1 semaine) - Polish & Optimisation
- [ ] Raccourcis clavier (Ctrl+B pour brancher)
- [ ] Prévisualisation avant fork
- [ ] Templates de fork
- [ ] Statistiques d'utilisation des branches
- [ ] Documentation utilisateur

## Considérations Techniques

### Performance
- Les branches sont des fichiers indépendants (pas de fichier monolithique)
- Calcul dynamique des relations parent-enfant (pas de double écriture)
- Chargement lazy des branches enfants
- Cache des métadonnées pour l'affichage de l'arbre

### Sécurité et Robustesse
- **Architecture unidirectionnelle** : Évite complètement les conflits de verrouillage
- Une seule écriture atomique lors de la création de branche
- Préservation du système de verrouillage existant sans modification
- Validation des références parent-enfant
- Limite du nombre de branches par conversation (configurable)
- Suppression de branche sans impact sur le parent

### Migration
- Rétrocompatibilité totale avec les conversations existantes
- Script de migration optionnel pour identifier les branches "naturelles"

## Métriques de Succès

1. **Adoption**: 50% des utilisateurs créent au moins une branche par semaine
2. **Profondeur**: Moyenne de 3 niveaux de branches par conversation complexe
3. **Réutilisation**: 30% des branches deviennent des conversations principales
4. **Satisfaction**: Score NPS > 8 pour la fonctionnalité

## Risques et Mitigations

| Risque | Impact | Mitigation |
|--------|--------|------------|
| Complexité UX | Élevé | Interface progressive, tutoriel intégré |
| Explosion du nombre de fichiers | Moyen | Archivage automatique, limite configurable |
| Confusion navigation | Moyen | Indicateurs visuels clairs, breadcrumbs, titre pré-rempli |
| Performance avec beaucoup de branches | Faible | Pagination, lazy loading, calcul dynamique |
| Conflits de verrouillage | Élevé | **RÉSOLU** par liaison unidirectionnelle |
| Complexité du "merge" | Moyen | Renommé en "Combinaison", attentes ajustées |

## Alternatives Considérées

1. **Branches dans un seul fichier**: Rejeté - Risque de corruption, complexité
2. **Simple duplication**: Rejeté - Perd le lien de parenté
3. **Système de tags uniquement**: Rejeté - Pas assez structuré

## Points Clés de l'Architecture

### Décisions Critiques Validées

1. **Liaison Unidirectionnelle** (Point le plus important)
   - Seul l'enfant connaît son parent via `forkInfo`
   - Pas de tableau `branches` dans le parent
   - Relations calculées dynamiquement : `getChildrenOf()`
   - **Bénéfice majeur** : Aucun conflit de verrouillage possible

2. **Logique de Fork Différenciée**
   - Fork sur message **user** : historique jusqu'à `messageIndex - 1`
   - Fork sur message **assistant** : historique jusqu'à `messageIndex`
   - Permet deux cas d'usage distincts et intuitifs

3. **UX Améliorée**
   - Titre pré-rempli : `"[Titre parent] - Branche [timestamp]"`
   - Modal dédiée plutôt que simple prompt
   - Indicateurs visuels clairs de parenté

4. **Nomenclature Ajustée**
   - "Combinaison" au lieu de "Merge" pour éviter les fausses attentes
   - Comparaison côte à côte priorisée (plus de valeur, plus simple)

## Conclusion

Cette évolution transformera la Toolbox en un véritable **"IDE conversationnel"**, permettant une exploration créative et structurée des idées. L'approche par branches offre la flexibilité du brainstorming tout en conservant la traçabilité et l'organisation nécessaires pour des projets complexes.

L'architecture unidirectionnelle garantit une implémentation robuste et sans conflits, tout en préservant la simplicité du système existant.

## Détails d'Implémentation Validés

### Navigation Parent-Enfant Active
- Les liens vers les parents sont **cliquables** dans la liste
- Création d'un "breadcrumb" naturel pour naviguer dans l'arbre
- Chargement immédiat de la conversation parente au clic

### Méthode initializeBranch Clarifiée
- Réinitialisation de `currentConversationId` à `null` (force la modal)
- Stockage des métadonnées de fork
- Pré-remplissage du titre suggéré
- Envoi automatique au LLM si dernier message = user

### Outils Recommandés
- **diff-match-patch** (Google) pour la comparaison visuelle
- Surlignage HTML des différences entre branches

### Prochaines Étapes Immédiates
1. ✅ Validation de l'architecture unidirectionnelle
2. ✅ Validation des détails d'implémentation
3. Création d'un prototype UI (maquettes)
4. Début du Sprint 1 avec le remplacement du bouton
5. Tests de la logique de fork différenciée

---

*Document créé le 20/01/2025*  
*Version: 2.1 - Intégration complète des validations et précisions d'implémentation*  
*Auteur: Assistant Claude + Analyse utilisateur approfondie + Validation finale*