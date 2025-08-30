# Configuration Proxy pour les LLM

## Vue d'ensemble

Cette documentation explique comment configurer un proxy HTTP/HTTPS pour accéder aux services LLM externes depuis un environnement d'entreprise avec des restrictions réseau.

## Cas d'usage

Lorsque votre clé API atteint sa limite de tokens sur les serveurs internes, vous pouvez basculer vers des services LLM externes (OpenAI, Anthropic, etc.) qui nécessitent de passer par un proxy d'entreprise pour sortir sur Internet.

## Configuration

### 1. Configuration par modèle LLM

Chaque modèle LLM peut avoir sa propre configuration proxy dans `config.ini`. Ajoutez ces paramètres dans la section du modèle concerné :

```ini
[LLM:GPT-4o]
url = https://api.openai.com/v1
apikey = YOUR_OPENAI_API_KEY
model = gpt-4o
api_type = openai
enabled = true
# Configuration proxy
proxy_http = http://proxy.entreprise.com:8080
proxy_https = http://proxy.entreprise.com:8080
proxy_no_proxy = localhost,127.0.0.1,.entreprise.local
```

### 2. Configuration pour le SummarizerLLM

Le service de résumé peut aussi utiliser un proxy :

```ini
[SummarizerLLM]
url = https://api.openai.com/v1
apikey = YOUR_API_KEY
model = gpt-3.5-turbo
api_type = openai
enabled = true
# Configuration proxy
proxy_http = http://proxy.entreprise.com:8080
proxy_https = http://proxy.entreprise.com:8080
proxy_no_proxy = localhost,127.0.0.1,.entreprise.local
```

### 3. Configuration pour le TitleGeneratorLLM

La génération automatique de titres peut également passer par un proxy :

```ini
[TitleGeneratorLLM]
enabled = true
# Hérite du modèle principal si non défini
proxy_http = http://proxy.entreprise.com:8080
proxy_https = http://proxy.entreprise.com:8080
proxy_no_proxy = localhost,127.0.0.1,.entreprise.local
```

## Paramètres de proxy

### `proxy_http`
- **Description** : URL du proxy pour les requêtes HTTP
- **Format** : `http://[utilisateur:motdepasse@]proxy.entreprise.com:port`
- **Exemple** : `http://proxy.entreprise.com:8080`
- **Avec authentification** : `http://user:pass@proxy.entreprise.com:8080`

### `proxy_https`
- **Description** : URL du proxy pour les requêtes HTTPS
- **Format** : Identique à `proxy_http`
- **Note** : Généralement la même valeur que `proxy_http`

### `proxy_no_proxy`
- **Description** : Liste des domaines/IPs à exclure du proxy
- **Format** : Liste séparée par des virgules
- **Exemple** : `localhost,127.0.0.1,.entreprise.local,10.0.0.0/8`
- **Utilité** : Permet d'accéder directement aux services internes sans passer par le proxy

## Exemples de configuration

### Exemple 1 : OpenAI via proxy d'entreprise

```ini
[LLM:OpenAI-External]
url = https://api.openai.com/v1
apikey = sk-xxxxxxxxxxxxxxxxxxxxxxxx
model = gpt-4
api_type = openai
enabled = true
stream_response = true
ssl_verify = true
timeout_seconds = 300
temperature = 0.7
max_tokens = 4096
default = false
# Proxy d'entreprise pour sortir sur Internet
proxy_http = http://proxy.entreprise.fr:3128
proxy_https = http://proxy.entreprise.fr:3128
proxy_no_proxy = localhost,127.0.0.1,.entreprise.fr,10.0.0.0/8
```

### Exemple 2 : Configuration mixte (interne et externe)

```ini
# Modèle interne (sans proxy)
[LLM:Interne]
url = https://llm.interne.entreprise.fr/v1
apikey = internal-key
model = gemini-pro
api_type = openai
enabled = true
default = true
# Pas de proxy nécessaire pour l'interne

# Modèle externe (avec proxy)
[LLM:Claude-External]
url = https://api.anthropic.com/v1
apikey = sk-ant-xxxxxxxxxxxxxxxx
model = claude-3-opus-20240229
api_type = anthropic
enabled = true
default = false
# Proxy pour sortir sur Internet
proxy_http = http://proxy.entreprise.fr:3128
proxy_https = http://proxy.entreprise.fr:3128
proxy_no_proxy = localhost,127.0.0.1,.entreprise.fr
```

### Exemple 3 : Proxy avec authentification

```ini
[LLM:GPT-4-Auth]
url = https://api.openai.com/v1
apikey = YOUR_API_KEY
model = gpt-4
api_type = openai
enabled = true
# Proxy avec authentification
proxy_http = http://username:password@proxy.entreprise.com:8080
proxy_https = http://username:password@proxy.entreprise.com:8080
proxy_no_proxy = localhost,127.0.0.1
```

