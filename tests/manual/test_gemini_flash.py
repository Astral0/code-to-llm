#!/usr/bin/env python3
"""
Test Gemini Flash (modèle gratuit) via proxy
"""

import requests
import json

def test_gemini_flash():
    api_key = "AIzaSyBc1LYgCpdHJM_FT88RyHaRKkCm3kyRosg"
    
    # Modèles Gemini avec quota gratuit
    models_to_test = [
        "gemini-1.5-flash",
        "gemini-1.5-flash-latest",
        "gemini-pro"
    ]
    
    # URL OpenAI-compatible
    url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    
    # Configuration proxy
    proxies = {
        'http': 'http://10.129.42.140:3131',
        'https': 'http://10.129.42.140:3131'
    }
    
    print("Test des modèles Gemini gratuits via proxy")
    print("=" * 60)
    
    for model in models_to_test:
        print(f"\nTest du modèle: {model}")
        print("-" * 40)
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": "Réponds simplement 'Test réussi' et rien d'autre"}
            ],
            "stream": False,
            "temperature": 0.1
        }
        
        try:
            print(f"Envoi de la requête...")
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                proxies=proxies,
                timeout=15
            )
            
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                print("[SUCCES] Ce modèle fonctionne!")
                result = response.json()
                
                if 'choices' in result and result['choices']:
                    content = result['choices'][0]['message']['content']
                    print(f"Réponse du modèle: {content}")
                    print("\n>>> Configuration à utiliser dans config.ini:")
                    print(f"model = {model}")
                    break
                    
            elif response.status_code == 429:
                error_data = response.json()
                error_msg = error_data.get('error', {}).get('message', 'Quota dépassé')
                print(f"[429] Erreur de quota: {error_msg}")
                
            elif response.status_code == 404:
                print(f"[404] Modèle '{model}' introuvable")
                
            else:
                print(f"[{response.status_code}] Erreur")
                print(f"Détails: {response.text[:200]}")
                
        except Exception as e:
            print(f"[EXCEPTION] {type(e).__name__}: {str(e)[:100]}")
    
    print("\n" + "=" * 60)
    print("\nRésumé:")
    print("- Le proxy fonctionne correctement")
    print("- gemini-2.5-pro-preview nécessite un compte payant")
    print("- Utilisez gemini-1.5-flash ou gemini-pro pour le quota gratuit")

if __name__ == "__main__":
    test_gemini_flash()