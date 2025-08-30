# 🚀 LLM Context Builder - Édition Desktop

Une application de bureau complète pour préparer, analyser et interagir avec vos projets de code via des LLMs. Créez un contexte de projet sécurisé et optimisé, et dialoguez avec une IA grâce à une boîte à outils de développement intégrée.

> 🛡️ **Sécurité avant tout** : Cet outil intègre un puissant mécanisme de détection et de masquage des secrets (clés API, mots de passe, tokens) pour prévenir toute fuite d'informations sensibles vers les modèles de langage.

![Aperçu de l'interface](https://github.com/user-attachments/assets/e2816992-9967-403a-b8d6-3df6e618a0e)

## ✨ Fonctionnalités Clés

- **🖥️ Application de Bureau Native** : Interface utilisateur web moderne (`Flask` + `pywebview`) encapsulée dans une application de bureau autonome pour une expérience fluide et intégrée.
- **🧠 Scan de Projet Intelligent** : Analyse les répertoires locaux en respectant automatiquement les règles `.gitignore` et en filtrant les fichiers non pertinents (binaires, logs, etc.).
- **🔐 Masquage de Secrets Avancé** : Utilise `detect-secrets` et des expressions régulières pour identifier et masquer les informations sensibles avant la génération du contexte.
- **🔄 Persistance de Sélection de Fichiers** : Sauvegarde automatiquement votre sélection de fichiers et permet de la restaurer en un clic lors de la prochaine ouverture du projet. Identifie et met en évidence les nouveaux fichiers ajoutés depuis la dernière session.
- **💾 Gestion de Conversations** : Sauvegardez, chargez, dupliquez et gérez vos sessions de chat avec **génération automatique de titre par IA**. Le système inclut le contexte du projet et un **mécanisme de verrouillage** pour un travail multi-instances sécurisé.
- **🧰 Toolbox Développeur Augmenté** : Un puissant assistant IA intégré avec deux modes :
    - **Mode API** : Un client de chat direct avec votre LLM configuré (supporte OpenAI et Ollama), avec gestion de l'historique, streaming, et export des conversations.
    - **Mode Navigateur** : Pilote une fenêtre de navigateur intégrée pour interagir avec des services comme ChatGPT, Gemini ou Claude AI directement depuis l'application.
- **📚 Bibliothèque de Prompts** : Une collection de prompts prédéfinis et personnalisables pour des tâches complexes : analyse d'architecture, audit de sécurité, planification de fonctionnalités, etc.
- **🔄 Intégration `git diff`** : Analysez en un clic les modifications en attente (`--staged`) pour générer des messages de commit ou obtenir des revues de code.
- **📄 Export Multi-format** : Exportez vos conversations au format Markdown, DOCX ou PDF.
- **⚡ Gestion Avancée des Erreurs** : Système de retry intelligent avec circuit breaker, failover automatique entre endpoints LLM et notifications visuelles en temps réel.
- **🌐 Support Proxy d'Entreprise** : Configuration proxy HTTP/HTTPS pour accéder aux LLM externes depuis un environnement d'entreprise avec restrictions réseau.

## ⚙️ Installation

### Prérequis
- Windows (l'application est optimisée pour Windows via `run.bat`)
- [Miniconda](https://docs.conda.io/en/latest/miniconda.html) ou Anaconda

### Étapes d'installation
1.  Clonez le dépôt :
    ```bash
    git clone https://github.com/Astral0/code-to-llm.git
    cd code-to-llm
    ```
2.  Le script `run.bat` est conçu pour automatiser la configuration. Il va :
    - Chercher votre installation Conda.
    - Vérifier et activer l'environnement `code2llm` (il doit exister).
    - Lancer l'application.

    Si c'est la première fois, créez l'environnement Conda :
    ```bash
    conda create -n code2llm python=3.9
    conda activate code2llm
    pip install -r requirements.txt
    ```
3.  **Configuration Essentielle** :
    Copiez `config.ini.template` vers `config.ini` et configurez-le. L'application supporte maintenant **plusieurs modèles LLM indépendants** que vous pouvez sélectionner directement depuis l'interface :
    
    ```ini
    # Chaque section [LLM:nom] définit un modèle indépendant
    # Le nom après "LLM:" apparaîtra dans le sélecteur de l'interface
    
    [LLM:GPT-4o]
    url = https://api.openai.com/v1
    apikey = YOUR_OPENAI_API_KEY_HERE
    model = gpt-4o
    api_type = openai
    enabled = true  # Mettre à true pour activer ce modèle
    stream_response = true
    ssl_verify = true
    timeout_seconds = 300
    temperature = 0.7
    max_tokens = 4096
    default = true  # Ce modèle sera sélectionné par défaut
    # Configuration proxy optionnelle (décommentez si nécessaire)
    # proxy_http = http://proxy.entreprise.com:8080
    # proxy_https = http://proxy.entreprise.com:8080
    # proxy_no_proxy = localhost,127.0.0.1,.entreprise.local
    
    [LLM:Ollama Local]
    url = http://localhost:11434
    apikey =  # Pas de clé API pour Ollama local
    model = llama3:70b
    api_type = ollama
    enabled = true
    stream_response = false
    ssl_verify = false
    timeout_seconds = 600
    ```
    
    **Nouvelles fonctionnalités :**
    - **Multi-modèles** : Configurez autant de modèles que nécessaire
    - **Sélecteur dans l'interface** : Changez de modèle à la volée sans redémarrer
    - **Configuration indépendante** : Chaque modèle a ses propres paramètres
    - **Persistance du choix** : Le modèle sélectionné est mémorisé entre les sessions
4.  Lancez l'application en double-cliquant sur **`run.bat`**.

## 🚀 Guide d'Utilisation

1.  **Scanner un Projet** :
    - Lancez l'application via `run.bat`.
    - Cliquez sur **"Sélectionner un répertoire"** pour ouvrir la boîte de dialogue native.
    - Choisissez votre projet et cliquez sur **"Scanner le répertoire"**.
2.  **Sélectionner les Fichiers** :
    - L'arbre des fichiers de votre projet (filtrés) apparaît.
    - Si vous avez déjà travaillé sur ce projet, une section **"Session Précédente Détectée"** apparaît :
        - Cliquez sur le bouton **"Restaurer la sélection précédente"** pour réappliquer votre sélection de fichiers.
        - Les **nouveaux fichiers** ajoutés depuis votre dernière session sont mis en évidence dans une section dédiée.
    - Cochez les fichiers et dossiers que vous souhaitez inclure dans le contexte.
3.  **Générer le Contexte** :
    - Dans la section 3, ajoutez des instructions initiales au LLM si nécessaire.
    - Choisissez un mode de **Compression** si besoin (Mode Compact ou Résumé par IA).
    - Cliquez sur **"Generate context for selection"**.
4.  **Interagir avec l'IA** :
    - Le contexte Markdown est généré et affiché.
    - Cliquez sur **"Ouvrir la Toolbox"**.
    - Choisissez votre mode (`API` ou `Navigateur Intégré`).
    - Dans la Toolbox, cliquez sur **"Importer le contexte du projet"**.
    - Vous pouvez maintenant utiliser les prompts ou discuter avec l'IA à propos de votre code.

## 💾 Gestion Avancée des Conversations

La Toolbox va au-delà d'un simple chat en proposant un système de sauvegarde complet, transformant chaque session en une "capsule temporelle" réutilisable.

### 🎯 Génération Automatique de Titres par IA
Lors de la sauvegarde d'une conversation, vous pouvez :
- **Saisir manuellement** un titre descriptif
- **Utiliser la baguette magique** 🪄 pour obtenir une suggestion de titre générée par l'IA qui analyse le contenu de votre conversation
- L'IA effectue une **analyse sémantique** en ignorant les blocs de code pour se concentrer sur le sujet principal de la discussion

### "Capsules Temporelles" de Conversation
Chaque sauvegarde n'enregistre pas seulement l'historique des messages, mais aussi **l'intégralité du contexte du projet** tel qu'il était au moment de la conversation. Cela vous permet de reprendre une analyse ou un développement exactement là où vous l'aviez laissé, même si le code source a changé depuis.

### Système de Verrouillage Multi-Instance
Pour garantir l'intégrité de vos données, un système de verrouillage intelligent est intégré :
-   **Verrouillage Automatique** : Lorsque vous chargez ou sauvegardez une conversation, elle est automatiquement "verrouillée" par votre session.
-   **Prévention des Conflits** : Si vous ouvrez la même conversation dans une autre fenêtre, elle apparaîtra comme verrouillée, vous empêchant de la modifier et d'écraser accidentellement des données.
-   **Information Visuelle** : Des icônes claires indiquent le statut de chaque conversation (verrouillée par vous, par un autre, ou libre).
-   **Gestion des Verrous** : Vous pouvez libérer manuellement vos verrous ou forcer la libération d'un verrou orphelin si une instance de l'application s'est mal fermée.

### Fonctionnalités de l'Interface
Depuis la barre latérale de la Toolbox, vous pouvez :
-   **Sauvegarder** la conversation actuelle.
-   **Charger** une conversation existante pour restaurer l'historique et le contexte.
-   **Dupliquer** une conversation pour explorer une nouvelle piste d'analyse sans altérer l'original.
-   **Renommer** vos conversations pour mieux les organiser.
-   **Supprimer** les sessions dont vous n'avez plus besoin.

## 🏗️ Architecture Technique

Le projet adopte une architecture orientée services pour garantir la modularité, la testabilité et la clarté. La classe `Api` dans `main_desktop.py` sert de **façade**, orchestrant les appels aux différents services backend.

- **`main_desktop.py` (API Façade)** : Point d'entrée de l'application de bureau. Gère les fenêtres (`pywebview`), expose les méthodes Python au JavaScript et orchestre les services.
- **`web_server.py` (Serveur Flask)** : Serveur local qui rend les templates HTML et fournit des endpoints API (principalement pour le mode web historique, mais utilisé par la fenêtre pywebview).
- **`services/` (Logique Métier)** :
    - `FileService` : Gère le scan des systèmes de fichiers, l'application des règles `.gitignore`, le filtrage des fichiers binaires et le **masquage des secrets**.
    - `ContextBuilderService` : Assemble le contexte final en Markdown, génère l'arbre de fichiers et estime la taille en tokens.
    - `LlmApiService` : Gère toute la communication avec les API LLM (OpenAI, Ollama), y compris la gestion du streaming et une stratégie de `retry` intelligente.
    - `GitService` : Exécute les commandes Git, comme `git diff --staged`.
    - `ExportService` : Gère l'export des conversations en Markdown, DOCX et PDF.
- **`pywebview_driver.py` (Pilote Personnalisé)** : Un driver léger imitant l'API de Selenium pour interagir par programmation avec le contenu de la fenêtre de navigateur intégrée.
- **`tests/` (Suite de Tests)** : Le projet inclut des tests unitaires (`pytest`) pour chaque service ainsi que des tests d'intégration pour la façade `Api`, garantissant la robustesse de l'application.

## 🔧 Configuration Avancée

Le fichier `config.ini` permet une personnalisation fine :

### Configuration de la Génération de Titres par IA (`[TitleGeneratorLLM]`)

Configuration optionnelle pour personnaliser la génération automatique de titres. Si cette section est absente, le système utilise automatiquement la configuration de `[LLMServer]`.

```ini
[TitleGeneratorLLM]
# Activer/désactiver la fonctionnalité
enabled = true

# Configuration spécifique (optionnelle, utilise LLMServer si non définie)
# url = YOUR_TITLE_LLM_API_URL_HERE
# apikey = YOUR_TITLE_LLM_API_KEY_HERE
# model = gpt-3.5-turbo  # Modèle plus léger pour la génération de titres

# Prompt personnalisé pour la génération
title_prompt = Génère un titre court et descriptif...

# Paramètres de génération
max_title_length = 100
timeout_seconds = 15
# temperature = 0.5  # Plus déterministe pour les titres
```

### Exclusion de Fichiers (`[FileExclusion]`)

Excluez des fichiers ou des motifs de la sélection.

```ini
[FileExclusion]
# Fichiers spécifiques à exclure, séparés par des virgules
file_blacklist = .DS_Store, Thumbs.db, yarn.lock
# Motifs à exclure (supporte * et ?)
pattern_blacklist = *.min.js, *-lock.json, *.pyc
```

### Détection Binaire (`[BinaryDetection]`)

Affinez la détection des fichiers binaires.

```ini
[BinaryDetection]
# Extensions immédiatement rejetées
extension_blacklist = .png, .jpg, .exe, .dll, .so, .pdf, .zip, .woff
# Extensions immédiatement acceptées sans analyse de contenu
extension_whitelist = .py, .js, .html, .css, .json, .md, .txt, .sh
```

## 🆕 Nouvelles Fonctionnalités (Décembre 2024)

### ⚡ Gestion Intelligente des Erreurs Réseau

**Système de Retry avec Circuit Breaker** :
- **Retry automatique** : Jusqu'à 6 tentatives avec backoff exponentiel (1s → 30s)
- **Circuit breaker** : Désactive temporairement les endpoints défaillants après 3 échecs
- **Failover intelligent** : Bascule automatiquement entre les modèles LLM configurés
- **Notifications visuelles** : Affichage en temps réel des tentatives et erreurs
- **Récupération automatique** : Réactivation progressive des endpoints après 2 minutes

Cette fonctionnalité est particulièrement utile pour gérer :
- Les erreurs 504 Gateway Timeout
- Les surcharges serveur
- Les problèmes de connectivité réseau
- Les limites de quota atteintes

### 🌐 Support Proxy d'Entreprise

**Configuration proxy pour accéder aux LLM externes** :

```ini
[LLM:OpenAI-External]
url = https://api.openai.com/v1
apikey = YOUR_API_KEY
model = gpt-4
enabled = true
# Configuration proxy pour sortir sur Internet
proxy_http = http://proxy.entreprise.com:8080
proxy_https = http://proxy.entreprise.com:8080
proxy_no_proxy = localhost,127.0.0.1,.entreprise.local
```

**Caractéristiques** :
- Support proxy HTTP/HTTPS avec authentification
- Configuration indépendante par modèle LLM
- Exclusions via `proxy_no_proxy`
- Compatible avec SummarizerLLM et TitleGeneratorLLM
- Script de diagnostic inclus : `python test_proxy_llm.py`

**Cas d'usage** : Permet de basculer vers des services externes (OpenAI, Anthropic) lorsque les quotas internes sont atteints.

### 📊 Monitoring et Santé des Endpoints

- **Tableau de bord de santé** : Visualisation du statut de chaque endpoint LLM
- **Métriques** : Taux de succès, nombre de requêtes, dernière erreur
- **API de statut** : Récupération programmatique de l'état des services
- **Réinitialisation manuelle** : Possibilité de réactiver un endpoint

### 🛠️ Outils de Développement

**Scripts de test inclus** :
- `test_retry_manager.py` : Test du système de retry et failover
- `test_proxy_llm.py` : Vérification de la configuration proxy
- `test_llm_error_display.py` : Test des notifications d'erreur
- `test_error_notification.html` : Interface de test des notifications visuelles

**Documentation technique** :
- `docs/retry-failover-strategy.md` : Guide complet du système de retry
- `docs/proxy-configuration.md` : Configuration détaillée du proxy avec exemples

## 🔧 Dépannage

### Erreurs fréquentes

**Erreur 504 Gateway Timeout** :
- Le système de retry prend automatiquement le relais
- Vérifiez que plusieurs modèles LLM sont configurés pour le failover
- Augmentez `timeout_seconds` si nécessaire

**Erreur de connexion via proxy** :
- Vérifiez la configuration proxy dans `config.ini`
- Exécutez `python test_proxy_llm.py` pour diagnostiquer
- Assurez-vous que le domaine n'est pas bloqué par la politique d'entreprise

**Limite de tokens atteinte** :
- Basculez vers un autre modèle LLM via le sélecteur de l'interface
- Configurez un modèle externe avec proxy si nécessaire

## 🤝 Contribution

Les contributions sont les bienvenues ! Si vous souhaitez améliorer l'application, n'hésitez pas à forker le dépôt et à soumettre une Pull Request.

## 📄 Licence

Ce projet est sous licence MIT. Voir le fichier `LICENSE` pour plus de détails.