## Test de la configuration

### Script de test

Un script de test est fourni pour vérifier la configuration proxy :

```bash
python test_proxy_llm.py
```

Ce script va :
1. Lister toutes les configurations LLM
2. Tester la connectivité pour chaque modèle
3. Vérifier si le proxy est utilisé correctement
4. Afficher un rapport de diagnostic

### Vérification manuelle

Pour tester manuellement une configuration :

```python
import requests

# Configuration
proxies = {
    'http': 'http://proxy.entreprise.com:8080',
    'https': 'http://proxy.entreprise.com:8080'
}

# Test
response = requests.get('https://api.openai.com/v1/models', proxies=proxies)
print(f"Status: {response.status_code}")
```

## Dépannage

### Erreur "ProxyError"

**Symptôme** :
```
ProxyError('Unable to connect to proxy')
```

**Solutions** :
1. Vérifier l'URL du proxy (format, port)
2. Vérifier que le proxy est accessible : `ping proxy.entreprise.com`
3. Vérifier les identifiants si authentification requise

### Erreur "SSL Certificate"

**Symptôme** :
```
SSLError: certificate verify failed
```

**Solutions** :
1. Ajouter `ssl_verify = false` dans la configuration (non recommandé en production)
2. Ou configurer les certificats d'entreprise correctement

### Timeout avec proxy

**Symptôme** :
```
Timeout après 30 secondes
```

**Solutions** :
1. Augmenter `timeout_seconds` dans la configuration
2. Vérifier que le proxy autorise les connexions longues durées
3. Vérifier les règles firewall du proxy

### Domaine bloqué par le proxy

**Symptôme** :
```
403 Forbidden - Policy violation
```

**Solutions** :
1. Vérifier la politique du proxy d'entreprise
2. Demander l'autorisation pour le domaine concerné
3. Utiliser un modèle interne si disponible

## Sécurité

### Bonnes pratiques

1. **Ne jamais commiter les identifiants** : Utilisez des variables d'environnement ou un gestionnaire de secrets
2. **Chiffrer les mots de passe** : Si possible, utiliser un système de gestion des secrets
3. **Limiter les exclusions** : N'ajouter dans `proxy_no_proxy` que les domaines strictement nécessaires
4. **Valider SSL** : Garder `ssl_verify = true` sauf impossibilité absolue

### Exemple avec variables d'environnement

```ini
[LLM:Secure]
url = https://api.openai.com/v1
# Utiliser une variable d'environnement pour l'API key
apikey = ${OPENAI_API_KEY}
model = gpt-4
proxy_http = ${HTTP_PROXY}
proxy_https = ${HTTPS_PROXY}
proxy_no_proxy = ${NO_PROXY}
```

Puis définir les variables :
```bash
export OPENAI_API_KEY="sk-xxxxxxxxxxxxxxxx"
export HTTP_PROXY="http://proxy.entreprise.com:8080"
export HTTPS_PROXY="http://proxy.entreprise.com:8080"
export NO_PROXY="localhost,127.0.0.1,.entreprise.local"
```

## Architectures supportées

Le système de proxy fonctionne avec :

- **Proxy HTTP/HTTPS classique** : Support complet
- **Proxy SOCKS** : Non supporté actuellement
- **Proxy avec authentification** : Basic Auth supportée
- **Proxy avec NTLM** : Nécessite configuration supplémentaire
- **PAC files** : Non supporté, utiliser l'URL directe du proxy

## Performance

### Considérations

- Le proxy ajoute de la latence (100-500ms typiquement)
- Les timeouts doivent être ajustés en conséquence
- Le streaming peut être affecté par le buffering du proxy

### Optimisations

1. **Utiliser le failover** : Configurer plusieurs modèles avec et sans proxy
2. **Ajuster les timeouts** : Augmenter pour les proxies lents
3. **Mettre en cache** : Utiliser un cache local si possible
4. **Compression** : Certains proxies supportent la compression gzip

## Migration

### Depuis une configuration sans proxy

1. Identifier les modèles nécessitant un proxy
2. Ajouter les 3 lignes de configuration proxy
3. Tester avec `test_proxy_llm.py`
4. Basculer progressivement

### Vers une configuration multi-proxy

Si différents services nécessitent différents proxies :

```ini
[LLM:OpenAI-Proxy1]
proxy_http = http://proxy1.entreprise.com:8080
proxy_https = http://proxy1.entreprise.com:8080

[LLM:Claude-Proxy2]
proxy_http = http://proxy2.entreprise.com:3128
proxy_https = http://proxy2.entreprise.com:3128
```

## Support

Pour toute question ou problème :

1. Vérifier les logs de l'application
2. Exécuter le script de test
3. Consulter la documentation du proxy d'entreprise
4. Contacter l'équipe réseau pour les règles de proxy