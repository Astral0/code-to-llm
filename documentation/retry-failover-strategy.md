# Stratégie de Retry et Failover pour les Serveurs LLM

## Vue d'ensemble

Cette solution implémente une stratégie intelligente de retry et failover pour gérer les erreurs 504 et autres problèmes de surcharge sur les serveurs LLM.

## Fonctionnalités principales

### 1. **Retry Manager avec Circuit Breaker**
- **Backoff exponentiel** : Les délais entre les tentatives augmentent progressivement (1s, 2s, 4s, 8s...)
- **Jitter aléatoire** : Évite le "thundering herd" en ajoutant une variation aléatoire aux délais
- **Circuit breaker** : Après 3 échecs consécutifs, un endpoint est temporairement désactivé
- **Récupération automatique** : Les endpoints défaillants sont réessayés après 2 minutes

### 2. **Failover automatique**
- **Rotation intelligente** : Bascule automatiquement entre les 3 endpoints configurés
- **Sélection par taux de succès** : Privilégie les endpoints avec le meilleur historique
- **Mémorisation des états** : Suit l'état de santé de chaque endpoint

### 3. **Notifications visuelles**
- **Notifications en temps réel** : Affiche l'état des tentatives dans l'interface
- **Barre de progression** : Montre le temps avant la prochaine tentative
- **Codes couleur** :
  - 🟡 Jaune : Retry en cours
  - 🔵 Turquoise : Basculement d'endpoint
  - 🔴 Rouge : Erreur critique

## Architecture

### Services modifiés

1. **`services/retry_manager.py`** (nouveau)
   - Gère la logique de retry et failover
   - Implémente le circuit breaker
   - Suit l'état de santé des endpoints

2. **`services/llm_api_service.py`** (modifié)
   - Intègre le RetryManager
   - Sépare les méthodes internes pour le retry
   - Ajoute les callbacks d'erreur

3. **`main_desktop.py`** (modifié)
   - Enregistre les callbacks d'erreur
   - Transmet les notifications à l'interface
   - Expose les méthodes de statut de santé

4. **`static/llm_error_handler.js`** (nouveau)
   - Gère l'affichage des notifications
   - Maintient l'historique des erreurs
   - Affiche le statut de santé

## Configuration

Les paramètres de retry sont configurables dans `llm_api_service.py` :

```python
self.retry_manager = RetryManager(
    endpoints=list(self._llm_models.keys()),
    max_retries=6,           # Nombre maximum de tentatives
    initial_backoff=1.0,     # Délai initial (secondes)
    max_backoff=30.0,        # Délai maximum (secondes)
    backoff_multiplier=2.0,  # Multiplicateur exponentiel
    jitter=True,             # Ajouter du jitter aléatoire
    failure_threshold=3,     # Échecs avant circuit breaker
    recovery_time=120        # Temps de récupération (secondes)
)
```

## Comportement

### Scénario type avec erreur 504

1. **Première tentative** sur `iag.edf.fr` → Erreur 504
   - Notification : "Tentative 1: Échec sur iag.edf.fr"
   - Attente : 1 seconde

2. **Deuxième tentative** sur `iag.edf.fr` → Erreur 504
   - Notification : "Tentative 2: Échec sur iag.edf.fr"
   - Attente : 2 secondes

3. **Troisième tentative** sur `iag.edf.fr` → Erreur 504
   - Circuit breaker s'active pour `iag.edf.fr`
   - Notification : "Basculement vers oneapi"

4. **Quatrième tentative** sur `oneapi` → Succès
   - La réponse est retournée normalement

### États des endpoints

- **HEALTHY** : Endpoint fonctionnel
- **DEGRADED** : Quelques échecs mais encore utilisable
- **CIRCUIT_OPEN** : Trop d'échecs, temporairement désactivé

## Utilisation

### Pour les développeurs

La solution est transparente. Les appels LLM utilisent automatiquement le système de retry :

```python
# L'appel utilise automatiquement le retry manager
result = self.llm_service.send_to_llm(chat_history)
```

### Pour les utilisateurs

Les utilisateurs verront :
- Des notifications visuelles des tentatives de retry
- Les basculements entre serveurs
- Une barre de progression pendant l'attente

## Test

Exécutez le script de test pour vérifier le fonctionnement :

```bash
python test_retry_manager.py
```

Ce script simule des échecs et vérifie :
- Le retry avec backoff exponentiel
- Le failover entre endpoints
- Le circuit breaker
- La récupération automatique

## Monitoring

### API de statut

Récupérer le statut de santé des endpoints :

```python
health_status = desktop_app.get_llm_health_status()
```

Retourne :
```json
{
  "iag.edf.fr": {
    "state": "healthy",
    "success_rate": 0.95,
    "consecutive_failures": 0,
    "total_requests": 150
  },
  "oneapi": {
    "state": "degraded",
    "success_rate": 0.80,
    "consecutive_failures": 2,
    "total_requests": 50
  }
}
```

### Réinitialisation manuelle

Pour réinitialiser un endpoint défaillant :

```python
desktop_app.reset_llm_endpoint("iag.edf.fr")
```

## Avantages

1. **Résilience** : Continue de fonctionner même si un serveur est surchargé
2. **Performance** : Privilégie les endpoints les plus fiables
3. **Transparence** : L'utilisateur est informé des problèmes
4. **Automatique** : Pas d'intervention manuelle nécessaire
5. **Intelligent** : S'adapte à la charge et aux pannes

## Limitations

- Les 3 endpoints configurés pointent vers le même serveur Google (chemins différents)
- Le circuit breaker ne distingue pas les types d'erreurs (504 vs autres)
- Les notifications peuvent s'accumuler si tous les serveurs sont down

## Évolutions futures possibles

1. **Persistance** : Sauvegarder l'état de santé entre les sessions
2. **Métriques** : Dashboard de monitoring détaillé
3. **Configuration dynamique** : Ajuster les paramètres sans redémarrer
4. **Priorisation** : Définir des endpoints prioritaires
5. **Health checks** : Vérifications proactives de santé