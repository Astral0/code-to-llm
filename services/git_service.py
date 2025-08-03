import subprocess
import logging
from typing import Dict, Any, Optional
from .base_service import BaseService
from .exceptions import GitServiceException


class GitService(BaseService):
    """Service pour gérer les opérations Git."""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """
        Initialise le service Git.
        
        Args:
            config: Dictionnaire de configuration contenant 'executable_path'
            logger: Logger optionnel
        """
        super().__init__(config, logger)
        self._git_path = config.get('executable_path', 'git')
        
    def validate_config(self):
        """Valide la configuration du service Git."""
        # Pas de validation spécifique requise pour l'instant
        pass
    
    def run_git_diff(self, directory_path: str) -> Dict[str, Any]:
        """
        Exécute git diff HEAD dans le répertoire spécifié.
        
        Args:
            directory_path: Le répertoire où exécuter git diff
            
        Returns:
            Dict contenant soit 'diff' avec le résultat, soit 'error' avec le message d'erreur
            
        Raises:
            GitServiceException: En cas d'erreur lors de l'exécution
        """
        try:
            # Vérifier que le répertoire est fourni
            if not directory_path:
                return {'error': 'Aucun répertoire de travail spécifié'}
            
            # Construire la commande
            git_command = [self._git_path, 'diff', 'HEAD']
            self.logger.info(f"Exécution de la commande: {' '.join(git_command)}")
            self.logger.info(f"Dans le répertoire: {directory_path}")
            
            # Exécuter git diff HEAD
            result = subprocess.run(
                git_command,
                cwd=directory_path,
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
            
            if result.returncode != 0:
                # Vérifier si c'est parce que ce n'est pas un repo git
                if "not a git repository" in result.stderr.lower():
                    self.logger.warning(f"Le répertoire {directory_path} n'est pas un dépôt git")
                    return {'error': 'Le répertoire actuel n\'est pas un dépôt git'}
                else:
                    self.logger.error(f"Erreur git: {result.stderr}")
                    return {'error': f'Erreur git: {result.stderr}'}
            
            diff_size = len(result.stdout)
            diff_lines = result.stdout.count('\n')
            self.logger.info(f"Git diff exécuté avec succès: {diff_size} caractères, {diff_lines} lignes")
            
            return {'diff': result.stdout}
            
        except FileNotFoundError:
            error_msg = 'Git n\'est pas installé ou le chemin est incorrect. Vérifiez config.ini'
            self.logger.error(error_msg)
            raise GitServiceException(error_msg)
        except subprocess.CalledProcessError as e:
            error_msg = f"Erreur lors de l'exécution de git diff: {e}"
            self.logger.error(error_msg)
            raise GitServiceException(error_msg)
        except Exception as e:
            error_msg = f"Erreur inattendue lors de l'exécution de git diff: {str(e)}"
            self.logger.error(error_msg)
            raise GitServiceException(error_msg)