#!/usr/bin/env python3
"""
Test direct de la configuration Gemini depuis config.ini
"""

import requests
import json
import logging
from configparser import ConfigParser

# Configuration du logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Désactiver les warnings SSL
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def test_gemini_from_config():
    """Teste la configuration Gemini depuis config.ini."""
    print("\n" + "=" * 60)
    print("Test de Gemini depuis config.ini")
    print("=" * 60)
    
    config = ConfigParser()
    config.read('config.ini', encoding='utf-8')
    
    # Chercher la section Gemini
    gemini_section = 'LLM:gemini-2.5-pro-preview-06-05'
    
    if not config.has_section(gemini_section):
        print(f"[ERREUR] Section {gemini_section} non trouvée")
        return
    
    # Extraire la configuration
    url = config.get(gemini_section, 'url', fallback='')
    api_key = config.get(gemini_section, 'apikey', fallback='')
    model = config.get(gemini_section, 'model', fallback='')
    proxy_http = config.get(gemini_section, 'proxy_http', fallback=None)
    proxy_https = config.get(gemini_section, 'proxy_https', fallback=None)
    api_type = config.get(gemini_section, 'api_type', fallback='openai')
    
    print(f"\nConfiguration trouvée:")
    print(f"  Section: {gemini_section}")
    print(f"  URL: {url}")
    print(f"  Model: {model}")
    print(f"  API Type: {api_type}")
    print(f"  API Key: ...{api_key[-10:] if api_key else 'Non définie'}")
    print(f"  Proxy HTTP: {proxy_http}")
    print(f"  Proxy HTTPS: {proxy_https}")
    
    # Construire l'URL complète pour OpenAI-compatible
    if api_type == 'openai' and not url.endswith('/chat/completions'):
        if '/v1' in url:
            url = url.rstrip('/') + '/chat/completions'
        else:
            url = url.rstrip('/') + '/v1/chat/completions'
    
    print(f"\nURL finale: {url}")
    
    # Headers
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # Payload OpenAI-compatible
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": "Réponds simplement 'Test réussi' sans rien d'autre"}
        ],
        "stream": False,
        "temperature": 0.5
    }
    
    print(f"\nPayload envoyé:")
    print(f"  Model dans payload: {payload['model']}")
    print(f"  Messages: {len(payload['messages'])} message(s)")
    print(f"  Stream: {payload['stream']}")
    
    # Configuration proxy
    proxies = None
    if proxy_http or proxy_https:
        proxies = {}
        if proxy_http:
            proxies['http'] = proxy_http
        if proxy_https:
            proxies['https'] = proxy_https
        print(f"\nUtilisation du proxy:")
        print(f"  HTTP: {proxies.get('http', 'Non configuré')}")
        print(f"  HTTPS: {proxies.get('https', 'Non configuré')}")
    
    try:
        print(f"\n>>> Envoi de la requête POST à {url}")
        print(">>> Headers Authorization: Bearer ..." + api_key[-10:] if api_key else "Non définie")
        
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            proxies=proxies,
            timeout=30,
            verify=True  # ou False si problème SSL
        )
        
        print(f"\n<<< Réponse reçue")
        print(f"<<< Status Code: {response.status_code}")
        print(f"<<< Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            print("\n[SUCCES] Requête réussie!")
            result = response.json()
            print(f"Structure de la réponse: {list(result.keys())}")
            
            if 'choices' in result and result['choices']:
                content = result['choices'][0].get('message', {}).get('content', 'Pas de contenu')
                print(f"\n>>> Réponse du modèle: {content}")
            elif 'error' in result:
                print(f"\n[ERREUR] dans la réponse: {result['error']}")
            else:
                print(f"\nRéponse complète: {json.dumps(result, indent=2)}")
        else:
            print(f"\n[ERREUR] Status HTTP: {response.status_code}")
            print(f"Contenu de l'erreur: {response.text[:1000]}")
            
    except requests.exceptions.ProxyError as e:
        print(f"\n[ERREUR PROXY]")
        print(f"  Type: ProxyError")
        print(f"  Message: {e}")
        print(f"  Proxy utilisé: {proxies}")
        
    except requests.exceptions.SSLError as e:
        print(f"\n[ERREUR SSL]")
        print(f"  Type: SSLError")
        print(f"  Message: {e}")
        print("\n  Suggestion: Essayez avec verify=False dans le code")
        
    except requests.exceptions.ConnectionError as e:
        print(f"\n[ERREUR CONNEXION]")
        print(f"  Type: ConnectionError")
        print(f"  Message: {e}")
        print(f"  URL tentée: {url}")
        print(f"  Proxy: {proxies}")
        
    except requests.exceptions.Timeout as e:
        print(f"\n[TIMEOUT]")
        print(f"  La requête a expiré après 30 secondes")
        print(f"  URL: {url}")
        
    except Exception as e:
        print(f"\n[ERREUR INATTENDUE]")
        print(f"  Type: {type(e).__name__}")
        print(f"  Message: {e}")
        import traceback
        print("\nStack trace complet:")
        traceback.print_exc()

if __name__ == "__main__":
    print("Test de la configuration Gemini avec proxy")
    print("=" * 60)
    test_gemini_from_config()
    print("\n" + "=" * 60)
    print("Test terminé")