# Changelog

Tous les changements notables de ce projet seront documentés dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Non publié]

### 🎉 Ajouté - Décembre 2024

#### ⚡ Système de Retry Intelligent et Failover
- **Retry Manager avec Circuit Breaker** : Nouveau gestionnaire de retry intelligent (`services/retry_manager.py`)
  - Backoff exponentiel avec jitter pour éviter le "thundering herd"
  - Circuit breaker qui désactive temporairement les endpoints après 3 échecs consécutifs
  - Récupération automatique après 2 minutes
  - Jusqu'à 6 tentatives avec délais progressifs (1s → 30s)
  
- **Failover Automatique entre Endpoints** :
  - Rotation intelligente entre plusieurs modèles LLM configurés
  - Sélection basée sur le taux de succès historique
  - Bascule transparente sans interruption de service
  
- **Notifications Visuelles en Temps Réel** (`static/llm_error_handler.js`) :
  - Affichage des tentatives de retry avec barre de progression
  - Codes couleur : jaune (retry), turquoise (basculement), rouge (erreur critique)
  - Historique des erreurs consultable
  - Auto-suppression après délai configurable

#### 🌐 Support Proxy d'Entreprise
- **Configuration Proxy HTTP/HTTPS** : Support complet pour accéder aux LLM externes
  - Configuration indépendante par modèle LLM
  - Support de l'authentification proxy (Basic Auth)
  - Gestion des exclusions via `proxy_no_proxy`
  - Compatible avec tous les services : chat, résumé, génération de titre
  
- **Paramètres de Configuration** :
  ```ini
  proxy_http = http://proxy.entreprise.com:8080
  proxy_https = http://proxy.entreprise.com:8080
  proxy_no_proxy = localhost,127.0.0.1,.entreprise.local
  ```

#### 📊 Monitoring et Diagnostics
- **API de Santé des Endpoints** :
  - `get_llm_health_status()` : État détaillé de chaque endpoint
  - `reset_llm_endpoint()` : Réinitialisation manuelle d'un endpoint
  - Métriques : taux de succès, échecs consécutifs, total de requêtes
  
- **Scripts de Test et Diagnostic** :
  - `test_retry_manager.py` : Validation du système de retry et failover
  - `test_proxy_llm.py` : Vérification de la configuration proxy
  - `test_llm_error_display.py` : Test des notifications d'erreur
  - `test_error_notification.html` : Interface de test visuel des notifications

### 🔧 Modifié

#### Services LLM (`services/llm_api_service.py`)
- Intégration du RetryManager pour la gestion des erreurs
- Séparation des méthodes internes pour le retry (`_send_to_llm_internal`, `_send_to_llm_stream_internal`)
- Ajout de callbacks pour les notifications d'erreur
- Nouveau système de gestion des timeouts (adaptatif, 30s par défaut)
- Méthode `_get_proxy_config()` pour extraire la configuration proxy
- Support des proxies dans tous les appels HTTP

#### Interface Desktop (`main_desktop.py`)
- Enregistrement automatique des callbacks d'erreur LLM
- Nouvelle méthode `_handle_llm_error()` pour transmettre les erreurs au frontend
- Support de la configuration proxy lors du chargement des modèles
- APIs pour le monitoring : `get_llm_health_status()`, `reset_llm_endpoint()`

#### Serveur Web (`web_server.py`)
- Support proxy pour le SummarizerLLM
- Variables globales pour la configuration proxy
- Gestion améliorée des erreurs réseau

#### Interface Utilisateur (`templates/toolbox.html`, `static/toolbox.js`)
- Intégration du handler d'erreurs LLM
- Gestion des erreurs dans le streaming
- Appel automatique du handler global lors des échecs

### 📚 Documentation

- **Nouvelle documentation** :
  - `documentation/retry-failover-strategy.md` : Guide complet du système de retry et failover
  - `documentation/proxy-configuration.md` : Configuration détaillée du proxy avec exemples
  - `documentation/CHANGELOG.md` : Ce fichier de suivi des modifications
  
- **README.md mis à jour** :
  - Section "Nouvelles Fonctionnalités" avec les ajouts récents
  - Section "Dépannage" pour les erreurs fréquentes
  - Exemples de configuration proxy

### 🐛 Corrigé

- Gestion des erreurs de timeout qui n'étaient pas correctement propagées
- Amélioration de la détection des erreurs de connexion
- Correction de l'encodage des caractères spéciaux dans les notifications

### 🔒 Sécurité

- Support de l'authentification proxy sécurisée
- Gestion des exclusions de proxy pour les domaines internes
- Pas de modification des paramètres SSL par défaut

## [1.0.0] - 2024-11-30

### Version initiale
- Application de bureau native avec Flask + pywebview
- Scan de projet intelligent avec respect des .gitignore
- Masquage de secrets avancé
- Persistance de sélection de fichiers
- Gestion de conversations avec verrouillage
- Toolbox développeur avec modes API et navigateur
- Bibliothèque de prompts prédéfinis
- Export multi-format (Markdown, DOCX, PDF)
- Support multi-modèles LLM
- Génération automatique de titres par IA