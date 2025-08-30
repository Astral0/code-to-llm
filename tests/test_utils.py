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
        # Reconstruire le netloc sans les credentials (support IPv6)
        host = parts.hostname or ''
        if ':' in host and not host.startswith('['):  # IPv6 literal
            host = f'[{host}]'
        netloc = f"{host}:{parts.port}" if parts.port else host
        # Reconstruire l'URL complète sans les credentials
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    
    return url


def check_no_proxy_match(hostname, no_proxy_list):
    """
    Vérifie si un hostname correspond à une entrée dans la liste no_proxy.
    
    Suit la sémantique standard no_proxy :
    - Wildcard "*" : matche tous les domaines
    - Correspondance exacte : "example.com" matche uniquement "example.com"
    - Correspondance de sous-domaine : "example.com" matche aussi "www.example.com"
    - Entrée avec point : ".example.com" matche les sous-domaines mais pas le domaine lui-même
    - Les ports dans les entrées sont ignorés pour la comparaison
    
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
        >>> check_no_proxy_match("api.example.com", ["*"])
        True
    """
    if not hostname or not no_proxy_list:
        return False
    
    hostname = hostname.lower()
    
    for entry in no_proxy_list:
        if not entry:
            continue
            
        entry = entry.lower().strip()
        
        # Wildcard - matche tout
        if entry == '*':
            return True
            
        # Retirer schéma/identifiants/chemin si fournis par erreur
        if '://' in entry:
            entry = entry.split('://', 1)[1]
        if '@' in entry:
            entry = entry.split('@', 1)[1]
        entry = entry.split('/', 1)[0]
        
        # Gérer IPv6 entre crochets et ports
        if entry.startswith('['):
            rb = entry.find(']')
            entry_host = entry[1:rb] if rb != -1 else entry
        else:
            entry_host = entry.split(':', 1)[0]
        
        core = entry_host.lstrip('.')
        if entry_host.startswith('.'):
            # Sous-domaines uniquement (".example.com" ne matche pas "example.com")
            if hostname.endswith('.' + core):
                return True
        else:
            # Correspondance exacte ou sous-domaine
            if hostname == core or hostname.endswith('.' + core):
                return True
    
    return False