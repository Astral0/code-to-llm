import os
import logging
from typing import Dict, Any, Optional, List
from .base_service import BaseService
from .exceptions import ServiceException


class ContextBuilderException(ServiceException):
    """Exception liée à la construction du contexte."""
    pass


class ContextBuilderService(BaseService):
    """Service pour construire et formater le contexte à partir des contenus de fichiers."""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """
        Initialise le service de construction de contexte.
        
        Args:
            config: Dictionnaire de configuration
            logger: Logger optionnel
        """
        super().__init__(config, logger)
        
    def validate_config(self):
        """Valide la configuration du service."""
        # Pas de configuration spécifique requise
        pass
    
    def build_context(self, 
                     project_name: str,
                     directory_path: str,
                     file_contents: List[Dict[str, Any]],
                     instructions: str = "") -> Dict[str, Any]:
        """
        Construit le contexte formaté à partir des contenus de fichiers.
        
        Args:
            project_name: Nom du projet (généralement le nom du répertoire)
            directory_path: Chemin du répertoire de base
            file_contents: Liste des dictionnaires contenant path, content et size
            instructions: Instructions optionnelles à inclure
            
        Returns:
            Dict contenant le contexte formaté et les statistiques
        """
        try:
            if not file_contents:
                return {
                    'success': False,
                    'error': 'Aucun contenu de fichier fourni'
                }
            
            context_parts = []
            total_chars = 0
            
            # En-tête du contexte
            context_parts.extend(self._build_header(project_name, directory_path, len(file_contents)))
            
            # Arbre des fichiers
            file_paths = [f['path'] for f in file_contents]
            context_parts.extend(self._build_file_tree(file_paths, project_name))
            context_parts.append("")
            
            # Trier les fichiers par taille décroissante
            sorted_contents = sorted(file_contents, key=lambda x: x['size'], reverse=True)
            
            # Ajouter le contenu de chaque fichier
            for file_data in sorted_contents:
                context_parts.extend(self._format_file_content(
                    file_data['path'], 
                    file_data['content']
                ))
                total_chars += file_data['size']
            
            # Ajouter les instructions si présentes
            if instructions and instructions.strip():
                context_parts.extend(self._format_instructions(instructions))
            
            # Statistiques finales
            context_parts.extend(self._build_statistics(
                len(file_contents), 
                total_chars,
                sorted_contents[:5]  # Top 5 des plus gros fichiers
            ))
            
            full_context = "\n".join(context_parts)
            
            return {
                'success': True,
                'context': full_context,
                'stats': {
                    'files_count': len(file_contents),
                    'total_chars': total_chars,
                    'estimated_tokens': total_chars // 4
                }
            }
            
        except Exception as e:
            error_msg = f"Erreur lors de la construction du contexte: {str(e)}"
            self.logger.error(error_msg)
            raise ContextBuilderException(error_msg)
    
    def _build_header(self, project_name: str, directory_path: str, file_count: int) -> List[str]:
        """Construit l'en-tête du contexte."""
        return [
            f"# Contexte du projet - {project_name}",
            f"Répertoire: {directory_path}",
            f"Fichiers inclus: {file_count}",
            ""
        ]
    
    def _build_file_tree(self, file_paths: List[str], project_name: str) -> List[str]:
        """Génère un arbre visuel des fichiers."""
        if not file_paths:
            return ["## Arbre des fichiers", "Aucun fichier"]
        
        tree_lines = ["## Arbre des fichiers", "```"]
        tree_lines.append(f"{project_name}/")
        
        # Trier les fichiers pour un affichage cohérent
        sorted_files = sorted(file_paths)
        
        # Construire l'arbre
        for i, file_path in enumerate(sorted_files):
            is_last = (i == len(sorted_files) - 1)
            parts = file_path.split('/')
            
            # Construire l'indentation
            prefix = "└── " if is_last else "├── "
            indent = "    " * (len(parts) - 1)
            
            tree_lines.append(f"{indent}{prefix}{parts[-1]}")
        
        tree_lines.append("```")
        return tree_lines
    
    def _format_file_content(self, file_path: str, content: str) -> List[str]:
        """Formate le contenu d'un fichier pour l'inclusion dans le contexte."""
        return [
            f"## Fichier: {file_path}",
            "```",
            content,
            "```",
            ""
        ]
    
    def _format_instructions(self, instructions: str) -> List[str]:
        """Formate les instructions pour l'inclusion dans le contexte."""
        return [
            "## Instructions",
            instructions,
            ""
        ]
    
    def _build_statistics(self, file_count: int, total_chars: int, 
                         largest_files: List[Dict[str, Any]]) -> List[str]:
        """Construit la section des statistiques."""
        stats = [
            "## Statistiques",
            f"- Fichiers traités: {file_count}",
            f"- Taille totale: {total_chars:,} caractères"
        ]
        
        if largest_files:
            stats.append(f"\n### Fichiers les plus volumineux:")
            for i, file_data in enumerate(largest_files):
                size_kb = file_data['size'] / 1024
                stats.append(f"{i+1}. {file_data['path']} ({size_kb:.1f} KB)")
        
        return stats