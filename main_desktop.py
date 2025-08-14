import webview
import threading
import time
import os
import json
import appdirs
import configparser
import logging
import uuid
import getpass
import socket
import re
from pathlib import Path
from datetime import datetime, timezone
# Enum local pour remplacer selenium.By
class By:
    ID = "id"
    NAME = "name"
    CLASS_NAME = "class name"
    TAG_NAME = "tag name"
    CSS_SELECTOR = "css selector"
    XPATH = "xpath"
from pywebview_driver import PywebviewDriver
from web_server import app
from services.export_service import ExportService
from services.git_service import GitService
from services.llm_api_service import LlmApiService
from services.file_service import FileService
from services.context_builder_service import ContextBuilderService

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

# Charger les configurations spécifiques aux services
def safe_parse_config_value(config, section, option, value_type=str, default=None):
    """
    Parse de manière sûre une valeur de configuration en gérant les commentaires inline.
    
    Args:
        config: ConfigParser instance
        section: Section du fichier config
        option: Option à lire
        value_type: Type attendu (str, int, float, bool)
        default: Valeur par défaut si le parsing échoue
        
    Returns:
        La valeur parsée ou default
    """
    if not config.has_option(section, option):
        return default
        
    try:
        value = config.get(section, option)
        
        # Nettoyer les commentaires inline si présents
        if '#' in value:
            value = value.split('#')[0].strip()
            
        if value_type == bool:
            return config.getboolean(section, option, fallback=default)
        elif value_type == int:
            return int(value)
        elif value_type == float:
            return float(value)
        else:
            return value
            
    except (ValueError, TypeError) as e:
        logging.warning(f"Impossible de parser {section}.{option}='{value}' comme {value_type.__name__}: {e}")
        return default

def load_service_configs():
    """Charge les configurations spécifiques pour chaque service"""
    config = configparser.ConfigParser()
    config_path = 'config.ini'
    
    service_configs = {
        'file_service': CONFIG.copy(),  # FileService utilise la config globale
        'git_service': {},  # GitService utilise seulement le chemin git
        'llm_service': {}   # LlmApiService aura sa propre config
    }
    
    if os.path.exists(config_path):
        config.read(config_path, encoding='utf-8')
        
        # Configuration Git
        if 'Git' in config:
            service_configs['git_service']['executable_path'] = config.get('Git', 'executable_path', fallback='git')
        
        # Configuration LLM
        if 'LLMServer' in config:
            llm_config = {
                'enabled': config.getboolean('LLMServer', 'enabled', fallback=False),
                'url': config.get('LLMServer', 'url', fallback=''),
                'apikey': config.get('LLMServer', 'apikey', fallback=''),
                'model': config.get('LLMServer', 'model', fallback=''),
                'api_type': config.get('LLMServer', 'api_type', fallback='openai').lower(),
                'ssl_verify': config.getboolean('LLMServer', 'ssl_verify', fallback=True),
                'stream_response': config.getboolean('LLMServer', 'stream_response', fallback=False),
                'timeout_seconds': config.getint('LLMServer', 'timeout_seconds', fallback=300)
            }
            
            # Ajouter les paramètres optionnels s'ils existent
            temp = safe_parse_config_value(config, 'LLMServer', 'temperature', float, None)
            if temp is not None:
                llm_config['temperature'] = temp
                
            max_tokens = safe_parse_config_value(config, 'LLMServer', 'max_tokens', int, None)
            if max_tokens is not None:
                llm_config['max_tokens'] = max_tokens
                    
            service_configs['llm_service'] = llm_config
    
    return service_configs

SERVICE_CONFIGS = load_service_configs()

# Configurer les logs selon le paramètre debug
if CONFIG['debug']:
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
    print("Mode debug activé - logs détaillés activés")
else:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    print("Mode normal - logs basiques activés")

