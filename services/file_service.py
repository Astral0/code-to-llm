import os
import logging
import pathspec
from pathspec.patterns import GitWildMatchPattern
from pathlib import Path
import fnmatch
import re
from typing import Dict, Any, Optional, List, Tuple
from .base_service import BaseService
from .exceptions import FileServiceException


# Import optionnel de detect-secrets
try:
    from detect_secrets import SecretsCollection
    from detect_secrets.plugins import initialize as initialize_detect_secrets_plugins
    HAS_DETECT_SECRETS = True
except ImportError:
    logging.warning("detect-secrets library not found. Secret masking will be disabled.")
    HAS_DETECT_SECRETS = False


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
        self.file_cache = []  # Cache des fichiers scannés
        self.current_directory = None  # Répertoire actuellement scanné
        
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
            
            # Préparer la structure pour l'affichage (inclure mtime)
            file_tree_data = [{"path": f["relative_path"], "size": f["size"], "mtime": f.get("mtime", 0)} for f in filtered_files]
            
            # Calculer les fichiers les plus volumineux (top 10)
            largest_files = sorted(filtered_files, key=lambda f: f['size'], reverse=True)[:10]
            largest_files_data = [
                {
                    "path": f["relative_path"],
                    "size": f["size"],
                    "size_kb": round(f["size"] / 1024, 1)
                }
                for f in largest_files
            ]
            
            self.logger.info(f"Scan terminé: {len(filtered_files)} fichiers trouvés")
            
            # Mettre à jour l'état interne
            self.file_cache = filtered_files
            self.current_directory = directory_path
            
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
                    'largest_files': largest_files_data,  # NOUVELLE DONNÉE
                    'debug': {
                        'gitignore_patterns_count': len(gitignore_spec.patterns) if hasattr(gitignore_spec, 'patterns') else 0
                    }
                }
            }
            
        except Exception as e:
            error_msg = f"Erreur lors du scan du répertoire: {str(e)}"
            self.logger.error(error_msg)
            raise FileServiceException(error_msg)
    
    def get_file_content(self, relative_path: str, current_directory: Optional[str] = None, 
                        file_cache: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Récupère le contenu d'un fichier.
        
        Cette méthode utilise l'état interne de l'instance (self.current_directory, 
        self.file_cache) si les paramètres current_directory et file_cache ne sont 
        pas fournis. Cela permet deux modes d'utilisation :
        
        1. Mode avec état (après scan_local_directory) :
           result = file_service.get_file_content('main.py')
           
        2. Mode sans état (paramètres explicites) :
           result = file_service.get_file_content('main.py', '/path/to/dir', file_cache)
        
        Args:
            relative_path: Le chemin relatif du fichier
            current_directory: Le répertoire de base (utilise self.current_directory si None)
            file_cache: Le cache des fichiers scannés (utilise self.file_cache si None)
            
        Returns:
            Dict contenant le contenu du fichier avec les clés :
            - success (bool): Indique si la lecture a réussi
            - content (str): Le contenu du fichier (si succès)
            - path (str): Le chemin relatif du fichier (si succès)
            - size (int): La taille du fichier (si succès)
            - error (str): Message d'erreur (si échec)
        """
        try:
            # Utiliser l'état interne si les paramètres ne sont pas fournis
            if current_directory is None:
                current_directory = self.current_directory
            if file_cache is None:
                file_cache = self.file_cache
                
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
    
    def get_file_contents_batch(self, selected_files: List[str], current_directory: Optional[str] = None,
                              file_cache: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Récupère le contenu de plusieurs fichiers en batch.
        
        Cette méthode utilise l'état interne de l'instance si les paramètres 
        optionnels ne sont pas fournis. Idéal pour traiter plusieurs fichiers
        après un scan_local_directory.
        
        Exemple d'utilisation :
            # Après un scan
            file_service.scan_local_directory('/project')
            # Récupération batch utilisant l'état interne
            result = file_service.get_file_contents_batch(['main.py', 'utils.py'])
        
        Args:
            selected_files: Liste des chemins relatifs des fichiers sélectionnés
            current_directory: Le répertoire de base (utilise self.current_directory si None)
            file_cache: Le cache des fichiers (utilise self.file_cache si None)
            
        Returns:
            Dict contenant :
            - success (bool): Indique si l'opération a réussi
            - file_contents (list): Liste des fichiers récupérés avec succès
            - failed_files (list): Liste des fichiers qui n'ont pas pu être lus
            - stats (dict): Statistiques de l'opération
            - error (str): Message d'erreur global (si échec complet)
        """
        try:
            # Utiliser l'état interne si les paramètres ne sont pas fournis
            if current_directory is None:
                current_directory = self.current_directory
            if file_cache is None:
                file_cache = self.file_cache
                
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
        """
        Scanne récursivement les fichiers en appliquant les règles gitignore
        avec une stratégie d'élagage pour une performance optimale.
        """
        scanned_files = []
        base_path = Path(directory_path)
        
        for root, dirs, files in os.walk(directory_path, topdown=True):
            root_path = Path(root)
            
            # OPTIMISATION CLÉ : Élagage des répertoires ignorés
            # Approche pythonique : modification en place avec list comprehension
            # Plus performant (une seule passe) et plus expressif
            dirs[:] = [
                d for d in dirs 
                if not gitignore_spec.match_file(
                    root_path.joinpath(d).relative_to(base_path).as_posix() + '/'
                )
            ]
            
            # Traiter les fichiers du répertoire courant
            for filename in files:
                file_abs_path = root_path.joinpath(filename)
                file_rel_path = file_abs_path.relative_to(base_path).as_posix()
                
                if not gitignore_spec.match_file(file_rel_path):
                    try:
                        file_stat = file_abs_path.stat()
                        file_size = file_stat.st_size
                        file_mtime = file_stat.st_mtime  # Timestamp de modification
                        scanned_files.append({
                            'absolute_path': str(file_abs_path),
                            'relative_path': file_rel_path,
                            'name': filename,
                            'size': file_size,
                            'mtime': file_mtime
                        })
                        
                        if self.config.get('debug') and len(scanned_files) % 1000 == 0:
                            self.logger.debug(f"Scanné {len(scanned_files)} fichiers...")
                            
                    except OSError as e:
                        self.logger.warning(f"Impossible d'accéder au fichier {file_abs_path}: {e}")
                        continue
        
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
    
    def detect_and_redact_secrets(self, content: str, file_path: str, 
                                  redact_mode: str = 'mask') -> Tuple[str, int]:
        """
        Détecte et masque les secrets dans le contenu d'un fichier.
        
        Args:
            content: Le contenu du fichier à analyser
            file_path: Le chemin du fichier (utilisé pour les règles spécifiques au format)
            redact_mode: Le mode de redaction ('mask' pour [MASKED SECRET], 'remove' pour supprimer la ligne)
        
        Returns:
            tuple: (contenu redacté, nombre de secrets détectés)
        """
        # Vérifier si la bibliothèque detect-secrets est disponible
        if not HAS_DETECT_SECRETS:
            return content, 0

        try:
            # Initialiser la collection de secrets
            secrets = SecretsCollection()
            
            # Initialiser les plugins de détection disponibles
            plugins_used = list(initialize_detect_secrets_plugins.from_parser_builder([]))
            for plugin in plugins_used:
                try:
                    secrets.scan_string_content(content, plugin, path=file_path)
                except Exception as plugin_error:
                    self.logger.debug(f"Plugin {plugin.__class__.__name__} failed for {file_path}: {plugin_error}")
            
            # Si aucun secret n'est détecté, retourner le contenu original
            if not secrets.data:
                return content, 0
            
            # Redacter les secrets détectés
            lines = content.splitlines()
            redacted_lines = list(lines)  # Copie pour modification
            
            # Trier les secrets par numéro de ligne
            secrets_by_line = {}
            for filename, secret_list in secrets.data.items():
                for secret in secret_list:
                    line_num = secret['line_number'] - 1  # Ajuster pour l'indexation à 0
                    if line_num not in secrets_by_line:
                        secrets_by_line[line_num] = []
                    secrets_by_line[line_num].append(secret)
            
            # Redacter chaque ligne contenant des secrets
            secrets_count = 0
            for line_num, line_secrets in sorted(secrets_by_line.items(), reverse=True):
                if line_num >= len(redacted_lines):
                    continue  # Ignorer si la ligne est hors limites
                
                if redact_mode == 'remove':
                    # Supprimer la ligne entière
                    redacted_lines[line_num] = f"[LINE REMOVED DUE TO DETECTED SECRET]"
                    secrets_count += len(line_secrets)
                else:
                    # Mode par défaut: masquer les secrets individuellement
                    current_line = redacted_lines[line_num]
                    redacted_lines[line_num] = f"[LINE CONTAINING SENSITIVE DATA: {line_secrets[0]['type']}]"
                    secrets_count += 1
            
            # Reconstituer le contenu avec les lignes redactées
            redacted_content = "\n".join(redacted_lines)
            
            return redacted_content, secrets_count
            
        except Exception as e:
            self.logger.error(f"Error using detect-secrets: {e}")
            return content, 0

    def detect_and_redact_with_regex(self, content: str, file_path: str) -> Tuple[str, int]:
        """
        Détecte et masque les patterns courants de secrets avec des expressions régulières.
        Complémentaire à detect-secrets pour des cas spécifiques.
        
        Args:
            content: Le contenu du fichier
            file_path: Le chemin du fichier (pour le logging)
            
        Returns:
            tuple: (contenu redacté, nombre de secrets détectés)
        """
        # Patterns courants de secrets et informations d'identification
        patterns = {
            # API Keys - différents formats courants
            'api_key': r'(?i)(api[_-]?key|apikey|api_token|auth_token|authorization_token|bearer_token)["\']?\s*[:=]\s*["\']?([0-9a-zA-Z\-_\.]{16,128})["\']?',
            # Tokens divers (OAuth, JWT, etc.)
            'token': r'(?i)(access_token|auth_token|token)["\']?\s*[:=]\s*["\']?([0-9a-zA-Z._\-]{8,64})["\']?',
            # Clés AWS
            'aws_key': r'(?i)(AKIA[0-9A-Z]{16})',
            # URLs contenant username:password
            'url_auth': r'(?i)https?://[^:@/\s]+:[^:@/\s]+@[^/\s]+',
            # Clés privées
            'private_key_pem': r'-----BEGIN ((RSA|EC|OPENSSH|PGP) )?PRIVATE KEY-----',
            # Documentation de credentials/variables sensibles avec valeurs
            'credentials_doc': r'(?i)# ?(password|secret|key|token|credential).*[=:] ?"[^"]{3,}"',
            # Clés AWS
            'aws_secret': r'(?i)(aws[\w_\-]*secret[\w_\-]*key)["\']?\s*[:=]\s*["\']?([0-9a-zA-Z\-_\/+]{40})["\']?',
            # Clés privées
            'private_key': r'(?i)(-----BEGIN [A-Z]+ PRIVATE KEY-----)',
            # Connection strings
            'connection_string': r'(?i)(mongodb|mysql|postgresql|sqlserver|redis|amqp)://[^:]+:[^@]+@[:\w\.\-]+[/:\w\d\?=&%\-\.]*'
        }
        
        # Initialiser les variables
        lines = content.splitlines()
        redacted_lines = list(lines)
        count = 0
        
        # Parcourir chaque ligne pour détecter les patterns
        for i, line in enumerate(lines):
            for pattern_name, pattern in patterns.items():
                matches = list(re.finditer(pattern, line))
                if matches:
                    redacted_lines[i] = f"[LINE CONTAINING SENSITIVE DATA: {pattern_name}]"
                    count += 1
                    break  # Passer à la ligne suivante une fois qu'un pattern est trouvé
        
        # Reconstituer le contenu
        redacted_content = "\n".join(redacted_lines)
        
        return redacted_content, count
