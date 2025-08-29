#!/usr/bin/env python3
"""
Script de test pour vérifier la configuration proxy des LLM.
"""

import sys
import os
import logging
import requests
from configparser import ConfigParser

# Ajouter le répertoire parent pour accéder aux utilitaires de test
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from test_utils import mask_credentials, check_no_proxy_match

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def test_direct_connection(url):
    """Test une connexion directe sans proxy."""
    try:
        logger.info(f"Test de connexion directe vers {url}")
        response = requests.get(url, timeout=5)
        logger.info(f"✅ Connexion directe réussie: {response.status_code}")
        return True
    except Exception as e:
        logger.error(f"❌ Connexion directe échouée: {e}")
        return False

def test_proxy_connection(url, proxy_config):
    """Test une connexion via proxy."""
    try:
        proxies = {}
        if proxy_config.get('http'):
            proxies['http'] = proxy_config['http']
        if proxy_config.get('https'):
            proxies['https'] = proxy_config['https']
        
        # Utiliser la fonction utilitaire pour masquer les credentials
        safe_proxies = {k: mask_credentials(v) for k, v in proxies.items()}
        
        logger.info(f"Test de connexion via proxy vers {url}")
        logger.info(f"Configuration proxy (credentials masqués): {safe_proxies}")
        
        response = requests.get(url, proxies=proxies, timeout=10)
        logger.info(f"✅ Connexion via proxy réussie: {response.status_code}")
        return True
    except Exception as e:
        logger.error(f"❌ Connexion via proxy échouée: {e}")
        return False

def load_config():
    """Charge la configuration depuis config.ini."""
    config = ConfigParser()
    config.read('config.ini', encoding='utf-8')
    
    llm_configs = []
    
    # Chercher toutes les sections LLM
    for section in config.sections():
        if section.startswith('LLM:'):
            if not config.getboolean(section, 'enabled', fallback=True):
                continue
            
            llm_config = {
                'name': section[4:],
                'url': config.get(section, 'url', fallback=''),
                'proxy_http': config.get(section, 'proxy_http', fallback=None),
                'proxy_https': config.get(section, 'proxy_https', fallback=None),
                'proxy_no_proxy': config.get(section, 'proxy_no_proxy', fallback=None)
            }
            llm_configs.append(llm_config)
    
    # Ajouter SummarizerLLM si configuré
    if config.has_section('SummarizerLLM'):
        if config.getboolean('SummarizerLLM', 'enabled', fallback=False):
            llm_configs.append({
                'name': 'SummarizerLLM',
                'url': config.get('SummarizerLLM', 'url', fallback=''),
                'proxy_http': config.get('SummarizerLLM', 'proxy_http', fallback=None),
                'proxy_https': config.get('SummarizerLLM', 'proxy_https', fallback=None),
                'proxy_no_proxy': config.get('SummarizerLLM', 'proxy_no_proxy', fallback=None)
            })
    
    return llm_configs

def test_llm_proxy_config(llm_config):
    """Test la configuration proxy d'un LLM spécifique."""
    print("\n" + "=" * 60)
    print(f"Test pour {llm_config['name']}")
    print("=" * 60)
    
    url = llm_config['url']
    if not url:
        logger.warning(f"Pas d'URL configurée pour {llm_config['name']}")
        return
    
    # Extraire le domaine pour le test
    from urllib.parse import urlparse
    parsed = urlparse(url)
    test_url = f"{parsed.scheme}://{parsed.netloc}"
    
    logger.info(f"URL du LLM: {url}")
    
    # Test selon la configuration
    has_proxy = llm_config['proxy_http'] or llm_config['proxy_https']
    
    if has_proxy:
        logger.info(f"Configuration proxy détectée:")
        if llm_config['proxy_http']:
            logger.info(f"  HTTP Proxy: {mask_credentials(llm_config['proxy_http'])}")
        if llm_config['proxy_https']:
            logger.info(f"  HTTPS Proxy: {mask_credentials(llm_config['proxy_https'])}")
        if llm_config['proxy_no_proxy']:
            logger.info(f"  No Proxy: {llm_config['proxy_no_proxy']}")
        
        # Vérifier si l'URL est dans la liste no_proxy
        if llm_config['proxy_no_proxy']:
            no_proxy_list = [s.strip() for s in llm_config['proxy_no_proxy'].split(',') if s.strip()]
            host = parsed.hostname or ''
            # Utiliser la fonction utilitaire pour vérifier la correspondance no_proxy
            if check_no_proxy_match(host, no_proxy_list):
                logger.info(f"ℹ️ {parsed.netloc} est dans la liste no_proxy - connexion directe")
                test_direct_connection(test_url)
            else:
                proxy_config = {
                    'http': llm_config['proxy_http'],
                    'https': llm_config['proxy_https']
                }
                test_proxy_connection(test_url, proxy_config)
        else:
            proxy_config = {
                'http': llm_config['proxy_http'],
                'https': llm_config['proxy_https']
            }
            test_proxy_connection(test_url, proxy_config)
    else:
        logger.info("Pas de proxy configuré - test de connexion directe")
        test_direct_connection(test_url)

def main():
    print("Test de configuration proxy pour les LLM")
    print("=" * 60)
    
    # Charger la configuration
    llm_configs = load_config()
    
    if not llm_configs:
        logger.warning("Aucune configuration LLM trouvée")
        return
    
    logger.info(f"Configurations trouvées: {len(llm_configs)}")
    
    # Tester chaque configuration
    for llm_config in llm_configs:
        test_llm_proxy_config(llm_config)
    
    print("\n" + "=" * 60)
    print("Tests terminés")
    print("=" * 60)
    
    # Afficher un résumé
    print("\n📋 Résumé:")
    print("Pour configurer un proxy, ajoutez ces lignes dans la section du LLM dans config.ini:")
    print("proxy_http = http://proxy.entreprise.com:8080")
    print("proxy_https = http://proxy.entreprise.com:8080")
    print("proxy_no_proxy = localhost,127.0.0.1,.entreprise.local")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Erreur lors des tests: {e}")
        sys.exit(1)