class Api:
    def __init__(self):
        # Initialiser le logger pour cette classe
        self.logger = logging.getLogger(self.__class__.__name__)
        
        self._main_window = None
        self._browser_window = None
        
        # Générer un ID unique pour cette instance
        self.instance_id = str(uuid.uuid4())
        self.logger.info(f"Instance API initialisée avec l'ID: {self.instance_id}")
        
        # Créer le répertoire conversations
        self.conversations_dir = os.path.join(DATA_DIR, 'conversations')
        os.makedirs(self.conversations_dir, exist_ok=True)
        
        # Initialisation des services avec leurs configurations spécifiques
        self.git_service = GitService(SERVICE_CONFIGS['git_service'])
        self.llm_service = LlmApiService(SERVICE_CONFIGS['llm_service'])
        self.file_service = FileService(SERVICE_CONFIGS['file_service'])
        self.context_builder = ContextBuilderService({})
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
    
    def check_browser_status(self):
        """Vérifie si la fenêtre navigateur est active"""
        if not self._browser_window:
            return {'active': False, 'error': 'Aucune fenêtre navigateur ouverte'}
        
        # Vérifier si la fenêtre a été détruite
        if hasattr(self._browser_window, 'destroyed') and self._browser_window.destroyed:
            self._browser_window = None
            self.driver = None
            return {'active': False, 'error': 'La fenêtre navigateur a été fermée'}
        
        try:
            # Vérifier que le driver peut encore communiquer avec la fenêtre
            if self.driver:
                url = self.driver.get_current_url()
                return {'active': True, 'url': url}
            else:
                return {'active': False, 'error': 'Driver non initialisé'}
        except Exception as e:
            # Si une erreur survient, la fenêtre est probablement fermée
            self._browser_window = None
            self.driver = None
            return {'active': False, 'error': f'Erreur de communication avec le navigateur: {str(e)}'}
    
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
        result = self.file_service.scan_local_directory(directory_path)
        if result.get('success'):
            self.current_directory = result.get('directory')
            self.file_cache = result.get('file_cache', [])
            return result.get('response_for_frontend')
        else:
            return {'success': False, 'error': result.get('error', 'Erreur inconnue')}
    
    def get_file_content(self, relative_path):
        """Récupère le contenu d'un fichier depuis le cache local"""
        return self.file_service.get_file_content(relative_path, self.current_directory, self.file_cache)
    
    def generate_context_from_selection(self, selected_files, instructions=""):
        """Génère le contexte depuis une sélection de fichiers locaux"""
        # Étape 1: Récupérer les contenus des fichiers
        file_result = self.file_service.get_file_contents_batch(
            selected_files,
            self.current_directory,
            self.file_cache
        )
        
        if not file_result.get('success'):
            return file_result
        
        # Étape 2: Construire le contexte avec le ContextBuilderService
        context_result = self.context_builder.build_context(
            project_name=os.path.basename(self.current_directory),
            directory_path=self.current_directory,
            file_contents=file_result['file_contents'],
            instructions=instructions
        )
        
        if context_result.get('success'):
            # Stocker le contexte pour la Toolbox
            self._last_generated_context = context_result['context']
            
            # Calculer les statistiques complètes pour le frontend
            file_contents = file_result['file_contents']
            
            # Calculer le nombre total de lignes
            total_lines = sum(content['content'].count('\n') + 1 for content in file_contents)
            
            # Trier les fichiers par taille et prendre les 10 plus gros
            largest_files = sorted(file_contents, key=lambda f: f['size'], reverse=True)[:10]
            formatted_largest_files = [{'path': f['path'], 'size': f['size']} for f in largest_files]
            
            # Obtenir le nombre total de fichiers scannés (avant sélection)
            total_scanned_files = len(self.file_cache) if self.file_cache else len(selected_files)
            included_count = len(selected_files)
            
            # Rendre le format compatible avec l'ancien format attendu par le frontend
            return {
                'success': True,
                'context': context_result['context'],
                'stats': {
                    'total_files': total_scanned_files,
                    'included_files_count': included_count,
                    'excluded_files_count': total_scanned_files - included_count,
                    'total_lines': total_lines,
                    'total_chars': context_result['stats']['total_chars'],
                    'estimated_tokens': context_result['stats']['estimated_tokens'],
                    'largest_files': formatted_largest_files,
                    'secrets_masked': 0,  # Le masquage n'est pas implémenté en local
                    'files_with_secrets': []
                }
            }
        else:
            return context_result
    
    
    def open_toolbox_window(self, mode='api', target_url=None):
        """
        Ouvre une nouvelle fenêtre pour la Toolbox Développeur
        mode: 'api' ou 'browser'
        target_url: 'gemini', 'chatgpt' ou 'claude' pour le mode browser
        """
        try:
            logging.info(f"Ouverture de la fenêtre Toolbox Développeur en mode {mode}")
            
            # En mode browser, s'assurer que la fenêtre navigateur est ouverte
            if mode == 'browser':
                if not self._browser_window or (hasattr(self._browser_window, 'destroyed') and self._browser_window.destroyed):
                    # Déterminer l'URL selon target_url
                    urls = {
                        'gemini': 'https://gemini.google.com',
                        'chatgpt': 'https://chat.openai.com',
                        'claude': 'https://claude.ai/chat'
                    }
                    browser_url = urls.get(target_url, urls['gemini'])
                    
                    logging.info(f"Création de la fenêtre navigateur pour {target_url} - URL: {browser_url}")
                    
                    # Créer la fenêtre navigateur
                    self._browser_window = webview.create_window(
                        f"Navigateur - {target_url.title() if target_url else 'Chatbot'}",
                        browser_url,
                        width=1200,
                        height=800,
                        x=100,  # Position décalée
                        y=100
                    )
                    
                    # Initialiser le driver
                    self.driver = PywebviewDriver(self._browser_window)
                    
                    # Attendre que la fenêtre soit prête
                    import time
                    time.sleep(2)
            
            # Créer la fenêtre Toolbox
            self._toolbox_window = webview.create_window(
                "Toolbox Développeur Augmenté",
                "http://127.0.0.1:5000/toolbox",
                js_api=self,  # Partager la même API
                width=1400,
                height=800,
                min_size=(1200, 600),
                x=200,  # Position légèrement décalée
                y=150
            )
            
            # Passer le mode au JavaScript une fois chargé
            def on_toolbox_loaded():
                js_code = f"""
                    window.toolboxMode = '{mode}';
                    window.toolboxTarget = '{target_url or ''}';
                    if (window.initializeToolboxMode) {{
                        window.initializeToolboxMode();
                    }}
                """
                self._toolbox_window.evaluate_js(js_code)
                logging.info(f"Mode {mode} injecté dans la fenêtre Toolbox")
            
            self._toolbox_window.events.loaded += on_toolbox_loaded
            
            return {'success': True, 'message': f'Fenêtre Toolbox ouverte avec succès en mode {mode}'}
            
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
        """Exécute git diff --staged et retourne le résultat"""
        print("=== APPEL run_git_diff ===")
        print(f"Répertoire actuel: {self.current_directory}")
        logging.info("=== APPEL run_git_diff ===")
        logging.info(f"Répertoire actuel: {self.current_directory}")
        
        if not self.current_directory:
            logging.error("Aucun répertoire de travail sélectionné")
            return {'error': 'Aucun répertoire de travail sélectionné'}
        
        try:
            result = self.git_service.run_git_diff(self.current_directory)
            print(f"Résultat de git_service.run_git_diff: {result.keys()}")
            if 'diff' in result:
                print(f"Taille du diff: {len(result['diff'])} caractères")
                if result['diff']:
                    print(f"Début du diff: {result['diff'][:100]}...")
                else:
                    print("Le diff est vide")
            if 'error' in result:
                print(f"Erreur retournée: {result['error']}")
            return result
        except Exception as e:
            logging.error(f"Erreur lors de l'exécution de git diff: {str(e)}")
            return {'error': str(e)}
    
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
    
    
    def send_to_llm_stream(self, chat_history, callback_id):
        """Envoie l'historique au LLM en mode streaming avec callback vers le frontend"""
        logging.info(f"send_to_llm_stream appelé avec callback_id: {callback_id}")
        
        # Créer les callbacks pour gérer l'interaction avec la fenêtre
        def on_start():
            if self._toolbox_window:
                logging.info(f"Envoi de onStreamStart pour {callback_id}")
                self._toolbox_window.evaluate_js(f'window.onStreamStart && window.onStreamStart("{callback_id}")')
        
        def on_chunk(chunk):
            if self._toolbox_window:
                escaped_chunk = chunk.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
                self._toolbox_window.evaluate_js(f'window.onStreamChunk && window.onStreamChunk("{callback_id}", "{escaped_chunk}")')
        
        def on_end(total_tokens):
            if self._toolbox_window:
                logging.info(f"Envoi de onStreamEnd pour {callback_id} avec {total_tokens} tokens")
                self._toolbox_window.evaluate_js(f'window.onStreamEnd && window.onStreamEnd("{callback_id}", {total_tokens})')
        
        def on_error(error_msg):
            if self._toolbox_window:
                escaped_error = error_msg.replace('\\', '\\\\').replace('"', '\\"')
                self._toolbox_window.evaluate_js(f'window.onStreamError && window.onStreamError("{callback_id}", "{escaped_error}")')
        
        try:
            return self.llm_service.send_to_llm_stream(
                chat_history, 
                on_start=on_start,
                on_chunk=on_chunk,
                on_end=on_end,
                on_error=on_error
            )
        except Exception as e:
            logging.error(f"Erreur lors de l'appel au LLM en streaming: {str(e)}")
            on_error(str(e))
            return {'error': str(e)}
    
    def send_to_llm(self, chat_history, stream=False):
        """Envoie l'historique du chat au LLM et retourne la réponse"""
        try:
            return self.llm_service.send_to_llm(chat_history, stream)
        except Exception as e:
            logging.error(f"Erreur lors de l'appel au LLM: {str(e)}")
            return {'error': str(e)}
    
    def generate_conversation_title(self, chat_history):
        """
        Demande au service LLM de générer un titre basé sur l'historique.
        
        Args:
            chat_history: L'historique de la conversation.
        
        Returns:
            Un dictionnaire avec le titre suggéré.
        """
        try:
            self.logger.info("Génération d'un titre pour la conversation")
            suggested_title = self.llm_service.generate_title(chat_history)
            
            if suggested_title:
                self.logger.info(f"Titre généré avec succès: {suggested_title}")
                return {'success': True, 'title': suggested_title}
            else:
                self.logger.info("Aucun titre généré, utilisation du fallback")
                return {'success': True, 'title': ''}
                
        except Exception as e:
            self.logger.error(f"Erreur dans la façade API lors de la génération du titre: {e}")
            return {'success': False, 'error': str(e), 'title': ''}

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
    
    def get_conversations(self):
        """Récupère la liste des conversations avec leur statut de verrouillage"""
        try:
            conversations = []
            
            # Parcourir tous les fichiers JSON dans le répertoire
            for filename in os.listdir(self.conversations_dir):
                if filename.endswith('.json'):
                    filepath = os.path.join(self.conversations_dir, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        # Extraire les informations de verrouillage
                        lock = data.get('metadata', {}).get('lock', {})
                        is_locked = lock.get('active', False)
                        is_locked_by_me = is_locked and lock.get('instanceId') == self.instance_id
                        
                        conversations.append({
                            'id': data.get('id'),
                            'title': data.get('title', 'Sans titre'),
                            'updatedAt': data.get('updatedAt', ''),
                            'isLocked': is_locked,
                            'isLockedByMe': is_locked_by_me,
                            'lockInfo': f"{lock.get('user', 'inconnu')}@{lock.get('host', 'inconnu')}" if is_locked else None
                        })
                    except Exception as e:
                        logging.error(f"Erreur lors de la lecture de {filename}: {str(e)}")
                        continue
            
            # Trier par date de mise à jour (plus récent en premier)
            conversations.sort(key=lambda x: x['updatedAt'], reverse=True)
            
            return conversations
            
        except Exception as e:
            logging.error(f"Erreur lors de la récupération des conversations: {str(e)}")
            return []
    
    def save_conversation(self, conversation_data, force_save=False):
        """Sauvegarde une conversation avec verrouillage automatique"""
        try:
            conv_id = conversation_data.get('id')
            
            # Si c'est une nouvelle conversation, générer un ID
            if not conv_id:
                conv_id = str(uuid.uuid4())
                conversation_data['id'] = conv_id
                conversation_data['createdAt'] = datetime.now(timezone.utc).isoformat()
            
            # Vérifier le verrouillage existant si nécessaire
            if conv_id and not force_save:
                filepath = os.path.join(self.conversations_dir, f"{conv_id}.json")
                if os.path.exists(filepath):
                    with open(filepath, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                    
                    existing_lock = existing_data.get('metadata', {}).get('lock', {})
                    if existing_lock.get('active', False) and existing_lock.get('instanceId') != self.instance_id:
                        lock_info = f"{existing_lock.get('user', 'inconnu')}@{existing_lock.get('host', 'inconnu')}"
                        raise ValueError(f"Conversation verrouillée par {lock_info}")
            
            # Mettre à jour les métadonnées
            conversation_data['updatedAt'] = datetime.now(timezone.utc).isoformat()
            conversation_data['version'] = '2.0'
            
            # Appliquer notre verrou
            conversation_data.setdefault('metadata', {})
            conversation_data['metadata']['lock'] = {
                'active': True,
                'instanceId': self.instance_id,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'user': getpass.getuser(),
                'host': socket.gethostname()
            }
            
            # Sauvegarder le fichier
            filepath = os.path.join(self.conversations_dir, f"{conv_id}.json")
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(conversation_data, f, ensure_ascii=False, indent=2)
            
            logging.info(f"Conversation {conv_id} sauvegardée avec succès")
            return {'success': True, 'id': conv_id, 'title': conversation_data.get('title', 'Sans titre')}
            
        except Exception as e:
            logging.error(f"Erreur lors de la sauvegarde de la conversation: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def get_conversation_details(self, conversation_id):
        """Récupère les détails complets d'une conversation"""
        try:
            filepath = os.path.join(self.conversations_dir, f"{conversation_id}.json")
            if not os.path.exists(filepath):
                raise FileNotFoundError(f"Conversation {conversation_id} non trouvée")
            
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        except Exception as e:
            logging.error(f"Erreur lors de la récupération de la conversation {conversation_id}: {str(e)}")
            return None
    
    def release_conversation_lock(self, conversation_id):
        """Libère le verrou d'une conversation"""
        try:
            filepath = os.path.join(self.conversations_dir, f"{conversation_id}.json")
            if not os.path.exists(filepath):
                return {'success': False, 'error': 'Conversation non trouvée'}
            
            # Lire directement le fichier
            with open(filepath, 'r', encoding='utf-8') as f:
                conversation = json.load(f)
            
            # Désactiver le verrou
            if 'metadata' in conversation and 'lock' in conversation['metadata']:
                conversation['metadata']['lock']['active'] = False
            
            # Sauvegarder directement
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(conversation, f, ensure_ascii=False, indent=2)
            
            logging.info(f"Verrou libéré pour la conversation {conversation_id}")
            return {'success': True}
            
        except Exception as e:
            logging.error(f"Erreur lors de la libération du verrou: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def force_release_lock(self, conversation_id: str) -> dict:
        """
        Force la libération du verrou pour une conversation spécifique.
        
        Args:
            conversation_id: L'ID de la conversation à déverrouiller.
        
        Returns:
            Dictionnaire avec le statut de l'opération.
        """
        try:
            filepath = os.path.join(self.conversations_dir, f"{conversation_id}.json")
            if not os.path.exists(filepath):
                return {'success': False, 'error': 'Conversation non trouvée'}

            with open(filepath, 'r', encoding='utf-8') as f:
                conversation = json.load(f)

            lock = conversation.get('metadata', {}).get('lock', {})
            if lock.get('active', False):
                # Log détaillé pour la traçabilité
                previous_owner = lock.get('user', 'inconnu')
                previous_host = lock.get('host', 'inconnu')
                logging.warning(f"Déverrouillage forcé de {conversation_id} - Propriétaire précédent: {previous_owner}@{previous_host}, Par: {getpass.getuser()}@{socket.gethostname()}")
                
                lock['active'] = False
                conversation['metadata']['lock'] = lock
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(conversation, f, ensure_ascii=False, indent=2)
                
                return {'success': True, 'message': 'Verrou libéré avec succès.'}
            else:
                return {'success': True, 'message': 'La conversation n\'était pas verrouillée.'}

        except Exception as e:
            error_msg = f"Erreur lors de la libération forcée du verrou : {str(e)}"
            logging.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def delete_conversation(self, conversation_id):
        """Supprime une conversation"""
        try:
            filepath = os.path.join(self.conversations_dir, f"{conversation_id}.json")
            if os.path.exists(filepath):
                os.remove(filepath)
                logging.info(f"Conversation {conversation_id} supprimée")
                return {'success': True}
            else:
                return {'success': False, 'error': 'Conversation non trouvée'}
        
        except Exception as e:
            logging.error(f"Erreur lors de la suppression de la conversation: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def update_conversation_title(self, conversation_id: str, new_title: str) -> dict:
        """Met à jour le titre d'une conversation avec validation."""
        try:
            # Validation du titre
            if not new_title or not new_title.strip():
                return {'success': False, 'error': 'Le titre ne peut pas être vide'}
            
            if len(new_title) > 100:
                return {'success': False, 'error': 'Le titre ne peut pas dépasser 100 caractères'}
            
            filepath = os.path.join(self.conversations_dir, f"{conversation_id}.json")
            if not os.path.exists(filepath):
                return {'success': False, 'error': 'Conversation non trouvée'}

            with open(filepath, 'r', encoding='utf-8') as f:
                conversation = json.load(f)
            
            # Vérification du verrou
            lock = conversation.get('metadata', {}).get('lock', {})
            if lock.get('active', False) and lock.get('instanceId') != self.instance_id:
                return {'success': False, 'error': f"Conversation verrouillée par {lock.get('user', 'inconnu')}"}

            conversation['title'] = new_title.strip()
            conversation['updatedAt'] = datetime.now(timezone.utc).isoformat()
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(conversation, f, ensure_ascii=False, indent=2)
            
            logging.info(f"Titre de la conversation {conversation_id} mis à jour: {new_title}")
            return {'success': True, 'id': conversation_id, 'title': new_title.strip()}
            
        except Exception as e:
            error_msg = f"Erreur lors de la mise à jour du titre: {str(e)}"
            logging.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def duplicate_conversation(self, conversation_id: str) -> dict:
        """
        Duplique une conversation. La nouvelle conversation n'est pas verrouillée
        et appartient à l'instance actuelle.
        """
        try:
            source_conv = self.get_conversation_details(conversation_id)
            if not source_conv:
                return {'success': False, 'error': 'Conversation source non trouvée'}

            # Création d'un objet propre au lieu d'une copie
            # On ne prend que les données nécessaires de la source
            new_conv_data = {
                "history": source_conv.get('history', []),
                "context": source_conv.get('context', {})
                # L'ID, titre, dates, version et métadonnées seront créés par save_conversation
            }

            # Gestion intelligente du titre pour éviter "Copie de Copie de..."
            original_title = source_conv.get('title', 'Sans titre')
            # Utilise une regex pour trouver "Copie de (N)"
            match = re.match(r'Copie de \((\d+)\) (.+)', original_title)
            if match:
                count = int(match.group(1)) + 1
                base_title = match.group(2)
                new_title = f"Copie de ({count}) {base_title}"
            elif original_title.startswith('Copie de '):
                # Si c'est déjà "Copie de X" sans numéro, on ajoute (2)
                base_title = original_title[9:]  # Enlève "Copie de "
                new_title = f"Copie de (2) {base_title}"
            else:
                # Si c'est la première copie
                new_title = f"Copie de {original_title}"
            
            new_conv_data['title'] = new_title

            logging.info(f"Duplication de la conversation '{original_title}' vers '{new_title}'")
            
            # save_conversation va maintenant créer une conversation 100% neuve et propre
            return self.save_conversation(new_conv_data)
            
        except Exception as e:
            error_msg = f"Erreur lors de la duplication : {str(e)}"
            logging.error(error_msg, exc_info=True)  # exc_info=True pour avoir la stack trace
            return {'success': False, 'error': error_msg}
    
    def close_toolbox_window(self):
        """Ferme proprement la fenêtre toolbox"""
        try:
            if self._toolbox_window:
                try:
                    self._toolbox_window.destroy()
                    logging.info("Fenêtre Toolbox fermée proprement")
                except Exception as destroy_error:
                    # La fenêtre pourrait déjà être fermée
                    logging.debug(f"Erreur lors de la destruction de la fenêtre (peut être ignorée): {destroy_error}")
                finally:
                    self._toolbox_window = None
                return {'success': True}
            return {'success': False, 'error': 'Aucune fenêtre Toolbox ouverte'}
        except Exception as e:
            logging.error(f"Erreur lors de la fermeture de la Toolbox: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def release_all_instance_locks(self):
        """Libère tous les verrous créés par l'utilisateur actuel sur cette machine."""
        try:
            released_count = 0
            
            # Récupérer l'utilisateur et l'hôte actuels
            current_user = getpass.getuser()
            current_host = socket.gethostname()
            
            logging.info(f"Libération de tous les verrous pour {current_user}@{current_host}")

            # Parcourir tous les fichiers de conversations
            for filename in os.listdir(self.conversations_dir):
                if filename.endswith('.json'):
                    filepath = os.path.join(self.conversations_dir, filename)
                    try:
                        # Lire le fichier
                        with open(filepath, 'r', encoding='utf-8') as f:
                            conversation = json.load(f)
                        
                        lock = conversation.get('metadata', {}).get('lock', {})
                        
                        # Condition de vérification changée : on compare l'utilisateur et l'hôte
                        if (lock.get('active', False) and 
                            lock.get('user') == current_user and 
                            lock.get('host') == current_host):
                            
                            # Libérer le verrou
                            conversation['metadata']['lock']['active'] = False
                            
                            # Sauvegarder
                            with open(filepath, 'w', encoding='utf-8') as f:
                                json.dump(conversation, f, ensure_ascii=False, indent=2)
                            
                            released_count += 1
                            logging.info(f"Verrou orphelin libéré pour {conversation.get('title', filename)}")
                    
                    except Exception as e:
                        logging.error(f"Erreur lors du traitement de {filename} pour libérer le verrou: {str(e)}")
                        continue
            
            message = f"{released_count} verrou(x) libéré(s)" if released_count > 0 else "Aucun verrou actif trouvé pour cet utilisateur."
            return {'success': True, 'count': released_count, 'message': message}
            
        except Exception as e:
            logging.error(f"Erreur lors de la libération des verrous: {str(e)}")
            return {'success': False, 'error': str(e)}

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