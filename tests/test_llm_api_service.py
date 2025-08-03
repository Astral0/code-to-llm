import pytest
from unittest.mock import patch, MagicMock, Mock
import requests
import json
from services.llm_api_service import LlmApiService, LlmApiServiceException, NetworkException, RateLimitException


class TestLlmApiService:
    """Tests unitaires pour LlmApiService."""
    
    @pytest.fixture
    def llm_service(self):
        """Fixture pour créer une instance de LlmApiService."""
        config = {'debug': False}
        return LlmApiService(config)
    
    @pytest.fixture
    def mock_config(self):
        """Fixture pour mocker la configuration."""
        config = MagicMock()
        config.getboolean.side_effect = lambda section, key, fallback=None: {
            ('LLMServer', 'enabled'): True,
            ('LLMServer', 'ssl_verify'): True
        }.get((section, key), fallback)
        config.get.side_effect = lambda section, key, fallback=None: {
            ('LLMServer', 'url'): 'https://api.openai.com/v1',
            ('LLMServer', 'apikey'): 'test-api-key',
            ('LLMServer', 'model'): 'gpt-3.5-turbo',
            ('LLMServer', 'api_type'): 'openai'
        }.get((section, key), fallback)
        return config
    
    @pytest.fixture
    def chat_history(self):
        """Fixture pour l'historique de chat de test."""
        return [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"}
        ]
    
    def test_init(self):
        """Test de l'initialisation du service."""
        config = {'debug': True}
        service = LlmApiService(config)
        assert service.config == config
        assert hasattr(service, 'session')
    
    def test_setup_http_session(self, llm_service):
        """Test de la configuration de la session HTTP avec retry."""
        assert llm_service.session is not None
        adapters = llm_service.session.adapters
        assert 'http://' in adapters
        assert 'https://' in adapters
        # Vérifier que le retry est configuré
        adapter = adapters['https://']
        assert adapter.max_retries.total == 3
        assert 500 in adapter.max_retries.status_forcelist
        assert adapter.max_retries.respect_retry_after_header == True
    
    def test_get_llm_config(self, llm_service):
        """Test de la récupération de la configuration LLM injectée."""
        # La config devrait être celle passée au constructeur
        config = llm_service._get_llm_config()
        
        # Config par défaut du fixture
        assert config['debug'] == False
    
    @patch('configparser.ConfigParser')
    def test_prepare_request_openai(self, mock_config_parser, mock_config, llm_service, chat_history):
        """Test de la préparation de requête pour OpenAI."""
        mock_config_parser.return_value = mock_config
        
        url, headers, payload, ssl_verify = llm_service._prepare_request(chat_history, stream=False)
        
        assert url == 'https://api.openai.com/v1/chat/completions'
        assert headers['Authorization'] == 'Bearer test-api-key'
        assert payload['model'] == 'gpt-3.5-turbo'
        assert payload['messages'] == chat_history
        assert payload['stream'] == False
    
    @patch('configparser.ConfigParser')
    def test_prepare_request_ollama(self, mock_config_parser, llm_service, chat_history):
        """Test de la préparation de requête pour Ollama."""
        mock_config = MagicMock()
        mock_config.getboolean.return_value = True
        mock_config.get.side_effect = lambda section, key, fallback=None: {
            ('LLMServer', 'url'): 'http://localhost:11434',
            ('LLMServer', 'apikey'): '',
            ('LLMServer', 'model'): 'llama2',
            ('LLMServer', 'api_type'): 'ollama'
        }.get((section, key), fallback)
        mock_config_parser.return_value = mock_config
        
        url, headers, payload, ssl_verify = llm_service._prepare_request(chat_history, stream=True)
        
        assert url == 'http://localhost:11434/api/generate'
        assert 'Authorization' not in headers
        assert payload['model'] == 'llama2'
        assert 'prompt' in payload
        assert payload['stream'] == True
    
    @patch('configparser.ConfigParser')
    def test_prepare_request_disabled(self, mock_config_parser, llm_service, chat_history):
        """Test quand LLM est désactivé."""
        mock_config = MagicMock()
        mock_config.getboolean.return_value = False
        mock_config_parser.return_value = mock_config
        
        with pytest.raises(LlmApiServiceException) as exc_info:
            llm_service._prepare_request(chat_history)
        
        assert "not enabled" in str(exc_info.value)
    
    @patch.object(LlmApiService, '_prepare_request')
    def test_send_to_llm_success_openai(self, mock_prepare, llm_service, chat_history):
        """Test d'envoi réussi vers OpenAI."""
        mock_prepare.return_value = (
            'https://api.openai.com/v1/chat/completions',
            {'Authorization': 'Bearer test-key'},
            {'model': 'gpt-3.5-turbo', 'messages': chat_history},
            True
        )
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{'message': {'content': 'Test response'}}]
        }
        
        with patch.object(llm_service.session, 'post', return_value=mock_response):
            result = llm_service.send_to_llm(chat_history)
        
        assert result == {'response': 'Test response'}
    
    @patch.object(LlmApiService, '_prepare_request')
    @patch.object(LlmApiService, '_load_llm_config')
    def test_send_to_llm_success_ollama(self, mock_load_config, mock_prepare, llm_service, chat_history):
        """Test d'envoi réussi vers Ollama."""
        mock_load_config.return_value = {'api_type': 'ollama'}
        mock_prepare.return_value = (
            'http://localhost:11434/api/generate',
            {},
            {'model': 'llama2', 'prompt': 'test'},
            True
        )
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'response': 'Test response from Ollama'}
        
        with patch.object(llm_service.session, 'post', return_value=mock_response):
            result = llm_service.send_to_llm(chat_history)
        
        assert result == {'response': 'Test response from Ollama'}
    
    @patch.object(LlmApiService, '_prepare_request')
    def test_send_to_llm_rate_limit(self, mock_prepare, llm_service, chat_history):
        """Test de gestion du rate limit (429)."""
        mock_prepare.return_value = ('url', {}, {}, True)
        
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {'Retry-After': '30'}
        
        with patch.object(llm_service.session, 'post', return_value=mock_response):
            with pytest.raises(RateLimitException) as exc_info:
                llm_service.send_to_llm(chat_history)
        
        assert exc_info.value.retry_after == 30
    
    @patch.object(LlmApiService, '_prepare_request')
    def test_send_to_llm_network_error(self, mock_prepare, llm_service, chat_history):
        """Test de gestion des erreurs réseau."""
        mock_prepare.return_value = ('url', {}, {}, True)
        
        with patch.object(llm_service.session, 'post', side_effect=requests.ConnectionError("Network error")):
            with pytest.raises(NetworkException) as exc_info:
                llm_service.send_to_llm(chat_history)
        
        assert "Network error" in str(exc_info.value)
    
    @patch.object(LlmApiService, '_prepare_request')
    def test_send_to_llm_stream_success(self, mock_prepare, llm_service, chat_history):
        """Test du streaming réussi."""
        mock_prepare.return_value = (
            'https://api.openai.com/v1/chat/completions',
            {'Authorization': 'Bearer test-key'},
            {'model': 'gpt-3.5-turbo', 'messages': chat_history, 'stream': True},
            True
        )
        
        # Mock de la réponse streaming
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = [
            b'data: {"choices":[{"delta":{"content":"Hello"}}]}',
            b'data: {"choices":[{"delta":{"content":" world"}}]}',
            b'data: [DONE]'
        ]
        
        # Mock des callbacks
        on_start = MagicMock()
        on_chunk = MagicMock()
        on_end = MagicMock()
        on_error = MagicMock()
        
        with patch.object(llm_service.session, 'post', return_value=mock_response):
            with patch.object(llm_service, '_get_llm_config', return_value={'api_type': 'openai'}):
                result = llm_service.send_to_llm_stream(
                    chat_history, 
                    on_start=on_start,
                    on_chunk=on_chunk,
                    on_end=on_end,
                    on_error=on_error
                )
        
        assert result['response'] == 'Hello world'
        assert result['total_tokens'] > 0
        # Vérifier que les callbacks ont été appelés
        on_start.assert_called_once()
        assert on_chunk.call_count == 2  # "Hello" et " world"
        on_end.assert_called_once()
        on_error.assert_not_called()
    
    def test_count_tokens_for_history(self, llm_service, chat_history):
        """Test du comptage de tokens."""
        token_count = llm_service._count_tokens_for_history(chat_history)
        
        # Vérification approximative
        assert token_count > 0
        assert token_count < 100  # Pour un court historique
    
    def test_estimate_tokens(self, llm_service):
        """Test de l'estimation de tokens."""
        # Cas simples
        assert llm_service._estimate_tokens("") == 0
        assert llm_service._estimate_tokens("Hello world") > 0
        
        # Texte avec ponctuation et nombres
        text = "Hello, world! This is test 123."
        tokens = llm_service._estimate_tokens(text)
        assert tokens > 5  # Au moins quelques tokens
        
        # Texte long
        long_text = "supercalifragilisticexpialidocious " * 10
        long_tokens = llm_service._estimate_tokens(long_text)
        assert long_tokens > tokens  # Plus de tokens pour un texte plus long
    
    @patch.object(LlmApiService, '_prepare_request')
    def test_send_to_llm_stream_error_handling(self, mock_prepare, llm_service, chat_history):
        """Test de la gestion d'erreur pendant le streaming."""
        mock_prepare.return_value = ('url', {}, {}, True)
        
        on_error = MagicMock()
        
        with patch.object(llm_service.session, 'post', side_effect=Exception("Stream error")):
            with pytest.raises(LlmApiServiceException):
                llm_service.send_to_llm_stream(
                    chat_history,
                    on_error=on_error
                )
        
        # Vérifier que le callback d'erreur a été appelé
        on_error.assert_called_once_with("Stream error")