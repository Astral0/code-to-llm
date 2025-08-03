"""Exceptions personnalisées pour les services."""


class ServiceException(Exception):
    """Exception de base pour tous les services."""
    pass


class GitServiceException(ServiceException):
    """Exception liée aux opérations Git."""
    pass


class LlmApiServiceException(ServiceException):
    """Exception liée aux appels API LLM."""
    pass


class FileServiceException(ServiceException):
    """Exception liée aux opérations sur les fichiers."""
    pass


class ConfigurationException(ServiceException):
    """Exception liée à la configuration des services."""
    pass


class NetworkException(LlmApiServiceException):
    """Exception liée aux problèmes réseau."""
    pass


class RateLimitException(LlmApiServiceException):
    """Exception liée au dépassement de limite de taux."""
    
    def __init__(self, message: str, retry_after: int = None):
        """
        Args:
            message: Message d'erreur
            retry_after: Temps d'attente en secondes avant de réessayer
        """
        super().__init__(message)
        self.retry_after = retry_after