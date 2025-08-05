import requests
import json
import logging
import re
import time
from typing import Dict, Any, Optional, List, Callable
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from .base_service import BaseService
from .exceptions import LlmApiServiceException, NetworkException, RateLimitException


class LlmApiService(BaseService):
    """Service pour gérer les communications avec les API LLM."""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """
        Initialise le service LLM API.
        
        Args:
            config: Dictionnaire de configuration contenant les paramètres LLM
            logger: Logger optionnel
        """
        super().__init__(config, logger)
        self._llm_config = config  # Stocker la config LLM directement
        self._setup_http_session()
        
    def validate_config(self):
        """Valide la configuration du service LLM."""
        # La validation sera faite lors de l'appel aux méthodes
        pass
    
    def _setup_http_session(self):
        """Configure une session HTTP avec retry strategy intelligente."""
        self.session = requests.Session()
        
        # Configuration du retry avec backoff exponentiel
        retry_strategy = Retry(
            total=3,
            status_forcelist=[500, 502, 503, 504],  # Erreurs récupérables seulement
            allowed_methods=["GET", "POST"],  # Changé de method_whitelist (déprécié)
            backoff_factor=1,
            respect_retry_after_header=True  # Support du 429 Too Many Requests
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
    
    def _get_llm_config(self) -> Dict[str, Any]:
        """Retourne la configuration LLM injectée."""
        return self._llm_config
    
    def _prepare_request(self, chat_history: List[Dict[str, str]], stream: bool = False) -> tuple:
        """
        Prépare les données pour la requête LLM.
        
        Returns:
            tuple: (url, headers, payload)
        """
        llm_config = self._get_llm_config()
        
        if not llm_config['enabled']:
            raise LlmApiServiceException('LLM feature is not enabled in config.ini')
        
        if not llm_config['url'] or not llm_config['model']:
            raise LlmApiServiceException('LLM server configuration is incomplete in config.ini')
        
        headers = {"Content-Type": "application/json"}
        if llm_config['apikey']:
            headers["Authorization"] = f"Bearer {llm_config['apikey']}"
        
        if llm_config['api_type'] == "openai":
            payload = {
                "model": llm_config['model'],
                "messages": chat_history,
                "stream": stream
            }
            target_url = llm_config['url'].rstrip('/')
            if not target_url.endswith('/chat/completions'):
                target_url += '/chat/completions' if '/v1' in target_url else '/v1/chat/completions'
        else:  # ollama
            prompt = "\n\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in chat_history])
            payload = {
                "model": llm_config['model'],
                "prompt": prompt,
                "stream": stream
            }
            target_url = llm_config['url'].rstrip('/') + "/api/generate"
        
        return target_url, headers, payload, llm_config['ssl_verify']
    
    def send_to_llm(self, chat_history: List[Dict[str, str]], stream: bool = False) -> Dict[str, Any]:
        """
        Envoie l'historique du chat au LLM et retourne la réponse.
        
        Args:
            chat_history: Liste des messages de la conversation
            stream: Si True, utilise le mode streaming
            
        Returns:
            Dict contenant la réponse ou une erreur
        """
        try:
            target_url, headers, payload, ssl_verify = self._prepare_request(chat_history, stream)
            
            self.logger.info(f"Sending request to LLM at {target_url} (SSL verify: {ssl_verify})")
            
            if not ssl_verify:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            token_count = self._count_tokens_for_history(chat_history)
            self.logger.info(f"Estimated token count: {token_count}")
            
            response = self.session.post(
                target_url,
                headers=headers,
                json=payload,
                verify=ssl_verify,
                timeout=self._llm_config.get('timeout_seconds', 300)
            )
            
            # Gérer les erreurs HTTP
            if response.status_code == 429:
                retry_after = response.headers.get('Retry-After', 60)
                raise RateLimitException(
                    f"Rate limit exceeded. Retry after {retry_after} seconds",
                    int(retry_after)
                )
            
            response.raise_for_status()
            
            # Parser la réponse selon le type d'API
            llm_config = self._get_llm_config()
            if llm_config['api_type'] == "openai":
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
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Network error calling LLM: {e}")
            raise NetworkException(f"Network error: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error calling LLM: {e}")
            raise LlmApiServiceException(f"Error calling LLM: {str(e)}")
    
    def send_to_llm_stream(self, chat_history: List[Dict[str, str]], 
                          on_start: Optional[Callable[[], None]] = None,
                          on_chunk: Optional[Callable[[str], None]] = None,
                          on_end: Optional[Callable[[int], None]] = None,
                          on_error: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
        """
        Envoie l'historique au LLM en mode streaming avec callbacks.
        
        Args:
            chat_history: Liste des messages de la conversation
            on_start: Callback appelé au début du streaming
            on_chunk: Callback appelé pour chaque chunk reçu
            on_end: Callback appelé à la fin avec le nombre total de tokens
            on_error: Callback appelé en cas d'erreur
            
        Returns:
            Dict contenant le statut ou une erreur
        """
        try:
            target_url, headers, payload, ssl_verify = self._prepare_request(chat_history, stream=True)
            
            self.logger.info(f"Sending streaming request to LLM at {target_url}")
            
            if not ssl_verify:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            token_count = self._count_tokens_for_history(chat_history)
            self.logger.info(f"Estimated token count: {token_count}")
            
            response = self.session.post(
                target_url,
                headers=headers,
                json=payload,
                verify=ssl_verify,
                stream=True,
                timeout=self._llm_config.get('timeout_seconds', 300)
            )
            
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
            llm_config = self._get_llm_config()
            accumulated_content = ""
            
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    
                    if llm_config['api_type'] == "openai":
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
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Network error during streaming: {e}")
            # Appeler le callback d'erreur
            if on_error:
                on_error(str(e))
            raise NetworkException(f"Network error during streaming: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error during streaming: {e}")
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