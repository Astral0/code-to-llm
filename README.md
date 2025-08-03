# 🔍 LLM Context Builder - Desktop Edition

Application desktop pour préparer le contexte de vos projets de code pour l'analyse et la modification par LLM. Créez un contexte concis et bien formaté de vos projets, facilement partageable avec les LLMs.

> 🛡️ **Sécurité** : Détecte et masque automatiquement les informations sensibles comme les clés API, identifiants et tokens pour éviter leur partage accidentel avec les LLMs.

## 🚀 Fonctionnalités Principales

- **📁 Scan Intelligent** : Parcourt récursivement les répertoires en respectant automatiquement les règles .gitignore
- **🎨 Formatage Optimal** : Crée des blocs de code avec détection automatique du langage
- **🌳 Visualisation Arborescente** : Génère une représentation visuelle de la structure du projet
- **💻 Interface Desktop Native** : Application autonome avec sélecteur de fichiers système
- **🔐 Protection des Données Sensibles** : Détecte et masque les clés API, mots de passe, tokens et autres identifiants
- **📊 Estimation des Tokens** : Fournit un nombre approximatif de tokens pour les fenêtres de contexte LLM
- **🧰 Toolbox Développeur** : Assistant IA avancé avec bibliothèque de prompts pour le développement

## 📸 Aperçu

