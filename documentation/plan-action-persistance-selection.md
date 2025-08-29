# Plan d'Action : Persistance et Restauration de la Sélection de Fichiers

## Vue d'ensemble

### Contexte
L'application **code-to-llm** permet de scanner des projets et de sélectionner des fichiers pour générer un contexte. Actuellement, les utilisateurs doivent resélectionner manuellement les fichiers à chaque nouvelle session sur le même projet, ce qui est chronophage et source d'erreurs.

### Objectif
Implémenter un système de persistance de la sélection de fichiers permettant :
1. **Sauvegarde automatique** de la sélection lors de la génération du contexte
2. **Restauration en un clic** de la sélection précédente
3. **Identification visuelle** des nouveaux fichiers depuis la dernière session

### User Story
> "En tant que développeur, lorsque je rouvre un projet déjà analysé, je veux pouvoir **restaurer ma sélection de fichiers précédente en un clic** et être **clairement notifié des nouveaux fichiers** ajoutés depuis ma dernière session."

---

## Architecture Technique

### Stockage des Données
- **Format** : JSON (`selection_cache.json`)
- **Emplacement** : `DATA_DIR` (répertoire de données persistantes de l'application)
- **Structure** :
```json
{
  "/path/to/project1": ["file1.py", "file2.js", "README.md"],
  "/path/to/project2": ["src/main.py", "tests/test_main.py"]
}
```

### Flux de Données
1. **Scan** → Vérifie le cache → Retourne la sélection sauvegardée si elle existe
2. **Génération** → Sauvegarde la sélection actuelle dans le cache
3. **Restauration** → Applique la sélection sauvegardée aux checkboxes

---

## Phase 1 : Backend (`main_desktop.py`)

### 1.1. Configuration du Cache
```python
# Ajouter après la ligne 36 (SETTINGS_PATH)
SELECTION_CACHE_PATH = os.path.join(DATA_DIR, 'selection_cache.json')
```

**✅ Critère** : Constante définie pour le chemin du cache

### 1.2. Méthode de Sauvegarde
```python
def _save_selection_for_project(self, directory_path, selected_files):
    """
    Sauvegarde la liste des fichiers sélectionnés pour un projet.
    
    Args:
        directory_path (str): Chemin absolu du répertoire du projet
        selected_files (list): Liste des chemins relatifs des fichiers sélectionnés
    """
    try:
        # Charger le cache existant
        cache = {}
        if os.path.exists(SELECTION_CACHE_PATH):
            with open(SELECTION_CACHE_PATH, 'r', encoding='utf-8') as f:
                cache = json.load(f)
        
        # Mettre à jour avec la nouvelle sélection
        cache[directory_path] = selected_files
        
        # Sauvegarder
        with open(SELECTION_CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"✓ Sélection sauvegardée : {len(selected_files)} fichiers pour {directory_path}")
        
    except Exception as e:
        self.logger.error(f"✗ Erreur sauvegarde sélection : {e}")
```

**✅ Critère** : Méthode implémentée avec gestion d'erreurs

### 1.3. Intégration dans `generate_context_from_selection`
```python
# Dans la méthode generate_context_from_selection
# Ajouter juste avant le return final :

# Sauvegarder la sélection pour ce projet
self._save_selection_for_project(self.current_directory, selected_files)
```

**✅ Critère** : Sauvegarde automatique lors de la génération

### 1.4. Enrichissement de `scan_local_directory`
```python
# Dans scan_local_directory, avant le return final :

# Charger la sélection sauvegardée si elle existe
saved_selection = []
if os.path.exists(SELECTION_CACHE_PATH):
    try:
        with open(SELECTION_CACHE_PATH, 'r', encoding='utf-8') as f:
            cache = json.load(f)
            saved_selection = cache.get(directory_path, [])
            self.logger.info(f"✓ Sélection précédente trouvée : {len(saved_selection)} fichiers")
    except Exception as e:
        self.logger.error(f"✗ Erreur lecture cache : {e}")

# Ajouter à la réponse
response = result.get('response_for_frontend')
response['saved_selection'] = saved_selection
response['saved_selection_count'] = len(saved_selection)  # Pour affichage UI

return response
```

**✅ Critère** : La réponse contient la sélection sauvegardée

---

## Phase 2 : Frontend - HTML (`templates/toolbox.html`)

### 2.1. Ajout des Éléments UI - Interface Unifiée

Insérer **après** la div `#fileList` :

```html
<!-- Section unifiée pour la gestion de session (affichée conditionnellement) -->
<div id="sessionManagementSection" class="mt-4 d-none">
    <div class="card border-info shadow-sm">
        <div class="card-header bg-info bg-opacity-10 d-flex justify-content-between align-items-center" 
             role="button" 
             data-bs-toggle="collapse" 
             data-bs-target="#sessionCollapse">
            <h6 class="mb-0">
                <i class="fas fa-history text-info"></i>
                Session Précédente Détectée
                <span class="badge bg-info ms-2">
                    <span id="savedFileCount">0</span> fichiers sauvegardés
                </span>
            </h6>
            <i class="fas fa-chevron-down"></i>
        </div>
        <div id="sessionCollapse" class="collapse show">
            <div class="card-body">
                <!-- Bouton de restauration principal -->
                <div class="d-grid gap-2 mb-3">
                    <button id="restoreSelectionBtn" class="btn btn-info btn-lg">
                        <i class="fas fa-magic"></i> 
                        Restaurer la sélection précédente
                        <small class="d-block mt-1 opacity-75">
                            Réappliquer les <span class="savedFileCountDup">0</span> fichiers de la dernière session
                        </small>
                    </button>
                </div>
                
                <!-- Séparateur visuel -->
                <div class="separator-with-text my-4">
                    <hr class="bg-secondary opacity-25">
                    <span class="bg-white px-3 text-muted small">Et/Ou</span>
                </div>

                <!-- Zone pour les nouveaux fichiers (affichée conditionnellement) -->
                <div id="newFilesContainer" class="d-none">
                    <div class="alert alert-warning d-flex align-items-center mb-3" role="alert">
                        <i class="fas fa-exclamation-triangle me-2"></i>
                        <div>
                            <strong>Nouveaux fichiers détectés</strong>
                            <span class="badge bg-warning text-dark ms-2" id="newFilesCount">0</span>
                            <div class="small opacity-75">Ces fichiers n'étaient pas dans votre sélection précédente</div>
                        </div>
                    </div>
                    
                    <div class="form-check mb-3">
                        <input class="form-check-input" type="checkbox" id="selectAllNewFiles">
                        <label class="form-check-label fw-bold" for="selectAllNewFiles">
                            Sélectionner tous les nouveaux fichiers
                        </label>
                    </div>
                    
                    <div id="newFilesList" class="list-group list-group-flush max-height-300 overflow-auto">
                        <!-- Fichiers injectés dynamiquement -->
                    </div>
                </div>

                <!-- Message si aucun nouveau fichier -->
                <div id="noNewFilesMessage" class="d-none">
                    <div class="alert alert-success d-flex align-items-center" role="alert">
                        <i class="fas fa-check-circle me-2"></i>
                        <div>
                            <strong>Projet à jour</strong>
                            <div class="small opacity-75">Aucun nouveau fichier depuis votre dernière session</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<!-- CSS additionnel pour le séparateur (à ajouter dans style.css) -->
<style>
.separator-with-text {
    position: relative;
    text-align: center;
}
.separator-with-text hr {
    position: absolute;
    width: 100%;
    top: 50%;
    margin: 0;
}
.separator-with-text span {
    position: relative;
    background: white;
    padding: 0 1rem;
}
.max-height-300 {
    max-height: 300px;
}
</style>
```

**✅ Critère** : Interface utilisateur unifiée et cohérente avec toutes les actions de session regroupées

---

## Phase 3 : Frontend - JavaScript (`static/toolbox.js`)

### 3.1. Variables Globales
```javascript
// Ajouter au début du fichier, après les autres déclarations globales
let savedSelection = [];  // Stocke la sélection sauvegardée
let currentFiles = [];    // Stocke les fichiers du scan actuel
```

### 3.2. Gestion de la Réponse du Scan - Interface Unifiée
```javascript
// Dans le gestionnaire scanDirectoryBtn.addEventListener('click', ...)
// Après if (result.success) {

// Stocker les données
savedSelection = result.saved_selection || [];
currentFiles = result.files.map(f => f.path);

// Gérer l'affichage de la section de gestion de session
const sessionSection = document.getElementById('sessionManagementSection');

if (savedSelection.length > 0) {
    // Afficher la section de gestion de session
    sessionSection.classList.remove('d-none');
    
    // Mettre à jour les compteurs
    document.getElementById('savedFileCount').textContent = savedSelection.length;
    document.querySelector('.savedFileCountDup').textContent = savedSelection.length;
    
    // Identifier et afficher les nouveaux fichiers
    const newFiles = currentFiles.filter(file => !savedSelection.includes(file));
    
    if (newFiles.length > 0) {
        // Afficher les nouveaux fichiers
        document.getElementById('newFilesContainer').classList.remove('d-none');
        document.getElementById('noNewFilesMessage').classList.add('d-none');
        displayNewFiles(newFiles);
    } else {
        // Afficher le message "Projet à jour"
        document.getElementById('newFilesContainer').classList.add('d-none');
        document.getElementById('noNewFilesMessage').classList.remove('d-none');
    }
} else {
    // Aucune session précédente
    sessionSection.classList.add('d-none');
}
```

### 3.3. Fonction d'Affichage des Nouveaux Fichiers - Version Améliorée
```javascript
function displayNewFiles(newFiles) {
    const container = document.getElementById('newFilesContainer');
    const list = document.getElementById('newFilesList');
    const count = document.getElementById('newFilesCount');
    
    if (!container || !list) return;
    
    // Mettre à jour le compteur
    count.textContent = newFiles.length;
    
    // Réinitialiser la liste
    list.innerHTML = '';
    
    // Créer les éléments de liste avec une meilleure UX
    newFiles.forEach((filePath, index) => {
        const item = document.createElement('div');
        item.className = 'list-group-item d-flex align-items-center py-2';
        
        // Créer une structure plus riche
        const itemContent = document.createElement('div');
        itemContent.className = 'd-flex align-items-center flex-grow-1';
        
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'form-check-input me-3';
        checkbox.id = `new-file-${index}`;
        checkbox.dataset.filePath = filePath;
        
        // Synchronisation bidirectionnelle
        checkbox.addEventListener('change', function() {
            syncFileSelection(filePath, this.checked);
            updateNewFilesSelectAll(); // Mettre à jour l'état du "select all"
        });
        
        const label = document.createElement('label');
        label.htmlFor = checkbox.id;
        label.className = 'form-check-label d-flex align-items-center flex-grow-1';
        label.style.cursor = 'pointer';
        
        // Icône selon le type de fichier
        const fileIcon = getFileIcon(filePath);
        
        label.innerHTML = `
            <i class="${fileIcon} text-muted me-2"></i>
            <span class="text-truncate" title="${filePath}">${filePath}</span>
        `;
        
        itemContent.appendChild(checkbox);
        itemContent.appendChild(label);
        item.appendChild(itemContent);
        list.appendChild(item);
    });
    
    // Animation d'apparition
    list.style.opacity = '0';
    setTimeout(() => {
        list.style.transition = 'opacity 0.3s';
        list.style.opacity = '1';
    }, 100);
}

// Fonction helper pour obtenir l'icône selon l'extension
function getFileIcon(filePath) {
    const ext = filePath.split('.').pop().toLowerCase();
    const iconMap = {
        'js': 'fab fa-js-square',
        'py': 'fab fa-python',
        'html': 'fab fa-html5',
        'css': 'fab fa-css3-alt',
        'json': 'fas fa-code',
        'md': 'fab fa-markdown',
        'txt': 'far fa-file-alt',
        'pdf': 'far fa-file-pdf',
        'jpg': 'far fa-file-image',
        'png': 'far fa-file-image',
        'gif': 'far fa-file-image'
    };
    return iconMap[ext] || 'far fa-file-code';
}

// Fonction pour mettre à jour l'état du checkbox "select all"
function updateNewFilesSelectAll() {
    const selectAll = document.getElementById('selectAllNewFiles');
    const checkboxes = document.querySelectorAll('#newFilesList input[type="checkbox"]');
    const checkedBoxes = document.querySelectorAll('#newFilesList input[type="checkbox"]:checked');
    
    if (selectAll) {
        selectAll.checked = checkboxes.length > 0 && checkboxes.length === checkedBoxes.length;
        selectAll.indeterminate = checkedBoxes.length > 0 && checkedBoxes.length < checkboxes.length;
    }
}
```

### 3.4. Fonction de Restauration - Version Améliorée avec Animation
```javascript
// Gestionnaire du bouton de restauration
document.getElementById('restoreSelectionBtn')?.addEventListener('click', async function() {
    const btn = this;
    const originalContent = btn.innerHTML;
    
    // Animation de chargement
    btn.disabled = true;
    btn.innerHTML = `
        <span class="spinner-border spinner-border-sm me-2" role="status"></span>
        Restauration en cours...
    `;
    
    // Désélectionner tout d'abord avec une petite pause pour l'effet visuel
    document.querySelectorAll('#fileList input[type="checkbox"]').forEach(cb => {
        cb.checked = false;
    });
    
    // Attendre un peu pour l'effet visuel
    await new Promise(resolve => setTimeout(resolve, 300));
    
    // Appliquer la sélection sauvegardée avec animation
    let restoredCount = 0;
    let failedCount = 0;
    const restorationPromises = [];
    
    savedSelection.forEach((filePath, index) => {
        restorationPromises.push(new Promise(resolve => {
            setTimeout(() => {
                const checkbox = document.querySelector(`#fileList input[value="${filePath}"]`);
                if (checkbox) {
                    checkbox.checked = true;
                    restoredCount++;
                    
                    // Animation visuelle sur la checkbox
                    checkbox.parentElement.style.backgroundColor = '#d1ecf1';
                    setTimeout(() => {
                        checkbox.parentElement.style.transition = 'background-color 0.5s';
                        checkbox.parentElement.style.backgroundColor = '';
                    }, 500);
                } else {
                    failedCount++;
                }
                resolve();
            }, index * 10); // Délai progressif pour effet cascade
        }));
    });
    
    // Attendre que toutes les restaurations soient terminées
    await Promise.all(restorationPromises);
    
    // Mettre à jour les compteurs et l'état des boutons parents
    updateFileCount();
    updateParentCheckboxes();
    
    // Restaurer le bouton
    btn.disabled = false;
    btn.innerHTML = originalContent;
    
    // Feedback visuel avec détails
    let message = `✓ ${restoredCount} fichiers restaurés`;
    if (failedCount > 0) {
        message += ` (${failedCount} fichiers introuvables)`;
        showNotification(message, 'warning');
    } else {
        showNotification(message, 'success');
    }
    
    // Optionnel : faire défiler jusqu'au premier fichier sélectionné
    const firstSelected = document.querySelector('#fileList input[type="checkbox"]:checked');
    if (firstSelected) {
        firstSelected.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
});
```

### 3.5. Fonction de Synchronisation
```javascript
function syncFileSelection(filePath, isChecked) {
    // Synchroniser dans l'arbre principal
    const mainCheckbox = document.querySelector(`#fileList input[value="${filePath}"]`);
    if (mainCheckbox && mainCheckbox.checked !== isChecked) {
        mainCheckbox.checked = isChecked;
        updateParentCheckboxes(mainCheckbox);
    }
    
    // Synchroniser dans la liste des nouveaux fichiers
    const newFileCheckbox = document.querySelector(`#newFilesList input[data-file-path="${filePath}"]`);
    if (newFileCheckbox && newFileCheckbox.checked !== isChecked) {
        newFileCheckbox.checked = isChecked;
    }
    
    // Mettre à jour le compteur
    updateFileCount();
}
```

### 3.6. Sélection Groupée des Nouveaux Fichiers
```javascript
// Gestionnaire "Sélectionner tous les nouveaux fichiers"
document.getElementById('selectAllNewFiles')?.addEventListener('change', function() {
    const isChecked = this.checked;
    
    document.querySelectorAll('#newFilesList input[type="checkbox"]').forEach(cb => {
        cb.checked = isChecked;
        syncFileSelection(cb.dataset.filePath, isChecked);
    });
});
```

---

## Phase 4 : Améliorations & Optimisations

### 4.1. Notification Utilisateur
```javascript
function showNotification(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-white bg-${type} border-0`;
    toast.setAttribute('role', 'alert');
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">${message}</div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;
    
    document.querySelector('.toast-container')?.appendChild(toast);
    const bsToast = new bootstrap.Toast(toast);
    bsToast.show();
}
```

### 4.2. Nettoyage du Cache (Backend)
```python
def _clean_old_cache_entries(self, max_age_days=90):
    """Nettoie les entrées de cache pour les projets non accédés depuis X jours."""
    # À implémenter si nécessaire pour éviter une croissance infinie du cache
    pass
```

### 4.3. Validation de la Sélection
```python
def _validate_saved_selection(self, directory_path, saved_files):
    """Vérifie que les fichiers sauvegardés existent toujours."""
    valid_files = []
    for file_path in saved_files:
        full_path = os.path.join(directory_path, file_path)
        if os.path.exists(full_path):
            valid_files.append(file_path)
    return valid_files
```

---

## Tests & Validation

### Tests Unitaires Backend
- [ ] Test de sauvegarde de sélection
- [ ] Test de chargement de sélection
- [ ] Test de mise à jour de sélection existante
- [ ] Test avec cache corrompu
- [ ] Test avec fichiers supprimés

### Tests Unitaires Frontend
- [ ] Test d'affichage du bouton de restauration
- [ ] Test d'identification des nouveaux fichiers
- [ ] Test de synchronisation des checkboxes
- [ ] Test de sélection groupée

### Tests d'Intégration
- [ ] Workflow complet : scan → sélection → génération → nouveau scan → restauration
- [ ] Persistance après redémarrage de l'application
- [ ] Gestion de plusieurs projets simultanés

### Tests de Performance
- [ ] Cache avec 1000+ entrées
- [ ] Sélection de 500+ fichiers
- [ ] Temps de restauration < 1 seconde

---

## Checklist de Déploiement

- [ ] **Documentation**
  - [ ] Mettre à jour le README avec la nouvelle fonctionnalité
  - [ ] Ajouter des exemples d'utilisation
  - [ ] Documenter le format du cache

- [ ] **Migration**
  - [ ] Script de création du cache pour les utilisateurs existants (optionnel)
  - [ ] Gestion de la rétrocompatibilité

- [ ] **Monitoring**
  - [ ] Logs pour les opérations de cache
  - [ ] Métriques d'utilisation de la fonctionnalité

- [ ] **Sécurité**
  - [ ] Validation des chemins de fichiers
  - [ ] Limitation de la taille du cache
  - [ ] Permissions sur le fichier cache

---

## Évolutions Futures

### Court Terme
1. **Profils de Sélection** : Permettre plusieurs sélections nommées par projet
2. **Import/Export** : Partager des sélections entre développeurs
3. **Historique** : Garder les N dernières sélections

### Moyen Terme
1. **Sélection Intelligente** : Suggestions basées sur les patterns d'utilisation
2. **Synchronisation Cloud** : Partage entre machines
3. **Templates de Projet** : Sélections prédéfinies par type de projet

### Long Terme
1. **IA Prédictive** : Anticipation des besoins basée sur le contexte
2. **Intégration IDE** : Plugin VSCode/IntelliJ
3. **API REST** : Exposition de la fonctionnalité pour outils tiers

---

## Notes d'Implémentation

### Points d'Attention
- ⚠️ **Chemins Absolus** : Le cache utilise des chemins absolus comme clés
- ⚠️ **Encodage UTF-8** : Important pour les noms de fichiers internationaux
- ⚠️ **Concurrence** : Gérer les accès simultanés au cache
- ⚠️ **Taille du Cache** : Implémenter une limite ou un nettoyage automatique

### Conventions de Code
- Utiliser les logs existants (`self.logger`)
- Respecter le style de code Python (PEP 8)
- Maintenir la cohérence avec le code existant
- Ajouter des commentaires pour la logique complexe

### Performances
- Cache en mémoire pour éviter les lectures disque répétées
- Debounce sur les opérations de synchronisation
- Lazy loading pour les grandes listes de fichiers

---

## Points Clés des Améliorations

### 🎯 Interface Unifiée
- **Regroupement logique** : Toutes les actions de session dans une seule card
- **Hiérarchie visuelle claire** : Bouton de restauration principal, puis options secondaires
- **Feedback contextuel** : Messages différenciés selon l'état (nouveaux fichiers ou projet à jour)

### 🎨 Expérience Utilisateur Enrichie
- **Animations progressives** : Effet cascade lors de la restauration
- **Icônes contextuelles** : Reconnaissance visuelle des types de fichiers
- **États intermédiaires** : Checkbox indéterminée pour sélection partielle
- **Scroll intelligent** : Navigation automatique vers les éléments restaurés

### 🔧 Robustesse Technique
- **Gestion des erreurs** : Comptage des fichiers introuvables
- **Feedback détaillé** : Notifications avec contexte (succès/warning)
- **Performance optimisée** : Animations asynchrones sans blocage UI

## Conclusion

Ce plan d'action améliore significativement l'expérience utilisateur en :
1. **Unifiant l'interface** pour une meilleure cohérence et clarté
2. **Réduisant le temps** de configuration à chaque session
3. **Prévenant les oublis** grâce à la mise en évidence des nouveaux fichiers
4. **Offrant une flexibilité** avec la possibilité de modifier la sélection restaurée
5. **Enrichissant le feedback** avec des animations et notifications contextuelles

L'implémentation est **progressive et testable**, permettant une validation à chaque étape. La solution est **extensible** pour accueillir les évolutions futures sans refactoring majeur.

### Estimation de Temps (Révisée)
- **Phase 1 (Backend)** : 2-3 heures
- **Phase 2 (Frontend HTML)** : 1-2 heures (interface unifiée)
- **Phase 3 (Frontend JS)** : 4-5 heures (avec animations et UX enrichie)
- **Phase 4 (Tests)** : 2-3 heures
- **Total** : ~9-13 heures de développement

### Priorité d'Implémentation
1. ⭐⭐⭐ Persistance basique (sauvegarde/restauration)
2. ⭐⭐⭐ Interface unifiée (meilleure UX)
3. ⭐⭐ Identification des nouveaux fichiers
4. ⭐ Améliorations visuelles (animations, icônes)