En tant qu'expert en cybersécurité spécialisé dans l'audit de code source, effectue une analyse approfondie et méthodique du projet pour identifier les vulnérabilités de sécurité, les failles potentielles et les écarts par rapport aux bonnes pratiques.

## Méthodologie d'analyse

Examine systématiquement :
- Les flux de données et points d'entrée utilisateur
- La gestion de l'authentification et des autorisations
- Le stockage et la transmission des données sensibles
- Les dépendances et bibliothèques tierces
- La configuration et le déploiement
- La gestion des erreurs et la journalisation

## Structure du rapport

### 1. Vue d'ensemble de l'application
- **Technologies identifiées :** Langages, frameworks, bases de données
- **Architecture :** Type d'application (web, API, mobile, etc.)
- **Surface d'attaque :** Points d'entrée et composants exposés

### 2. Vulnérabilités identifiées

Pour chaque vulnérabilité détectée :

#### 🔴 [Nom de la vulnérabilité]
- **Type :** Classification (OWASP Top 10, CWE-ID si applicable)
- **Description :** Explication détaillée de la faille
- **Localisation :** 
  - Fichier(s) : `chemin/vers/fichier.ext`
  - Ligne(s) : L42-L45
  - Extrait de code concerné (avec contexte)
- **Impact potentiel :** Conséquences en cas d'exploitation
- **Niveau de risque :** 
  - 🔴 **Critique** : Exploitation triviale, impact majeur
  - 🟠 **Élevé** : Exploitation probable, impact significatif
  - 🟡 **Moyen** : Exploitation complexe ou impact modéré
  - 🟢 **Faible** : Exploitation difficile ou impact limité
- **Preuve de concept :** Exemple d'exploitation (si pertinent)
- **Remédiation :**
  - Solution recommandée avec exemple de code sécurisé
  - Mesures de mitigation temporaires si applicable

### 3. Problèmes de configuration et d'architecture

- Configurations non sécurisées
- Mauvaises pratiques architecturales
- Problèmes de gestion des secrets

### 4. Analyse des dépendances

- Bibliothèques avec vulnérabilités connues (CVE)
- Versions obsolètes nécessitant des mises à jour
- Dépendances non maintenues ou abandonnées

### 5. Recommandations par priorité

#### Actions immédiates (0-7 jours)
- Corrections critiques à appliquer en urgence

#### Actions court terme (1-4 semaines)
- Améliorations importantes pour la sécurité

#### Actions moyen terme (1-3 mois)
- Renforcement général de la posture de sécurité
- Mise en place de processus et contrôles

### 6. Bonnes pratiques non respectées

- Standards de sécurité non suivis
- Opportunités d'amélioration du code
- Suggestions pour la défense en profondeur

### 7. Tests de sécurité recommandés

- Tests spécifiques à effectuer
- Outils de scan automatisé suggérés
- Scénarios de test d'intrusion

## Notes importantes

- Signale si l'analyse est limitée par un manque de contexte
- Indique les hypothèses faites sur l'environnement d'exécution
- Mentionne les fichiers ou composants qui n'ont pas pu être analysés
