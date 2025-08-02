import webview
import threading
import time
import os
import json
import appdirs
import configparser
import logging
import re
from selenium.webdriver.common.by import By
from pywebview_driver import PywebviewDriver
from web_server import app
import pathspec
from pathspec.patterns import GitWildMatchPattern
from pathlib import Path
import fnmatch
from services.export_service import ExportService

# Définir le chemin de stockage des données persistantes
DATA_DIR = appdirs.user_data_dir('WebAutomationDesktop', 'WebAutomationTools')
os.makedirs(DATA_DIR, exist_ok=True)

# Définir le chemin du fichier de paramètres
SETTINGS_PATH = os.path.join(DATA_DIR, 'settings.json')

# Lire la configuration
def load_config():
    """Charge la configuration depuis config.ini"""
    config = configparser.ConfigParser()
    config_path = 'config.ini'
    
    if os.path.exists(config_path):
        config.read(config_path, encoding='utf-8')
    else:
        print(f"Fichier de configuration {config_path} non trouvé, utilisation des valeurs par défaut")
        return {'debug': False, 'binary_blacklist': set(), 'binary_whitelist': set()}
    
    # Lire le paramètre debug avec une valeur par défaut
    debug_enabled = config.getboolean('Debug', 'debug', fallback=False)
    
    # Lire la configuration de détection binaire
    binary_blacklist = set()
    binary_whitelist = set()
    
    if 'BinaryDetection' in config:
        blacklist_str = config.get('BinaryDetection', 'extension_blacklist', fallback='')
        whitelist_str = config.get('BinaryDetection', 'extension_whitelist', fallback='')
        
        # Convertir les chaînes en sets
        binary_blacklist = {ext.strip() for ext in blacklist_str.split(',') if ext.strip()}
        binary_whitelist = {ext.strip() for ext in whitelist_str.split(',') if ext.strip()}
        
        if debug_enabled:
            print(f"Binary detection lists loaded: {len(binary_blacklist)} blacklisted, {len(binary_whitelist)} whitelisted")
    
    # Lire la configuration d'exclusion de fichiers
    file_blacklist = set()
    pattern_blacklist = []
    
    if 'FileExclusion' in config:
        file_blacklist_str = config.get('FileExclusion', 'file_blacklist', fallback='')
        pattern_blacklist_str = config.get('FileExclusion', 'pattern_blacklist', fallback='')
        
        # Convertir les chaînes en sets/listes
        file_blacklist = {f.strip() for f in file_blacklist_str.split(',') if f.strip()}
        pattern_blacklist = [p.strip() for p in pattern_blacklist_str.split(',') if p.strip()]
        
        if debug_enabled:
            print(f"File exclusion lists loaded: {len(file_blacklist)} files, {len(pattern_blacklist)} patterns")
    
    return {
        'debug': debug_enabled,
        'binary_blacklist': binary_blacklist,
        'binary_whitelist': binary_whitelist,
        'file_blacklist': file_blacklist,
        'pattern_blacklist': pattern_blacklist
    }

# Charger la configuration
CONFIG = load_config()

# Configurer les logs selon le paramètre debug
if CONFIG['debug']:
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
    print("Mode debug activé - logs détaillés activés")
else:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    print("Mode normal - logs basiques activés")

