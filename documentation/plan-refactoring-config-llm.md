# Plan d'action : Refactoring de la configuration multi-LLM

Bonjour ! 👋

Voici le guide détaillé pour le refactoring de la configuration des LLMs. L'objectif est de rendre chaque modèle défini dans `config.ini` totalement autonome et de permettre à l'utilisateur de basculer entre eux directement depuis l'interface.

Suis ces étapes attentivement. Le plan est conçu pour être suivi de manière séquentielle. N'hésite jamais à poser des questions si tu es bloqué.

## État actuel du code
Après analyse du codebase, voici les constats :
- La configuration actuelle utilise une section `[LLMServer]` unique dans `config.ini.template`
- Il existe des sections spécifiques pour `[SummarizerLLM]` et `[TitleGeneratorLLM]` qui héritent de `[LLMServer]`
- Le code ne supporte pas encore la sélection dynamique entre plusieurs modèles LLM
- `main_desktop.py` charge la configuration LLM dans `load_service_configs()` (lignes 135-177)
- `LlmApiService` utilise directement la configuration passée dans son constructeur

## Phase 0 : Préparation et Installation

Avant toute modification, assurons-nous que notre base de travail est saine et stable.

- [ ] **Tâche :** Créer une nouvelle branche Git pour ce chantier.
  - Cela nous permet de travailler en toute sécurité sans impacter le code principal.
  - Exécute ces commandes :
    ```bash
    git checkout main
    git pull
    git checkout -b feature/multi-llm-config
    ```
  - ✅ **Critère d'acceptation :** La commande `git status` confirme que tu es sur la branche `feature/multi-llm-config`.

- [ ] **Tâche :** Valider l'environnement de développement.
  - Suis les instructions du `README.md` pour activer l'environnement Conda (`conda activate code2llm`) et lancer l'application avec `run.bat`.
  - ✅ **Critère d'acceptation :** La fenêtre principale de l'application s'ouvre sans aucune erreur dans la console.

- [ ] **Tâche :** Lancer la suite de tests pour établir une référence.
  - C'est notre filet de sécurité. Nous devons nous assurer que tout est vert avant de commencer.
  - Dans le terminal, avec l'environnement activé, exécute :
    ```bash
    pytest
    ```
  - ✅ **Critère d'acceptation :** La commande `pytest` se termine avec succès, tous les tests sont marqués comme "passed".

## Phase 1 : Refactoring du Backend

Objectif : Adapter le code pour qu'il comprenne la nouvelle structure de configuration autonome.

- [ ] **Tâche :** Mettre à jour la lecture de la configuration dans `main_desktop.py`.
  - Nous allons modifier `load_service_configs()` pour qu'elle lise chaque section `[LLM:...]` comme une entité complète et indépendante.
  - Dans `main_desktop.py`, localise `load_service_configs()` et remplace la logique de configuration LLM par celle-ci :
    ```python
    # Dans main_desktop.py -> load_service_configs()
    
    llm_models = {}
    default_llm_id = None
    for section in config.sections():
        if section.startswith('LLM:'):
            # Ignorer les modèles désactivés
            if not config.getboolean(section, 'enabled', fallback=True):
                continue
    
            llm_id = section[4:].strip()
            is_default = config.getboolean(section, 'default', fallback=False)
    
            llm_models[llm_id] = {
                'id': llm_id,
                'name': llm_id,
                'url': config.get(section, 'url', fallback=''),
                'apikey': config.get(section, 'apikey', fallback=''),
                'model': config.get(section, 'model', fallback=''),
                'api_type': config.get(section, 'api_type', fallback='openai').lower(),
                'stream_response': config.getboolean(section, 'stream_response', fallback=False),
                'ssl_verify': config.getboolean(section, 'ssl_verify', fallback=True),
                'timeout_seconds': config.getint(section, 'timeout_seconds', fallback=300),
                'temperature': safe_parse_config_value(config, section, 'temperature', float, None),
                'max_tokens': safe_parse_config_value(config, section, 'max_tokens', int, None),
                'default': is_default
            }
            if is_default:
                default_llm_id = llm_id
    
    service_configs['llm_service'] = {
        'models': llm_models,
        'default_id': default_llm_id
    }
    ```
  - ✅ **Critère d'acceptation :** L'application se lance toujours sans erreur.

