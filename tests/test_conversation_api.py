import pytest
import json
import os
import uuid
import tempfile
import shutil
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from main_desktop import Api


@pytest.fixture
def temp_conversations_dir():
    """Créer un répertoire temporaire pour les conversations."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def api_instance(temp_conversations_dir):
    """Créer une instance d'API avec un répertoire de conversations temporaire."""
    with patch('main_desktop.SERVICE_CONFIGS', {
        'git_service': {},
        'llm_service': {},
        'file_service': {}
    }):
        api = Api()
        api.conversations_dir = temp_conversations_dir
        api.file_service = MagicMock()
        api.context_builder = MagicMock()
        api.llm_service = MagicMock()
        api.git_service = MagicMock()
        api.export_service = MagicMock()
        return api


@pytest.fixture
def api_instance2(temp_conversations_dir):
    """Créer une seconde instance d'API partageant le même répertoire."""
    with patch('main_desktop.SERVICE_CONFIGS', {
        'git_service': {},
        'llm_service': {},
        'file_service': {}
    }):
        api = Api()
        api.conversations_dir = temp_conversations_dir
        api.file_service = MagicMock()
        api.context_builder = MagicMock()
        api.llm_service = MagicMock()
        api.git_service = MagicMock()
        api.export_service = MagicMock()
        return api


def test_conversations_directory_is_created(api_instance):
    """Test que le répertoire de conversations est créé."""
    assert os.path.isdir(api_instance.conversations_dir)


def test_api_instance_has_unique_id(api_instance):
    """Test que chaque instance a un ID unique."""
    # Vérifie que chaque instance a un ID unique
    assert hasattr(api_instance, 'instance_id')
    assert isinstance(api_instance.instance_id, str)
    # Vérifie que c'est un UUID valide
    uuid.UUID(api_instance.instance_id)


def test_get_conversations_shows_lock_status(api_instance, api_instance2):
    """Test que la liste des conversations montre le statut de verrouillage."""
    # Test avec deux instances différentes
    conv_data = {
        "title": "Test Conversation",
        "history": [
            {"role": "user", "content": "Test message"}
        ]
    }
    
    # Instance 1 sauvegarde une conversation
    saved = api_instance.save_conversation(conv_data)
    conv_id = saved['id']
    
    # Instance 1 voit son propre verrou
    convs1 = api_instance.get_conversations()
    assert len(convs1) == 1
    assert convs1[0]['isLockedByMe'] == True
    assert convs1[0]['isLocked'] == True
    
    # Instance 2 voit le verrou de l'autre
    convs2 = api_instance2.get_conversations()
    assert len(convs2) == 1
    assert convs2[0]['isLocked'] == True
    assert convs2[0]['isLockedByMe'] == False
    assert convs2[0]['lockInfo'] is not None


def test_save_conversation_creates_lock(api_instance):
    """Test que la sauvegarde crée un verrou."""
    conv_data = {
        "title": "Test avec verrou",
        "history": []
    }
    
    saved = api_instance.save_conversation(conv_data)
    
    # Vérifier que le fichier existe
    filepath = os.path.join(api_instance.conversations_dir, f"{saved['id']}.json")
    assert os.path.exists(filepath)
    
    # Vérifier le contenu du fichier
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    assert 'metadata' in data
    assert 'lock' in data['metadata']
    lock = data['metadata']['lock']
    assert lock['active'] == True
    assert lock['instanceId'] == api_instance.instance_id


def test_cannot_modify_locked_conversation(api_instance, api_instance2):
    """Test qu'une instance ne peut pas modifier une conversation verrouillée par une autre."""
    # Instance 1 crée une conversation
    conv_data = {"title": "Verrouillée", "history": []}
    saved = api_instance.save_conversation(conv_data)
    conv_id = saved['id']
    
    # Instance 2 essaie de modifier
    result = api_instance2.save_conversation({
        "id": conv_id,
        "title": "Tentative de modification",
        "history": []
    })
    
    # Vérifier que la modification a échoué
    assert result['success'] == False
    assert "verrouillée" in result['error'].lower()


