#!/usr/bin/env python3
"""
Test complet de l'intégration Gemini avec retry et proxy
"""

import sys
import json
import configparser
from services.llm_api_service import LlmApiService
from services.retry_manager import RetryManager

def safe_parse_config_value(config, section, key, value_type, default_value):
    """Parse une valeur de config en gérant les erreurs"""
    try:
        value = config.get(section, key, fallback=default_value)
        if value is None or value == '':
            return default_value
        return value_type(value)
    except (ValueError, TypeError, configparser.NoOptionError):
        return default_value

def test_gemini_integration():
    """Test l'intégration complète de Gemini."""
    print("\n" + "=" * 60)
    print("Test d'intégration Gemini avec retry et proxy")
    print("=" * 60)
    
    # Charger la configuration
    config = configparser.ConfigParser()
    config.read('config.ini', encoding='utf-8')
    
    # Construire la configuration LLM comme le fait main_desktop.py
    llm_models = {}
    default_llm_id = None
    
    for section in config.sections():
        if section.startswith('LLM:'):
            if not config.getboolean(section, 'enabled', fallback=True):
                continue
            
            llm_id = section[4:].strip()
            is_default = config.getboolean(section, 'default', fallback=False)
            
            llm_models[llm_id] = {
                'id': llm_id,
                'name': llm_id,
                'url': config.get(section, 'url', fallback=''),
                'apikey': config.get(section, 'apikey', fallback=''),
                'model': config.get(section, 'model', fallback=''),
                'api_type': config.get(section, 'api_type', fallback='openai').lower(),
                'stream_response': config.getboolean(section, 'stream_response', fallback=False),
                'ssl_verify': config.getboolean(section, 'ssl_verify', fallback=True),
                'timeout_seconds': config.getint(section, 'timeout_seconds', fallback=300),
                'temperature': safe_parse_config_value(config, section, 'temperature', float, None),
                'max_tokens': safe_parse_config_value(config, section, 'max_tokens', int, None),
                'default': is_default,
                'proxy_http': config.get(section, 'proxy_http', fallback=None),
                'proxy_https': config.get(section, 'proxy_https', fallback=None),
                'proxy_no_proxy': config.get(section, 'proxy_no_proxy', fallback=None)
            }
            if is_default:
                default_llm_id = llm_id
    
    service_config = {
        'models': llm_models,
        'default_id': default_llm_id
    }
    
    # Créer le service LLM
    service = LlmApiService(service_config)
    
    # Vérifier que Gemini est configuré
    gemini_models = [name for name in service._llm_models if 'gemini' in name.lower()]
    if not gemini_models:
        print("[ERREUR] Aucun modèle Gemini configuré")
        return
    
    print(f"\nModèles Gemini trouvés: {gemini_models}")
    
    # Sélectionner le modèle Gemini
    gemini_model = gemini_models[0]
    service._default_llm_id = gemini_model
    print(f"Modèle sélectionné: {gemini_model}")
    
    # Afficher la configuration
    gemini_config = service._llm_models[gemini_model]
    print(f"\nConfiguration:")
    print(f"  URL: {gemini_config['url']}")
    print(f"  Model: {gemini_config['model']}")
    print(f"  Proxy HTTP: {gemini_config.get('proxy_http', 'Non configuré')}")
    print(f"  Proxy HTTPS: {gemini_config.get('proxy_https', 'Non configuré')}")
    
    # Test simple
    test_message = "Réponds simplement 'Test d'intégration réussi' et rien d'autre"
    
    try:
        print(f"\n>>> Envoi du message test...")
        print(f">>> Message: {test_message}")
        
        # Appeler le service
        chat_history = [
            {"role": "user", "content": test_message}
        ]
        response = service.send_to_llm(
            chat_history=chat_history,
            stream=False,
            llm_id=gemini_model
        )
        
        if response:
            print(f"\n[DEBUG] Response type: {type(response)}")
            print(f"[DEBUG] Response keys: {response.keys() if isinstance(response, dict) else 'Not a dict'}")
            
            if 'choices' in response:
                print(f"\n[SUCCES] Réponse reçue (format OpenAI)")
                content = response['choices'][0].get('message', {}).get('content', 'Pas de contenu')
                print(f">>> Réponse: {content}")
            elif 'response' in response:
                print(f"\n[SUCCES] Réponse reçue (format direct)")
                content = response['response']
                print(f">>> Réponse: {content}")
            elif 'error' in response:
                print(f"\n[ERREUR] Erreur dans la réponse: {response['error']}")
            else:
                print(f"\n[DEBUG] Structure de réponse inattendue:")
                print(json.dumps(response, indent=2))
            
            # Vérifier les métriques du retry manager
            if hasattr(service, 'retry_manager'):
                print(f"\nStatistiques du retry manager:")
                for endpoint_name, health in service.retry_manager.endpoint_health.items():
                    print(f"  - {endpoint_name}:")
                    print(f"      Statut: {health.state.value}")
                    print(f"      Échecs consécutifs: {health.consecutive_failures}")
                    print(f"      Dernière utilisation: {health.last_success_time or 'Jamais'}")
                    print(f"      Taux de succès: {health.get_success_rate():.1%}")
        else:
            print(f"\n[ERREUR] Pas de réponse reçue (response=None ou False)")
            
    except Exception as e:
        print(f"\n[ERREUR] Exception: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("Test terminé")

if __name__ == "__main__":
    test_gemini_integration()