- [ ] **Tâche :** Adapter le service `LlmApiService` à la nouvelle structure.
  - Le constructeur du service doit être mis à jour pour accepter la nouvelle structure de configuration.
  - Dans `services/llm_api_service.py`, modifie la méthode `__init__` :
    ```python
    # Dans services/llm_api_service.py -> __init__
    super().__init__(config, logger)
    self._llm_models = config.get('models', {})
    self._default_llm_id = config.get('default_id', None)
    self._setup_http_session()
    ```
  - Ensuite, ajoute une méthode pour obtenir les modèles disponibles :
    ```python
    def get_available_models(self):
        """Retourne la liste des modèles LLM disponibles."""
        return [
            {'id': llm_id, 'name': model['name'], 'default': model.get('default', False)}
            for llm_id, model in self._llm_models.items()
        ]
    ```
  - Modifie la méthode `_prepare_request` pour qu'elle accepte un paramètre `llm_id` et utilise la configuration du modèle demandé :
    ```python
    # Dans services/llm_api_service.py -> _prepare_request
    def _prepare_request(self, chat_history: List[Dict[str, str]], stream: bool = False, llm_id: Optional[str] = None) -> tuple:
        target_llm_id = llm_id if llm_id and llm_id in self._llm_models else self._default_llm_id
        if not target_llm_id:
            raise LlmApiServiceException('No default or valid LLM configured.')
        
        final_config = self._llm_models[target_llm_id]
        # ... le reste de la fonction utilise `final_config` pour tous les paramètres.
    ```
  - ✅ **Critère d'acceptation :** Adapte les tests unitaires dans `tests/test_llm_api_service.py` pour qu'ils passent avec la nouvelle logique.

- [ ] **Tâche :** Mettre à jour les méthodes de l'API dans `main_desktop.py`.
  - L'API doit être "stateless". Nous exposons la liste des modèles et nous nous attendons à recevoir l'ID du modèle à chaque appel.
  - Dans la classe `Api` de `main_desktop.py` :
    1. Ajoute une nouvelle méthode : `get_available_llms()`.
    2. Modifie les signatures de `send_to_llm` et `send_to_llm_stream` pour qu'elles acceptent un paramètre `llm_id`.
    ```python
    # Dans main_desktop.py -> class Api
    
    def get_available_llms(self):
        """Retourne la liste des LLMs configurés."""
        return self.llm_service.get_available_models()
    
    def send_to_llm(self, chat_history, stream=False, llm_id=None):
        # ... passe llm_id à self.llm_service.send_to_llm
        return self.llm_service.send_to_llm(chat_history, stream, llm_id)
    
    def send_to_llm_stream(self, chat_history, callback_id, llm_id=None):
        # ... passe llm_id dans le thread
        def stream_worker():
            # ... appel avec llm_id
    ```
  - ✅ **Critère d'acceptation :** Les nouvelles méthodes sont en place et les signatures sont mises à jour.

## Phase 2 : Mise à jour du Frontend

Objectif : Créer l'interface permettant à l'utilisateur de choisir son modèle.

- [ ] **Tâche :** Ajouter le sélecteur de LLM dans `templates/toolbox.html`.
  - Nous allons ajouter un menu déroulant (`<select>`) dans la zone de contrôles du chat.
  - Dans `templates/toolbox.html`, juste avant la barre de contrôle de navigation, ajoute ce bloc :
    ```html
    <!-- Sélecteur de LLM -->
    <div class="d-flex align-items-center api-mode-only">
        <label for="llmSelector" class="form-label-sm me-2 mb-0 text-muted">Modèle:</label>
        <select class="form-select form-select-sm" id="llmSelector" style="width: auto;" title="Choisir le modèle LLM à utiliser">
            <!-- Options chargées dynamiquement -->
        </select>
    </div>
    ```
  - ✅ **Critère d'acceptation :** Un menu déroulant vide apparaît dans l'interface de la Toolbox.

- [ ] **Tâche :** Implémenter la logique frontend dans `static/toolbox.js`.
  - Le JavaScript doit charger la liste des modèles, la persister et l'envoyer au backend à chaque requête.
  - Dans `static/toolbox.js` :
    1. Crée une nouvelle fonction `loadAvailableLlmModels()` qui appelle `window.pywebview.api.get_available_llms()` et remplit le sélecteur. Appelle cette fonction dans `initializeUI()`.
    2. Sauvegarde le choix de l'utilisateur dans le `localStorage` à chaque changement du sélecteur.
    3. Au chargement, essaie de restaurer le choix depuis le `localStorage`.
    4. Dans `sendMessage` et `sendMessageStream`, récupère la valeur de `#llmSelector` et passe-la dans l'appel à l'API backend.
  - ✅ **Critère d'acceptation :** Le sélecteur se remplit avec les modèles du `config.ini`. Le choix est conservé après un rechargement. L'envoi d'un message fonctionne.

