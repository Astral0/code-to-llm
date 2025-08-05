import webview
import threading
import time
import os
import json
import appdirs
import configparser
import logging
from pathlib import Path
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
            service_configs['llm_service'] = {
                'enabled': config.getboolean('LLMServer', 'enabled', fallback=False),
                'url': config.get('LLMServer', 'url', fallback=''),
                'apikey': config.get('LLMServer', 'apikey', fallback=''),
                'model': config.get('LLMServer', 'model', fallback=''),
                'api_type': config.get('LLMServer', 'api_type', fallback='openai').lower(),
                'ssl_verify': config.getboolean('LLMServer', 'ssl_verify', fallback=True),
                'stream_response': config.getboolean('LLMServer', 'stream_response', fallback=False),
                'timeout_seconds': config.getint('LLMServer', 'timeout_seconds', fallback=300)
            }
    
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
        self._main_window = None
        self._browser_window = None
        
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