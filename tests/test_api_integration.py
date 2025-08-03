import pytest
from unittest.mock import patch, MagicMock, Mock
import os
import json
from pathlib import Path
from main_desktop import Api, load_service_configs


class TestApiIntegration:
    """Tests d'intégration pour la classe Api (façade)."""
    
    @pytest.fixture
    def api_instance(self):
        """Fixture pour créer une instance Api avec configuration de test."""
        with patch('main_desktop.webview.create_window') as mock_window:
            mock_window.return_value = MagicMock()
            api = Api()
            yield api
    
    @pytest.fixture
    def temp_project(self, tmp_path):
        """Crée une structure de projet temporaire pour les tests."""
        # Créer la structure
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()
        
        # Fichiers Python
        (project_dir / "main.py").write_text('''
def main():
    print("Hello World")
    api_key = "sk-1234567890abcdef"  # Secret à masquer

if __name__ == "__main__":
    main()
''')
        
        # README
        (project_dir / "README.md").write_text('''
# Test Project

This is a test project for integration testing.
''')
        
        # Fichier de configuration
        (project_dir / "config.json").write_text('''
{
    "database": {
        "host": "localhost",
        "password": "secret123"
    }
}
''')
        
        # .gitignore
        (project_dir / ".gitignore").write_text('''
*.pyc
__pycache__/
.env
build/
''')
        
        # Créer un sous-dossier avec des fichiers
        utils_dir = project_dir / "utils"
        utils_dir.mkdir()
        (utils_dir / "helper.py").write_text('''
def format_data(data):
    return f"Formatted: {data}"
''')
        
        # Fichier binaire (devrait être ignoré)
        (project_dir / "binary.exe").write_bytes(b'\x00\x01\x02\x03')
        
        # Fichier dans __pycache__ (devrait être ignoré)
        pycache_dir = project_dir / "__pycache__"
        pycache_dir.mkdir()
        (pycache_dir / "main.cpython-39.pyc").write_bytes(b'\x00\x01')
        
        return str(project_dir)
    
    def test_scan_local_directory_integration(self, api_instance, temp_project):
        """Test complet du scan de répertoire."""
        result = api_instance.scan_local_directory(temp_project)
        
        assert result['success'] == True
        assert result['directory'] == temp_project
        
        # Vérifier la structure de la réponse frontend
        response = result['response_for_frontend']
        assert response['success'] == True
        assert response['directory'] == temp_project
        assert 'files' in response
        assert 'count' in response
        assert 'debug' in response
        
        # Vérifier que les fichiers appropriés sont trouvés
        files = response['files']
        file_paths = [f['path'] for f in files]
        
        # Ces fichiers devraient être présents
        assert 'main.py' in file_paths
        assert 'README.md' in file_paths
        assert 'config.json' in file_paths
        assert 'utils/helper.py' in file_paths
        
        # Ces fichiers ne devraient PAS être présents (gitignore ou binaires)
        assert 'binary.exe' not in file_paths
        assert '__pycache__/main.cpython-39.pyc' not in file_paths
        
        # Vérifier le cache interne
        assert hasattr(api_instance.file_service, 'file_cache')
        assert len(api_instance.file_service.file_cache) > 0
        assert api_instance.file_service.current_directory == temp_project
    
    def test_get_file_content_integration(self, api_instance, temp_project):
        """Test de récupération du contenu d'un fichier."""
        # D'abord scanner le répertoire
        api_instance.scan_local_directory(temp_project)
        
        # Récupérer le contenu de main.py
        result = api_instance.get_file_content('main.py')
        
        assert result['success'] == True
        assert 'content' in result
        assert 'def main():' in result['content']
        assert 'Hello World' in result['content']
    
    def test_get_file_contents_batch_integration(self, api_instance, temp_project):
        """Test de récupération batch avec détection de secrets."""
        # Scanner d'abord
        api_instance.scan_local_directory(temp_project)
        
        # Récupérer plusieurs fichiers
        selected_files = ['main.py', 'config.json', 'README.md']
        result = api_instance.get_file_contents_batch(selected_files)
        
        assert result['success'] == True
        assert 'file_contents' in result
        assert 'context' in result
        assert 'stats' in result
        
        # Vérifier que tous les fichiers sont récupérés
        file_contents = result['file_contents']
        assert len(file_contents) == 3
        
        # Vérifier la détection de secrets
        context = result['context']
        # Le secret dans main.py devrait être masqué
        assert 'sk-1234567890abcdef' not in context
        assert '[LINE CONTAINING SENSITIVE DATA' in context or 'MASKED' in context
        
        # Le mot de passe dans config.json devrait aussi être masqué
        assert 'secret123' not in context
    
    def test_run_git_diff_integration(self, api_instance, temp_project):
        """Test de l'exécution de git diff."""
        # Initialiser un repo git
        os.system(f'cd "{temp_project}" && git init')
        os.system(f'cd "{temp_project}" && git add .')
        os.system(f'cd "{temp_project}" && git commit -m "Initial commit"')
        
        # Modifier un fichier
        with open(os.path.join(temp_project, 'main.py'), 'a') as f:
            f.write('\n# New comment\n')
        
        # Exécuter git diff
        result = api_instance.run_git_diff(temp_project)
        
        assert result['success'] == True
        assert 'diff' in result
        # Le diff devrait contenir la nouvelle ligne
        assert '# New comment' in result['diff'] or result['diff'] == ''
    
    @patch('main_desktop.requests.post')
    def test_send_to_llm_stream_integration(self, mock_post, api_instance):
        """Test de l'envoi en streaming vers le LLM."""
        # Mock la réponse streaming
        mock_response = MagicMock()
        mock_response.iter_lines.return_value = [
            b'data: {"choices":[{"delta":{"content":"Hello"}}]}',
            b'data: {"choices":[{"delta":{"content":" World"}}]}',
            b'data: [DONE]'
        ]
        mock_post.return_value = mock_response
        
        # Configurer le streaming
        api_instance.llm_service.config['stream_response'] = True
        
        # Callbacks pour capturer les événements
        chunks = []
        started = False
        ended = False
        
        def on_start():
            nonlocal started
            started = True
        
        def on_chunk(chunk):
            chunks.append(chunk)
        
        def on_end(total):
            nonlocal ended
            ended = True
        
        # Envoyer au LLM
        chat_history = [
            {'role': 'user', 'content': 'Hello'}
        ]
        
        api_instance.send_to_llm_stream(
            chat_history,
            on_start=on_start,
            on_chunk=on_chunk,
            on_end=on_end
        )
        
        # Vérifier les callbacks
        assert started == True
        assert chunks == ['Hello', ' World']
        assert ended == True
    
    def test_error_handling_integration(self, api_instance):
        """Test de la gestion d'erreur à travers la façade."""
        # Test avec un répertoire invalide
        result = api_instance.scan_local_directory('/nonexistent/path')
        assert result['success'] == False
        assert 'error' in result
        
        # Test de récupération de fichier sans scan préalable
        api_instance.file_service.current_directory = None
        result = api_instance.get_file_content('any.py')
        assert result['success'] == False
        assert 'répertoire' in result['error'].lower()
    
    def test_full_workflow_integration(self, api_instance, temp_project):
        """Test d'un workflow complet: scan -> sélection -> contexte."""
        # 1. Scanner le répertoire
        scan_result = api_instance.scan_local_directory(temp_project)
        assert scan_result['success'] == True
        
        # 2. Sélectionner des fichiers
        selected_files = ['main.py', 'README.md', 'utils/helper.py']
        
        # 3. Récupérer les contenus en batch
        batch_result = api_instance.get_file_contents_batch(selected_files)
        assert batch_result['success'] == True
        
        # 4. Vérifier le contexte généré
        context = batch_result['context']
        stats = batch_result['stats']
        
        # Le contexte devrait contenir l'arbre des fichiers
        assert 'Contexte du projet' in context
        assert 'Arbre des fichiers' in context
        assert 'main.py' in context
        assert 'README.md' in context
        assert 'utils/helper.py' in context
        
        # Vérifier les statistiques
        assert stats['files_count'] == 3
        assert stats['total_chars'] > 0
        assert stats['estimated_tokens'] > 0
        assert 'model_compatibility' in stats
        
        # Vérifier le masquage des secrets
        assert 'sk-1234567890abcdef' not in context
        assert stats.get('secrets_masked', 0) >= 1