## Phase 3 : Configuration et Documentation

Objectif : Rendre la nouvelle configuration facile à comprendre et à utiliser.

- [ ] **Tâche :** Mettre à jour `config.ini.template`.
  - Le template doit servir d'exemple clair pour la nouvelle structure.
  - Supprime complètement la section `[LLMServer]`.
  - Assure-toi que chaque section `[LLM:...]` contient tous les paramètres nécessaires (`model`, `api_type`, `enabled`, etc.).
  - Ajoute des commentaires pour expliquer les nouveaux paramètres `enabled = true/false` et `default = true`.
  - ✅ **Critère d'acceptation :** Le fichier `config.ini.template` est propre, à jour et bien commenté.

- [ ] **Tâche :** Mettre à jour le `README.md`.
  - La documentation est essentielle pour que les utilisateurs comprennent ce changement majeur.
  - Dans la section "Configuration Essentielle" du `README.md`, remplace l'ancien exemple de configuration par le nouveau, en montrant un exemple avec plusieurs modèles.
  - ✅ **Critère d'acceptation :** Le `README.md` explique clairement comment configurer plusieurs LLMs.

- [ ] **Tâche (optionnelle) :** Créer un script de migration `migrate_config.py`.
  - Pour faciliter la transition des utilisateurs existants.
  - Le script doit lire l'ancien format avec `[LLMServer]` et générer le nouveau format.
  - Faire une sauvegarde de l'ancienne configuration avant modification.
  - ✅ **Critère d'acceptation :** Les utilisateurs peuvent migrer leur configuration existante automatiquement.

## Phase 4 : Tests et Validation

Objectif : Garantir que le refactoring n'a introduit aucune régression et que la nouvelle fonctionnalité est robuste.

- [ ] **Tâche :** Adapter les tests unitaires et d'intégration.
  - Les tests doivent refléter l'architecture stateless.
  - Dans `tests/test_llm_api_service.py` et `tests/test_api_integration.py`, modifie les tests pour passer l'`llm_id` aux fonctions `send_...` et vérifie que la bonne configuration est utilisée.
  - Ajoute un test qui vérifie qu'un modèle avec `enabled = false` n'apparaît pas dans la liste retournée par `get_available_llms()`.
  - ✅ **Critère d'acceptation :** Tous les tests dans la suite `pytest` passent avec succès.

- [ ] **Tâche :** Effectuer des tests manuels complets.
  - Crée un `config.ini` avec au moins 3 modèles (ex: un Ollama, un OpenAI, et un désactivé).
  - Vérifie que seuls les modèles activés apparaissent dans le sélecteur.
  - Vérifie que le modèle par défaut est bien sélectionné au démarrage.
  - Teste l'envoi de messages avec chaque modèle et valide que les réponses proviennent bien des bons services.
  - Teste les différents paramètres (ex: `stream_response = false` sur un modèle) pour confirmer qu'ils sont bien respectés.
  - ✅ **Critère d'acceptation :** Tous les scénarios de test manuels se déroulent comme attendu.

## Phase 5 : Finalisation

La dernière ligne droite !

- [ ] **Tâche :** Créer une Pull Request (PR) claire et concise.
  - Assure-toi que tout ton code est "commit" et poussé sur ta branche.
  - Ouvre une PR vers la branche principale.
  - Dans la description, résume les changements, explique le "breaking change" pour le `config.ini` et fais référence à ce plan d'action.
  - ✅ **Critère d'acceptation :** La Pull Request est créée et prête pour la relecture par l'équipe.

## Points d'attention importants

### ⚠️ Architecture stateless
- **Important :** L'API backend doit rester stateless. Chaque appel doit inclure l'ID du modèle à utiliser.
- Le frontend gère la persistance du choix utilisateur via le localStorage.
- Pas de notion de "modèle actif" côté backend, uniquement un modèle par défaut.

### 🔄 Breaking changes
- Les utilisateurs devront migrer leur `config.ini` existant.
- La section `[LLMServer]` n'existera plus.
- Les intégrations externes devront passer l'`llm_id` dans leurs appels.

