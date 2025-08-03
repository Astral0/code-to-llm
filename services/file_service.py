import os
import logging
import pathspec
from pathspec.patterns import GitWildMatchPattern
from pathlib import Path
import fnmatch
from typing import Dict, Any, Optional, List
from .base_service import BaseService
from .exceptions import FileServiceException


class FileService(BaseService):
    """Service pour gérer les opérations sur les fichiers et répertoires."""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """
        Initialise le service de fichiers.
        
        Args:
            config: Dictionnaire de configuration
            logger: Logger optionnel
        """
        super().__init__(config, logger)
        self.gitignore_cache = {}  # Cache pour les specs gitignore
        
    def validate_config(self):
        """Valide la configuration du service."""
        # Pas de validation spécifique requise pour l'instant
        pass
    
    def scan_local_directory(self, directory_path: str) -> Dict[str, Any]:
        """
        Scanne un répertoire local et applique les règles .gitignore.
        
        Args:
            directory_path: Le chemin du répertoire à scanner
            
        Returns:
            Dict contenant les informations du scan
        """
        try:
            if not directory_path or not os.path.exists(directory_path):
                error_msg = f"Répertoire invalide: {directory_path}"
                self.logger.error(error_msg)
                return {
                    'success': False,
                    'error': error_msg,
                    'response_for_frontend': {'success': False, 'error': error_msg}
                }
            
            self.logger.info(f"Début du scan local du répertoire: {directory_path}")
            
            # Charger les règles .gitignore
            gitignore_spec = self._load_gitignore_spec(directory_path)
            
            # Scanner les fichiers
            scanned_files = self._scan_files_with_gitignore(directory_path, gitignore_spec)
            
            # Filtrer les fichiers binaires
            filtered_files = self._filter_binary_files(scanned_files)
            
            # Préparer la structure pour l'affichage
            file_tree_data = [{"path": f["relative_path"], "size": f["size"]} for f in filtered_files]
            
            self.logger.info(f"Scan terminé: {len(filtered_files)} fichiers trouvés")
            
            return {
                'success': True,
                'directory': directory_path,
                'file_cache': filtered_files,
                'response_for_frontend': {
                    'success': True,
                    'files': file_tree_data,
                    'count': len(filtered_files),
                    'directory': directory_path,
                    'total_files': len(filtered_files),
                    'debug': {
                        'gitignore_patterns_count': len(gitignore_spec.patterns) if hasattr(gitignore_spec, 'patterns') else 0
                    }
                }
            }
            
        except Exception as e:
            error_msg = f"Erreur lors du scan du répertoire: {str(e)}"
            self.logger.error(error_msg)
            raise FileServiceException(error_msg)
    
    def get_file_content(self, relative_path: str, current_directory: str, 
                        file_cache: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Récupère le contenu d'un fichier.
        
        Args:
            relative_path: Le chemin relatif du fichier
            current_directory: Le répertoire de base
            file_cache: Le cache des fichiers scannés
            
        Returns:
            Dict contenant le contenu du fichier
        """
        try:
            if not current_directory:
                return {'success': False, 'error': 'Aucun répertoire spécifié'}
            
            # Trouver le fichier dans le cache
            file_info = next((f for f in file_cache if f['relative_path'] == relative_path), None)
            
            if not file_info:
                return {'success': False, 'error': f'Fichier non trouvé: {relative_path}'}
            
            # Lire le contenu
            with open(file_info['absolute_path'], 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            return {
                'success': True,
                'content': content,
                'path': relative_path,
                'size': file_info['size']
            }
            
        except Exception as e:
            error_msg = f"Erreur lors de la lecture du fichier {relative_path}: {str(e)}"
            self.logger.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def get_file_contents_batch(self, selected_files: List[str], current_directory: str,
                              file_cache: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Récupère le contenu de plusieurs fichiers en batch.
        
        Args:
            selected_files: Liste des fichiers sélectionnés
            current_directory: Le répertoire de base
            file_cache: Le cache des fichiers
            
        Returns:
            Dict contenant les contenus des fichiers et les statistiques
        """
        try:
            if not selected_files:
                return {'success': False, 'error': 'Aucun fichier sélectionné'}
            
            file_contents = []
            failed_files = []
            
            # Récupérer le contenu de chaque fichier
            for file_path in selected_files:
                file_result = self.get_file_content(file_path, current_directory, file_cache)
                if file_result['success']:
                    content = file_result['content']
                    file_contents.append({
                        'path': file_path,
                        'content': content,
                        'size': len(content)
                    })
                else:
                    failed_files.append({
                        'path': file_path,
                        'error': file_result.get('error', 'Erreur inconnue')
                    })
                    self.logger.warning(f"Échec lecture fichier: {file_path}")
            
            return {
                'success': True,
                'file_contents': file_contents,
                'failed_files': failed_files,
                'stats': {
                    'requested': len(selected_files),
                    'successful': len(file_contents),
                    'failed': len(failed_files)
                }
            }
            
        except Exception as e:
            error_msg = f"Erreur lors de la récupération des contenus: {str(e)}"
            self.logger.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def _load_gitignore_spec(self, directory_path: str) -> pathspec.PathSpec:
        """Charge les règles .gitignore depuis le répertoire."""
        try:
            # Vérifier le cache
            if directory_path in self.gitignore_cache:
                return self.gitignore_cache[directory_path]
            
            gitignore_path = os.path.join(directory_path, '.gitignore')
            patterns = ['.git/', '__pycache__/', 'node_modules/', '.vscode/', '.idea/']
            
            if os.path.exists(gitignore_path):
                with open(gitignore_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                    
                # Nettoyer les lignes
                cleaned_lines = [
                    line.strip() for line in lines 
                    if line.strip() and not line.strip().startswith('#')
                ]
                patterns.extend(cleaned_lines)
                self.logger.info(f"Chargé {len(cleaned_lines)} règles depuis .gitignore")
            else:
                self.logger.info("Aucun .gitignore trouvé, utilisation des règles par défaut")
            
            spec = pathspec.PathSpec.from_lines(GitWildMatchPattern, patterns)
            self.gitignore_cache[directory_path] = spec
            return spec
            
        except Exception as e:
            self.logger.warning(f"Erreur lors du chargement de .gitignore: {e}")
            # Retourner un spec avec seulement les règles par défaut
            default_patterns = ['.git/', '__pycache__/', 'node_modules/', '.vscode/', '.idea/']
            return pathspec.PathSpec.from_lines(GitWildMatchPattern, default_patterns)
    
    def _scan_files_with_gitignore(self, directory_path: str, 
                                  gitignore_spec: pathspec.PathSpec) -> List[Dict[str, Any]]:
        """Scanne récursivement les fichiers en appliquant les règles gitignore."""
        scanned_files = []
        directory_path = Path(directory_path)
        
        try:
            for file_path in directory_path.rglob('*'):
                if file_path.is_file():
                    try:
                        # Calculer le chemin relatif
                        relative_path = file_path.relative_to(directory_path).as_posix()
                        
                        # Vérifier si le fichier est ignoré
                        if not gitignore_spec.match_file(relative_path):
                            file_size = file_path.stat().st_size
                            scanned_files.append({
                                'absolute_path': str(file_path),
                                'relative_path': relative_path,
                                'name': file_path.name,
                                'size': file_size
                            })
                            
                            if self.config.get('debug') and len(scanned_files) % 1000 == 0:
                                self.logger.debug(f"Scanné {len(scanned_files)} fichiers...")
                                
                    except Exception as file_error:
                        self.logger.warning(f"Erreur lors du traitement de {file_path}: {file_error}")
                        continue
                        
        except Exception as e:
            self.logger.error(f"Erreur lors du scan récursif: {e}")
            
        return scanned_files
    
    def _filter_binary_files(self, files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filtre les fichiers binaires basé sur l'extension et le contenu."""
        filtered_files = []
        
        for file_info in files:
            file_path = Path(file_info['absolute_path'])
            ext = file_path.suffix.lower()
            filename = file_path.name
            
            # Vérifier d'abord les exclusions de fichiers spécifiques
            if filename in self.config.get('file_blacklist', set()):
                if self.config.get('debug'):
                    self.logger.debug(f"Ignoré (fichier dans la blacklist): {file_info['relative_path']}")
                continue
            
            # Vérifier les patterns d'exclusion
            excluded_by_pattern = False
            for pattern in self.config.get('pattern_blacklist', []):
                if fnmatch.fnmatch(filename, pattern):
                    if self.config.get('debug'):
                        self.logger.debug(f"Ignoré (correspond au pattern '{pattern}'): {file_info['relative_path']}")
                    excluded_by_pattern = True
                    break
            
            if excluded_by_pattern:
                continue
            
            # Niveau 1: Liste Noire d'extensions (Rejet Immédiat)
            if ext in self.config.get('binary_blacklist', set()):
                if self.config.get('debug'):
                    self.logger.debug(f"Ignoré (binaire par extension): {file_info['relative_path']}")
                continue
                
            # Niveau 2: Liste Blanche d'extensions (Acceptation immédiate pour .md, .txt, .json)
            if ext in self.config.get('binary_whitelist', set()):
                filtered_files.append(file_info)
                continue
            
            # Niveau 3: Test de contenu pour les autres extensions
            if file_info['size'] > 0:  # Ne pas tester les fichiers vides
                try:
                    # Déterminer la taille de l'échantillon (max 8KB pour les gros fichiers)
                    sample_size = min(file_info['size'], 8192)
                    
                    with open(file_info['absolute_path'], 'rb') as f:
                        sample = f.read(sample_size)
                    
                    # Vérifier s'il contient des octets nuls (indicateur fort de binaire)
                    if b'\x00' in sample:
                        if self.config.get('debug'):
                            self.logger.debug(f"Ignoré (binaire détecté - octets nuls): {file_info['relative_path']}")
                        continue
                    
                    # Essayer de décoder en UTF-8
                    try:
                        sample.decode('utf-8')
                        filtered_files.append(file_info)
                    except UnicodeDecodeError:
                        if self.config.get('debug'):
                            self.logger.debug(f"Ignoré (binaire détecté - pas UTF-8): {file_info['relative_path']}")
                        continue
                        
                except Exception as e:
                    self.logger.warning(f"Erreur lors du test binaire de {file_info['relative_path']}: {e}")
                    # En cas d'erreur, on inclut le fichier par défaut
                    filtered_files.append(file_info)
            else:
                # Les fichiers vides sont acceptés
                filtered_files.append(file_info)
                
        return filtered_files
    
