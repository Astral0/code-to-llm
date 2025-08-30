#!/usr/bin/env python3
"""
Script de test spécifique pour Gemini via proxy.
"""

import requests
import json
import logging
import sys
from configparser import ConfigParser

# Configuration du logging avec plus de détails
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Activer les logs de debug pour requests
import http.client as http_client
http_client.HTTPConnection.debuglevel = 1

logger = logging.getLogger(__name__)

def test_gemini_direct():
    """Test de connexion directe à Gemini (sans proxy)."""
    print("\n" + "=" * 60)
    print("Test 1: Connexion DIRECTE à Gemini (sans proxy)")
    print("=" * 60)
    
    url = "https://generativelanguage.googleapis.com/v1beta/openai/v1/chat/completions"
    api_key = "AIzaSyBc1LYgCpdHJM_FT88RyHaRKkCm3kyRosg"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    payload = {
        "model": "gemini-2.5-pro-preview-06-05",
        "messages": [
            {"role": "user", "content": "Dis simplement 'test réussi'"}
        ],
        "stream": False
    }
    
    try:
        logger.info(f"URL: {url}")
        logger.info("Envoi sans proxy...")
        
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=10
        )
        
        logger.info(f"Status: {response.status_code}")
        logger.info(f"Headers: {response.headers}")
        
        if response.status_code == 200:
            print("✅ Connexion directe réussie")
            result = response.json()
            print(f"Réponse: {result.get('choices', [{}])[0].get('message', {}).get('content', 'Pas de contenu')}")
        else:
            print(f"❌ Erreur: {response.status_code}")
            print(f"Détails: {response.text}")
            
    except Exception as e:
        print(f"❌ Exception: {e}")
        logger.error(f"Détails de l'erreur: {e}", exc_info=True)

def test_gemini_with_proxy():
    """Test de connexion à Gemini via proxy."""
    print("\n" + "=" * 60)
    print("Test 2: Connexion à Gemini VIA PROXY")
    print("=" * 60)
    
    url = "https://generativelanguage.googleapis.com/v1beta/openai/v1/chat/completions"
    api_key = "AIzaSyBc1LYgCpdHJM_FT88RyHaRKkCm3kyRosg"
    
    # Configuration proxy depuis config.ini
    proxies = {
        'http': 'http://10.129.42.140:3131',
        'https': 'http://10.129.42.140:3131'
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    payload = {
        "model": "gemini-2.5-pro-preview-06-05",
        "messages": [
            {"role": "user", "content": "Dis simplement 'test via proxy réussi'"}
        ],
        "stream": False
    }
    
    try:
        logger.info(f"URL: {url}")
        logger.info(f"Proxy HTTP: {proxies['http']}")
        logger.info(f"Proxy HTTPS: {proxies['https']}")
        logger.info("Envoi via proxy...")
        
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            proxies=proxies,
            timeout=15
        )
        
        logger.info(f"Status: {response.status_code}")
        logger.info(f"Headers: {response.headers}")
        
        if response.status_code == 200:
            print("✅ Connexion via proxy réussie")
            result = response.json()
            print(f"Réponse: {result.get('choices', [{}])[0].get('message', {}).get('content', 'Pas de contenu')}")
        else:
            print(f"❌ Erreur: {response.status_code}")
            print(f"Détails: {response.text}")
            
    except requests.exceptions.ProxyError as e:
        print(f"❌ Erreur de proxy: {e}")
        logger.error(f"ProxyError détails: {e}", exc_info=True)
        
    except requests.exceptions.SSLError as e:
        print(f"❌ Erreur SSL: {e}")
        logger.error(f"SSLError détails: {e}", exc_info=True)
        
    except requests.exceptions.ConnectionError as e:
        print(f"❌ Erreur de connexion: {e}")
        logger.error(f"ConnectionError détails: {e}", exc_info=True)
        
    except Exception as e:
        print(f"❌ Exception: {e}")
        logger.error(f"Détails de l'erreur: {e}", exc_info=True)

