import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class BaseService(ABC):
    """Classe de base pour tous les services."""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """
        Initialise le service de base.
        
        Args:
            config: Dictionnaire de configuration
            logger: Logger optionnel, crée un logger par défaut si non fourni
        """
        self.config = config
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.validate_config()
    
    @abstractmethod
    def validate_config(self):
        """
        Valide la configuration requise pour le service.
        
        Raises:
            ValueError: Si la configuration est invalide
        """
        pass
    
    def get_config_value(self, key: str, default: Any = None) -> Any:
        """
        Récupère une valeur de configuration de manière sûre.
        
        Args:
            key: Clé de configuration
            default: Valeur par défaut si la clé n'existe pas
            
        Returns:
            La valeur de configuration ou la valeur par défaut
        """
        return self.config.get(key, default)