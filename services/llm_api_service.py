import requests
import json
import logging
import re
import time
from typing import Dict, Any, Optional, List, Callable, Tuple
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from configparser import ConfigParser
from .base_service import BaseService
from .exceptions import LlmApiServiceException, NetworkException, RateLimitException
from .retry_manager import RetryManager


class LlmApiService(BaseService):
    """Service pour gérer les communications avec les API LLM."""
    
    # Prompt par défaut pour la génération de titre
    DEFAULT_TITLE_PROMPT = """En te basant sur l'historique de conversation suivant, génère un titre court et descriptif (maximum 10 mots) qui résume le sujet principal. Réponds UNIQUEMENT avec le titre, sans guillemets ni préfixe comme "Titre :".

### Historique
{history}"""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """
        Initialise le service LLM API.
        
        Args:
            config: Dictionnaire de configuration contenant les modèles LLM
            logger: Logger optionnel
        """
        super().__init__(config, logger)
        self._llm_models = config.get('models', {})
        self._default_llm_id = config.get('default_id', None)
        self._setup_http_session()
        
        # Initialiser le RetryManager si on a plusieurs modèles
        if self._llm_models:
            self.retry_manager = RetryManager(
                endpoints=list(self._llm_models.keys()),
                max_retries=6,  # Plus de tentatives
                initial_backoff=1.0,
                max_backoff=30.0,
                backoff_multiplier=2.0,
                jitter=True,
                failure_threshold=3,  # Circuit breaker après 3 échecs
                recovery_time=120  # 2 minutes avant de réessayer
            )
        else:
            self.retry_manager = None
        
        # Callbacks pour le suivi des erreurs
        self.error_callbacks = []
        
    def validate_config(self):
        """Valide la configuration du service LLM."""
        # La validation sera faite lors de l'appel aux méthodes
        pass
    
    def _setup_http_session(self):
        """Configure une session HTTP de base sans retry (géré par RetryManager)."""
        self.session = requests.Session()
        
        # Pas de retry automatique ici, le RetryManager s'en charge
        adapter = HTTPAdapter(max_retries=0)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
    
    def _get_proxy_config(self, config: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Extrait la configuration proxy d'un modèle LLM.
        
        Args:
            config: Configuration du modèle LLM
            
        Returns:
            Dict avec les proxies ou None si pas de proxy configuré
        """
        proxy_http = config.get('proxy_http')
        proxy_https = config.get('proxy_https')
        
        if not proxy_http and not proxy_https:
            self.logger.debug("Pas de configuration proxy détectée")
            return None
        
        proxies = {}
        if proxy_http:
            proxies['http'] = proxy_http
            self.logger.info(f"Proxy HTTP configuré: {proxy_http}")
        if proxy_https:
            proxies['https'] = proxy_https
            self.logger.info(f"Proxy HTTPS configuré: {proxy_https}")
        
        # Gérer les exclusions no_proxy
        no_proxy = config.get('proxy_no_proxy')
        if no_proxy:
            # Configurer les exclusions via les variables d'environnement
            # car requests utilise ces variables pour les exclusions
            import os
            os.environ['NO_PROXY'] = no_proxy
            os.environ['no_proxy'] = no_proxy
            self.logger.info(f"Exclusions proxy (NO_PROXY): {no_proxy}")
        
        self.logger.info(f"Configuration proxy finale: {proxies}")
        return proxies
    
    def get_available_models(self) -> List[Dict[str, Any]]:
        """Retourne la liste des modèles LLM disponibles."""
        models = [
            {'id': llm_id, 'name': model['name'], 'default': model.get('default', False)}
            for llm_id, model in self._llm_models.items()
        ]
        
        # Ajouter le statut de santé si disponible
        if self.retry_manager:
            health_status = self.retry_manager.get_health_status()
            for model in models:
                if model['id'] in health_status:
                    model['health'] = health_status[model['id']]
        
        return models
    
    def get_endpoints_health(self) -> Optional[Dict[str, Any]]:
        """Retourne le statut de santé de tous les endpoints."""
        if self.retry_manager:
            return self.retry_manager.get_health_status()
        return None
    
    def reset_endpoint_health(self, endpoint_id: str):
        """Réinitialise le statut de santé d'un endpoint."""
        if self.retry_manager:
            self.retry_manager.reset_endpoint(endpoint_id)
    
    def _build_openai_request(self, api_url: str, model: str, messages: List[Dict[str, str]], 
                              stream: bool = False, temperature: float = None, 
                              max_tokens: int = None) -> tuple:
        """
        Construit une requête pour une API compatible OpenAI.
        
        Returns:
            tuple: (target_url, payload)
        """
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream
        }
        
        # Ajouter les paramètres optionnels s'ils sont définis
        if temperature is not None:
            payload['temperature'] = temperature
        if max_tokens is not None:
            payload['max_tokens'] = max_tokens
            
        # Construire l'URL complète
        target_url = api_url.rstrip('/')
        if not target_url.endswith('/chat/completions'):
            target_url += '/chat/completions' if '/v1' in target_url else '/v1/chat/completions'
            
        return target_url, payload
    
    def _prepare_request(self, chat_history: List[Dict[str, str]], stream: bool = False, llm_id: Optional[str] = None) -> tuple:
        """
        Prépare les données pour la requête LLM.
        
        Args:
            chat_history: Historique de la conversation
            stream: Mode streaming ou non
            llm_id: ID du modèle à utiliser (optionnel, fallback sur le défaut)
            
        Returns:
            tuple: (url, headers, payload, ssl_verify)
        """
        # Sélectionner le modèle à utiliser
        target_llm_id = llm_id if llm_id and llm_id in self._llm_models else self._default_llm_id
        if not target_llm_id:
            raise LlmApiServiceException('No default or valid LLM configured.')
        
        self.logger.debug(f"Préparation de la requête pour le modèle: {target_llm_id}")
        final_config = self._llm_models[target_llm_id]
        
        if not final_config.get('url') or not final_config.get('model'):
            raise LlmApiServiceException(f'LLM configuration is incomplete for model {target_llm_id}')
        
        headers = {"Content-Type": "application/json"}
        if final_config.get('apikey'):
            headers["Authorization"] = f"Bearer {final_config['apikey']}"
        
        if final_config.get('api_type') == "openai":
            # Utiliser la méthode factorisée
            target_url, payload = self._build_openai_request(
                api_url=final_config['url'],
                model=final_config['model'],
                messages=chat_history,
                stream=stream,
                temperature=final_config.get('temperature'),
                max_tokens=final_config.get('max_tokens')
            )
        else:  # ollama
            prompt = "\n\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in chat_history])
            payload = {
                "model": final_config['model'],
                "prompt": prompt,
                "stream": stream
            }
            # Ajouter les paramètres optionnels pour Ollama aussi
            if final_config.get('temperature') is not None:
                payload['temperature'] = final_config['temperature']
                
            target_url = final_config['url'].rstrip('/') + "/api/generate"
        
        self.logger.debug(f"URL finale construite: {target_url}")
        self.logger.debug(f"Type d'API: {final_config.get('api_type')}")
        self.logger.debug(f"Nombre de messages dans l'historique: {len(chat_history)}")
        
        return target_url, headers, payload, final_config.get('ssl_verify', True)
    
    def register_error_callback(self, callback: Callable[[str, int, float], None]):
        """Enregistre un callback pour les notifications d'erreur."""
        self.error_callbacks.append(callback)
    
    def _notify_error(self, message: str, attempt: int = 0, wait_time: float = 0):
        """Notifie les callbacks d'une erreur."""
        for callback in self.error_callbacks:
            try:
                callback(message, attempt, wait_time)
            except Exception as e:
                self.logger.warning(f"Erreur dans le callback d'erreur: {e}")
    
    def send_to_llm(self, chat_history: List[Dict[str, str]], stream: bool = False, llm_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Envoie l'historique du chat au LLM et retourne la réponse.
        
        Args:
            chat_history: Liste des messages de la conversation
            stream: Si True, utilise le mode streaming
            llm_id: ID du modèle à utiliser (optionnel)
            
        Returns:
            Dict contenant la réponse ou une erreur
        """
        # Si un modèle spécifique est demandé, essayer d'abord celui-ci
        if llm_id and llm_id in self._llm_models:
            try:
                self.logger.info(f"Utilisation du modèle spécifiquement sélectionné: {llm_id}")
                return self._send_to_llm_internal(chat_history, stream, llm_id)
            except Exception as e:
                self.logger.warning(f"Échec du modèle sélectionné {llm_id}: {str(e)}")
                # Si le modèle sélectionné échoue et qu'on a un retry manager, continuer avec le failover
                if not self.retry_manager or len(self._llm_models) <= 1:
                    raise  # Pas de failover disponible, propager l'erreur
                
        # Si on a un retry manager et plusieurs endpoints, l'utiliser pour le failover
        if self.retry_manager and len(self._llm_models) > 1:
            def execute_request(endpoint_id: str) -> Dict[str, Any]:
                # Ne pas réessayer le modèle qui vient d'échouer
                if llm_id and endpoint_id == llm_id:
                    raise Exception(f"Modèle {endpoint_id} déjà essayé")
                return self._send_to_llm_internal(chat_history, stream, endpoint_id)
            
            def on_retry(attempt: int, endpoint: str, wait_time: float):
                # Ajuster le compteur de tentatives si on a déjà essayé le modèle sélectionné
                actual_attempt = attempt + (1 if llm_id and llm_id in self._llm_models else 0)
                msg = f"Tentative {actual_attempt}: Échec sur {endpoint}. Nouvelle tentative dans {wait_time:.1f}s..."
                self._notify_error(msg, actual_attempt, wait_time)
            
            def on_endpoint_switch(new_endpoint: str):
                model_name = self._llm_models[new_endpoint].get('name', new_endpoint)
                msg = f"Basculement vers le modèle: {model_name}"
                self._notify_error(msg, 0, 0)
            
            try:
                return self.retry_manager.execute_with_retry(
                    execute_request,
                    on_retry=on_retry,
                    on_endpoint_switch=on_endpoint_switch
                )
            except Exception as e:
                # Ajouter le statut de santé des endpoints dans l'erreur
                health_status = self.retry_manager.get_health_status()
                self.logger.error(f"Tous les endpoints ont échoué. Statut: {health_status}")
                self._notify_error(f"Erreur critique: Tous les serveurs LLM sont indisponibles", -1, 0)
                raise LlmApiServiceException(f"Tous les endpoints LLM ont échoué: {str(e)}")
        else:
            # Pas de retry manager, utiliser l'ancienne méthode
            return self._send_to_llm_internal(chat_history, stream, llm_id)
    
    def _send_to_llm_internal(self, chat_history: List[Dict[str, str]], stream: bool = False, llm_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Méthode interne pour envoyer au LLM (utilisée par le retry manager).
        """
        try:
            target_url, headers, payload, ssl_verify = self._prepare_request(chat_history, stream, llm_id)
            
            # Récupérer la config du modèle utilisé
            target_llm_id = llm_id if llm_id and llm_id in self._llm_models else self._default_llm_id
            if not target_llm_id:
                raise LlmApiServiceException('No model configured')
            current_config = self._llm_models[target_llm_id]
            
            self.logger.info(f"Sending request to {target_llm_id} at {target_url}")
            
            if not ssl_verify:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            token_count = self._count_tokens_for_history(chat_history)
            self.logger.info(f"Estimated token count: {token_count}")
            
            # Timeout adaptatif : plus court pour les premières tentatives
            timeout = min(current_config.get('timeout_seconds', 300), 30)
            
            # Configurer le proxy si défini
            proxies = self._get_proxy_config(current_config)
            
            # Log détaillé de la requête
            self.logger.info(f"=== Début de requête LLM ===")
            self.logger.info(f"Endpoint: {llm_id}")
            self.logger.info(f"URL cible: {target_url}")
            self.logger.info(f"Modèle: {current_config.get('model')}")
            self.logger.info(f"SSL verify: {ssl_verify}")
            self.logger.info(f"Timeout: {timeout}s")
            self.logger.info(f"Utilisation proxy: {'Oui' if proxies else 'Non'}")
            if proxies:
                self.logger.info(f"Détails proxy: {proxies}")
            self.logger.debug(f"Headers: {headers}")
            self.logger.debug(f"Payload keys: {payload.keys() if payload else 'None'}")
            
            response = self.session.post(
                target_url,
                headers=headers,
                json=payload,
                verify=ssl_verify,
                timeout=timeout,
                proxies=proxies
            )
            
            self.logger.info(f"Réponse reçue: Status {response.status_code}")
            self.logger.debug(f"Headers de réponse: {response.headers}")
            
            # Gérer les erreurs HTTP
            if response.status_code == 429:
                retry_after = response.headers.get('Retry-After', 60)
                raise RateLimitException(
                    f"Rate limit exceeded. Retry after {retry_after} seconds",
                    int(retry_after)
                )
            
            response.raise_for_status()
            
            # Parser la réponse selon le type d'API
            if current_config.get('api_type') == "openai":
                result = response.json()
                if 'choices' in result and result['choices']:
                    return {'response': result['choices'][0]['message']['content']}
                else:
                    return {'error': 'Unexpected response format from LLM'}
            else:  # ollama
                result = response.json()
                if 'response' in result:
                    return {'response': result['response']}
                else:
                    return {'error': 'Unexpected response format from LLM'}
                    
        except RateLimitException:
            raise  # Re-raise pour que l'appelant puisse gérer
        except requests.exceptions.ProxyError as e:
            self.logger.error(f"=== ERREUR PROXY ===")
            self.logger.error(f"Erreur de proxy pour {llm_id}: {e}")
            self.logger.error(f"Configuration proxy utilisée: {proxies if 'proxies' in locals() else 'Non défini'}")
            self.logger.error(f"URL tentée: {target_url if 'target_url' in locals() else 'Non défini'}")
            self._notify_error(f"Erreur de proxy sur {llm_id}: {str(e)}", -1, 0)
            raise NetworkException(f"Erreur de proxy: {str(e)}")
        except requests.exceptions.SSLError as e:
            self.logger.error(f"=== ERREUR SSL ===")
            self.logger.error(f"Erreur SSL pour {llm_id}: {e}")
            self.logger.error(f"SSL verify était: {ssl_verify if 'ssl_verify' in locals() else 'Non défini'}")
            self._notify_error(f"Erreur SSL sur {llm_id}", -1, 0)
            raise NetworkException(f"Erreur SSL: {str(e)}")
        except requests.exceptions.Timeout as e:
            self.logger.error(f"=== TIMEOUT ===")
            self.logger.error(f"Timeout calling LLM {llm_id}: {e}")
            self.logger.error(f"Timeout configuré: {timeout if 'timeout' in locals() else 'Non défini'}s")
            # Notifier l'erreur de timeout
            self._notify_error(f"Timeout après {timeout if 'timeout' in locals() else '?'}s sur {llm_id}", -1, 0)
            raise NetworkException(f"Timeout après {timeout if 'timeout' in locals() else '?'} secondes")
        except requests.exceptions.ConnectionError as e:
            self.logger.error(f"=== ERREUR DE CONNEXION ===")
            self.logger.error(f"Connection error calling LLM {llm_id}: {e}")
            self.logger.error(f"URL: {target_url if 'target_url' in locals() else 'Non défini'}")
            self.logger.error(f"Proxy: {proxies if 'proxies' in locals() else 'Aucun'}")
            self._notify_error(f"Erreur de connexion sur {llm_id}", -1, 0)
            raise NetworkException(f"Erreur de connexion: {str(e)}")
        except requests.exceptions.RequestException as e:
            self.logger.error(f"=== ERREUR RÉSEAU GÉNÉRALE ===")
            self.logger.error(f"Network error calling LLM {llm_id}: {e}")
            self.logger.error(f"Type d'erreur: {type(e).__name__}")
            raise NetworkException(f"Network error: {str(e)}")
        except Exception as e:
            self.logger.error(f"=== ERREUR INATTENDUE ===")
            self.logger.error(f"Error calling LLM {llm_id}: {e}")
            self.logger.error(f"Type d'erreur: {type(e).__name__}")
            import traceback
            self.logger.error(f"Stack trace: {traceback.format_exc()}")
            raise LlmApiServiceException(f"Error calling LLM: {str(e)}")
    
    def send_to_llm_stream(self, chat_history: List[Dict[str, str]], 
                          on_start: Optional[Callable[[], None]] = None,
                          on_chunk: Optional[Callable[[str], None]] = None,
                          on_end: Optional[Callable[[int], None]] = None,
                          on_error: Optional[Callable[[str], None]] = None,
                          llm_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Envoie l'historique au LLM en mode streaming avec callbacks.
        
        Args:
            chat_history: Liste des messages de la conversation
            on_start: Callback appelé au début du streaming
            on_chunk: Callback appelé pour chaque chunk reçu
            on_end: Callback appelé à la fin avec le nombre total de tokens
            on_error: Callback appelé en cas d'erreur
            llm_id: ID du modèle à utiliser (optionnel)
            
        Returns:
            Dict contenant le statut ou une erreur
        """
        # Si un modèle spécifique est demandé, essayer d'abord celui-ci
        if llm_id and llm_id in self._llm_models:
            try:
                self.logger.info(f"Utilisation du modèle spécifiquement sélectionné (streaming): {llm_id}")
                return self._send_to_llm_stream_internal(chat_history, on_start, on_chunk, on_end, on_error, llm_id)
            except Exception as e:
                self.logger.warning(f"Échec du modèle sélectionné {llm_id} en streaming: {str(e)}")
                # Si le modèle sélectionné échoue et qu'on a un retry manager, continuer avec le failover
                if not self.retry_manager or len(self._llm_models) <= 1:
                    raise  # Pas de failover disponible, propager l'erreur
        
        # Si on a un retry manager et plusieurs endpoints, l'utiliser pour le failover
        if self.retry_manager and len(self._llm_models) > 1:
            def execute_stream(endpoint_id: str) -> Dict[str, Any]:
                # Ne pas réessayer le modèle qui vient d'échouer
                if llm_id and endpoint_id == llm_id:
                    raise Exception(f"Modèle {endpoint_id} déjà essayé")
                return self._send_to_llm_stream_internal(
                    chat_history, on_start, on_chunk, on_end, None, endpoint_id
                )
            
            def on_retry(attempt: int, endpoint: str, wait_time: float):
                # Ajuster le compteur de tentatives si on a déjà essayé le modèle sélectionné
                actual_attempt = attempt + (1 if llm_id and llm_id in self._llm_models else 0)
                msg = f"Tentative {actual_attempt}: Échec sur {endpoint}. Nouvelle tentative dans {wait_time:.1f}s..."
                self._notify_error(msg, actual_attempt, wait_time)
                if on_error:
                    on_error(msg)
            
            def on_endpoint_switch(new_endpoint: str):
                model_name = self._llm_models[new_endpoint].get('name', new_endpoint)
                msg = f"Basculement vers le modèle: {model_name}"
                self._notify_error(msg, 0, 0)
            
            try:
                return self.retry_manager.execute_with_retry(
                    execute_stream,
                    on_retry=on_retry,
                    on_endpoint_switch=on_endpoint_switch
                )
            except Exception as e:
                health_status = self.retry_manager.get_health_status()
                self.logger.error(f"Tous les endpoints ont échoué en streaming. Statut: {health_status}")
                if on_error:
                    on_error(f"Erreur critique: Tous les serveurs LLM sont indisponibles")
                raise LlmApiServiceException(f"Tous les endpoints LLM ont échoué: {str(e)}")
        else:
            # Pas de retry manager, utiliser l'ancienne méthode
            return self._send_to_llm_stream_internal(
                chat_history, on_start, on_chunk, on_end, on_error, llm_id
            )
    
    def _send_to_llm_stream_internal(self, chat_history: List[Dict[str, str]], 
                                    on_start: Optional[Callable[[], None]] = None,
                                    on_chunk: Optional[Callable[[str], None]] = None,
                                    on_end: Optional[Callable[[int], None]] = None,
                                    on_error: Optional[Callable[[str], None]] = None,
                                    llm_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Méthode interne pour le streaming (utilisée par le retry manager).
        """
        try:
            target_url, headers, payload, ssl_verify = self._prepare_request(chat_history, stream=True, llm_id=llm_id)
            
            # Récupérer la config du modèle utilisé
            target_llm_id = llm_id if llm_id and llm_id in self._llm_models else self._default_llm_id
            if not target_llm_id:
                raise LlmApiServiceException('No model configured')
            current_config = self._llm_models[target_llm_id]
            
            self.logger.info(f"Sending streaming request to {target_llm_id} at {target_url}")
            
            if not ssl_verify:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            token_count = self._count_tokens_for_history(chat_history)
            self.logger.info(f"Estimated token count: {token_count}")
            
            # Timeout adaptatif : plus court pour les premières tentatives
            timeout = min(current_config.get('timeout_seconds', 300), 30)
            
            # Configurer le proxy si défini
            proxies = self._get_proxy_config(current_config)
            
            # Log détaillé pour le streaming
            self.logger.info(f"=== Début de streaming LLM ===")
            self.logger.info(f"Endpoint: {llm_id}")
            self.logger.info(f"URL cible: {target_url}")
            self.logger.info(f"Mode streaming: Oui")
            self.logger.info(f"Utilisation proxy: {'Oui' if proxies else 'Non'}")
            if proxies:
                self.logger.info(f"Détails proxy: {proxies}")
            
            response = self.session.post(
                target_url,
                headers=headers,
                json=payload,
                verify=ssl_verify,
                stream=True,
                timeout=timeout,
                proxies=proxies
            )
            
            self.logger.info(f"Streaming réponse reçue: Status {response.status_code}")
            
            # Gérer les erreurs HTTP
            if response.status_code == 429:
                retry_after = response.headers.get('Retry-After', 60)
                raise RateLimitException(
                    f"Rate limit exceeded. Retry after {retry_after} seconds",
                    int(retry_after)
                )
            
            response.raise_for_status()
            
            # Appeler le callback de début
            if on_start:
                self.logger.info("Appel du callback de début de streaming")
                on_start()
            
            # Parser la réponse en streaming
            accumulated_content = ""
            
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    
                    if current_config.get('api_type') == "openai":
                        if line_str.startswith('data: '):
                            data_str = line_str[6:]
                            if data_str == '[DONE]':
                                break
                            try:
                                data = json.loads(data_str)
                                if 'choices' in data and data['choices']:
                                    delta = data['choices'][0].get('delta', {})
                                    if 'content' in delta:
                                        content = delta['content']
                                        accumulated_content += content
                                        # Appeler le callback de chunk
                                        if on_chunk:
                                            on_chunk(content)
                            except json.JSONDecodeError:
                                self.logger.warning(f"Failed to parse streaming data: {data_str}")
                    else:  # ollama
                        try:
                            data = json.loads(line_str)
                            if 'response' in data:
                                content = data['response']
                                accumulated_content += content
                                # Appeler le callback de chunk
                                if on_chunk:
                                    on_chunk(content)
                            if data.get('done', False):
                                break
                        except json.JSONDecodeError:
                            self.logger.warning(f"Failed to parse streaming data: {line_str}")
            
            # Créer l'historique final et compter les tokens
            final_history = chat_history + [{'role': 'assistant', 'content': accumulated_content}]
            total_tokens = self._count_tokens_for_history(final_history)
            
            # Appeler le callback de fin avec le comptage de tokens
            if on_end:
                on_end(total_tokens)
            
            self.logger.info(f"Streaming completed. Total content length: {len(accumulated_content)}, tokens: {total_tokens}")
            return {'response': accumulated_content, 'total_tokens': total_tokens}
            
        except RateLimitException:
            raise
        except requests.exceptions.ProxyError as e:
            self.logger.error(f"=== ERREUR PROXY (STREAMING) ===")
            self.logger.error(f"Erreur de proxy pendant streaming {llm_id}: {e}")
            self.logger.error(f"Configuration proxy: {proxies if 'proxies' in locals() else 'Non défini'}")
            error_msg = f"Erreur de proxy sur {llm_id}: {str(e)}"
            if on_error:
                on_error(error_msg)
            self._notify_error(error_msg, -1, 0)
            raise NetworkException(error_msg)
        except requests.exceptions.SSLError as e:
            self.logger.error(f"=== ERREUR SSL (STREAMING) ===")
            self.logger.error(f"Erreur SSL pendant streaming {llm_id}: {e}")
            error_msg = f"Erreur SSL sur {llm_id}: {str(e)}"
            if on_error:
                on_error(error_msg)
            self._notify_error(error_msg, -1, 0)
            raise NetworkException(error_msg)
        except requests.exceptions.Timeout as e:
            self.logger.error(f"=== TIMEOUT (STREAMING) ===")
            self.logger.error(f"Timeout during streaming with {llm_id}: {e}")
            self.logger.error(f"Timeout était: {timeout if 'timeout' in locals() else '?'}s")
            error_msg = f"Timeout après {timeout if 'timeout' in locals() else '?'} secondes sur {llm_id}"
            # Notifier via callback et notification globale
            if on_error:
                on_error(error_msg)
            self._notify_error(error_msg, -1, 0)
            raise NetworkException(error_msg)
        except requests.exceptions.ConnectionError as e:
            self.logger.error(f"=== ERREUR DE CONNEXION (STREAMING) ===")
            self.logger.error(f"Connection error during streaming with {llm_id}: {e}")
            self.logger.error(f"URL: {target_url if 'target_url' in locals() else '?'}")
            self.logger.error(f"Proxy: {proxies if 'proxies' in locals() else 'Aucun'}")
            error_msg = f"Erreur de connexion sur {llm_id}: {str(e)}"
            if on_error:
                on_error(error_msg)
            self._notify_error(error_msg, -1, 0)
            raise NetworkException(error_msg)
        except requests.exceptions.RequestException as e:
            self.logger.error(f"=== ERREUR RÉSEAU (STREAMING) ===")
            self.logger.error(f"Network error during streaming with {llm_id}: {e}")
            self.logger.error(f"Type: {type(e).__name__}")
            # Appeler le callback d'erreur
            if on_error:
                on_error(str(e))
            raise NetworkException(f"Network error during streaming: {str(e)}")
        except Exception as e:
            self.logger.error(f"=== ERREUR INATTENDUE (STREAMING) ===")
            self.logger.error(f"Error during streaming with {llm_id}: {e}")
            self.logger.error(f"Type: {type(e).__name__}")
            import traceback
            self.logger.error(f"Stack trace: {traceback.format_exc()}")
            # Appeler le callback d'erreur
            if on_error:
                on_error(str(e))
            raise LlmApiServiceException(f"Error during streaming: {str(e)}")
    
    def _count_tokens_for_history(self, chat_history: List[Dict[str, str]]) -> int:
        """Compte le nombre total de tokens dans l'historique du chat."""
        try:
            total_tokens = 0
            
            for message in chat_history:
                content = message.get('content', '')
                role = message.get('role', '')
                
                # Compter les tokens du contenu
                content_tokens = self._estimate_tokens(content)
                
                # Ajouter le surcoût pour le rôle et la structure
                role_tokens = len(role.split()) + 5
                
                total_tokens += content_tokens + role_tokens
            
            # Ajouter un surcoût pour la structure globale
            total_tokens += len(chat_history) * 3
            
            return total_tokens
        except Exception as e:
            self.logger.warning(f"Error counting tokens: {e}")
            return len(str(chat_history)) // 4  # Approximation grossière
    
    def _estimate_tokens(self, text: str) -> int:
        """Estime le nombre de tokens dans un texte donné."""
        if not text:
            return 0
        
        # Approximation basée sur l'analyse des patterns de tokenization GPT/Claude
        words = text.split()
        word_count = len(words)
        
        # Compter les caractères de ponctuation
        punctuation_count = len(re.findall(r'[.,!?;:()\[\]{}"\'`\-–—…]', text))
        
        # Compter les nombres
        number_sequences = re.findall(r'\d+', text)
        number_tokens = sum(len(num) // 3 + 1 for num in number_sequences)
        
        # Compter les retours à la ligne
        newline_count = text.count('\n')
        
        # Gérer les mots longs
        long_words = [w for w in words if len(w) > 10]
        extra_tokens_long_words = sum((len(w) - 5) // 5 for w in long_words)
        
        # Calcul final
        estimated_tokens = (
            word_count + 
            punctuation_count // 2 + 
            number_tokens +
            newline_count +
            extra_tokens_long_words
        )
        
        # Ajuster selon le ratio observé (~1.3 tokens par mot en moyenne)
        return int(estimated_tokens * 1.3)
    
    def _safe_getint(self, config: ConfigParser, section: str, option: str, default):
        """
        Récupère une valeur entière de la configuration de manière sûre.
        Gère les cas où la valeur contient des commentaires inline.
        
        Args:
            default: Valeur par défaut (peut être None ou un entier)
        
        Returns:
            int ou None selon la configuration et le défaut
        """
        try:
            # Si l'option n'existe pas et que le défaut est None, retourner None
            if not config.has_option(section, option):
                return default
                
            value = config.get(section, option)
            # Nettoyer la valeur en enlevant les commentaires potentiels
            if '#' in value:
                value = value.split('#')[0].strip()
            return int(value)
        except (ValueError, TypeError):
            if default is not None:
                self.logger.warning(f"Impossible de parser {section}.{option}='{value}' comme entier, utilisation de la valeur par défaut {default}")
            return default
    
    def _clean_history_for_titling(self, chat_history: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Nettoie l'historique en supprimant les blocs de code pour une analyse sémantique pure.
        
        Patterns à supprimer:
        - Blocs de code markdown (```)
        - Blocs de diff (---, +++, @@)
        - Longues chaînes de caractères techniques
        
        Args:
            chat_history: L'historique de conversation original
            
        Returns:
            L'historique nettoyé pour l'analyse sémantique
        """
        cleaned_history = []
        
        for message in chat_history:
            cleaned_content = message['content']
            
            # Supprimer les blocs de code markdown (avec ou sans langage spécifié)
            cleaned_content = re.sub(r'```[\s\S]*?```', '[CODE BLOCK REMOVED]', cleaned_content)
            
            # Supprimer les blocs de code inline
            cleaned_content = re.sub(r'`[^`]+`', '[CODE]', cleaned_content)
            
            # Supprimer les blocs de diff
            # Pattern pour les lignes de diff qui commencent par ---, +++, @@, +, -
            cleaned_content = re.sub(r'^[\+\-@]{1,3}.*$', '[DIFF LINE REMOVED]', cleaned_content, flags=re.MULTILINE)
            
            # Remplacer les multiples espaces/lignes vides par un seul espace
            cleaned_content = re.sub(r'\n{3,}', '\n\n', cleaned_content)
            cleaned_content = re.sub(r'[ \t]{2,}', ' ', cleaned_content)
            
            # Ne pas tronquer ici - la troncature sera faite lors du formatage final
            
            cleaned_history.append({
                'role': message['role'],
                'content': cleaned_content.strip()
            })
        
        return cleaned_history
    
    def _get_title_generation_config(self) -> Dict[str, Any]:
        """
        Récupère la configuration pour la génération de titre avec fallback.
        Priorité : TitleGeneratorLLM > Modèle LLM par défaut
        
        Returns:
            Dict contenant la configuration pour générer le titre
        """
        try:
            # Lire le fichier config.ini
            config = ConfigParser()
            config.read('config.ini', encoding='utf-8')
            
            # Tenter d'abord la config spécifique TitleGeneratorLLM
            if config.has_section('TitleGeneratorLLM'):
                if config.getboolean('TitleGeneratorLLM', 'enabled', fallback=True):
                    self.logger.info("Utilisation de la configuration TitleGeneratorLLM")
                    
                    # Si TitleGeneratorLLM n'a pas d'URL/apikey, utiliser le modèle par défaut
                    default_model = self._llm_models.get(self._default_llm_id, {}) if self._default_llm_id else {}
                    
                    # Récupérer les paramètres avec fallback sur le modèle par défaut
                    return {
                        'api_url': config.get('TitleGeneratorLLM', 'url', 
                                            fallback=default_model.get('url', '')),
                        'api_key': config.get('TitleGeneratorLLM', 'apikey', 
                                             fallback=default_model.get('apikey', '')),
                        'model': config.get('TitleGeneratorLLM', 'model', 
                                          fallback=default_model.get('model', '')),
                        'api_type': config.get('TitleGeneratorLLM', 'api_type',
                                             fallback=default_model.get('api_type', 'openai')),
                        'prompt': config.get('TitleGeneratorLLM', 'title_prompt', 
                                           fallback=self.DEFAULT_TITLE_PROMPT),
                        'timeout': self._safe_getint(config, 'TitleGeneratorLLM', 'timeout_seconds', 15),
                        'max_length': self._safe_getint(config, 'TitleGeneratorLLM', 'max_title_length', 100),
                        'temperature': config.getfloat('TitleGeneratorLLM', 'temperature', fallback=None),
                        'max_tokens': self._safe_getint(config, 'TitleGeneratorLLM', 'max_tokens', None),
                        'ssl_verify': default_model.get('ssl_verify', True),
                        # Configuration proxy
                        'proxy_http': config.get('TitleGeneratorLLM', 'proxy_http', 
                                                fallback=default_model.get('proxy_http')),
                        'proxy_https': config.get('TitleGeneratorLLM', 'proxy_https', 
                                                 fallback=default_model.get('proxy_https')),
                        'proxy_no_proxy': config.get('TitleGeneratorLLM', 'proxy_no_proxy', 
                                                    fallback=default_model.get('proxy_no_proxy'))
                    }
                else:
                    self.logger.info("TitleGeneratorLLM est désactivé, fallback sur le modèle par défaut")
            
            # Fallback sur le modèle LLM par défaut
            if self._default_llm_id and self._default_llm_id in self._llm_models:
                default_model = self._llm_models[self._default_llm_id]
                self.logger.info(f"Utilisation du modèle par défaut '{self._default_llm_id}' pour la génération de titre")
                return {
                    'api_url': default_model.get('url', ''),
                    'api_key': default_model.get('apikey', ''),
                    'model': default_model.get('model', ''),
                    'api_type': default_model.get('api_type', 'openai'),
                    'prompt': self.DEFAULT_TITLE_PROMPT,
                    'timeout': 15,
                    'max_length': 100,
                    'temperature': None,  # Pas de temperature par défaut
                    'max_tokens': None,  # Pas de max_tokens par défaut
                    'ssl_verify': default_model.get('ssl_verify', True),
                    # Configuration proxy
                    'proxy_http': default_model.get('proxy_http'),
                    'proxy_https': default_model.get('proxy_https'),
                    'proxy_no_proxy': default_model.get('proxy_no_proxy')
                }
            
            # Aucune configuration trouvée
            self.logger.warning("Aucune configuration LLM trouvée pour la génération de titre")
            return None
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la lecture de la configuration: {e}")
            return None
    
    def extract_project_name(self, main_context: str) -> str:
        """
        Extrait le nom du projet depuis le contexte principal.
        
        Recherche les patterns suivants (par ordre de priorité):
        1. "# Contexte du projet - {nom}"
        2. "# Project Context - {nom}"
        3. Premier titre de niveau 1 ou 2
        
        Args:
            main_context: Le contexte complet du projet
            
        Returns:
            Le nom du projet ou une chaîne vide
        """
        if not main_context:
            return ""
        
        # Pattern 1: Format français
        match = re.search(r'#\s*Contexte du projet\s*[-–]\s*(.+?)(?:\n|$)', main_context, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        
        # Pattern 2: Format anglais
        match = re.search(r'#\s*Project Context\s*[-–]\s*(.+?)(?:\n|$)', main_context, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        
        # Pattern 3: Premier titre de niveau 1 ou 2
        match = re.search(r'^#{1,2}\s+(.+?)(?:\n|$)', main_context, re.MULTILINE)
        if match:
            # Nettoyer le titre (enlever les parties après - ou :)
            title = match.group(1).strip()
            # Si le titre contient un séparateur, prendre la partie après
            if ' - ' in title:
                title = title.split(' - ', 1)[1]
            elif ': ' in title:
                title = title.split(': ', 1)[1]
            return title.strip()
        
        return ""
    
    def generate_title(self, chat_history: List[Dict[str, str]], main_context: Optional[str] = None) -> str:
        """
        Génère un titre pour une conversation en utilisant le LLM.
        
        Args:
            chat_history: L'historique de la conversation à résumer.
            main_context: Le contexte complet du projet pour en extraire le nom.
            
        Returns:
            Le titre suggéré par le LLM préfixé par le nom du projet, ou une chaîne vide en cas d'échec.
        """
        try:
            # Extraire le nom du projet
            project_name = self.extract_project_name(main_context)
            if project_name:
                self.logger.info(f"Nom du projet extrait: '{project_name}'")
            
            # Récupérer la configuration avec fallback
            title_config = self._get_title_generation_config()
            
            if not title_config:
                self.logger.info("Pas de configuration LLM disponible pour générer un titre")
                return ""
            
            # Nettoyer l'historique pour l'analyse sémantique
            cleaned_history = self._clean_history_for_titling(chat_history)
            
            # Limiter le nombre de messages pour économiser les tokens
            if len(cleaned_history) > 10:
                # Prendre les 5 premiers et 5 derniers messages
                cleaned_history = cleaned_history[:5] + cleaned_history[-5:]
            
            # Formater l'historique pour l'inclure dans le prompt
            # Tronquer chaque message à 300 caractères pour économiser les tokens
            formatted_history = "\n".join([
                f"- {msg['role'].capitalize()}: {msg['content'][:300]}..." if len(msg['content']) > 300 
                else f"- {msg['role'].capitalize()}: {msg['content']}"
                for msg in cleaned_history
            ])
            
            # Préparer le prompt final
            final_prompt = title_config['prompt'].format(history=formatted_history)
            
            # Créer un message unique pour l'appel LLM
            title_request_history = [{'role': 'user', 'content': final_prompt}]
            
            # Préparer la requête selon le type d'API
            headers = {"Content-Type": "application/json"}
            if title_config['api_key']:
                headers["Authorization"] = f"Bearer {title_config['api_key']}"
            
            # Log pour debug
            self.logger.info(f"Configuration de génération de titre - api_type: {title_config.get('api_type', 'NON DÉFINI')}")
            
            if title_config['api_type'] == "openai":
                # Utiliser la méthode factorisée
                target_url, payload = self._build_openai_request(
                    api_url=title_config['api_url'],
                    model=title_config['model'],
                    messages=title_request_history,
                    stream=False,
                    temperature=title_config.get('temperature'),
                    max_tokens=title_config.get('max_tokens')
                )
            else:  # ollama
                prompt = title_request_history[0]['content']
                payload = {
                    "model": title_config['model'],
                    "prompt": prompt,
                    "stream": False
                }
                target_url = title_config['api_url'].rstrip('/') + "/api/generate"
            
            # Faire l'appel API avec timeout court
            self.logger.info(f"Génération du titre via {target_url} (api_type={title_config['api_type']})")
            
            if not title_config['ssl_verify']:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            # Récupérer la config proxy depuis title_config ou fallback sur le modèle par défaut
            proxy_config = {
                'proxy_http': title_config.get('proxy_http'),
                'proxy_https': title_config.get('proxy_https'),
                'proxy_no_proxy': title_config.get('proxy_no_proxy')
            }
            proxies = self._get_proxy_config(proxy_config) if any(proxy_config.values()) else None
            
            response = self.session.post(
                target_url,
                headers=headers,
                json=payload,
                verify=title_config['ssl_verify'],
                timeout=title_config['timeout'],
                proxies=proxies
            )
            
            response.raise_for_status()
            
            # Parser la réponse selon le type d'API
            if title_config['api_type'] == "openai":
                result = response.json()
                
                if 'choices' in result and result['choices']:
                    # Récupérer le message correctement
                    choice = result['choices'][0]
                    
                    # Vérifier si la génération a été tronquée
                    if choice.get('finish_reason') == 'length':
                        self.logger.warning("La génération a été tronquée (finish_reason='length'). Le LLM a besoin de plus de tokens.")
                    
                    if 'message' in choice:
                        message = choice['message']
                        title = message.get('content')
                    elif 'text' in choice:  # Format legacy OpenAI
                        title = choice.get('text')
                    else:
                        self.logger.warning(f"Structure de choice inattendue. Clés disponibles: {choice.keys() if isinstance(choice, dict) else type(choice)}")
                        title = None
                else:
                    self.logger.warning(f"Format de réponse inattendu du LLM - pas de choices: {result.keys()}")
                    return ""
            else:  # ollama
                result = response.json()
                self.logger.debug(f"Réponse brute du LLM (Ollama): {result}")
                if 'response' in result:
                    title = result.get('response')
                else:
                    self.logger.warning(f"Format de réponse inattendu du LLM: {result.keys()}")
                    return ""
            
            # Vérifier que le titre n'est pas None
            if not title:
                self.logger.warning(f"Le LLM a retourné un titre vide ou None. Result keys: {result.keys() if result else 'No result'}")
                return ""
            
            # Nettoyer le titre
            # Supprimer les guillemets, apostrophes au début et à la fin
            title = str(title).strip().strip('"\'`')
            
            # Supprimer les préfixes courants
            prefixes_to_remove = ['Titre :', 'Title:', 'Titre:', 'Title :', 
                                 'Sujet :', 'Subject:', 'Résumé :', 'Summary:']
            for prefix in prefixes_to_remove:
                if title.lower().startswith(prefix.lower()):
                    title = title[len(prefix):].strip()
            
            # Construire le titre final avec le nom du projet
            if project_name and title:
                # Format: "NomProjet: Titre"
                final_title = f"{project_name}: {title}"
                self.logger.info(f"Titre avec préfixe projet: '{final_title}'")
            else:
                final_title = title
            
            # Vérifier la longueur et tronquer si nécessaire
            max_length = title_config['max_length']
            if len(final_title) > max_length:
                # Tronquer intelligemment en gardant le nom du projet
                if project_name and len(project_name) < max_length - 10:
                    # Garder le nom du projet et tronquer le titre
                    remaining = max_length - len(project_name) - 2  # -2 pour ": "
                    truncated_title = title[:remaining-3] + "..."
                    final_title = f"{project_name}: {truncated_title}"
                else:
                    # Tronquer normalement
                    final_title = final_title[:max_length-3] + "..."
            
            self.logger.info(f"Titre final généré: '{final_title}'")
            return final_title
            
        except requests.exceptions.Timeout:
            timeout_val = title_config.get('timeout', 15) if title_config else 15
            self.logger.warning(f"Timeout lors de la génération du titre (>{timeout_val}s)")
            return ""
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Erreur réseau lors de la génération du titre: {e}")
            return ""
        except Exception as e:
            self.logger.error(f"Erreur lors de la génération du titre: {e}")
            return ""