"""Gestionnaire de retry intelligent avec circuit breaker et failover."""

import time
import random
import logging
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime, timedelta
from enum import Enum
from threading import Lock


class EndpointState(Enum):
    """États possibles d'un endpoint."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CIRCUIT_OPEN = "circuit_open"


class EndpointHealth:
    """Suivi de santé d'un endpoint individuel."""
    
    def __init__(self, endpoint_id: str, failure_threshold: int = 5, recovery_time: int = 60):
        self.endpoint_id = endpoint_id
        self.consecutive_failures = 0
        self.total_failures = 0
        self.total_requests = 0
        self.last_failure_time = None
        self.last_success_time = None
        self.state = EndpointState.HEALTHY
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time  # Temps en secondes avant de réessayer
        self._lock = Lock()
    
    def record_success(self):
        """Enregistre un succès."""
        with self._lock:
            self.consecutive_failures = 0
            self.last_success_time = datetime.now()
            self.total_requests += 1
            
            # Réinitialiser l'état si c'était ouvert
            if self.state == EndpointState.CIRCUIT_OPEN:
                self.state = EndpointState.HEALTHY
                logging.info(f"Circuit breaker fermé pour {self.endpoint_id} après succès")
    
    def record_failure(self):
        """Enregistre un échec."""
        with self._lock:
            self.consecutive_failures += 1
            self.total_failures += 1
            self.total_requests += 1
            self.last_failure_time = datetime.now()
            
            # Ouvrir le circuit si trop d'échecs
            if self.consecutive_failures >= self.failure_threshold:
                self.state = EndpointState.CIRCUIT_OPEN
                logging.warning(f"Circuit breaker ouvert pour {self.endpoint_id} après {self.consecutive_failures} échecs")
            elif self.consecutive_failures >= self.failure_threshold // 2:
                self.state = EndpointState.DEGRADED
    
    def is_available(self) -> bool:
        """Vérifie si l'endpoint est disponible."""
        with self._lock:
            if self.state != EndpointState.CIRCUIT_OPEN:
                return True
            
            # Vérifier si on peut réessayer après le temps de récupération
            if self.last_failure_time:
                time_since_failure = (datetime.now() - self.last_failure_time).total_seconds()
                if time_since_failure > self.recovery_time:
                    self.state = EndpointState.DEGRADED
                    self.consecutive_failures = self.failure_threshold // 2  # Reset partiel
                    logging.info(f"Tentative de récupération pour {self.endpoint_id}")
                    return True
            
            return False
    
    def get_success_rate(self) -> float:
        """Calcule le taux de succès."""
        if self.total_requests == 0:
            return 1.0
        return 1.0 - (self.total_failures / self.total_requests)


