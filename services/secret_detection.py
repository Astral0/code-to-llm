# services/secret_detection.py
"""
Service de détection et masquage des secrets
"""
import re
import logging

# Configuration du logger
logger = logging.getLogger(__name__)

# Import optionnel de detect-secrets
try:
    from detect_secrets import SecretsCollection
    from detect_secrets.settings import default_settings
    from detect_secrets.plugins import initialize as initialize_detect_secrets_plugins
    HAS_DETECT_SECRETS = True
except ImportError:
    logger.warning("detect-secrets library not found. Secret masking will be disabled.")
    HAS_DETECT_SECRETS = False

def detect_and_redact_secrets(content, file_path, redact_mode='mask'):
    """
    Détecte et masque les secrets dans le contenu d'un fichier.
    
    Args:
        content (str): Le contenu du fichier à analyser
        file_path (str): Le chemin du fichier (utilisé pour les règles spécifiques au format)
        redact_mode (str): Le mode de redaction ('mask' pour [MASKED SECRET], 'remove' pour supprimer la ligne)
    
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
                logger.debug(f"Plugin {plugin.__class__.__name__} failed for {file_path}: {plugin_error}")
        
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
        logger.error(f"Error using detect-secrets: {e}")
        return content, 0

def detect_and_redact_with_regex(content, file_path):
    """
    Détecte et masque les patterns courants de secrets avec des expressions régulières.
    Complémentaire à detect-secrets pour des cas spécifiques.
    
    Args:
        content (str): Le contenu du fichier
        file_path (str): Le chemin du fichier (pour le logging)
        
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