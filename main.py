import os
import asyncio
import inspect
import uuid
import chromadb
import speech_recognition as sr
import google.generativeai as genai
import edge_tts
import pygame
import tools
from PIL import ImageGrab
from dotenv import load_dotenv

# 1. CONFIGURAÇÃO INICIAL
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
pygame.mixer.init()

system_instruction = """
Você é JARVIS, um assistente virtual pessoal rodando localmente na máquina do usuário.
Suas respostas devem ser concisas, diretas, inteligentes e elegantes, em português.
Você tem acesso à tela do usuário quando ele pede para você "olhar" ou "ver" algo. Use esse contexto visual para resolver problemas de código, ler erros ou ajudar na navegação.
Sempre que usar uma ferramenta do sistema, avise brevemente.
Mantenha um tom de inteligência artificial avançada e perspicaz. Não use emojis.
"""

# =================================================================
# 2. SISTEMA DE MEMÓRIA SEMÂNTICA (CHROMADB)
# =================================================================
print("\n[Sistema] Inicializando Córtex Vetorial (ChromaDB)...")
try:
    # Cria uma pasta local chamada "memoria_jarvis_db" no seu SSD para persistir os dados
    chroma_client = chromadb.PersistentClient(path="./memoria_jarvis_db")
    colecao_memoria = chroma_client.get_or_create_collection(name="historico_conversas")
    print(f"[Sistema] Memória carregada. Lembranças armazenadas: {colecao_memoria.count()}")
except Exception as e:
    print(f"[Erro] Falha ao iniciar memória vetorial: {e}")

def salvar_memoria_vetorial(pergunta, resposta):
    """Vetoriza e salva a interação no banco de dados local."""
    if not pergunta or not resposta: return
    documento = f"Usuário disse: {pergunta} | JARVIS respondeu: {resposta}"
    try:
        colecao_memoria.add(
            documents=[documento],
            metadatas=[{"tipo": "interacao"}],
            ids=[str(uuid.uuid4())]
        )
    except Exception as e:
        print(f"[Aviso] Não foi possível salvar a memória: {e}")

def buscar_contexto_vetorial(pergunta_atual, max_resultados=2):
    """Busca as memórias passadas mais relevantes para o comando atual."""
    try:
        if colecao_memoria.count() == 0: 
            return ""
            
        resultados = colecao_memoria.query(
            query_texts=[pergunta_atual],
            n_results=min(max_resultados, colecao_memoria.count())
        )
        
        if resultados['documents'] and resultados['documents'][0]:
            contexto = " | ".join(resultados['documents'][0])
            return f"\n\n[INFORMAÇÃO OCULTA DE SISTEMA - CONTEXTO DO PASSADO: {contexto}]"
    except Exception:
        pass
    return ""

# =================================================================
# 3. SISTEMA DE AUTO-DETECÇÃO DE MODELO
# =================================================================
try:
    modelos_disponiveis = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    preferencias = [
        "models/gemini-1.5-pro-002", "models/gemini-1.5-pro-latest", "models/gemini-1.5-pro",
        "models/gemini-1.5-flash-002", "models/gemini-1.5-flash-latest", "models/gemini-1.5-flash"
    ]
    modelo_escolhido = next((pref for pref in preferencias if pref in modelos_disponiveis), "gemini-1.5-pro")
    print(f"[Sistema] Acesso concedido ao modelo: {modelo_escolhido}")
except Exception:
    modelo_escolhido = "models/gemini-1.5-pro-latest"

# =================================================================
# 4. ABSORÇÃO DINÂMICA DE SKILLS (REFLECTION)
# =================================================================
print("[Sistema] Absorvendo skills locais...")
skills_do_jarvis = [func for _, func in inspect.getmembers(tools, inspect.isfunction) if func.__module__ == tools.__name__]
print(f"[Sistema] {len(skills_do_jarvis)} skills carregadas.")

model = genai.GenerativeModel(
    model_name=modelo_escolhido,
    system_instruction=system_instruction,
    tools=skills_do_jarvis
)
chat = model.start_chat(enable_automatic_function_calling=True)

# =================================================================
# 5. FUNÇÕES DE ÁUDIO E MICROFONE
# =================================================================
async def generate_audio(text, filename="resposta.mp3"):
    communicate = edge_tts.Communicate(text, "pt-BR-AntonioNeural", rate="+10%")
    await communicate.save(filename)

def speak(text):
    print(f"\nJARVIS: {text}")
    asyncio.run(generate_audio(text))
    pygame.mixer.music.load("resposta.mp3")
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)
    pygame.mixer.music.unload()
    if os.path.exists("resposta.mp3"):
        try: os.remove("resposta.mp3")
        except: pass

def listen_command():
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("\n[Microfone aberto. Pode falar...]")
        recognizer.adjust_for_ambient_noise(source, duration=0.2)
        try:
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=15)
            text = recognizer.recognize_google(audio, language="pt-BR")
            print(f"Você (Voz): {text}")
            return text
        except (sr.WaitTimeoutError, sr.UnknownValueError):
            return None
        except Exception as e:
            print(f"Erro no microfone: {e}")
            return None

# =================================================================
# 6. LOOP PRINCIPAL
# =================================================================
def main():
    os.system('cls' if os.name == 'nt' else 'clear')
    print("="*40)
    print(" SISTEMA JARVIS INICIADO ".center(40, "="))
    print("="*40)
    
    speak("Sistemas online e banco de memória vetorial ativo, parceria.")
    gatilhos_visao = ["tela", "olhe", "veja", "isso", "print", "erro", "código"]

    while True:
        print("\n" + "-"*40)
        entrada_inicial = input("[ENTER para falar] ou [Digite seu comando]: ")
        user_input = listen_command() if entrada_inicial == "" else entrada_inicial
            
        if not user_input:
            continue
            
        if user_input.lower() in ['desligar', 'sair', 'encerrar']:
            speak("Desligando sistemas. Até breve.")
            pygame.mixer.quit()
            break
            
        try:
            # Resgata o contexto relevante do ChromaDB
            info_oculta = buscar_contexto_vetorial(user_input)
            comando_enriquecido = user_input + info_oculta
            
            precisa_ver = any(palavra in user_input.lower() for palavra in gatilhos_visao)
            
            if precisa_ver:
                print("[Capturando imagem da tela...]")
                print_tela = ImageGrab.grab(all_screens=True) 
                response = chat.send_message([comando_enriquecido, print_tela])
            else:
                response = chat.send_message(comando_enriquecido)
            
            try:
                texto_resposta = response.text
            except ValueError:
                texto_resposta = "Comando executado, meu parceiro."
                
            clean_text = texto_resposta.replace("*", "").replace("#", "")
            speak(clean_text)
            
            # Salva a nova memória no final da interação
            salvar_memoria_vetorial(user_input, clean_text)
            
        except Exception as e:
            speak("Falha de processamento neural.")
            print(f"Detalhe do Erro: {e}")

if __name__ == "__main__":
    main()