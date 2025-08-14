import requests
import json
import logging
import re
import time
from typing import Dict, Any, Optional, List, Callable
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from configparser import ConfigParser
from .base_service import BaseService
from .exceptions import LlmApiServiceException, NetworkException, RateLimitException


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
            # Utiliser la méthode factorisée
            target_url, payload = self._build_openai_request(
                api_url=llm_config['url'],
                model=llm_config['model'],
                messages=chat_history,
                stream=stream,
                temperature=llm_config.get('temperature'),
                max_tokens=llm_config.get('max_tokens')
            )
        else:  # ollama
            prompt = "\n\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in chat_history])
            payload = {
                "model": llm_config['model'],
                "prompt": prompt,
                "stream": stream
            }
            # Ajouter les paramètres optionnels pour Ollama aussi
            if 'temperature' in llm_config and llm_config['temperature'] is not None:
                payload['temperature'] = llm_config['temperature']
                
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
        Priorité : TitleGeneratorLLM > LLMServer
        
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
                    
                    # Récupérer les paramètres avec fallback sur LLMServer
                    return {
                        'api_url': config.get('TitleGeneratorLLM', 'url', 
                                            fallback=config.get('LLMServer', 'url')),
                        'api_key': config.get('TitleGeneratorLLM', 'apikey', 
                                             fallback=config.get('LLMServer', 'apikey')),
                        'model': config.get('TitleGeneratorLLM', 'model', 
                                          fallback=config.get('LLMServer', 'model')),
                        'api_type': config.get('TitleGeneratorLLM', 'api_type',
                                             fallback=config.get('LLMServer', 'api_type', fallback='openai')),
                        'prompt': config.get('TitleGeneratorLLM', 'title_prompt', 
                                           fallback=self.DEFAULT_TITLE_PROMPT),
                        'timeout': self._safe_getint(config, 'TitleGeneratorLLM', 'timeout_seconds', 15),
                        'max_length': self._safe_getint(config, 'TitleGeneratorLLM', 'max_title_length', 100),
                        'temperature': config.getfloat('TitleGeneratorLLM', 'temperature', fallback=None),
                        'max_tokens': self._safe_getint(config, 'TitleGeneratorLLM', 'max_tokens', None),
                        'ssl_verify': config.getboolean('LLMServer', 'ssl_verify', fallback=True)
                    }
                else:
                    self.logger.info("TitleGeneratorLLM est désactivé, fallback sur LLMServer")
            
            # Fallback sur la config principale LLMServer
            if config.has_section('LLMServer'):
                self.logger.info("Utilisation de la configuration LLMServer pour la génération de titre")
                return {
                    'api_url': config.get('LLMServer', 'url'),
                    'api_key': config.get('LLMServer', 'apikey'),
                    'model': config.get('LLMServer', 'model'),
                    'api_type': config.get('LLMServer', 'api_type', fallback='openai'),
                    'prompt': self.DEFAULT_TITLE_PROMPT,
                    'timeout': 15,
                    'max_length': 100,
                    'temperature': None,  # Pas de temperature par défaut
                    'max_tokens': None,  # Pas de max_tokens par défaut
                    'ssl_verify': config.getboolean('LLMServer', 'ssl_verify', fallback=True)
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
            
            response = self.session.post(
                target_url,
                headers=headers,
                json=payload,
                verify=title_config['ssl_verify'],
                timeout=title_config['timeout']
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