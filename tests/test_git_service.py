import pytest
from unittest.mock import patch, MagicMock, Mock
import subprocess
from services.git_service import GitService, GitServiceException


class TestGitService:
    """Tests unitaires pour GitService."""
    
    @pytest.fixture
    def git_service(self):
        """Fixture pour créer une instance de GitService."""
        config = {'debug': False}
        return GitService(config)
    
    @pytest.fixture
    def mock_subprocess_run(self):
        """Fixture pour mocker subprocess.run."""
        with patch('subprocess.run') as mock_run:
            yield mock_run
    
    def test_init(self):
        """Test de l'initialisation du service."""
        config = {'debug': True}
        service = GitService(config)
        assert service.config == config
        assert service._git_path in ['git', 'C:\\Program Files\\Git\\bin\\git.exe']  # Peut varier selon config.ini
    
    def test_git_path_from_config(self):
        """Test de la récupération du chemin git depuis la config injectée."""
        config = {'executable_path': '/custom/path/to/git'}
        service = GitService(config)
        
        assert service._git_path == '/custom/path/to/git'
    
    def test_run_git_diff_no_directory(self, git_service):
        """Test avec aucun répertoire spécifié."""
        result = git_service.run_git_diff('')
        assert 'error' in result
        assert result['error'] == 'Aucun répertoire de travail spécifié'
    
    def test_run_git_diff_success(self, git_service, mock_subprocess_run):
        """Test d'un git diff réussi."""
        # Mock de la sortie de git diff
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "diff --git a/file.txt b/file.txt\n+Added line"
        mock_result.stderr = ""
        mock_subprocess_run.return_value = mock_result
        
        result = git_service.run_git_diff('/path/to/repo')
        
        assert 'diff' in result
        assert result['diff'] == mock_result.stdout
        mock_subprocess_run.assert_called_once_with(
            [git_service._git_path, 'diff', 'HEAD'],
            cwd='/path/to/repo',
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
    
    def test_run_git_diff_not_git_repository(self, git_service, mock_subprocess_run):
        """Test dans un répertoire qui n'est pas un dépôt git."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "fatal: not a git repository"
        mock_subprocess_run.return_value = mock_result
        
        result = git_service.run_git_diff('/path/to/non-repo')
        
        assert 'error' in result
        assert result['error'] == 'Le répertoire actuel n\'est pas un dépôt git'
    
    def test_run_git_diff_other_git_error(self, git_service, mock_subprocess_run):
        """Test avec une autre erreur git."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "fatal: bad revision 'HEAD'"
        mock_subprocess_run.return_value = mock_result
        
        result = git_service.run_git_diff('/path/to/repo')
        
        assert 'error' in result
        assert 'Erreur git:' in result['error']
        assert 'bad revision' in result['error']
    
    def test_run_git_diff_git_not_found(self, git_service, mock_subprocess_run):
        """Test quand git n'est pas installé."""
        mock_subprocess_run.side_effect = FileNotFoundError("git not found")
        
        with pytest.raises(GitServiceException) as exc_info:
            git_service.run_git_diff('/path/to/repo')
        
        assert "Git n'est pas installé" in str(exc_info.value)
    
    def test_run_git_diff_subprocess_error(self, git_service, mock_subprocess_run):
        """Test avec une CalledProcessError."""
        mock_subprocess_run.side_effect = subprocess.CalledProcessError(
            returncode=128,
            cmd=['git', 'diff', 'HEAD'],
            stderr="Some git error"
        )
        
        with pytest.raises(GitServiceException) as exc_info:
            git_service.run_git_diff('/path/to/repo')
        
        assert "Erreur lors de l'exécution de git diff" in str(exc_info.value)
    
    def test_run_git_diff_unexpected_error(self, git_service, mock_subprocess_run):
        """Test avec une erreur inattendue."""
        mock_subprocess_run.side_effect = Exception("Unexpected error")
        
        with pytest.raises(GitServiceException) as exc_info:
            git_service.run_git_diff('/path/to/repo')
        
        assert "Erreur inattendue" in str(exc_info.value)
    
    def test_run_git_diff_empty_diff(self, git_service, mock_subprocess_run):
        """Test avec un diff vide (pas de changements)."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_subprocess_run.return_value = mock_result
        
        result = git_service.run_git_diff('/path/to/repo')
        
        assert 'diff' in result
        assert result['diff'] == ""
    
    @patch('logging.Logger')
    def test_logging(self, mock_logger, mock_subprocess_run):
        """Test que le logging fonctionne correctement."""
        service = GitService({}, logger=mock_logger)
        
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "some diff"
        mock_subprocess_run.return_value = mock_result
        
        service.run_git_diff('/path/to/repo')
        
        # Vérifier que les logs sont appelés
        assert mock_logger.info.called
        assert mock_logger.error.called == False