import pytest
from unittest.mock import patch, MagicMock
import subprocess
from services.git_service import GitService, GitServiceException


class TestGitService:
    """Tests unitaires pour GitService."""
    
    @pytest.fixture
    def git_service(self):
        """Fixture pour créer une instance de GitService."""
        config = {
            'git_path': 'git'
        }
        return GitService(config)
    
    def test_init(self):
        """Test de l'initialisation du service."""
        config = {'git_path': '/usr/bin/git'}
        service = GitService(config)
        assert service.config == config
        assert service._git_path == '/usr/bin/git'
    
    def test_validate_config_missing_git_path(self):
        """Test de validation avec git_path manquant."""
        config = {}
        with pytest.raises(ValueError, match="git_path manquant"):
            GitService(config)
    
    @patch('subprocess.run')
    def test_run_git_diff_success(self, mock_run, git_service):
        """Test d'exécution réussie de git diff --staged."""
        # Mock la réponse de subprocess
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "diff --git a/file.py b/file.py\n+added line"
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        result = git_service.run_git_diff('/path/to/repo')
        
        assert result['success'] == True
        assert result['diff'] == "diff --git a/file.py b/file.py\n+added line"
        
        # Vérifier l'appel subprocess avec --staged
        mock_run.assert_called_once_with(
            ['git', 'diff', '--staged'],
            cwd='/path/to/repo',
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
    
    @patch('subprocess.run')
    def test_run_git_diff_no_changes(self, mock_run, git_service):
        """Test git diff sans changements."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        result = git_service.run_git_diff('/path/to/repo')
        
        assert result['success'] == True
        assert result['diff'] == ""
        assert result.get('message') == "Aucune modification détectée"
    
    @patch('subprocess.run')
    def test_run_git_diff_not_git_repo(self, mock_run, git_service):
        """Test git diff dans un dossier non-git."""
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stdout = ""
        mock_result.stderr = "fatal: not a git repository"
        mock_run.return_value = mock_result
        
        with pytest.raises(GitServiceException, match="n'est pas un dépôt Git"):
            git_service.run_git_diff('/not/a/git/repo')
    
    @patch('subprocess.run')
    def test_run_git_diff_error(self, mock_run, git_service):
        """Test git diff avec erreur."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error: something went wrong"
        mock_run.return_value = mock_result
        
        with pytest.raises(GitServiceException, match="Erreur lors de l'exécution de git diff"):
            git_service.run_git_diff('/path/to/repo')
    
    @patch('subprocess.run')
    def test_run_git_diff_subprocess_error(self, mock_run, git_service):
        """Test git diff avec erreur subprocess."""
        mock_run.side_effect = subprocess.SubprocessError("Command failed")
        
        with pytest.raises(GitServiceException, match="Erreur lors de l'exécution de git"):
            git_service.run_git_diff('/path/to/repo')
    
    @patch('subprocess.run')
    def test_run_git_diff_file_not_found(self, mock_run, git_service):
        """Test git diff avec git non trouvé."""
        mock_run.side_effect = FileNotFoundError("git not found")
        
        with pytest.raises(GitServiceException, match="Erreur lors de l'exécution de git"):
            git_service.run_git_diff('/path/to/repo')
    
    @patch('subprocess.run')
    def test_run_git_diff_with_warning(self, mock_run, git_service):
        """Test git diff avec warning non bloquant."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "diff --git a/file.py b/file.py\n+added line"
        mock_result.stderr = "warning: LF will be replaced by CRLF"
        mock_run.return_value = mock_result
        
        result = git_service.run_git_diff('/path/to/repo')
        
        # Les warnings ne doivent pas empêcher le succès
        assert result['success'] == True
        assert result['diff'] == "diff --git a/file.py b/file.py\n+added line"
    
    def test_git_path_configuration(self):
        """Test de différentes configurations de chemin git."""
        # Chemin absolu
        config1 = {'git_path': '/usr/local/bin/git'}
        service1 = GitService(config1)
        assert service1._git_path == '/usr/local/bin/git'
        
        # Chemin relatif
        config2 = {'git_path': 'git'}
        service2 = GitService(config2)
        assert service2._git_path == 'git'
        
        # Chemin Windows
        config3 = {'git_path': 'C:\\Program Files\\Git\\bin\\git.exe'}
        service3 = GitService(config3)
        assert service3._git_path == 'C:\\Program Files\\Git\\bin\\git.exe'