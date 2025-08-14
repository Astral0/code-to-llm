# Modèles de Données - Gestion des Conversations

## Structure JSON de la "Capsule Temporelle" (v2.0)

Cette structure représente le format de stockage d'une conversation dans le système de gestion avancée des conversations.

```json
{
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "Titre de la conversation",
    "version": "2.0",
    "createdAt": "2025-01-12T10:00:00Z",
    "updatedAt": "2025-01-12T10:30:00Z",
    "metadata": {
        "mode": "api",
        "tags": [],
        "isSummary": false,
        "sourceConversationId": null,
        "lock": {
            "active": true,
            "instanceId": "c9b7e4f0-9a3e-4f1a-b34b-12345abcdef",
            "timestamp": "2025-01-12T10:30:00Z",
            "user": "username",
            "host": "hostname"
        }
    },
    "context": {
        "fullContext": "# Contexte du projet\n\n...",
        "metadata": {
            "projectPath": "C:\\Users\\username\\project",
            "filesIncluded": 37,
            "estimatedTokens": 312585,
            "contextHash": "sha256:abcdef123456..."
        }
    },
    "history": [
        {
            "role": "user",
            "content": "Contenu du message utilisateur",
            "timestamp": "2025-01-12T10:00:00Z"
        },
        {
            "role": "assistant",
            "content": "Réponse de l'assistant",
            "timestamp": "2025-01-12T10:01:00Z"
        }
    ]
}
```

## Description des champs

### Racine
- `id` : UUID unique de la conversation
- `title` : Titre de la conversation (généré automatiquement ou défini par l'utilisateur)
- `version` : Version du format de données
- `createdAt` : Date de création (ISO 8601 UTC)
- `updatedAt` : Date de dernière modification (ISO 8601 UTC)

### Metadata
- `mode` : Mode de conversation ("api" ou "toolbox")
- `tags` : Liste de tags pour organiser les conversations
- `isSummary` : Indique si c'est une synthèse d'une autre conversation
- `sourceConversationId` : ID de la conversation source (si synthèse)
- `lock` : Informations de verrouillage
  - `active` : État du verrou (true/false)
  - `instanceId` : UUID de l'instance qui détient le verrou
  - `timestamp` : Date du verrouillage
  - `user` : Nom d'utilisateur système
  - `host` : Nom de la machine

### Context
- `fullContext` : Contexte complet du projet au moment de la conversation
- `metadata` : Métadonnées du contexte
  - `projectPath` : Chemin du projet
  - `filesIncluded` : Nombre de fichiers inclus
  - `estimatedTokens` : Estimation du nombre de tokens
  - `contextHash` : Hash du contexte pour détecter les changements

### History
- Liste des messages échangés
  - `role` : "user" ou "assistant"
  - `content` : Contenu du message
  - `timestamp` : Date/heure du message

## Système de verrouillage

Le système de verrouillage permet de gérer la concurrence entre plusieurs instances de l'application :

1. **Verrouillage à la création/modification** : Toute sauvegarde applique automatiquement le verrou de l'instance
2. **Vérification avant modification** : Une instance ne peut modifier que les conversations qu'elle verrouille
3. **Libération explicite** : Le verrou peut être libéré sans modifier la conversation
4. **Libération automatique** : Les verrous sont libérés à la fermeture de la fenêtre Toolbox
5. **Gestion des verrous orphelins** : Interface pour forcer le déverrouillage si nécessaire

## Format de fichier

Les conversations sont stockées dans des fichiers JSON individuels :
- Répertoire : `conversations/`
- Nom de fichier : `{id}.json`
- Encodage : UTF-8
- Indentation : 2 espaces