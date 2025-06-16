import os
import subprocess
import platform
import time
import pyperclip
from threading import Thread
import queue
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Note: La logique de StreamingManager et StopButtonMonitor sera intégrée plus tard si nécessaire.
# Pour l'instant, nous nous concentrons sur le lancement, l'attachement et l'envoi.

class BrowserManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BrowserManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        self.driver = None
        self.active_llm = None
        self.process = None
        self.socketio = None
        self.logger = None

    def set_integrations(self, socketio, logger):
        self.socketio = socketio
        self.logger = logger
        self.logger.info("BrowserManager intégré avec Socket.IO et Logger.")

    def _emit_log(self, message):
        if self.socketio:
            self.socketio.emit('browser_log', {'message': message})
        if self.logger:
            self.logger.info(f"[BrowserManager] {message}")

    def _get_chrome_path(self):
        if platform.system() == "Windows":
            # Chercher dans les emplacements communs de Windows
            for path in [r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"]:
                if os.path.exists(path):
                    return path
        elif platform.system() == "Linux":
            return "/usr/bin/google-chrome"
        elif platform.system() == "Darwin": # macOS
            return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        raise FileNotFoundError("Google Chrome n'a pas été trouvé.")

    def launch_browser(self, llm_type, config):
        self.active_llm = llm_type
        chrome_path = self._get_chrome_path()
        login_url = config[llm_type].get('login_url')
        if not login_url:
            self._emit_log(f"Erreur: 'login_url' non trouvé pour le llm_type '{llm_type}' dans la configuration.")
            return False
            
        profile_dir = os.path.join(os.path.expanduser('~'), '.code2llm_chrome_profile')

        if not os.path.exists(profile_dir):
            os.makedirs(profile_dir)

        self.process = subprocess.Popen([
            chrome_path,
            f"--user-data-dir={profile_dir}",
            "--remote-debugging-port=9222",
            login_url
        ])
        self._emit_log(f"Processus Chrome lancé pour {llm_type} sur {login_url}. PID: {self.process.pid}.")
        return True

    def attach_browser(self):
        try:
            options = webdriver.ChromeOptions()
            options.add_experimental_option("debuggerAddress", "localhost:9222")
            self.driver = webdriver.Chrome(options=options)
            self._emit_log(f"Connecté au navigateur Chrome. Titre de la page active : {self.driver.title}")
            return True
        except Exception as e:
            self._emit_log(f"Échec de la connexion au navigateur : {e}")
            self.driver = None
            return False

    def send_context_to_browser(self, context, config, llm_type): # Ajout de llm_type
        if not self.driver:
            self._emit_log("Erreur: Le pilote n'est pas initialisé.")
            return False
        
        self.active_llm = llm_type # Définir active_llm ici
        
        try:
            selector = config[self.active_llm]['prompt_textarea_selector']
            textarea = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
            self._emit_log("Champ de prompt trouvé.")
            
            # Utilisation de pyperclip pour coller le contexte (plus fiable pour les longs textes)
            pyperclip.copy(context)
            textarea.click()
            textarea.clear()
            time.sleep(1) # Ajouter un petit délai après le clear
            # Coller le contenu
            if platform.system() == "Darwin": # macOS
                textarea.send_keys(Keys.COMMAND, 'v')
            else: # Windows/Linux
                textarea.send_keys(Keys.CONTROL, 'v')
            
            self._emit_log("Contexte collé dans le champ de prompt.")
            
            # Soumettre le prompt
            submit_button_selector = config[self.active_llm]['submit_button_selector']
            submit_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, submit_button_selector))
            )
            submit_button.click()
            self._emit_log("Contexte soumis au LLM.")
            return True
        except Exception as e:
            self._emit_log(f"Erreur lors de l'envoi du contexte : {e}")
            self.logger.error(f"Détails de l'erreur lors de l'envoi du contexte: {e}", exc_info=True) # Ajout pour un log plus détaillé
            return False