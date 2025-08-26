#!/usr/bin/env python3
"""
Script de test pour vérifier le RetryManager et la gestion des erreurs LLM.
"""

import logging
import sys
import time
from services.retry_manager import RetryManager, EndpointState, EndpointHealth

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def simulate_llm_call(endpoint_id: str, fail_count: dict):
    """Simule un appel LLM avec des échecs contrôlés."""
    # Compter les appels par endpoint
    if endpoint_id not in fail_count:
        fail_count[endpoint_id] = 0
    
    fail_count[endpoint_id] += 1
    
    # Simuler des échecs pour les premiers appels
    if endpoint_id == "iag.edf.fr" and fail_count[endpoint_id] <= 2:
        logging.info(f"[ECHEC] Échec simulé sur {endpoint_id} (tentative {fail_count[endpoint_id]})")
        raise Exception(f"504 Gateway Timeout sur {endpoint_id}")
    
    if endpoint_id == "oneapi" and fail_count[endpoint_id] <= 1:
        logging.info(f"[ECHEC] Échec simulé sur {endpoint_id} (tentative {fail_count[endpoint_id]})")
        raise Exception(f"503 Service Unavailable sur {endpoint_id}")
    
    # Succès
    logging.info(f"[SUCCES] Succès sur {endpoint_id} (tentative {fail_count[endpoint_id]})")
    return f"Réponse réussie de {endpoint_id}"

def test_retry_manager():
    """Test du RetryManager avec plusieurs endpoints."""
    print("=" * 60)
    print("Test du RetryManager avec failover automatique")
    print("=" * 60)
    
    # Créer le manager avec 3 endpoints
    endpoints = ["iag.edf.fr", "oneapi", "litellm"]
    manager = RetryManager(
        endpoints=endpoints,
        max_retries=6,
        initial_backoff=0.5,  # Plus court pour le test
        max_backoff=5.0,
        backoff_multiplier=2.0,
        jitter=True,
        failure_threshold=3,
        recovery_time=10  # 10 secondes pour le test
    )
    
    # Dictionnaire pour suivre les échecs
    fail_count = {}
    
    def on_retry(attempt, endpoint, wait_time):
        print(f"[ATTENTE] Tentative {attempt}: Échec sur {endpoint}. Attente de {wait_time:.2f}s...")
    
    def on_endpoint_switch(new_endpoint):
        print(f"[BASCULEMENT] Basculement vers l'endpoint: {new_endpoint}")
    
    try:
        # Test 1: Appel avec retry et failover
        print("\n[TEST 1] Appel avec échecs simulés et failover")
        result = manager.execute_with_retry(
            lambda endpoint_id: simulate_llm_call(endpoint_id, fail_count),
            on_retry=on_retry,
            on_endpoint_switch=on_endpoint_switch
        )
        print(f"[RESULTAT] Résultat final: {result}")
        
    except Exception as e:
        print(f"[ERREUR] Erreur finale: {e}")
    
    # Afficher le statut de santé
    print("\n[STATUT] Statut de santé des endpoints:")
    health_status = manager.get_health_status()
    for endpoint, status in health_status.items():
        print(f"  • {endpoint}:")
        print(f"    - État: {status['state']}")
        print(f"    - Taux de succès: {status['success_rate']*100:.1f}%")
        print(f"    - Échecs consécutifs: {status['consecutive_failures']}")
        print(f"    - Total requêtes: {status['total_requests']}")
    
    # Test 2: Circuit breaker
    print("\n[TEST 2] Test du circuit breaker")
    print("Attendre 11 secondes pour que le circuit se referme...")
    time.sleep(11)
    
    # Réinitialiser les compteurs
    fail_count = {}
    
    try:
        result = manager.execute_with_retry(
            lambda endpoint_id: simulate_llm_call(endpoint_id, fail_count),
            on_retry=on_retry,
            on_endpoint_switch=on_endpoint_switch
        )
        print(f"[RESULTAT] Résultat après récupération: {result}")
    except Exception as e:
        print(f"[ERREUR] Erreur: {e}")
    
    # Afficher le statut final
    print("\n[STATUT FINAL] Statut final de santé:")
    health_status = manager.get_health_status()
    for endpoint, status in health_status.items():
        state_text = "[OK]" if status['state'] == "healthy" else "[DEGRADE]" if status['state'] == "degraded" else "[FERME]"
        print(f"  {state_text} {endpoint}: {status['success_rate']*100:.1f}% succès")

def test_endpoint_health():
    """Test de la classe EndpointHealth."""
    print("\n" + "=" * 60)
    print("Test de EndpointHealth")
    print("=" * 60)
    
    health = EndpointHealth("test_endpoint", failure_threshold=3, recovery_time=5)
    
    # Simuler des échecs
    print("Simulation de 3 échecs consécutifs...")
    for i in range(3):
        health.record_failure()
        print(f"  Échec {i+1}: État = {health.state.value}, Disponible = {health.is_available()}")
    
    print(f"\n[CIRCUIT OUVERT] Circuit ouvert après {health.failure_threshold} échecs")
    print(f"  État: {health.state.value}")
    print(f"  Disponible: {health.is_available()}")
    
    # Attendre la récupération
    print(f"\nAttente de {health.recovery_time + 1} secondes pour la récupération...")
    time.sleep(health.recovery_time + 1)
    
    print(f"  État après attente: {health.state.value}")
    print(f"  Disponible après attente: {health.is_available()}")
    
    # Enregistrer un succès
    health.record_success()
    print(f"\n[SUCCES] Succès enregistré")
    print(f"  État: {health.state.value}")
    print(f"  Taux de succès: {health.get_success_rate()*100:.1f}%")

if __name__ == "__main__":
    try:
        test_endpoint_health()
        test_retry_manager()
        print("\n[TERMINE] Tous les tests sont terminés avec succès!")
    except Exception as e:
        print(f"\n[ERREUR] Erreur lors des tests: {e}")
        sys.exit(1)