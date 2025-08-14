Rôle et Mission :

Agis en tant que Développeur Senior et Mentor Technique. Ta mission est de générer un plan d'action complet et détaillé, sous forme de "todo list", pour un développeur junior qui doit réaliser un chantier de refactoring technique. Le plan doit être si clair qu'il minimise le besoin de supervision.

Contexte Technique du Chantier :

L'objectif est de 
Le code de l'application est en FastAPI pour la backend et React pour le frontend et les tests utilisent Pytest.

Destinataire du Plan d'Action :

Le plan est destiné à un développeur junior. Les instructions doivent donc être atomiques, explicites et ne laisser aucune place à l'ambiguïté. Le ton doit être encourageant, pédagogique et précis.

Format de Sortie Exigé :

Structure ta réponse en Markdown en suivant impérativement ce format :

1.  **Titre principal :** `Plan d'action : XXX`
    
2.  **Phases numérotées :** Découpe le plan en grandes phases logiques (ex: 0. Préparation de l'environnement, 1. Analyse et premier jalon, 2. Migration progressive, etc.).
    
3.  **Tâches en checklist :** Pour chaque phase, liste les tâches unitaires à réaliser sous forme de checklist (`- [ ] Action à faire`).
    
4.  **Critères d'acceptation obligatoires :** Pour **CHAQUE** tâche de la checklist, ajoute un sous-point intitulé `✅ **Critère d'acceptation :**` qui décrit de manière non-équivoque comment valider que la tâche est terminée et réussie.
    
5.  **Commandes et extraits de code :** Inclus les commandes shell (`git`, `docker`, etc.) et les extraits de code pertinents pour guider le développeur.
    

**Contenu Spécifique à Inclure :**

-   **Phase 0 : Préparation et Installation**
    
    -   Commence par une étape sur la création d'une branche Git dédiée (ex: `feature/xxx-xxx`).
        
    -   Détaille la procédure d'installation de l'application en local pour le développement, en te basant sur le fichier `INSTALLATION.md`. Précise qu'il faut utiliser une base de données **SQLite** pour cette configuration initiale.
        
    -   Inclus une tâche pour lancer la suite de tests existante et vérifier que tout fonctionne avant de commencer les modifications. Le critère d'acceptation sera "La suite de tests passe à 100% sur la branche `main` ou `develop` avant toute modification".
        
-   **Phases suivantes : Migration**
    
    -   Détaille la stratégie pour identifier les tests à migrer.
        
    -   Propose une approche itérative : migrer un seul fichier de test en premier pour servir d'exemple.
        
    -   Explique comment créer le mécanisme de setup/teardown de la base de données de test.
        
    -   Termine par une phase de validation finale et de nettoyage du code.
        
-   **Points de communication :**
    
    -   Insère des rappels pour que le développeur demande une revue de code (Pull Request) à des étapes clés (ex: après la migration du premier fichier de test).
        
    -   Encourage-le à poser des questions s'il est bloqué.
        

**Exemple de structure attendue pour une tâche :**

-   [ ] **Tâche :** Isoler le premier fichier de test `tests/test_users.py`.
    
    -   ✅ **Critère d'acceptation :** Les tests dans `tests/test_users.py` s'exécutent désormais sur leur propre base de données temporaire et réussissent. Tous les autres tests continuent de fonctionner comme avant.