![Interface principale](https://github.com/user-attachments/assets/e2816992-9967-403a-b8d6-3df66e618a0e)

### Interface Desktop

- **Sélection Native** : Dialogue système pour choisir un répertoire local
- **Arbre de Fichiers Interactif** : Sélectionnez/désélectionnez les fichiers à inclure
- **Instructions Personnalisées** : Ajoutez des instructions spécifiques au contexte
- **Masquage des Secrets** : Activez/désactivez la protection des données sensibles
- **Copie Rapide** : Copiez le contexte généré dans le presse-papiers

## ⚙️ Installation

### Prérequis

- Python 3.8+
- Windows (pour l'exécution via `run.bat`)

### Installation Rapide

```bash
git clone https://github.com/Astral0/code-to-llm.git
cd code-to-llm
pip install -r requirements.txt
```

### Configuration

Créez `config.ini` à partir de `config.ini.template` et personnalisez-le :

```ini
[Instructions]
instruction1_text = Ne fais rien, attends mes instructions.
instruction2_text = Si des modifications du code source sont nécessaires, présente ta réponse sous forme de patch Linux.

[LLMServer]
url = YOUR_LLM_API_URL_HERE      # ex: https://api.openai.com/v1 ou http://localhost:11434
apikey = YOUR_LLM_API_KEY_HERE   # Optionnel pour Ollama local, requis pour OpenAI
model = YOUR_LLM_MODEL_HERE      # ex: gpt-3.5-turbo ou llama3
api_type = openai                # 'openai' ou 'ollama'
enabled = true                   # Active l'intégration LLM
stream_response = true           # Active le streaming des réponses
```

## 🚀 Utilisation

### Lancement de l'Application

Double-cliquez sur `run.bat` ou exécutez :

```bash
run.bat
```

L'application s'ouvre dans une fenêtre native avec interface web intégrée.

### Workflow Type

1. **Sélectionner un Répertoire** : Cliquez sur "Sélectionner un répertoire" pour choisir votre projet
2. **Scanner** : L'application analyse le répertoire en respectant .gitignore
3. **Choisir les Fichiers** : Sélectionnez les fichiers à inclure dans le contexte
4. **Générer le Contexte** : Créez le document Markdown formaté
5. **Utiliser la Toolbox** : Ouvrez la Toolbox Développeur pour l'analyse IA

## 🧰 Toolbox Développeur

La Toolbox est un assistant IA intégré offrant des fonctionnalités avancées :

### Modes Disponibles

#### Mode API
- Communication directe avec l'API LLM configurée
- Historique de conversation local
- Export des conversations
- Compteur de tokens en temps réel
- Support du streaming

#### Mode Navigateur Intégré
- Ouvre les sites de chatbot (ChatGPT, Gemini, Claude) dans une fenêtre pywebview
- Navigation sécurisée au sein de l'application
- Idéal pour utiliser des services web sans quitter l'application

### Prompts Prédéfinis

Le répertoire `prompts/` contient des modèles optimisés :

1. **Analyse Générale** (`01_analyse_generale.md`)
   - Revue complète de l'architecture
   - Identification des points forts et axes d'amélioration
   - Résumé de la stack technique

2. **Analyse de Sécurité** (`02_analyse_securite.md`)
   - Audit de sécurité ciblé
   - Évaluation des risques (Critique/Élevé/Moyen/Faible)
   - Recommandations de sécurité

3. **Planification de Fonctionnalité** (`03_plan_action_fonctionnalite.md`)
   - Plans d'action détaillés
   - Modifications de fichiers nécessaires
   - Stratégie de test

4. **Revue de Code** (`04_revue_de_diff.md`)
   - Intégration automatique de `git diff`
   - Évaluation de la qualité
   - Suggestions d'amélioration

### Personnalisation des Prompts

Ajoutez vos propres prompts en créant des fichiers `.md` dans `prompts/` :

```markdown
# prompts/05_analyse_custom.md
Votre prompt personnalisé ici...
```

## 🛡️ Sécurité et Protection des Données

### Masquage Automatique

L'outil détecte et masque automatiquement :
- Clés API et tokens
- Mots de passe et identifiants
- Clés privées et certificats
- Chaînes de connexion avec identifiants
- Clés AWS et autres credentials cloud

Exemple de masquage :
```
[LINE CONTAINING SENSITIVE DATA: api_key]
```

### Méthodes de Détection

1. **Bibliothèque detect-secrets** : Détecteurs spécialisés pour différents types de secrets
2. **Patterns Regex personnalisés** : Motifs supplémentaires pour formats courants

## 📋 Format de Sortie

Le contexte généré inclut :

```
--- START CONTEXT ---
Objective: Provide the complete context of a project...
Security Note: Sensitive information has been masked...

--- START DIRECTORY TREE ---
Project_Root/
├── src/
│   ├── main.py
│   └── utils.py
└── README.md
--- END DIRECTORY TREE ---

--- START FILE: src/main.py ---
```python
# Code content here
```
--- END FILE: src/main.py ---
```

## 💡 Conseils d'Utilisation

- **Sélection Ciblée** : Pour les gros projets, sélectionnez uniquement les fichiers pertinents
- **Vérification Sécurité** : Toujours vérifier que les données sensibles sont masquées
- **Gestion des Tokens** : Surveillez l'estimation pour rester dans les limites LLM
- **Instructions Claires** : Ajoutez des instructions précises pour guider le LLM

## 🔧 Configuration Avancée

### Exclusion de Fichiers

Par défaut, l'application ignore :
- `.git/`, `__pycache__/`, `.gitignore`
- `.vscode/`, `.idea/`, `.kilocode/`, `.claude/`
- Fichiers binaires et médias
- Fichiers de lock (`package-lock.json`, etc.)

Personnalisez via `config.ini` :
```ini
[FileExclusion]
file_blacklist = .DS_Store, Thumbs.db
pattern_blacklist = *.min.js, *.min.css, *-lock.json
```

### Détection Binaire

```ini
[BinaryDetection]
extension_blacklist = .exe, .dll, .so, .pdf, .zip
extension_whitelist = .py, .js, .html, .css, .json
```

## 🤝 Contribution

Les contributions sont bienvenues ! N'hésitez pas à soumettre des Pull Requests.

## 📄 Licence

Ce projet est sous licence MIT - voir le fichier LICENSE pour plus de détails.

## 🆘 Support

Pour signaler des bugs ou demander des fonctionnalités, ouvrez une issue sur GitHub.