import os
import logging
from dotenv import load_dotenv
import google.generativeai as genai

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def executar_radar():
    print("=" * 50)
    print(" RADAR DE DIAGNÓSTICO DA API GEMINI ".center(50))
    print("=" * 50)

    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[ERRO] Chave GEMINI_API_KEY não encontrada no .env!")
        return

    genai.configure(api_key=api_key)

    try:
        print("\n1. Mapeando Modelos de Texto (Chat)...")
        modelos_texto = []
        for m in genai.list_models():
            if "generateContent" in m.supported_generation_methods:
                print(f"   ✅ Liberado: {m.name}")
                modelos_texto.append(m.name)

        print("\n2. Mapeando Modelos de Vetorização (Embedding)...")
        modelos_embedding = []
        for m in genai.list_models():
            if "embedContent" in m.supported_generation_methods:
                print(f"   ✅ Liberado: {m.name}")
                modelos_embedding.append(m.name)

        print("\n3. Teste de Fogo: Comunicação HTTP com a Google...")
        if not modelos_texto:
            print("[ERRO] Nenhum modelo de texto disponível.")
            return

        # Pega o primeiro modelo da lista (que sabemos que funciona) para testar
        modelo_teste = modelos_texto[0]
        print(f"   -> Enviando pacote de teste para '{modelo_teste}'...")
        
        model = genai.GenerativeModel(modelo_teste)
        response = model.generate_content("Responda apenas com: 'Conexão HTTP 100% limpa e operante.'")
        
        print(f"\n[SUCESSO] Resposta recebida da Google: {response.text}")
        print("=" * 50)

    except Exception as e:
        print(f"\n[FALHA CRÍTICA] Ocorreu um erro de conexão ou permissão: {e}")

if __name__ == "__main__":
    executar_radar()