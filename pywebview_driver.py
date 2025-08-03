# pywebview_driver.py

import webview
# Enum local pour remplacer selenium.By
class By:
    ID = "id"
    NAME = "name"
    CLASS_NAME = "class name"
    TAG_NAME = "tag name"
    CSS_SELECTOR = "css selector"
    XPATH = "xpath"
import json

class PywebviewElement:
    """
    Représente un élément HTML dans la vue pywebview.
    Imite l'objet WebElement de Selenium.
    """
    def __init__(self, window: webview.Window, css_selector: str):
        if not window:
            raise ValueError("L'objet window ne peut pas être nul.")
        self._window = window
        self._selector = css_selector.replace("'", "\\'") # Échapper les apostrophes pour JS

    def _execute_js(self, command: str):
        """Exécute du JS sur l'élément et retourne le résultat."""
        js_code = f"document.querySelector('{self._selector}').{command}"
        return self._window.evaluate_js(js_code)

    def click(self):
        """Simule un clic sur l'élément."""
        print(f"DRIVER ACTION: Clic sur l'élément '{self._selector}'")
        self._execute_js("click()")

    def send_keys(self, text: str):
        """Simule la saisie de texte dans un champ de formulaire."""
        # Échapper les caractères spéciaux pour l'injection dans une chaîne JS
        escaped_text = json.dumps(text)
        print(f"DRIVER ACTION: Saisie de {escaped_text} dans '{self._selector}'")
        
        # Version améliorée pour éviter les problèmes de sécurité avec innerHTML
        js_code = f"""
        (function() {{
            const element = document.querySelector('{self._selector}');
            if (!element) {{
                console.log('Élément non trouvé avec le sélecteur: {self._selector}');
                return 'ELEMENT_NOT_FOUND';
            }}
            
            const text = {escaped_text};
            console.log('Injection de texte dans:', element);
            
            // Méthode 1: Propriété value (pour les inputs normaux)
            if (element.tagName === 'INPUT' || element.tagName === 'TEXTAREA') {{
                element.value = text;
                element.dispatchEvent(new Event('input', {{ bubbles: true }}));
                element.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return 'INPUT_VALUE_SET';
            }}
            
            // Méthode 2: Pour les éléments contentEditable - ÉVITER innerHTML
            if (element.isContentEditable || element.getAttribute('contenteditable') === 'true') {{
                // Focus sur l'élément d'abord
                element.focus();
                element.click();
                
                // Sélectionner tout le contenu existant
                const selection = window.getSelection();
                const range = document.createRange();
                range.selectNodeContents(element);
                selection.removeAllRanges();
                selection.addRange(range);
                
                // Utiliser textContent au lieu de innerHTML pour éviter les erreurs CSP
                element.textContent = text;
                
                // Déclencher les événements nécessaires
                element.dispatchEvent(new Event('input', {{ bubbles: true }}));
                element.dispatchEvent(new Event('change', {{ bubbles: true }}));
                
                // Placer le curseur à la fin
                range.selectNodeContents(element);
                range.collapse(false);
                selection.removeAllRanges();
                selection.addRange(range);
                
                return 'CONTENTEDITABLE_TEXTCONTENT_SET';
            }}
            
            // Méthode 3: Utiliser document.execCommand si disponible
            if (document.execCommand) {{
                element.focus();
                element.click();
                
                // Sélectionner tout d'abord
                document.execCommand('selectAll');
                
                // Insérer le texte
                const success = document.execCommand('insertText', false, text);
                if (success) {{
                    return 'EXECCOMMAND_SUCCESS';
                }}
            }}
            
            // Méthode 4: Simulation d'événements clavier avec Clipboard API
            element.focus();
            element.click();
            
            // Essayer d'utiliser l'API Clipboard moderne
            if (navigator.clipboard && navigator.clipboard.writeText) {{
                navigator.clipboard.writeText(text).then(() => {{
                    // Sélectionner tout le contenu
                    document.execCommand('selectAll');
                    // Coller
                    document.execCommand('paste');
                }}).catch(() => {{
                    // Fallback si le clipboard ne fonctionne pas
                    element.textContent = text;
                    element.dispatchEvent(new Event('input', {{ bubbles: true }}));
                }});
                return 'CLIPBOARD_API_USED';
            }}
            
            // Méthode 5: Fallback avec textContent
            element.textContent = text;
            element.dispatchEvent(new Event('focus', {{ bubbles: true }}));
            element.dispatchEvent(new Event('input', {{ bubbles: true }}));
            element.dispatchEvent(new Event('change', {{ bubbles: true }}));
            element.dispatchEvent(new Event('blur', {{ bubbles: true }}));
            
            return 'TEXTCONTENT_FALLBACK';
        }})();
        """
        
        result = self._window.evaluate_js(js_code)
        print(f"DRIVER RESULT: {result}")
        
        return result
        
    @property
    def text(self) -> str:
        """Récupère le contenu textuel de l'élément (similaire à .innerText)."""
        return self._execute_js("innerText")

    def get_attribute(self, attribute_name: str) -> str:
        """Récupère la valeur d'un attribut de l'élément."""
        return self._execute_js(f"getAttribute('{attribute_name}')")