def test_proxy_connectivity():
    """Test de base de la connectivité proxy."""
    print("\n" + "=" * 60)
    print("Test 3: Connectivité du proxy")
    print("=" * 60)
    
    proxies = {
        'http': 'http://10.129.42.140:3131',
        'https': 'http://10.129.42.140:3131'
    }
    
    # Test avec une URL simple
    test_urls = [
        "http://www.google.com",
        "https://www.google.com",
        "https://api.openai.com",
        "https://generativelanguage.googleapis.com"
    ]
    
    for test_url in test_urls:
        try:
            print(f"\nTest de {test_url}...")
            response = requests.get(test_url, proxies=proxies, timeout=5)
            print(f"  ✅ {test_url}: Status {response.status_code}")
        except Exception as e:
            print(f"  ❌ {test_url}: {type(e).__name__}: {str(e)[:100]}")

def load_and_test_config():
    """Charge la config depuis config.ini et teste."""
    print("\n" + "=" * 60)
    print("Test 4: Configuration depuis config.ini")
    print("=" * 60)
    
    config = ConfigParser()
    config.read('config.ini', encoding='utf-8')
    
    # Chercher la config Gemini
    gemini_section = None
    for section in config.sections():
        if section.startswith('LLM:') and 'gemini' in section.lower():
            gemini_section = section
            break
    
    if not gemini_section:
        print("❌ Pas de configuration Gemini trouvée dans config.ini")
        return
    
    print(f"Configuration trouvée: {gemini_section}")
    
    # Extraire la config
    url = config.get(gemini_section, 'url', fallback='')
    api_key = config.get(gemini_section, 'apikey', fallback='')
    model = config.get(gemini_section, 'model', fallback='')
    proxy_http = config.get(gemini_section, 'proxy_http', fallback=None)
    proxy_https = config.get(gemini_section, 'proxy_https', fallback=None)
    
    print(f"  URL: {url}")
    print(f"  Modèle: {model}")
    print(f"  API Key: {'***' + api_key[-4:] if api_key else 'Non définie'}")
    print(f"  Proxy HTTP: {proxy_http or 'Non défini'}")
    print(f"  Proxy HTTPS: {proxy_https or 'Non défini'}")
    
    if not (url and api_key and model):
        print("❌ Configuration incomplète")
        return
    
    # Construire l'URL complète
    if not url.endswith('/chat/completions'):
        url = url.rstrip('/') + '/chat/completions'
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": "Test depuis config.ini"}
        ],
        "stream": False,
        "temperature": 0.5
    }
    
    # Configuration proxy
    proxies = None
    if proxy_http or proxy_https:
        proxies = {}
        if proxy_http:
            proxies['http'] = proxy_http
        if proxy_https:
            proxies['https'] = proxy_https
        print(f"\n  Utilisation du proxy: {proxies}")
    else:
        print("\n  Pas de proxy configuré")
    
    try:
        print(f"\nEnvoi de la requête à {url}...")
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            proxies=proxies,
            timeout=15
        )
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ Requête réussie")
            result = response.json()
            if 'choices' in result:
                content = result['choices'][0].get('message', {}).get('content', 'Pas de contenu')
                print(f"Réponse du modèle: {content[:100]}...")
            else:
                print(f"Structure de réponse: {list(result.keys())}")
        else:
            print(f"❌ Erreur {response.status_code}")
            print(f"Détails: {response.text[:500]}")
            
    except Exception as e:
        print(f"❌ Exception: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Fonction principale."""
    print("Test de connectivité Gemini avec et sans proxy")
    print("=" * 60)
    
    # Désactiver les warnings SSL pour les tests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    # Menu de sélection
    print("\nChoisissez un test:")
    print("1. Test direct (sans proxy)")
    print("2. Test avec proxy")
    print("3. Test de connectivité proxy")
    print("4. Test depuis config.ini")
    print("5. Tous les tests")
    
    choice = input("\nVotre choix (1-5): ").strip()
    
    if choice == '1':
        test_gemini_direct()
    elif choice == '2':
        test_gemini_with_proxy()
    elif choice == '3':
        test_proxy_connectivity()
    elif choice == '4':
        load_and_test_config()
    elif choice == '5':
        test_gemini_direct()
        test_gemini_with_proxy()
        test_proxy_connectivity()
        load_and_test_config()
    else:
        print("Choix invalide")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest interrompu par l'utilisateur")
    except Exception as e:
        print(f"\n❌ Erreur fatale: {e}")
        import traceback
        traceback.print_exc()