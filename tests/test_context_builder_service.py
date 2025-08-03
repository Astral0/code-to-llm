import pytest
from services.context_builder_service import ContextBuilderService, ContextBuilderException


class TestContextBuilderService:
    """Tests unitaires pour ContextBuilderService."""
    
    @pytest.fixture
    def context_builder(self):
        """Fixture pour créer une instance de ContextBuilderService."""
        return ContextBuilderService({})
    
    @pytest.fixture
    def sample_file_contents(self):
        """Contenus de fichiers d'exemple pour les tests."""
        return [
            {
                'path': 'main.py',
                'content': 'def main():\n    print("Hello World")',
                'size': 35
            },
            {
                'path': 'README.md',
                'content': '# My Project\n\nThis is a test project.',
                'size': 37
            },
            {
                'path': 'utils/helper.py',
                'content': 'def helper():\n    return True',
                'size': 29
            }
        ]
    
    def test_init(self):
        """Test de l'initialisation du service."""
        service = ContextBuilderService({'debug': True})
        assert service.config == {'debug': True}
    
    def test_build_context_success(self, context_builder, sample_file_contents):
        """Test de construction réussie du contexte."""
        result = context_builder.build_context(
            project_name='MyProject',
            directory_path='/path/to/project',
            file_contents=sample_file_contents,
            instructions='Please analyze this code'
        )
        
        assert result['success'] == True
        assert 'context' in result
        assert 'stats' in result
        
        # Vérifier le contenu du contexte
        context = result['context']
        assert '# Contexte du projet - MyProject' in context
        assert 'Répertoire: /path/to/project' in context
        assert 'Fichiers inclus: 3' in context
        assert '## Arbre des fichiers' in context
        assert '## Instructions' in context
        assert 'Please analyze this code' in context
        assert '## Statistiques' in context
        
        # Vérifier les stats
        stats = result['stats']
        assert stats['files_count'] == 3
        assert stats['total_chars'] == 101  # 35 + 37 + 29
        assert stats['estimated_tokens'] == 25  # 101 // 4
    
    def test_build_context_no_files(self, context_builder):
        """Test avec aucun fichier."""
        result = context_builder.build_context(
            project_name='Empty',
            directory_path='/empty',
            file_contents=[]
        )
        
        assert result['success'] == False
        assert 'Aucun contenu de fichier fourni' in result['error']
    
    def test_build_context_no_instructions(self, context_builder, sample_file_contents):
        """Test sans instructions."""
        result = context_builder.build_context(
            project_name='MyProject',
            directory_path='/path/to/project',
            file_contents=sample_file_contents
        )
        
        assert result['success'] == True
        context = result['context']
        assert '## Instructions' not in context
    
    def test_file_tree_generation(self, context_builder):
        """Test de la génération de l'arbre de fichiers."""
        file_paths = ['src/main.py', 'src/utils.py', 'README.md', 'tests/test_main.py']
        tree = context_builder._build_file_tree(file_paths, 'MyProject')
        
        assert '## Arbre des fichiers' in tree
        assert 'MyProject/' in tree
        assert any('main.py' in line for line in tree)
        assert any('utils.py' in line for line in tree)
        assert any('README.md' in line for line in tree)
        assert any('test_main.py' in line for line in tree)
    
    def test_file_sorting_by_size(self, context_builder):
        """Test que les fichiers sont triés par taille décroissante."""
        file_contents = [
            {'path': 'small.txt', 'content': 'a', 'size': 1},
            {'path': 'large.txt', 'content': 'a' * 100, 'size': 100},
            {'path': 'medium.txt', 'content': 'a' * 50, 'size': 50}
        ]
        
        result = context_builder.build_context(
            project_name='Test',
            directory_path='/test',
            file_contents=file_contents
        )
        
        context = result['context']
        # Vérifier l'ordre dans le contexte
        large_pos = context.find('## Fichier: large.txt')
        medium_pos = context.find('## Fichier: medium.txt')
        small_pos = context.find('## Fichier: small.txt')
        
        assert large_pos < medium_pos < small_pos
    
    def test_largest_files_statistics(self, context_builder):
        """Test de l'affichage des plus gros fichiers."""
        # Créer 10 fichiers de tailles différentes
        file_contents = []
        for i in range(10):
            size = (i + 1) * 100
            file_contents.append({
                'path': f'file{i}.txt',
                'content': 'x' * size,
                'size': size
            })
        
        result = context_builder.build_context(
            project_name='Test',
            directory_path='/test',
            file_contents=file_contents
        )
        
        context = result['context']
        assert '### Fichiers les plus volumineux:' in context
        # Le plus gros fichier (file9.txt avec 1000 octets) devrait être premier
        assert '1. file9.txt' in context
    
    def test_format_file_content(self, context_builder):
        """Test du formatage du contenu d'un fichier."""
        formatted = context_builder._format_file_content(
            'test.py',
            'print("Hello")'
        )
        
        assert formatted[0] == '## Fichier: test.py'
        assert formatted[1] == '```'
        assert formatted[2] == 'print("Hello")'
        assert formatted[3] == '```'
        assert formatted[4] == ''
    
    def test_build_header(self, context_builder):
        """Test de la construction de l'en-tête."""
        header = context_builder._build_header('MyProject', '/path/to/project', 5)
        
        assert header[0] == '# Contexte du projet - MyProject'
        assert header[1] == 'Répertoire: /path/to/project'
        assert header[2] == 'Fichiers inclus: 5'
        assert header[3] == ''
    
    def test_build_statistics(self, context_builder):
        """Test de la construction des statistiques."""
        largest_files = [
            {'path': 'big.txt', 'size': 2048},
            {'path': 'medium.txt', 'size': 1024}
        ]
        
        stats = context_builder._build_statistics(10, 5000, largest_files)
        
        assert stats[0] == '## Statistiques'
        assert stats[1] == '- Fichiers traités: 10'
        assert stats[2] == '- Taille totale: 5,000 caractères'
        assert any('big.txt (2.0 KB)' in line for line in stats)
        assert any('medium.txt (1.0 KB)' in line for line in stats)