#!/usr/bin/env python3
"""
Utilitaires partagés pour les tests.
"""

from urllib.parse import urlsplit, urlunsplit


def mask_credentials(url):
    """
    Masque les identifiants (username/password) dans une URL.
    
    Args:
        url (str): L'URL à masquer
        
    Returns:
        str: L'URL avec les identifiants masqués
        
    Examples:
        >>> mask_credentials("http://user:pass@proxy.com:8080")
        "http://proxy.com:8080"
        >>> mask_credentials("https://proxy.com:8080")
        "https://proxy.com:8080"
    """
    if not url:
        return url
    
    parts = urlsplit(url)
    if parts.username or parts.password:
        # Reconstruire le netloc sans les credentials
        netloc = f"{parts.hostname}:{parts.port}" if parts.port else parts.hostname or ''
        # Reconstruire l'URL complète sans les credentials
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    
    return url


def check_no_proxy_match(hostname, no_proxy_list):
    """
    Vérifie si un hostname correspond à une entrée dans la liste no_proxy.
    
    Suit la sémantique standard no_proxy :
    - Correspondance exacte : "example.com" matche uniquement "example.com"
    - Correspondance de sous-domaine : "example.com" matche aussi "www.example.com"
    - Entrée avec point : ".example.com" matche les sous-domaines mais pas le domaine lui-même
    
    Args:
        hostname (str): Le nom d'hôte à vérifier
        no_proxy_list (list): Liste des domaines/hôtes à exclure du proxy
        
    Returns:
        bool: True si le hostname doit bypasser le proxy
        
    Examples:
        >>> check_no_proxy_match("www.example.com", ["example.com"])
        True
        >>> check_no_proxy_match("example.com", ["example.com"])
        True
        >>> check_no_proxy_match("other.com", ["example.com"])
        False
    """
    if not hostname or not no_proxy_list:
        return False
    
    hostname = hostname.lower()
    
    for entry in no_proxy_list:
        if not entry:
            continue
            
        entry = entry.lower().strip()
        
        # Correspondance exacte ou sous-domaine
        if hostname == entry or hostname.endswith('.' + entry.lstrip('.')):
            return True
    
    return False