### 🔒 Sécurité
- Les clés API doivent rester isolées par modèle.
- Ne jamais exposer les clés API dans les logs ou l'interface.
- Valider que l'`llm_id` reçu existe bien dans la configuration.

### 🧪 Tests critiques à ne pas oublier
1. Configuration avec 0 modèle → Message d'erreur clair.
2. Configuration avec 1 seul modèle → Le sélecteur peut être masqué ou disabled.
3. Configuration avec N modèles → Sélecteur fonctionnel avec le bon défaut.
4. Modèle avec `enabled = false` → N'apparaît pas dans la liste.
5. Changement de modèle en cours de conversation → Continuité assurée.

## Structure de configuration cible

```ini
# Exemple de configuration multi-modèles

[LLM:GPT-4o]
url = https://api.openai.com/v1
apikey = sk-xxxxxxxxxxxxx
model = gpt-4o
api_type = openai
enabled = true  # Si false, ce modèle n'apparaîtra pas dans le sélecteur
stream_response = true
ssl_verify = true
timeout_seconds = 300
temperature = 0.7
max_tokens = 4096
default = true  # Ce modèle sera sélectionné par défaut au démarrage

[LLM:Claude-3.5 Sonnet]
url = https://api.anthropic.com/v1
apikey = sk-ant-xxxxxxxxxxxxx
model = claude-3-5-sonnet-20241022
api_type = anthropic  # ou openai si utilisation via proxy OpenAI-compatible
enabled = true
stream_response = true
ssl_verify = true
timeout_seconds = 300
temperature = 0.5
max_tokens = 8192
default = false

[LLM:Ollama Llama3 Local]
url = http://localhost:11434
apikey =  # Pas de clé API pour Ollama local
model = llama3:70b
api_type = ollama
enabled = true
stream_response = false  # Désactivé pour ce modèle spécifique
ssl_verify = false
timeout_seconds = 600  # Timeout plus long pour les modèles locaux
temperature = 0.8
# max_tokens non défini : utilisera le défaut du modèle

[LLM:Modèle Désactivé]
url = https://api.example.com
apikey = xxx
model = test-model
api_type = openai
enabled = false  # Ce modèle n'apparaîtra PAS dans le sélecteur

# Note: Les sections SummarizerLLM et TitleGeneratorLLM peuvent être conservées
# pour une future évolution, mais ne sont pas traitées dans ce refactoring
```

## Critères de succès

✅ **Le refactoring est réussi si :**
1. L'application fonctionne avec plusieurs modèles LLM configurés indépendamment.
2. L'utilisateur peut changer de modèle via le sélecteur dans l'interface.
3. Chaque appel API utilise la configuration complète du modèle spécifié.
4. Les modèles avec `enabled = false` n'apparaissent pas dans le sélecteur.
5. Le modèle marqué `default = true` est sélectionné au démarrage.
6. Le choix de l'utilisateur est persisté dans le localStorage.
7. Tous les tests unitaires et d'intégration passent.
8. La documentation est claire sur le nouveau format de configuration.
9. Aucune régression n'est introduite dans les fonctionnalités existantes.

---

## Notes importantes pour l'implémentation

### Philosophie de l'approche stateless
- Le backend ne maintient pas d'état sur le modèle "actif".
- Chaque requête contient l'ID du modèle à utiliser.
- Si aucun ID n'est fourni, utiliser le modèle par défaut.
- Cela rend l'API plus flexible et facilite les intégrations futures.

### Gestion des services spécialisés (SummarizerLLM, TitleGeneratorLLM)
- **Pour cette première itération**, nous ne touchons pas à ces services.
- Ils continueront à fonctionner avec leur logique actuelle.
- Une évolution future pourra les intégrer dans le système multi-modèles.

### Points de vigilance
1. **Validation des entrées** : Toujours vérifier que l'`llm_id` reçu existe.
2. **Fallback intelligent** : Si le modèle demandé n'existe pas, utiliser le défaut.
3. **Gestion d'erreur** : Messages clairs si aucun modèle n'est configuré.
4. **Compatibilité API** : L'API Anthropic peut nécessiter un format différent.

### Améliorations futures possibles
1. Indicateur visuel du modèle en cours d'utilisation dans les réponses.
2. Possibilité de changer de modèle en cours de conversation.
3. Statistiques d'utilisation par modèle.
4. Tests automatiques de connexion pour chaque modèle configuré.