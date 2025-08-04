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
        Exécute git diff --staged dans le répertoire spécifié.
        
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
                self.logger.error("Aucun répertoire de travail spécifié")
                return {'error': 'Aucun répertoire de travail spécifié'}
            
            # Vérifier que le répertoire existe
            import os
            if not os.path.exists(directory_path):
                self.logger.error(f"Le répertoire n'existe pas: {directory_path}")
                return {'error': f"Le répertoire n'existe pas: {directory_path}"}
            
            # Construire la commande
            git_command = [self._git_path, 'diff', '--staged']
            print(f"=== DÉBUT DEBUG GIT DIFF ===")
            print(f"Exécution de la commande: {' '.join(git_command)}")
            print(f"Dans le répertoire: {directory_path}")
            print(f"Git path utilisé: {self._git_path}")
            self.logger.info(f"Exécution de la commande: {' '.join(git_command)}")
            self.logger.info(f"Dans le répertoire: {directory_path}")
            
            # Exécuter git diff
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
            print(f"Retour de git diff: returncode={result.returncode}")
            print(f"Stdout: {diff_size} caractères, {diff_lines} lignes")
            print(f"Stderr: {result.stderr}")
            self.logger.info(f"Git diff exécuté avec succès: {diff_size} caractères, {diff_lines} lignes")
            
            # Debug: afficher les 200 premiers caractères du diff
            if result.stdout:
                preview = result.stdout[:200] + '...' if len(result.stdout) > 200 else result.stdout
                self.logger.info(f"Aperçu du diff: {preview}")
            else:
                self.logger.warning("Le diff est vide!")
                
                # Exécuter git status pour comprendre l'état
                status_command = [self._git_path, 'status', '--porcelain']
                print(f"Exécution de git status pour debug: {' '.join(status_command)}")
                status_result = subprocess.run(
                    status_command,
                    cwd=directory_path,
                    capture_output=True,
                    text=True,
                    encoding='utf-8'
                )
                print(f"Git status returncode: {status_result.returncode}")
                print(f"Git status stdout:\n{status_result.stdout}")
                print(f"Git status stderr: {status_result.stderr}")
                
                # Vérifier s'il y a des fichiers stagés
                staged_command = [self._git_path, 'diff', '--staged', '--name-only']
                print(f"Vérification des fichiers stagés: {' '.join(staged_command)}")
                staged_result = subprocess.run(
                    staged_command,
                    cwd=directory_path,
                    capture_output=True,
                    text=True,
                    encoding='utf-8'
                )
                print(f"Fichiers stagés returncode: {staged_result.returncode}")
                print(f"Fichiers stagés:\n{staged_result.stdout}")
                print(f"Fichiers stagés stderr: {staged_result.stderr}")
            
            print(f"=== FIN DEBUG GIT DIFF ===")
            
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