class Api:
    def __init__(self):
        self._main_window = None
        self._browser_window = None
        self._toolbox_window = None
        self.driver = None
        self.current_directory = None
        self.file_cache = []
        self.export_service = ExportService()
    
    def set_main_window(self, window):
        """Définit la référence à la fenêtre principale"""
        self._main_window = window
        if CONFIG['debug']:
            logging.debug("Fenêtre principale définie dans l'API")
    
    def select_directory_dialog(self):
        """Ouvre une boîte de dialogue native pour sélectionner un répertoire"""
        if not self._main_window:
            error_msg = 'Fenêtre principale non disponible'
            logging.error(error_msg)
            return {'success': False, 'error': error_msg}
        
        try:
            # Initialiser le chemin initial par défaut (dossier utilisateur)
            initial_path = os.path.expanduser('~')
            
            # Vérifier si le fichier settings.json existe et récupérer le dernier répertoire
            try:
                if os.path.exists(SETTINGS_PATH):
                    with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
                        settings = json.load(f)
                        last_directory = settings.get('last_directory', '')
                        if last_directory and os.path.exists(last_directory):
                            initial_path = last_directory
                            logging.info(f"Répertoire initial restauré: {initial_path}")
                        else:
                            logging.info("Dernier répertoire non valide, utilisation du répertoire par défaut")
            except (json.JSONDecodeError, KeyError, OSError) as e:
                logging.warning(f"Erreur lors de la lecture des paramètres: {e}, utilisation du répertoire par défaut")
            
            # Ouvrir la boîte de dialogue de sélection de répertoire
            if CONFIG['debug']:
                logging.debug(f"Ouverture de la boîte de dialogue avec répertoire initial: {initial_path}")
            
            result = self._main_window.create_file_dialog(
                webview.FOLDER_DIALOG,
                directory=initial_path
            )
            
            if result and len(result) > 0:
                selected_directory = result[0]
                logging.info(f"Répertoire sélectionné: {selected_directory}")
                
                # Sauvegarder le répertoire sélectionné
                save_result = self.save_last_directory(selected_directory)
                if not save_result['success']:
                    logging.warning(f"Avertissement lors de la sauvegarde: {save_result['error']}")
                
                return {
                    'success': True, 
                    'directory': selected_directory,
                    'message': 'Répertoire sélectionné avec succès'
                }
            else:
                logging.info("Aucun répertoire sélectionné par l'utilisateur")
                return {'success': False, 'error': 'Aucun répertoire sélectionné'}
                
        except Exception as e:
            error_msg = f"Erreur lors de l'ouverture de la boîte de dialogue: {str(e)}"
            logging.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def save_last_directory(self, directory_path):
        """Sauvegarde le dernier répertoire sélectionné dans le fichier de paramètres"""
        try:
            # Charger les paramètres existants s'ils existent
            settings = {}
            if os.path.exists(SETTINGS_PATH):
                with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
            
            # Mettre à jour avec le nouveau chemin
            settings['last_directory'] = directory_path
            
            # Écrire le dictionnaire mis à jour dans le fichier
            with open(SETTINGS_PATH, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
            
            logging.info(f"Répertoire sauvegardé dans les paramètres: {directory_path}")
            return {'success': True, 'message': 'Répertoire sauvegardé avec succès'}
            
        except Exception as e:
            error_msg = f"Erreur lors de la sauvegarde du répertoire: {str(e)}"
            logging.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def get_last_directory(self):
        """Récupère le dernier répertoire sélectionné depuis le fichier de paramètres"""
        try:
            if os.path.exists(SETTINGS_PATH):
                with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    directory = settings.get('last_directory', '')
                    if CONFIG['debug']:
                        logging.debug(f"Dernier répertoire lu depuis les paramètres: {directory}")
                    return {'success': True, 'directory': directory}
            else:
                if CONFIG['debug']:
                    logging.debug("Fichier de paramètres non trouvé, retour d'un répertoire vide")
                return {'success': True, 'directory': ''}
                
        except Exception as e:
            error_msg = f"Erreur lors de la lecture des paramètres: {str(e)}"
            logging.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def launch_pywebview_browser(self):
        """Lance une nouvelle fenêtre pywebview pour le navigateur"""
        try:
            logging.info("Lancement d'une nouvelle fenêtre pywebview pour le navigateur")
            
            # Créer la fenêtre du navigateur dans un thread séparé
            import threading
            
            def create_browser_window():
                if CONFIG['debug']:
                    logging.debug("Création de la fenêtre navigateur dans un thread séparé")
                
                self._browser_window = webview.create_window(
                    "Navigateur pour Automatisation", 
                    "https://gemini.google.com",
                    width=1200,
                    height=800
                )
                # Instancier et stocker le driver
                self.driver = PywebviewDriver(self._browser_window)
                
                # Attendre un peu que la fenêtre soit ready puis appeler le callback
                def delayed_callback():
                    import time
                    time.sleep(2)  # Attendre que la fenêtre soit prête
                    if self._main_window:
                        if CONFIG['debug']:
                            logging.debug("Appel du callback onBrowserConnected")
                        self._main_window.evaluate_js('onBrowserConnected()')
                
                callback_thread = threading.Thread(target=delayed_callback)
                callback_thread.daemon = True
                callback_thread.start()
            
            # Lancer la création dans un thread séparé
            browser_thread = threading.Thread(target=create_browser_window)
            browser_thread.daemon = True
            browser_thread.start()
            
            return {'success': True, 'message': 'Navigateur pywebview lancé avec succès'}
            
        except Exception as e:
            error_msg = f"Erreur lors du lancement du navigateur pywebview: {str(e)}"
            logging.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def send_context(self, context):
        """Envoie le contexte au navigateur pywebview"""
        if not (self.driver and self._browser_window):
            error_msg = 'Le navigateur pywebview n\'est pas lancé ou a été fermé.'
            logging.error(error_msg)
            return {'success': False, 'error': error_msg}

        try:
            url = self.driver.get_current_url()
            logging.info(f"Envoi du contexte vers l'URL : {url}")

            # Définir les sélecteurs possibles selon le site
            if "gemini.google.com" in url:
                selectors = [
                    # Nouveaux sélecteurs plus spécifiques pour Gemini
                    'div[contenteditable="plaintext-only"]',
                    'div[data-placeholder*="Demandez"]',
                    'div[aria-label*="Demandez"]',
                    'div.ql-editor[data-placeholder]',
                    'div[contenteditable="true"][data-placeholder]',
                    # Sélecteurs existants
                    '[role="textbox"]',
                    '[contenteditable="true"]',
                    'textarea',
                    '.ql-editor',
                    '[data-testid="textbox"]',
                    'div[aria-label*="message"]',
                    'div[aria-label*="chat"]',
                    'div[contenteditable]'
                ]
            elif "chat.openai.com" in url:
                selectors = [
                    '#prompt-textarea',
                    'textarea[placeholder*="Message"]',
                    '[contenteditable="true"]'
                ]
            else:
                error_msg = f"Le site actuel ({url}) n'est pas supporté pour l'envoi de contexte."
                logging.error(error_msg)
                return {'success': False, 'error': error_msg}
            
            # Toujours faire un debug des éléments disponibles pour diagnostiquer le problème
            logging.info("=== DEBUG DES ELEMENTS DE LA PAGE ===")
            try:
                elements = self.driver.debug_page_elements()
                logging.info(f"Nombre d'éléments trouvés: {len(elements)}")
                for i, elem in enumerate(elements):
                    if elem.get('visible', False):
                        logging.info(f"Élément visible {i+1}: {elem.get('selector')} - {elem.get('ariaLabel')} - {elem.get('dataPlaceholder')}")
            except Exception as debug_error:
                logging.warning(f"Erreur lors du debug: {debug_error}")
            logging.info("=== FIN DEBUG ===")
            
            # Essayer chaque sélecteur jusqu'à ce qu'un fonctionne
            last_error = None
            for selector in selectors:
                try:
                    logging.info(f"Tentative avec le sélecteur: {selector}")
                    
                    target_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    result = target_element.send_keys(context)
                    
                    if result and result != 'ELEMENT_NOT_FOUND':
                        success_msg = f'Contexte envoyé avec succès ! (méthode: {result})'
                        logging.info(f"Succès avec le sélecteur: {selector}, résultat: {result}")
                        return {'success': True, 'message': success_msg}
                    else:
                        logging.info(f"Échec avec le sélecteur: {selector}")
                        
                except Exception as selector_error:
                    logging.info(f"Erreur avec le sélecteur {selector}: {selector_error}")
                    last_error = selector_error
                    continue
            
            # Si aucun sélecteur n'a fonctionné
            error_msg = f"Aucun élément de saisie trouvé. Dernière erreur: {last_error}"
            logging.error(error_msg)
            return {'success': False, 'error': error_msg}

        except Exception as e:
            error_message = f"Erreur lors de l'interaction avec la page : {e}"
            logging.error(error_message)
            return {'success': False, 'error': error_message}
    
    def scan_local_directory(self, directory_path):
        """Scanne un répertoire local et applique les règles .gitignore sans upload"""
        try:
            if not directory_path or not os.path.exists(directory_path):
                error_msg = f"Répertoire invalide: {directory_path}"
                logging.error(error_msg)
                return {'success': False, 'error': error_msg}
            
            self.current_directory = directory_path
            logging.info(f"Début du scan local du répertoire: {directory_path}")
            
            # Charger les règles .gitignore
            gitignore_spec = self._load_gitignore_spec(directory_path)
            
            # Scanner les fichiers
            scanned_files = self._scan_files_with_gitignore(directory_path, gitignore_spec)
            
            # Filtrer les fichiers binaires
            filtered_files = self._filter_binary_files(scanned_files)
            
            # Mettre en cache les fichiers pour un accès rapide
            self.file_cache = filtered_files
            
            # Préparer la structure pour l'affichage
            file_tree_data = [{"path": f["relative_path"], "size": f["size"]} for f in filtered_files]
            
            logging.info(f"Scan terminé: {len(filtered_files)} fichiers trouvés")
            
            return {
                'success': True,
                'files': file_tree_data,
                'directory': directory_path,
                'total_files': len(filtered_files),
                'debug': {
                    'gitignore_patterns_count': len(gitignore_spec.patterns) if gitignore_spec else 0
                }
            }
            
        except Exception as e:
            error_msg = f"Erreur lors du scan du répertoire: {str(e)}"
            logging.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def _load_gitignore_spec(self, directory_path):
        """Charge les règles .gitignore depuis le répertoire"""
        try:
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
                logging.info(f"Chargé {len(cleaned_lines)} règles depuis .gitignore")
            else:
                logging.info("Aucun .gitignore trouvé, utilisation des règles par défaut")
            
            return pathspec.PathSpec.from_lines(GitWildMatchPattern, patterns)
            
        except Exception as e:
            logging.warning(f"Erreur lors du chargement de .gitignore: {e}")
            # Retourner un spec avec seulement les règles par défaut
            default_patterns = ['.git/', '__pycache__/', 'node_modules/', '.vscode/', '.idea/']
            return pathspec.PathSpec.from_lines(GitWildMatchPattern, default_patterns)
    
    def _scan_files_with_gitignore(self, directory_path, gitignore_spec):
        """Scanne récursivement les fichiers en appliquant les règles gitignore"""
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
                            
                            if CONFIG['debug'] and len(scanned_files) % 1000 == 0:
                                logging.debug(f"Scanné {len(scanned_files)} fichiers...")
                                
                    except Exception as file_error:
                        logging.warning(f"Erreur lors du traitement de {file_path}: {file_error}")
                        continue
                        
        except Exception as e:
            logging.error(f"Erreur lors du scan récursif: {e}")
            
        return scanned_files
    
    def _filter_binary_files(self, files):
        """Filtre les fichiers binaires basé sur l'extension et le contenu"""
        filtered_files = []
        
        for file_info in files:
            file_path = Path(file_info['absolute_path'])
            ext = file_path.suffix.lower()
            filename = file_path.name
            
            # Vérifier d'abord les exclusions de fichiers spécifiques
            if filename in CONFIG['file_blacklist']:
                if CONFIG['debug']:
                    logging.debug(f"Ignoré (fichier dans la blacklist): {file_info['relative_path']}")
                continue
            
            # Vérifier les patterns d'exclusion
            excluded_by_pattern = False
            for pattern in CONFIG['pattern_blacklist']:
                if fnmatch.fnmatch(filename, pattern):
                    if CONFIG['debug']:
                        logging.debug(f"Ignoré (correspond au pattern '{pattern}'): {file_info['relative_path']}")
                    excluded_by_pattern = True
                    break
            
            if excluded_by_pattern:
                continue
            
            # Niveau 1: Liste Noire d'extensions (Rejet Immédiat)
            if ext in CONFIG['binary_blacklist']:
                if CONFIG['debug']:
                    logging.debug(f"Ignoré (binaire par extension): {file_info['relative_path']}")
                continue
            
            # Niveau 2: Liste Blanche d'extensions (Acceptation Immédiate)
            if ext in CONFIG['binary_whitelist']:
                filtered_files.append(file_info)
                continue
            
            # Niveau 3: Vérifier le contenu pour les petits fichiers
            try:
                if file_info['size'] < 1024 * 1024:  # Moins de 1MB
                    with open(file_path, 'rb') as f:
                        sample = f.read(1024)
                        # Si plus de 30% de bytes non-ASCII, considérer comme binaire
                        non_ascii_count = sum(1 for b in sample if b > 127 or (b < 32 and b not in [9, 10, 13]))
                        if len(sample) > 0 and (non_ascii_count / len(sample)) > 0.3:
                            if CONFIG['debug']:
                                logging.debug(f"Ignoré (binaire par contenu): {file_info['relative_path']}")
                            continue
            except Exception:
                # En cas d'erreur de lecture, ignorer le fichier
                if CONFIG['debug']:
                    logging.debug(f"Ignoré (erreur de lecture): {file_info['relative_path']}")
                continue
                
            filtered_files.append(file_info)
        
        return filtered_files
    
    def get_file_content(self, relative_path):
        """Récupère le contenu d'un fichier depuis le cache local"""
        try:
            if not self.current_directory:
                return {'success': False, 'error': 'Aucun répertoire scanné'}
            
            # Trouver le fichier dans le cache
            file_info = next((f for f in self.file_cache if f['relative_path'] == relative_path), None)
            
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
            logging.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def generate_context_from_selection(self, selected_files, instructions=""):
        """Génère le contexte depuis une sélection de fichiers locaux"""
        try:
            if not selected_files:
                return {'success': False, 'error': 'Aucun fichier sélectionné'}
            
            context_parts = []
            total_chars = 0
            successful_files = 0
            
            # En-tête du contexte
            context_parts.append(f"# Contexte du projet - {os.path.basename(self.current_directory)}")
            context_parts.append(f"Répertoire: {self.current_directory}")
            context_parts.append(f"Fichiers inclus: {len(selected_files)}")
            context_parts.append("")
            
            # Générer l'arbre des fichiers
            tree_lines = self._generate_file_tree(selected_files)
            context_parts.extend(tree_lines)
            context_parts.append("")
            
            # Ajouter le contenu de chaque fichier et stocker les infos de taille
            file_contents = []
            for file_path in selected_files:
                file_result = self.get_file_content(file_path)
                if file_result['success']:
                    content = file_result['content']
                    size = len(content)
                    
                    # Stocker pour le tri par taille
                    file_contents.append({
                        'path': file_path,
                        'content': content,
                        'size': size
                    })
                    
                    context_parts.append(f"--- {file_path} ---")
                    context_parts.append(content)
                    context_parts.append(f"--- FIN {file_path} ---")
                    context_parts.append("")
                    total_chars += size
                    successful_files += 1
                else:
                    logging.warning(f"Échec lecture fichier: {file_path}")
            
            if instructions:
                context_parts.append("--- INSTRUCTIONS ---")
                context_parts.append(instructions)
                context_parts.append("--- FIN INSTRUCTIONS ---")
                context_parts.append("")
            
            context = "\n".join(context_parts)
            
            # Stocker le contexte pour la Toolbox
            self._last_generated_context = context
            
            # Trier les fichiers par taille et prendre les 10 plus gros
            largest_files = sorted(file_contents, key=lambda f: f['size'], reverse=True)[:10]
            formatted_largest_files = [{'path': f['path'], 'size': f['size']} for f in largest_files]
            
            return {
                'success': True,
                'context': context,
                'stats': {
                    'total_files': successful_files,
                    'total_chars': total_chars,
                    'estimated_tokens': total_chars // 4,  # Estimation approximative
                    'largest_files': formatted_largest_files  # NOUVELLE DONNÉE
                }
            }
            
        except Exception as e:
            error_msg = f"Erreur lors de la génération du contexte: {str(e)}"
            logging.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def _generate_file_tree(self, selected_files):
        """Génère un arbre visuel des fichiers sélectionnés"""
        if not selected_files:
            return ["## Arbre des fichiers", "Aucun fichier sélectionné"]
        
        tree_lines = ["## Arbre des fichiers", "```"]
        tree_lines.append(f"{os.path.basename(self.current_directory)}/")
        
        # Trier les fichiers pour un affichage cohérent
        sorted_files = sorted(selected_files)
        
        # Construire l'arbre
        for i, file_path in enumerate(sorted_files):
            is_last = (i == len(sorted_files) - 1)
            parts = file_path.split('/')
            
            # Construire l'indentation
            prefix = "└── " if is_last else "├── "
            indent = "    " * (len(parts) - 1)
            
            tree_lines.append(f"{indent}{prefix}{parts[-1]}")
        
        tree_lines.append("```")
        return tree_lines
    
    def open_toolbox_window(self):
        """Ouvre une nouvelle fenêtre pour la Toolbox Développeur"""
        try:
            logging.info("Ouverture de la fenêtre Toolbox Développeur")
            
            # Créer la fenêtre Toolbox
            self._toolbox_window = webview.create_window(
                "Toolbox Développeur Augmenté",
                "http://127.0.0.1:5000/toolbox",
                js_api=self,  # Partager la même API
                width=1400,
                height=800,
                min_size=(1200, 600)
            )
            
            return {'success': True, 'message': 'Fenêtre Toolbox ouverte avec succès'}
            
        except Exception as e:
            error_msg = f"Erreur lors de l'ouverture de la Toolbox: {str(e)}"
            logging.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def get_available_prompts(self):
        """Retourne la liste des prompts disponibles dans le répertoire prompts/"""
        try:
            prompts_dir = os.path.join(os.path.dirname(__file__), 'prompts')
            logging.info(f"Recherche des prompts dans: {prompts_dir}")
            
            if not os.path.exists(prompts_dir):
                logging.warning(f"Le répertoire prompts n'existe pas: {prompts_dir}")
                return []
            
            prompts = []
            files = sorted(os.listdir(prompts_dir))
            logging.info(f"Fichiers trouvés dans prompts/: {files}")
            
            for filename in files:
                if filename.endswith('.md'):
                    # Extraire le nom sans l'extension et le numéro
                    name = filename.replace('.md', '')
                    if name.startswith('0') and '_' in name:
                        # Enlever le numéro de préfixe (ex: "01_" devient "")
                        name = name.split('_', 1)[1].replace('_', ' ').title()
                    
                    prompts.append({
                        'filename': filename,
                        'name': name
                    })
                    logging.info(f"Prompt ajouté: {filename} -> {name}")
            
            logging.info(f"Total des prompts trouvés: {len(prompts)}")
            return prompts
            
        except Exception as e:
            logging.error(f"Erreur lors de la lecture des prompts: {str(e)}")
            return []
    
    def get_prompt_content(self, filename):
        """Retourne le contenu d'un fichier de prompt"""
        try:
            prompts_dir = os.path.join(os.path.dirname(__file__), 'prompts')
            file_path = os.path.join(prompts_dir, filename)
            
            # Vérification de sécurité pour éviter la traversée de répertoire
            if not os.path.abspath(file_path).startswith(os.path.abspath(prompts_dir)):
                raise ValueError("Chemin de fichier non autorisé")
            
            if os.path.exists(file_path) and file_path.endswith('.md'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
            else:
                raise FileNotFoundError(f"Prompt non trouvé: {filename}")
                
        except Exception as e:
            error_msg = f"Erreur lors de la lecture du prompt: {str(e)}"
            logging.error(error_msg)
            raise Exception(error_msg)
    
    def run_git_diff(self):
        """Exécute git diff HEAD et retourne le résultat"""
        try:
            import subprocess
            
            # Lire la configuration pour le chemin git
            config = configparser.ConfigParser()
            config.read('config.ini', encoding='utf-8')
            git_path = config.get('Git', 'executable_path', fallback='git').strip()
            
            if not git_path:
                git_path = 'git'
            
            # Vérifier que nous sommes dans le répertoire de travail
            if not self.current_directory:
                return {'error': 'Aucun répertoire de travail sélectionné'}
            
            # Construire la commande
            git_command = [git_path, 'diff', 'HEAD']
            logging.info(f"Exécution de la commande: {' '.join(git_command)}")
            logging.info(f"Dans le répertoire: {self.current_directory}")
            
            # Exécuter git diff HEAD
            result = subprocess.run(
                git_command,
                cwd=self.current_directory,
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
            
            if result.returncode != 0:
                # Vérifier si c'est parce que ce n'est pas un repo git
                if "not a git repository" in result.stderr.lower():
                    logging.warning(f"Le répertoire {self.current_directory} n'est pas un dépôt git")
                    return {'error': 'Le répertoire actuel n\'est pas un dépôt git'}
                else:
                    logging.error(f"Erreur git: {result.stderr}")
                    return {'error': f'Erreur git: {result.stderr}'}
            
            diff_size = len(result.stdout)
            diff_lines = result.stdout.count('\n')
            logging.info(f"Git diff exécuté avec succès: {diff_size} caractères, {diff_lines} lignes")
            
            return {'diff': result.stdout}
            
        except FileNotFoundError:
            return {'error': 'Git n\'est pas installé ou le chemin est incorrect. Vérifiez config.ini'}
        except Exception as e:
            error_msg = f"Erreur lors de l'exécution de git diff: {str(e)}"
            logging.error(error_msg)
            return {'error': error_msg}
    
    def get_main_context(self):
        """Retourne le contexte principal généré précédemment"""
        if hasattr(self, '_last_generated_context'):
            return self._last_generated_context
        return ""
    
    def get_stream_status(self):
        """Retourne l'état du streaming LLM"""
        try:
            config = configparser.ConfigParser()
            config.read('config.ini', encoding='utf-8')
            return config.getboolean('LLMServer', 'stream_response', fallback=False)
        except:
            return False
    
    def _count_tokens_for_history(self, chat_history):
        """Compte le nombre total de tokens dans l'historique du chat"""
        try:
            # Utiliser une approximation locale sans dépendance externe
            # Basée sur les observations de tokenization GPT/Claude
            total_tokens = 0
            
            for message in chat_history:
                content = message.get('content', '')
                role = message.get('role', '')
                
                # Compter les tokens du contenu
                content_tokens = self._estimate_tokens(content)
                
                # Ajouter le surcoût pour le rôle et la structure
                # Format typique: {"role": "user", "content": "..."} = ~5-7 tokens de structure
                role_tokens = len(role.split()) + 5
                
                total_tokens += content_tokens + role_tokens
            
            # Ajouter un surcoût pour la structure globale de la conversation
            total_tokens += 3
            
            logging.debug(f"Tokens estimés: {total_tokens} pour {len(chat_history)} messages")
            return total_tokens
            
        except Exception as e:
            logging.error(f"Erreur lors du comptage des tokens: {e}")
            # En cas d'erreur, retourner une estimation très basique
            total_chars = sum(len(msg.get('content', '')) for msg in chat_history)
            return total_chars // 4
    
    def _estimate_tokens(self, text):
        """Estime le nombre de tokens dans un texte donné"""
        if not text:
            return 0
        
        # Approximation basée sur l'analyse des patterns de tokenization GPT/Claude
        # 1. Compter les mots (séparés par espaces)
        words = text.split()
        word_count = len(words)
        
        # 2. Compter les caractères de ponctuation qui deviennent souvent des tokens séparés
        punctuation_count = len(re.findall(r'[.,!?;:()\[\]{}"\'`\-–—…]', text))
        
        # 3. Compter les nombres (souvent tokenizés différemment)
        number_sequences = re.findall(r'\d+', text)
        number_tokens = sum(len(num) // 3 + 1 for num in number_sequences)
        
        # 4. Compter les retours à la ligne (souvent des tokens séparés)
        newline_count = text.count('\n')
        
        # 5. Gérer les mots longs (souvent divisés en sous-tokens)
        long_words = [w for w in words if len(w) > 10]
        extra_tokens_from_long_words = sum(len(w) // 8 for w in long_words)
        
        # 6. Gérer le code (variables, syntaxe)
        # Détecter si c'est du code par la présence de patterns communs
        code_indicators = ['def ', 'function ', 'import ', 'const ', 'let ', 'var ', '{}', '()', '[]', '=>', '//']
        is_code = any(indicator in text for indicator in code_indicators)
        code_multiplier = 1.3 if is_code else 1.0
        
        # Calcul final avec pondération
        # Base: 1 token par mot, ajusté selon les observations
        base_tokens = word_count * 1.1  # Les mots courts font souvent 1 token, les longs plus
        
        total_tokens = int((
            base_tokens + 
            punctuation_count * 0.8 +  # Pas toute la ponctuation devient un token séparé
            number_tokens +
            newline_count +
            extra_tokens_from_long_words
        ) * code_multiplier)
        
        # Minimum de tokens (même une chaîne vide prend au moins 1 token)
        return max(1, total_tokens)
    
    def send_to_llm_stream(self, chat_history, callback_id):
        """Envoie l'historique au LLM en mode streaming avec callback vers le frontend"""
        logging.info(f"send_to_llm_stream appelé avec callback_id: {callback_id}")
        try:
            import requests
            import json
            
            # Lire la configuration LLM
            config = configparser.ConfigParser()
            config.read('config.ini', encoding='utf-8')
            
            if not config.getboolean('LLMServer', 'enabled', fallback=False):
                return {'error': 'LLM feature is not enabled in config.ini'}
            
            llm_url = config.get('LLMServer', 'url', fallback='')
            llm_apikey = config.get('LLMServer', 'apikey', fallback='')
            llm_model = config.get('LLMServer', 'model', fallback='')
            llm_api_type = config.get('LLMServer', 'api_type', fallback='openai').lower()
            ssl_verify = config.getboolean('LLMServer', 'ssl_verify', fallback=True)
            
            if not llm_url or not llm_model:
                return {'error': 'LLM server configuration is incomplete in config.ini'}
            
            headers = {"Content-Type": "application/json"}
            if llm_apikey:
                headers["Authorization"] = f"Bearer {llm_apikey}"
            
            if llm_api_type == "openai":
                payload = {
                    "model": llm_model,
                    "messages": chat_history,
                    "stream": True
                }
                target_url = llm_url.rstrip('/') 
                if not target_url.endswith('/chat/completions'):
                    target_url += '/chat/completions' if '/v1' in target_url else '/v1/chat/completions'
            else:  # ollama
                prompt = "\n\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in chat_history])
                payload = {
                    "model": llm_model,
                    "prompt": prompt,
                    "stream": True
                }
                target_url = llm_url.rstrip('/') + "/api/generate"
            
            logging.info(f"Sending streaming request to LLM at {target_url}")
            logging.info(f"Toolbox window exists: {self._toolbox_window is not None}")
            
            if not ssl_verify:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            response = requests.post(target_url, headers=headers, json=payload, stream=True, verify=ssl_verify)
            response.raise_for_status()
            
            full_response = ""
            chunk_count = 0
            
            # Envoyer un callback pour démarrer le streaming
            if self._toolbox_window:
                logging.info(f"Envoi de onStreamStart pour {callback_id}")
                self._toolbox_window.evaluate_js(f'window.onStreamStart && window.onStreamStart("{callback_id}")')
            
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    
                    if llm_api_type == "openai":
                        if line_str.startswith("data: "):
                            if line_str.strip() == "data: [DONE]":
                                break
                            try:
                                json_data = json.loads(line_str[6:])
                                if 'choices' in json_data and len(json_data['choices']) > 0:
                                    delta = json_data['choices'][0].get('delta', {})
                                    if 'content' in delta:
                                        chunk = delta['content']
                                        full_response += chunk
                                        # Envoyer le chunk au frontend
                                        if self._toolbox_window:
                                            chunk_count += 1
                                            if chunk_count % 10 == 1:  # Log tous les 10 chunks
                                                logging.info(f"Envoi du chunk {chunk_count}: {chunk[:20]}...")
                                            escaped_chunk = chunk.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
                                            self._toolbox_window.evaluate_js(f'window.onStreamChunk && window.onStreamChunk("{callback_id}", "{escaped_chunk}")')
                            except json.JSONDecodeError:
                                continue
                    else:  # ollama
                        try:
                            json_data = json.loads(line_str)
                            if 'response' in json_data:
                                chunk = json_data['response']
                                full_response += chunk
                                # Envoyer le chunk au frontend
                                if self._toolbox_window:
                                    escaped_chunk = chunk.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
                                    self._toolbox_window.evaluate_js(f'window.onStreamChunk && window.onStreamChunk("{callback_id}", "{escaped_chunk}")')
                                
                                if json_data.get('done', False):
                                    break
                        except json.JSONDecodeError:
                            continue
            
            # Créer l'historique final et compter les tokens
            final_history = chat_history + [{'role': 'assistant', 'content': full_response}]
            total_tokens = self._count_tokens_for_history(final_history)
            
            # Envoyer la fin du streaming avec le comptage de tokens
            logging.info(f"Streaming terminé, {chunk_count} chunks envoyés, taille totale: {len(full_response)}, tokens: {total_tokens}")
            if self._toolbox_window:
                logging.info(f"Envoi de onStreamEnd pour {callback_id} avec {total_tokens} tokens")
                self._toolbox_window.evaluate_js(f'window.onStreamEnd && window.onStreamEnd("{callback_id}", {total_tokens})')
            
            return {'response': full_response, 'total_tokens': total_tokens}
            
        except Exception as e:
            error_msg = f"Erreur lors du streaming: {str(e)}"
            logging.error(error_msg)
            # Envoyer l'erreur au frontend
            if self._toolbox_window:
                escaped_error = error_msg.replace('\\', '\\\\').replace('"', '\\"')
                self._toolbox_window.evaluate_js(f'window.onStreamError && window.onStreamError("{callback_id}", "{escaped_error}")')
            return {'error': error_msg}
    
    def send_to_llm(self, chat_history, stream=False):
        """Envoie l'historique du chat au LLM et retourne la réponse"""
        try:
            import requests
            import json
            
            # Lire la configuration LLM
            config = configparser.ConfigParser()
            config.read('config.ini', encoding='utf-8')
            
            if not config.getboolean('LLMServer', 'enabled', fallback=False):
                return {'error': 'LLM feature is not enabled in config.ini'}
            
            llm_url = config.get('LLMServer', 'url', fallback='')
            llm_apikey = config.get('LLMServer', 'apikey', fallback='')
            llm_model = config.get('LLMServer', 'model', fallback='')
            llm_api_type = config.get('LLMServer', 'api_type', fallback='openai').lower()
            ssl_verify = config.getboolean('LLMServer', 'ssl_verify', fallback=True)
            
            if not llm_url or not llm_model:
                return {'error': 'LLM server configuration is incomplete in config.ini'}
            
            headers = {"Content-Type": "application/json"}
            if llm_apikey:
                headers["Authorization"] = f"Bearer {llm_apikey}"
            
            if llm_api_type == "openai":
                payload = {
                    "model": llm_model,
                    "messages": chat_history,
                    "stream": stream
                }
                target_url = llm_url.rstrip('/') 
                if not target_url.endswith('/chat/completions'):
                    target_url += '/chat/completions' if '/v1' in target_url else '/v1/chat/completions'
            else:  # ollama
                prompt = "\n\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in chat_history])
                payload = {
                    "model": llm_model,
                    "prompt": prompt,
                    "stream": stream
                }
                target_url = llm_url.rstrip('/') + "/api/generate"
            
            logging.info(f"Sending request to LLM at {target_url} (SSL verify: {ssl_verify})")
            
            if not ssl_verify:
                # Désactiver la vérification SSL pour les environnements d'entreprise
                # ATTENTION : Ceci réduit la sécurité, à utiliser uniquement en environnement contrôlé
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                logging.warning("SSL certificate verification is disabled - use with caution!")
            
            response = requests.post(target_url, headers=headers, json=payload, stream=stream, verify=ssl_verify)
            response.raise_for_status()
            
            if stream:
                # Pour le streaming, collecter toute la réponse
                full_response = ""
                try:
                    for line in response.iter_lines():
                        if line:
                            line_str = line.decode('utf-8')
                            
                            if llm_api_type == "openai":
                                # Format OpenAI : data: {...}
                                if line_str.startswith("data: "):
                                    if line_str.strip() == "data: [DONE]":
                                        break
                                    try:
                                        json_data = json.loads(line_str[6:])
                                        if 'choices' in json_data and len(json_data['choices']) > 0:
                                            delta = json_data['choices'][0].get('delta', {})
                                            if 'content' in delta:
                                                full_response += delta['content']
                                    except json.JSONDecodeError:
                                        continue
                            else:  # ollama
                                # Format Ollama : ligne JSON directe
                                try:
                                    json_data = json.loads(line_str)
                                    if 'response' in json_data:
                                        full_response += json_data['response']
                                        
                                        # Vérifier si c'est le dernier message
                                        if json_data.get('done', False):
                                            break
                                except json.JSONDecodeError:
                                    continue
                    
                    # Créer l'historique final et compter les tokens
                    final_history = chat_history + [{'role': 'assistant', 'content': full_response}]
                    total_tokens = self._count_tokens_for_history(final_history)
                    
                    return {'response': full_response, 'total_tokens': total_tokens}
                except Exception as e:
                    logging.error(f"Erreur lors du streaming: {e}")
                    return {'error': f"Erreur lors du streaming: {str(e)}"}
            else:
                if llm_api_type == "openai":
                    result = response.json()
                    assistant_message = result['choices'][0]['message']['content']
                else:  # ollama
                    result = response.json()
                    assistant_message = result.get('response', '')
                
                # Créer l'historique final et compter les tokens
                final_history = chat_history + [{'role': 'assistant', 'content': assistant_message}]
                total_tokens = self._count_tokens_for_history(final_history)
                
                return {'response': assistant_message, 'total_tokens': total_tokens}
                
        except requests.exceptions.HTTPError as http_err:
            error_msg = f"HTTP error: {http_err}"
            try:
                error_details = http_err.response.json()
                error_msg += f" - Details: {error_details}"
            except:
                pass
            logging.error(error_msg)
            return {'error': error_msg}
        except Exception as e:
            error_msg = f"Erreur lors de la communication avec le LLM: {str(e)}"
            logging.error(error_msg)
            return {'error': error_msg}

    def save_conversation_dialog(self, chat_data):
        """Ouvre une boîte de dialogue pour sauvegarder la conversation"""
        if not self._toolbox_window:
            error_msg = 'Fenêtre Toolbox non disponible'
            logging.error(error_msg)
            return {'success': False, 'error': error_msg}
        
        try:
            # Configurer les types de fichiers
            file_types = (
                'Fichiers Markdown (*.md)',
                'Documents Word (*.docx)', 
                'Fichiers PDF (*.pdf)',
                'Tous les fichiers (*.*)'
            )
            
            # Ouvrir la boîte de dialogue de sauvegarde
            file_path = self._toolbox_window.create_file_dialog(
                webview.SAVE_DIALOG,
                allow_multiple=False,
                file_types=file_types
            )
            
            # Si l'utilisateur annule
            if not file_path:
                return {'success': False, 'cancelled': True}
            
            # S'assurer que le fichier a une extension valide
            path = Path(file_path)
            if path.suffix.lower() not in ['.md', '.docx', '.pdf']:
                # Ajouter l'extension .md par défaut
                file_path = str(path.with_suffix('.md'))
            
            # Appeler le service d'export
            result = self.export_service.generate_export(chat_data, file_path)
            
            if result['success']:
                logging.info(f"Conversation exportée avec succès: {file_path}")
                return {
                    'success': True,
                    'path': file_path,
                    'size': result.get('size', 0)
                }
            else:
                logging.error(f"Erreur lors de l'export: {result.get('error', 'Erreur inconnue')}")
                return result
                
        except Exception as e:
            error_msg = f"Erreur lors de l'export de la conversation: {str(e)}"
            logging.error(error_msg)
            return {'success': False, 'error': error_msg}

def run_flask():
    app.run(port=5000, debug=False)

if __name__ == "__main__":
    logging.info("Démarrage de l'application Desktop Mode")
    logging.info(f"Mode debug: {'activé' if CONFIG['debug'] else 'désactivé'}")
    logging.info(f"Répertoire de données: {DATA_DIR}")
    
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    time.sleep(1)
    
    api = Api()
    
    main_window = webview.create_window(
        "Bureau Mode", 
        "http://127.0.0.1:5000", 
        js_api=api,
        width=1000,
        height=700,
        min_size=(800, 600)
    )
    
    # Définir la référence à la fenêtre principale dans l'API
    api.set_main_window(main_window)
    
    # Démarrer pywebview avec la persistance des données et le mode debug depuis la config
    logging.info(f"Démarrage de pywebview en mode debug: {CONFIG['debug']}")
    webview.start(debug=CONFIG['debug'], private_mode=False, storage_path=DATA_DIR)