def test_force_save_bypasses_lock(api_instance, api_instance2):
    """Test que force_save permet de contourner le verrou."""
    # Instance 1 crée une conversation
    conv_data = {"title": "À forcer", "history": []}
    saved = api_instance.save_conversation(conv_data)
    conv_id = saved['id']
    
    # Instance 2 force la sauvegarde
    forced = api_instance2.save_conversation({
        "id": conv_id,
        "title": "Forcée",
        "history": []
    }, force_save=True)
    
    assert forced['title'] == "Forcée"
    
    # Le verrou appartient maintenant à l'instance 2
    convs = api_instance2.get_conversations()
    assert convs[0]['isLockedByMe'] == True


def test_release_conversation_lock(api_instance):
    """Test de la libération d'un verrou."""
    # Créer une conversation verrouillée
    conv_data = {"title": "À libérer", "history": []}
    saved = api_instance.save_conversation(conv_data)
    conv_id = saved['id']
    
    # Libérer le verrou
    api_instance.release_conversation_lock(conv_id)
    
    # Vérifier que le verrou est libéré
    filepath = os.path.join(api_instance.conversations_dir, f"{conv_id}.json")
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    assert data['metadata']['lock']['active'] == False


def test_duplicate_conversation_creates_new_lock(api_instance):
    """Test que la duplication crée une nouvelle conversation avec son propre verrou."""
    # Créer la conversation originale
    conv_data = {"title": "Original", "history": [{"role": "user", "content": "Test"}]}
    saved = api_instance.save_conversation(conv_data)
    original_id = saved['id']
    
    # Dupliquer
    duplicated = api_instance.duplicate_conversation(original_id)
    
    assert duplicated['id'] != original_id
    assert duplicated['title'] == "Copie de Original"
    
    # Vérifier que la copie a son propre verrou
    filepath = os.path.join(api_instance.conversations_dir, f"{duplicated['id']}.json")
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    assert data['metadata']['lock']['instanceId'] == api_instance.instance_id


def test_get_conversation_details(api_instance):
    """Test de récupération des détails d'une conversation."""
    # Créer une conversation
    conv_data = {
        "title": "Conversation détaillée",
        "history": [
            {"role": "user", "content": "Question"},
            {"role": "assistant", "content": "Réponse"}
        ]
    }
    saved = api_instance.save_conversation(conv_data)
    
    # Récupérer les détails
    details = api_instance.get_conversation_details(saved['id'])
    
    assert details['title'] == "Conversation détaillée"
    assert len(details['history']) == 2
    assert 'metadata' in details
    assert 'lock' in details['metadata']


def test_delete_conversation(api_instance):
    """Test de suppression d'une conversation."""
    # Créer une conversation
    conv_data = {"title": "À supprimer", "history": []}
    saved = api_instance.save_conversation(conv_data)
    conv_id = saved['id']
    
    # Supprimer
    result = api_instance.delete_conversation(conv_id)
    assert result['success'] == True
    
    # Vérifier que le fichier n'existe plus
    filepath = os.path.join(api_instance.conversations_dir, f"{conv_id}.json")
    assert not os.path.exists(filepath)
    
    # Vérifier que la liste est vide
    convs = api_instance.get_conversations()
    assert len(convs) == 0


def test_update_conversation_title(api_instance):
    """Test de mise à jour du titre d'une conversation."""
    # Créer une conversation
    conv_data = {"title": "Ancien titre", "history": []}
    saved = api_instance.save_conversation(conv_data)
    conv_id = saved['id']
    
    # Mettre à jour le titre
    result = api_instance.update_conversation_title(conv_id, "Nouveau titre")
    assert result['success'] == True
    
    # Vérifier la mise à jour
    details = api_instance.get_conversation_details(conv_id)
    assert details['title'] == "Nouveau titre"