class RetryManager:
    """Gestionnaire de retry avec failover intelligent."""
    
    def __init__(self, 
                 endpoints: List[str],
                 max_retries: int = 5,
                 initial_backoff: float = 1.0,
                 max_backoff: float = 60.0,
                 backoff_multiplier: float = 2.0,
                 jitter: bool = True,
                 failure_threshold: int = 3,
                 recovery_time: int = 60):
        """
        Args:
            endpoints: Liste des IDs d'endpoints disponibles
            max_retries: Nombre maximum de tentatives totales
            initial_backoff: Délai initial entre les tentatives (secondes)
            max_backoff: Délai maximum entre les tentatives (secondes)
            backoff_multiplier: Multiplicateur pour le backoff exponentiel
            jitter: Ajouter du jitter pour éviter le thundering herd
            failure_threshold: Nombre d'échecs avant d'ouvrir le circuit
            recovery_time: Temps avant de réessayer un endpoint défaillant (secondes)
        """
        self.endpoints = endpoints
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.backoff_multiplier = backoff_multiplier
        self.jitter = jitter
        
        # Initialiser le suivi de santé pour chaque endpoint
        self.endpoint_health = {
            endpoint: EndpointHealth(endpoint, failure_threshold, recovery_time)
            for endpoint in endpoints
        }
        
        self.logger = logging.getLogger(__name__)
    
    def calculate_backoff(self, attempt: int) -> float:
        """Calcule le temps d'attente avant la prochaine tentative."""
        # Backoff exponentiel
        backoff = min(
            self.initial_backoff * (self.backoff_multiplier ** attempt),
            self.max_backoff
        )
        
        # Ajouter du jitter si activé
        if self.jitter:
            # Jitter entre 0.5x et 1.5x du backoff
            backoff = backoff * (0.5 + random.random())
        
        return backoff
    
    def get_next_endpoint(self, exclude_endpoints: List[str] = None) -> Optional[str]:
        """
        Sélectionne le prochain endpoint disponible.
        
        Args:
            exclude_endpoints: Endpoints à exclure de la sélection
            
        Returns:
            ID de l'endpoint ou None si aucun disponible
        """
        exclude_endpoints = exclude_endpoints or []
        
        # Filtrer les endpoints disponibles
        available_endpoints = [
            ep for ep in self.endpoints
            if ep not in exclude_endpoints and self.endpoint_health[ep].is_available()
        ]
        
        if not available_endpoints:
            # Si aucun endpoint disponible, essayer de forcer la récupération du meilleur
            all_endpoints = [
                (ep, self.endpoint_health[ep].get_success_rate())
                for ep in self.endpoints
                if ep not in exclude_endpoints
            ]
            
            if all_endpoints:
                # Prendre celui avec le meilleur taux de succès
                all_endpoints.sort(key=lambda x: x[1], reverse=True)
                return all_endpoints[0][0]
            
            return None
        
        # Sélectionner l'endpoint avec le meilleur taux de succès
        best_endpoint = max(
            available_endpoints,
            key=lambda ep: self.endpoint_health[ep].get_success_rate()
        )
        
        return best_endpoint
    
    def execute_with_retry(self,
                          func: Callable,
                          on_retry: Optional[Callable[[int, str, float], None]] = None,
                          on_endpoint_switch: Optional[Callable[[str], None]] = None,
                          **kwargs) -> Any:
        """
        Exécute une fonction avec retry et failover.
        
        Args:
            func: Fonction à exécuter (doit accepter 'endpoint_id' comme paramètre)
            on_retry: Callback appelé avant chaque retry (attempt, endpoint, wait_time)
            on_endpoint_switch: Callback appelé lors du changement d'endpoint
            **kwargs: Arguments additionnels pour func
            
        Returns:
            Résultat de func
            
        Raises:
            Exception: Si toutes les tentatives échouent
        """
        attempt = 0
        used_endpoints = []
        last_exception = None
        
        while attempt < self.max_retries:
            # Sélectionner un endpoint
            endpoint = self.get_next_endpoint(exclude_endpoints=used_endpoints)
            
            if endpoint is None:
                # Réinitialiser la liste des endpoints utilisés si tous ont été essayés
                if len(used_endpoints) >= len(self.endpoints):
                    used_endpoints = []
                    endpoint = self.get_next_endpoint()
                    
                    if endpoint is None:
                        # Vraiment aucun endpoint disponible
                        if last_exception:
                            raise last_exception
                        raise Exception("Aucun endpoint LLM disponible")
            
            if endpoint not in used_endpoints:
                used_endpoints.append(endpoint)
                if on_endpoint_switch and attempt > 0:
                    on_endpoint_switch(endpoint)
            
            try:
                # Tenter l'appel
                self.logger.info(f"Tentative {attempt + 1}/{self.max_retries} avec endpoint {endpoint}")
                result = func(endpoint_id=endpoint, **kwargs)
                
                # Succès - enregistrer et retourner
                self.endpoint_health[endpoint].record_success()
                return result
                
            except Exception as e:
                last_exception = e
                self.endpoint_health[endpoint].record_failure()
                self.logger.warning(f"Échec sur {endpoint}: {str(e)}")
                
                # Déterminer si on doit réessayer
                attempt += 1
                if attempt < self.max_retries:
                    # Calculer le temps d'attente
                    wait_time = self.calculate_backoff(attempt - 1)
                    
                    # Notifier le retry
                    if on_retry:
                        on_retry(attempt, endpoint, wait_time)
                    
                    self.logger.info(f"Attente de {wait_time:.2f}s avant la tentative {attempt + 1}")
                    time.sleep(wait_time)
        
        # Toutes les tentatives ont échoué
        error_msg = f"Échec après {self.max_retries} tentatives sur {len(set(used_endpoints))} endpoints"
        self.logger.error(error_msg)
        
        if last_exception:
            raise type(last_exception)(f"{error_msg}: {str(last_exception)}")
        raise Exception(error_msg)
    
    def get_health_status(self) -> Dict[str, Any]:
        """Retourne le statut de santé de tous les endpoints."""
        return {
            endpoint: {
                'state': health.state.value,
                'consecutive_failures': health.consecutive_failures,
                'success_rate': health.get_success_rate(),
                'total_requests': health.total_requests,
                'last_failure': health.last_failure_time.isoformat() if health.last_failure_time else None,
                'last_success': health.last_success_time.isoformat() if health.last_success_time else None
            }
            for endpoint, health in self.endpoint_health.items()
        }
    
    def reset_endpoint(self, endpoint_id: str):
        """Réinitialise le statut d'un endpoint."""
        if endpoint_id in self.endpoint_health:
            self.endpoint_health[endpoint_id].consecutive_failures = 0
            self.endpoint_health[endpoint_id].state = EndpointState.HEALTHY
            self.logger.info(f"Endpoint {endpoint_id} réinitialisé")