class PywebviewDriver:
    """
    Un 'driver' qui imite l'API de Selenium pour contrôler une fenêtre pywebview.
    """
    def __init__(self, window: webview.Window):
        if not window:
            raise ValueError("L'objet window ne peut pas être nul.")
        self._window = window

    def find_element(self, by: By, value: str) -> PywebviewElement:
        """
        Trouve un élément en utilisant une stratégie 'By'.
        Retourne un objet PywebviewElement pour enchaîner les actions.
        NOTE : Seules les stratégies CSS les plus courantes sont implémentées.
        """
        css_selector = ""
        if by == By.ID:
            css_selector = f"#{value}"
        elif by == By.NAME:
            css_selector = f"[name='{value}']"
        elif by == By.CLASS_NAME:
            # Attention: ne prend que la première classe si plusieurs sont fournies
            css_selector = f".{value.split(' ')[0]}"
        elif by == By.CSS_SELECTOR:
            css_selector = value
        elif by == By.TAG_NAME:
            css_selector = value
        elif by == By.LINK_TEXT:
            css_selector = f"a:contains('{value}')" # Note: :contains est spécifique à jQuery, nécessite une adaptation
            # Adaptation pour du JS pur
            # Pour l'instant, on se limite aux sélecteurs CSS directs pour la simplicité.
            raise NotImplementedError("By.LINK_TEXT n'est pas supporté directement. Utilisez By.CSS_SELECTOR.")
        elif by == By.XPATH:
            raise NotImplementedError("By.XPATH n'est pas supporté. Utilisez By.CSS_SELECTOR.")
        else:
            raise ValueError(f"La stratégie de recherche '{by}' n'est pas supportée.")

        print(f"DRIVER ACTION: Recherche de l'élément avec le sélecteur '{css_selector}'")
        return PywebviewElement(self._window, css_selector)

    def get(self, url: str):
        """Charge une nouvelle URL dans la fenêtre."""
        print(f"DRIVER ACTION: Chargement de l'URL '{url}'")
        self._window.load_url(url)

    def get_current_url(self) -> str:
        """Retourne l'URL actuelle de la fenêtre."""
        return self._window.get_current_url()

    def quit(self):
        """Ferme la fenêtre du navigateur."""
        print("DRIVER ACTION: Fermeture de la fenêtre")
        self._window.destroy()

    def debug_page_elements(self):
        """Debug: Liste les éléments potentiels pour la saisie de texte"""
        js_code = """
        (function() {
            const elements = [];
            
            // Chercher tous les éléments de saisie possibles pour Gemini
            const selectors = [
                'input[type="text"]',
                'textarea', 
                '[contenteditable="true"]',
                '[contenteditable]',
                '[role="textbox"]',
                '[data-testid*="textbox"]',
                '[data-testid*="input"]',
                'div[aria-label*="message"]',
                'div[aria-label*="chat"]',
                'div[aria-label*="prompt"]',
                'div[aria-label*="Demandez"]',
                '.ql-editor',
                '[data-placeholder*="Demandez"]',
                'div[contenteditable="plaintext-only"]'
            ];
            
            selectors.forEach(selector => {
                const found = document.querySelectorAll(selector);
                found.forEach((el, index) => {
                    elements.push({
                        selector: selector,
                        index: index,
                        tagName: el.tagName,
                        id: el.id,
                        className: el.className,
                        ariaLabel: el.getAttribute('aria-label'),
                        placeholder: el.placeholder,
                        dataPlaceholder: el.getAttribute('data-placeholder'),
                        contentEditable: el.contentEditable,
                        visible: el.offsetWidth > 0 && el.offsetHeight > 0,
                        rect: el.getBoundingClientRect()
                    });
                });
            });
            
            return elements;
        })();
        """
        
        result = self._window.evaluate_js(js_code)
        print("ELEMENTS DE SAISIE DETECTES:")
        for i, element in enumerate(result):
            print(f"  {i+1}. {element}")
        
        return result

    def execute_script(self, script):
        """Exécute du JavaScript arbitraire dans la page"""
        return self._window.evaluate_js(script)
