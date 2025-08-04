import pytest
from unittest.mock import patch, MagicMock, Mock, mock_open
import os
from pathlib import Path
import pathspec
from services.file_service import FileService, FileServiceException


class TestFileService:
    """Tests unitaires pour FileService."""
    
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
    
    @pytest.fixture
    def mock_file_structure(self):
        """Structure de fichiers simulée pour les tests."""
        return [
            {'absolute_path': '/project/main.py', 'relative_path': 'main.py', 'name': 'main.py', 'size': 1024},
            {'absolute_path': '/project/README.md', 'relative_path': 'README.md', 'name': 'README.md', 'size': 512},
            {'absolute_path': '/project/test.log', 'relative_path': 'test.log', 'name': 'test.log', 'size': 256},
            {'absolute_path': '/project/binary.exe', 'relative_path': 'binary.exe', 'name': 'binary.exe', 'size': 2048},
        ]
    
    def test_init(self):
        """Test de l'initialisation du service."""
        config = {'debug': True}
        service = FileService(config)
        assert service.config == config
        assert service.gitignore_cache == {}
    
    def test_scan_local_directory_invalid_path(self, file_service):
        """Test avec un chemin invalide."""
        result = file_service.scan_local_directory('')
        assert result['success'] == False
        assert 'invalide' in result['error']
        
        result = file_service.scan_local_directory('/non/existent/path')
        assert result['success'] == False
    
    @patch('os.path.exists')
    @patch.object(FileService, '_load_gitignore_spec')
    @patch.object(FileService, '_scan_files_with_gitignore')
    @patch.object(FileService, '_filter_binary_files')
    def test_scan_local_directory_success(self, mock_filter, mock_scan, mock_gitignore, 
                                        mock_exists, file_service, mock_file_structure):
        """Test d'un scan réussi."""
        mock_exists.return_value = True
        mock_gitignore.return_value = MagicMock()
        mock_scan.return_value = mock_file_structure
        mock_filter.return_value = mock_file_structure[:2]  # Garde seulement les 2 premiers
        
        result = file_service.scan_local_directory('/project')
        
        assert result['success'] == True
        assert result['directory'] == '/project'
        assert len(result['file_cache']) == 2
        assert result['response_for_frontend']['success'] == True
        assert result['response_for_frontend']['count'] == 2
        assert 'largest_files' in result['response_for_frontend']
        assert len(result['response_for_frontend']['largest_files']) == 2  # Seulement 2 fichiers dans le mock
    
    def test_get_file_content_no_directory(self, file_service):
        """Test sans répertoire spécifié."""
        result = file_service.get_file_content('test.py', '', [])
        assert result['success'] == False
        assert 'Aucun répertoire' in result['error']
    
    def test_get_file_content_file_not_found(self, file_service):
        """Test avec fichier non trouvé."""
        result = file_service.get_file_content('missing.py', '/project', [])
        assert result['success'] == False
        assert 'non trouvé' in result['error']
    
    @patch('builtins.open', new_callable=mock_open, read_data='print("Hello World")')
    def test_get_file_content_success(self, mock_file, file_service, mock_file_structure):
        """Test de lecture réussie d'un fichier."""
        file_cache = [mock_file_structure[0]]  # main.py
        result = file_service.get_file_content('main.py', '/project', file_cache)
        
        assert result['success'] == True
        assert result['content'] == 'print("Hello World")'
        assert result['path'] == 'main.py'
        assert result['size'] == 1024
    
    def test_get_file_contents_batch_no_files(self, file_service):
        """Test sans fichiers sélectionnés."""
        result = file_service.get_file_contents_batch([], '/project', [])
        assert result['success'] == False
        assert 'Aucun fichier' in result['error']
    
    @patch.object(FileService, 'get_file_content')
    def test_get_file_contents_batch_success(self, mock_get_content, file_service):
        """Test de récupération batch réussie."""
        mock_get_content.side_effect = [
            {'success': True, 'content': 'print("Hello")', 'size': 14},
            {'success': True, 'content': '# README', 'size': 8},
            {'success': False, 'error': 'Fichier non trouvé'}
        ]
        
        result = file_service.get_file_contents_batch(
            ['main.py', 'README.md', 'missing.txt'], 
            '/project',
            []
        )
        
        assert result['success'] == True
        assert len(result['file_contents']) == 2
        assert len(result['failed_files']) == 1
        assert result['stats']['requested'] == 3
        assert result['stats']['successful'] == 2
        assert result['stats']['failed'] == 1
    
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data='*.pyc\n__pycache__/\ntest.log')
    def test_load_gitignore_spec(self, mock_file, mock_exists, file_service):
        """Test du chargement des règles gitignore."""
        mock_exists.return_value = True
        
        spec = file_service._load_gitignore_spec('/project')
        
        # Vérifier que les patterns par défaut et custom sont chargés
        assert spec is not None
        # Vérifier le cache
        assert '/project' in file_service.gitignore_cache
    
    @patch('os.path.exists')
    def test_load_gitignore_spec_no_file(self, mock_exists, file_service):
        """Test sans fichier .gitignore."""
        mock_exists.return_value = False
        
        spec = file_service._load_gitignore_spec('/project')
        
        # Devrait retourner seulement les patterns par défaut
        assert spec is not None
    
    def test_scan_files_with_gitignore(self, file_service, tmp_path):
        """Test du scan avec gitignore (utilise pyfakefs ou tmp_path)."""
        # Créer une structure de test
        (tmp_path / 'main.py').write_text('content')
        (tmp_path / 'test.pyc').write_text('binary')
        (tmp_path / '.git').mkdir()
        (tmp_path / '.git' / 'config').write_text('git config')
        
        # Mock gitignore spec
        mock_spec = MagicMock()
        mock_spec.match_file.side_effect = lambda path: path.endswith('.pyc') or '.git' in path
        
        files = file_service._scan_files_with_gitignore(str(tmp_path), mock_spec)
        
        # Devrait trouver seulement main.py
        assert len(files) == 1
        assert files[0]['name'] == 'main.py'
    
    def test_filter_binary_files(self, file_service, mock_file_structure):
        """Test du filtrage des fichiers binaires."""
        # Le mock_file_structure contient .py, .md, .log, .exe
        filtered = file_service._filter_binary_files(mock_file_structure)
        
        # .exe devrait être filtré (blacklist)
        # .log devrait être filtré (pattern blacklist)
        # .md devrait passer (whitelist)
        # .py devrait passer après test de contenu
        
        assert len(filtered) <= 2
        assert not any(f['name'].endswith('.exe') for f in filtered)
        assert not any(f['name'].endswith('.log') for f in filtered)
    
    @patch('builtins.open')
    def test_filter_binary_files_content_check(self, mock_open_func, file_service):
        """Test du filtrage par contenu."""
        files = [
            {'absolute_path': '/test.dat', 'relative_path': 'test.dat', 'name': 'test.dat', 'size': 100}
        ]
        
        # Simuler un fichier avec octets nuls (binaire)
        mock_open_func.return_value.__enter__.return_value.read.return_value = b'Hello\x00World'
        
        filtered = file_service._filter_binary_files(files)
        assert len(filtered) == 0  # Devrait être filtré
        
        # Simuler un fichier texte valide
        mock_open_func.return_value.__enter__.return_value.read.return_value = b'Hello World'
        
        filtered = file_service._filter_binary_files(files)
        assert len(filtered) == 1  # Devrait passer
    
    
    @patch('os.path.exists')
    @patch.object(FileService, '_load_gitignore_spec')
    def test_scan_error_handling(self, mock_gitignore, mock_exists, file_service):
        """Test de gestion d'erreur lors du scan."""
        mock_exists.return_value = True
        mock_gitignore.side_effect = Exception("Test error")
        
        with pytest.raises(FileServiceException):
            file_service.scan_local_directory('/project')