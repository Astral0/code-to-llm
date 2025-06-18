import webview
import threading
import time
import os
import json
import appdirs
import configparser
import logging
from selenium.webdriver.common.by import By
from pywebview_driver import PywebviewDriver
from web_server import app

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
        return {'debug': False}
    
    # Lire le paramètre debug avec une valeur par défaut
    debug_enabled = config.getboolean('Debug', 'debug', fallback=False)
    
    return {'debug': debug_enabled}

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
        self.driver = None
    
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