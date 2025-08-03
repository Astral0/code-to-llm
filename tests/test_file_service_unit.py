import pytest
from unittest.mock import patch, MagicMock, Mock, mock_open
import os
from pathlib import Path
import pathspec
from services.file_service import FileService, FileServiceException


class TestFileServiceUnit:
    """Tests unitaires pour FileService avec tests des nouvelles méthodes."""
    
    @pytest.fixture
    def file_service(self):
        """Fixture pour créer une instance de FileService."""
        config = {
            'debug': False,
            'binary_blacklist': {'.exe', '.dll', '.so'},
            'binary_whitelist': {'.md', '.txt', '.json'},
            'file_blacklist': {'thumbs.db', '.DS_Store'},
            'pattern_blacklist': ['*.tmp', '*.log']
        }
        return FileService(config)
    
    def test_detect_and_redact_secrets_no_library(self, file_service):
        """Test de masquage des secrets sans la bibliothèque detect-secrets."""
        # Simuler l'absence de la bibliothèque
        with patch('services.file_service.HAS_DETECT_SECRETS', False):
            content = "api_key = 'sk-1234567890abcdef'"
            result_content, count = file_service.detect_and_redact_secrets(content, 'test.py')
            
            # Sans la bibliothèque, le contenu reste inchangé
            assert result_content == content
            assert count == 0
    
    @patch('services.file_service.HAS_DETECT_SECRETS', True)
    @patch('services.file_service.SecretsCollection')
    @patch('services.file_service.initialize_detect_secrets_plugins')
    def test_detect_and_redact_secrets_with_secrets(self, mock_init_plugins, mock_collection, file_service):
        """Test de masquage avec détection de secrets."""
        # Mock la détection de secrets
        mock_secrets = MagicMock()
        mock_secrets.data = {
            'test.py': [
                {'line_number': 2, 'type': 'API Key'}
            ]
        }
        mock_collection.return_value = mock_secrets
        mock_init_plugins.from_parser_builder.return_value = [MagicMock()]
        
        content = "# Configuration\napi_key = 'sk-1234567890abcdef'\nprint('hello')"
        result_content, count = file_service.detect_and_redact_secrets(content, 'test.py', 'mask')
        
        assert count == 1
        assert '[LINE CONTAINING SENSITIVE DATA: API Key]' in result_content
        assert "print('hello')" in result_content  # Ligne non masquée
    
    @patch('services.file_service.HAS_DETECT_SECRETS', True)
    @patch('services.file_service.SecretsCollection')
    @patch('services.file_service.initialize_detect_secrets_plugins')
    def test_detect_and_redact_secrets_remove_mode(self, mock_init_plugins, mock_collection, file_service):
        """Test de masquage en mode 'remove'."""
        mock_secrets = MagicMock()
        mock_secrets.data = {
            'test.py': [
                {'line_number': 1, 'type': 'API Key'}
            ]
        }
        mock_collection.return_value = mock_secrets
        mock_init_plugins.from_parser_builder.return_value = [MagicMock()]
        
        content = "api_key = 'secret'\nprint('hello')"
        result_content, count = file_service.detect_and_redact_secrets(content, 'test.py', 'remove')
        
        assert count == 1
        assert '[LINE REMOVED DUE TO DETECTED SECRET]' in result_content
        assert "print('hello')" in result_content
    
    def test_detect_and_redact_with_regex_api_keys(self, file_service):
        """Test de détection regex pour les clés API."""
        content = """
config = {
    'api_key': 'sk-1234567890abcdef1234567890abcdef',
    'debug': True
}
"""
        result_content, count = file_service.detect_and_redact_with_regex(content, 'config.py')
        
        assert count == 1
        assert '[LINE CONTAINING SENSITIVE DATA: api_key]' in result_content
        assert "'debug': True" in result_content  # Ligne non masquée
    
    def test_detect_and_redact_with_regex_aws_keys(self, file_service):
        """Test de détection regex pour les clés AWS."""
        content = """
AWS_ACCESS_KEY = 'AKIAIOSFODNN7EXAMPLE'
AWS_SECRET_KEY = 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY'
"""
        result_content, count = file_service.detect_and_redact_with_regex(content, 'aws_config.py')
        
        assert count == 2
        lines = result_content.splitlines()
        assert any('[LINE CONTAINING SENSITIVE DATA: aws_key]' in line for line in lines)
        assert any('[LINE CONTAINING SENSITIVE DATA: aws_secret]' in line for line in lines)
    
    def test_detect_and_redact_with_regex_url_auth(self, file_service):
        """Test de détection regex pour les URLs avec auth."""
        content = """
database_url = 'mongodb://user:password@localhost:27017/mydb'
api_endpoint = 'https://api.example.com/v1/data'
"""
        result_content, count = file_service.detect_and_redact_with_regex(content, 'config.py')
        
        assert count == 1
        assert '[LINE CONTAINING SENSITIVE DATA: connection_string]' in result_content
        assert 'api_endpoint' in result_content  # URL sans auth non masquée
    
    def test_detect_and_redact_with_regex_private_keys(self, file_service):
        """Test de détection regex pour les clés privées."""
        content = """
-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEA...
-----END RSA PRIVATE KEY-----

public_key = "ssh-rsa AAAAB3..."
"""
        result_content, count = file_service.detect_and_redact_with_regex(content, 'keys.pem')
        
        assert count == 1
        assert '[LINE CONTAINING SENSITIVE DATA: private_key_pem]' in result_content
        assert 'public_key' in result_content  # Clé publique non masquée
    
    def test_detect_and_redact_with_regex_no_secrets(self, file_service):
        """Test de détection regex sans secrets."""
        content = """
def calculate_sum(a, b):
    return a + b

result = calculate_sum(5, 10)
print(f"Result: {result}")
"""
        result_content, count = file_service.detect_and_redact_with_regex(content, 'math.py')
        
        assert count == 0
        assert result_content == content  # Contenu inchangé
    
    def test_detect_and_redact_with_regex_multiple_patterns(self, file_service):
        """Test avec plusieurs patterns sur la même ligne."""
        content = "connection = 'mysql://admin:secret123@db.server.com/database?api_key=abc123'"
        
        result_content, count = file_service.detect_and_redact_with_regex(content, 'config.py')
        
        # Devrait détecter au moins un pattern (connection_string ou api_key)
        assert count == 1
        assert '[LINE CONTAINING SENSITIVE DATA' in result_content
    
    def test_state_management(self, file_service):
        """Test de la gestion de l'état interne."""
        # État initial
        assert file_service.file_cache == []
        assert file_service.current_directory is None
        
        # Simuler un scan qui met à jour l'état
        test_files = [
            {'absolute_path': '/test/file1.py', 'relative_path': 'file1.py', 'name': 'file1.py', 'size': 100},
            {'absolute_path': '/test/file2.py', 'relative_path': 'file2.py', 'name': 'file2.py', 'size': 200}
        ]
        
        # Mettre à jour l'état directement (normalement fait par scan_local_directory)
        file_service.file_cache = test_files
        file_service.current_directory = '/test'
        
        # Vérifier que l'état est bien conservé
        assert len(file_service.file_cache) == 2
        assert file_service.current_directory == '/test'
    
    @patch('builtins.open', new_callable=mock_open, read_data='print("Hello")')
    def test_get_file_content_with_state(self, mock_file, file_service):
        """Test de get_file_content utilisant l'état interne."""
        # Configurer l'état interne
        file_service.current_directory = '/test'
        file_service.file_cache = [
            {'absolute_path': '/test/hello.py', 'relative_path': 'hello.py', 'name': 'hello.py', 'size': 50}
        ]
        
        # Appeler sans paramètres (utilise l'état interne)
        result = file_service.get_file_content('hello.py')
        
        assert result['success'] == True
        assert result['content'] == 'print("Hello")'
        assert result['path'] == 'hello.py'
    
    def test_get_file_contents_batch_with_state(self, file_service):
        """Test de get_file_contents_batch utilisant l'état interne."""
        # Configurer l'état interne
        file_service.current_directory = '/test'
        file_service.file_cache = []
        
        # Appeler sans paramètres (utilise l'état interne)
        result = file_service.get_file_contents_batch(['file1.py', 'file2.py'])
        
        # Devrait échouer car les fichiers ne sont pas dans le cache
        assert result['success'] == True
        assert len(result['failed_files']) == 2