#!/usr/bin/env python3
"""
Script de test pour vérifier l'affichage des erreurs LLM dans l'interface.
"""

import sys
import os
import logging

# Ajouter la racine du dépôt au PYTHONPATH
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from services.llm_api_service import LlmApiService
from services.exceptions import NetworkException

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_timeout_error():
    """Test d'une erreur de timeout."""
    print("=" * 60)
    print("Test d'erreur de timeout LLM")
    print("=" * 60)
    
    # Configuration de test avec un timeout très court
    config = {
        'models': {
            'test_model': {
                'name': 'Test Model',
                'url': 'https://httpbin.org/delay/10',  # URL qui prend 10s à répondre
                'model': 'test',
                'api_type': 'openai',
                'apikey': 'test',
                'ssl_verify': True,
                'timeout_seconds': 1  # Timeout de 1 seconde seulement
            }
        },
        'default_id': 'test_model'
    }
    
    service = LlmApiService(config)
    
    # Enregistrer un callback pour voir les notifications
    notifications = []
    def on_error(msg, attempt, wait_time):
        notifications.append({
            'message': msg,
            'attempt': attempt,
            'wait_time': wait_time
        })
        print(f"[NOTIFICATION] {msg}")
    
    service.register_error_callback(on_error)
    
    # Test avec un message simple
    chat_history = [
        {'role': 'user', 'content': 'Test message'}
    ]
    
    try:
        print("\nEnvoi de la requête (timeout attendu dans 1 seconde)...")
        result = service.send_to_llm(chat_history)
        print(f"Résultat inattendu: {result}")
    except NetworkException as e:
        print(f"[ERREUR ATTENDUE] NetworkException: {e}")
    except Exception as e:
        print(f"[ERREUR] Exception: {e}")
    
    print(f"\nNotifications reçues: {len(notifications)}")
    for notif in notifications:
        print(f"  - {notif['message']}")

def test_connection_error():
    """Test d'une erreur de connexion."""
    print("\n" + "=" * 60)
    print("Test d'erreur de connexion")
    print("=" * 60)
    
    # Configuration avec une URL invalide
    config = {
        'models': {
            'test_model': {
                'name': 'Test Model',
                'url': 'https://invalid-server-that-does-not-exist.example.com',
                'model': 'test',
                'api_type': 'openai',
                'apikey': 'test',
                'ssl_verify': True,
                'timeout_seconds': 5
            }
        },
        'default_id': 'test_model'
    }
    
    service = LlmApiService(config)
    
    # Callback pour les notifications
    def on_error(msg, attempt, wait_time):
        print(f"[NOTIFICATION] {msg}")
    
    service.register_error_callback(on_error)
    
    chat_history = [
        {'role': 'user', 'content': 'Test message'}
    ]
    
    try:
        print("\nEnvoi de la requête (erreur de connexion attendue)...")
        result = service.send_to_llm(chat_history)
        print(f"Résultat inattendu: {result}")
    except NetworkException as e:
        print(f"[ERREUR ATTENDUE] NetworkException: {e}")
    except Exception as e:
        print(f"[ERREUR] Exception: {e}")

def test_retry_with_multiple_endpoints():
    """Test du retry avec plusieurs endpoints."""
    print("\n" + "=" * 60)
    print("Test du retry avec failover")
    print("=" * 60)
    
    # Configuration avec plusieurs endpoints qui échouent
    config = {
        'models': {
            'endpoint1': {
                'name': 'Endpoint 1',
                'url': 'https://httpbin.org/delay/10',
                'model': 'test',
                'api_type': 'openai',
                'apikey': 'test',
                'ssl_verify': True,
                'timeout_seconds': 1
            },
            'endpoint2': {
                'name': 'Endpoint 2',
                'url': 'https://invalid-server.example.com',
                'model': 'test',
                'api_type': 'openai',
                'apikey': 'test',
                'ssl_verify': True,
                'timeout_seconds': 2
            },
            'endpoint3': {
                'name': 'Endpoint 3 (OK)',
                'url': 'https://httpbin.org/json',
                'model': 'test',
                'api_type': 'openai',
                'apikey': 'test',
                'ssl_verify': True,
                'timeout_seconds': 5
            }
        },
        'default_id': 'endpoint1'
    }
    
    service = LlmApiService(config)
    
    # Callback pour les notifications
    def on_error(msg, attempt, wait_time):
        print(f"[NOTIFICATION] Attempt {attempt}: {msg} (wait: {wait_time:.1f}s)")
    
    service.register_error_callback(on_error)
    
    chat_history = [
        {'role': 'user', 'content': 'Test message'}
    ]
    
    try:
        print("\nEnvoi de la requête avec retry et failover...")
        result = service.send_to_llm(chat_history)
        print(f"Résultat: {result}")
    except Exception as e:
        print(f"[ERREUR FINALE] {e}")
    
    # Afficher le statut de santé
    if service.retry_manager:
        print("\nStatut de santé des endpoints:")
        health = service.get_endpoints_health()
        for endpoint, status in (health or {}).items():
            state = status.get('state', 'unknown')
            sr = status.get('success_rate')
            sr_txt = f"{sr*100:.0f}%" if isinstance(sr, (int, float)) else "N/A"
            print(f"  - {endpoint}: {state} (taux de succès: {sr_txt})")

if __name__ == "__main__":
    try:
        # Test 1: Timeout
        test_timeout_error()
        
        # Test 2: Erreur de connexion
        test_connection_error()
        
        # Test 3: Retry avec failover (commenté car prend du temps)
        # test_retry_with_multiple_endpoints()
        
        print("\n[TERMINE] Tests terminés")
    except Exception as e:
        print(f"\n[ERREUR] Erreur lors des tests: {e}")
        sys.exit(1)