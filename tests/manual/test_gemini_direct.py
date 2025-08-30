#!/usr/bin/env python3
"""
Test de l'API Gemini avec différentes URLs
"""

import requests
import json

def test_gemini_urls():
    """Teste différentes URLs possibles pour Gemini."""
    
    api_key = "AIzaSyBc1LYgCpdHJM_FT88RyHaRKkCm3kyRosg"
    model = "gemini-2.5-pro-preview-06-05"
    
    # Différentes URLs à tester
    urls_to_test = [
        # Format OpenAI-compatible
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "https://generativelanguage.googleapis.com/v1/openai/chat/completions",
        "https://generativelanguage.googleapis.com/v1beta/chat/completions",
        
        # Format Google AI natif
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro-preview-06-05:generateContent",
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
    ]
    
    # Proxy configuration
    proxies = {
        'http': 'http://10.129.42.140:3131',
        'https': 'http://10.129.42.140:3131'
    }
    
    print("Test des différentes URLs Gemini")
    print("=" * 60)
    
    for url in urls_to_test:
        print(f"\nTest: {url}")
        print("-" * 40)
        
        try:
            # Pour les URLs OpenAI-compatible
            if "openai" in url or "/chat/completions" in url:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}"
                }
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": "test"}],
                    "stream": False
                }
            # Pour l'API native Google
            else:
                headers = {
                    "Content-Type": "application/json"
                }
                payload = {
                    "contents": [{
                        "parts": [{
                            "text": "test"
                        }]
                    }]
                }
                # Si la clé n'est pas dans l'URL
                if "key=" not in url:
                    headers["x-goog-api-key"] = api_key
            
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                proxies=proxies,
                timeout=10
            )
            
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                print("[SUCCES] Cette URL fonctionne!")
                result = response.json()
                print(f"Structure de réponse: {list(result.keys())}")
                
                # Format OpenAI
                if 'choices' in result:
                    print("Format: OpenAI-compatible")
                # Format Google
                elif 'candidates' in result:
                    print("Format: Google AI natif")
                    if result['candidates']:
                        content = result['candidates'][0].get('content', {})
                        if 'parts' in content and content['parts']:
                            text = content['parts'][0].get('text', '')
                            print(f"Réponse: {text[:100]}...")
            elif response.status_code == 404:
                print("[404] URL introuvable")
            elif response.status_code == 401:
                print("[401] Problème d'authentification")
            elif response.status_code == 400:
                print("[400] Mauvaise requête")
                print(f"Erreur: {response.text[:200]}")
            else:
                print(f"[{response.status_code}] Erreur")
                print(f"Détails: {response.text[:200]}")
                
        except Exception as e:
            print(f"[EXCEPTION] {type(e).__name__}: {str(e)[:100]}")
    
    print("\n" + "=" * 60)
    print("\nConclusion:")
    print("Si aucune URL ne fonctionne, vérifiez:")
    print("1. La clé API est valide")
    print("2. Le modèle existe")
    print("3. Le proxy autorise l'accès à Google APIs")

if __name__ == "__main__":
    test_gemini_urls()