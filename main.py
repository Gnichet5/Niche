import os
import asyncio
import inspect
import uuid
import logging
import chromadb
import speech_recognition as sr
import google.generativeai as genai
import edge_tts
import pygame
import tools
from PIL import ImageGrab
from dotenv import load_dotenv

# CONFIGURAÇÃO DE LOGS PROFISSIONAIS
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)

# 1. CONFIGURAÇÃO INICIAL
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    logging.critical("A chave GEMINI_API_KEY não foi encontrada no arquivo .env!")
    exit(1)

genai.configure(api_key=api_key)
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
logging.info("Inicializando Córtex Vetorial (ChromaDB)...")
colecao_memoria = None
try:
    chroma_client = chromadb.PersistentClient(path="./memoria_jarvis_db")
    colecao_memoria = chroma_client.get_or_create_collection(name="historico_conversas")
    logging.info(f"Memória carregada com sucesso. Lembranças armazenadas: {colecao_memoria.count()}")
except Exception as e:
    logging.error(f"Falha ao iniciar memória vetorial: {e}", exc_info=True)

def salvar_memoria_vetorial(pergunta, resposta):
    if not pergunta or not resposta or not colecao_memoria: 
        return
    documento = f"Usuário disse: {pergunta} | JARVIS respondeu: {resposta}"
    try:
        colecao_memoria.add(
            documents=[documento],
            metadatas=[{"tipo": "interacao"}],
            ids=[str(uuid.uuid4())]
        )
    except Exception as e:
        logging.warning(f"Não foi possível salvar a memória: {e}")

def buscar_contexto_vetorial(pergunta_atual, max_resultados=2):
    try:
        if not colecao_memoria or colecao_memoria.count() == 0: 
            return ""
            
        resultados = colecao_memoria.query(
            query_texts=[pergunta_atual],
            n_results=min(max_resultados, colecao_memoria.count())
        )
        
        if resultados['documents'] and resultados['documents'][0]:
            contexto = " | ".join(resultados['documents'][0])
            return f"\n\n[INFORMAÇÃO OCULTA DE SISTEMA - CONTEXTO DO PASSADO: {contexto}]"
    except Exception as e:
        logging.debug(f"Erro ao buscar contexto vetorial: {e}")
    return ""

# =================================================================
# 3. SISTEMA DE AUTO-DETECÇÃO DINÂMICA DE MODELO
# =================================================================
logging.info("Analisando modelos disponíveis na API do Gemini...")
modelo_escolhido = None

try:
    modelos_compativeis = []
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            modelos_compativeis.append(m.name)
            logging.info(f"[API] Modelo compatível detectado: {m.name}")
    preferencias = ["gemini-1.5-flash", "gemini-1.5-pro", "flash", "pro"]
    
    for pref in preferencias:
        encontrado = next((mod for mod in modelos_compativeis if pref in mod), None)
        if encontrado:
            modelo_escolhido = encontrado
            break
    if not modelo_escolhido and modelos_compativeis:
        modelo_escolhido = modelos_compativeis[0]
        
    # Fallback de segurança absoluto caso a listagem falhe
    if not modelo_escolhido:
        modelo_escolhido = "models/gemini-1.5-flash"
        
    logging.info(f"Modelo final selecionado com sucesso: {modelo_escolhido}")
except Exception as e:
    logging.warning(f"Erro ao listar modelos dinamicamente: {e}. Usando fallback.")
    modelo_escolhido = "models/gemini-1.5-flash"

# =================================================================
# 4. ABSORÇÃO DINÂMICA DE SKILLS (REFLECTION)
# =================================================================
logging.info("Absorvendo skills locais do tools.py...")
skills_do_jarvis = [func for _, func in inspect.getmembers(tools, inspect.isfunction) if func.__module__ == tools.__name__]
logging.info(f"{len(skills_do_jarvis)} skills carregadas com sucesso.")

try:
    model = genai.GenerativeModel(
        model_name=modelo_escolhido,
        system_instruction=system_instruction,
        tools=skills_do_jarvis
    )
    chat = model.start_chat(enable_automatic_function_calling=True)
except Exception as e:
    logging.critical(f"Erro fatal ao instanciar o modelo do Gemini: {e}", exc_info=True)
    exit(1)

# =================================================================
# 5. FUNÇÕES DE ÁUDIO E MICROFONE
# =================================================================
async def generate_audio(text, filename="resposta.mp3"):
    communicate = edge_tts.Communicate(text, "pt-BR-AntonioNeural", rate="+10%")
    await communicate.save(filename)

def speak(text):
    logging.info(f"JARVIS: {text}")
    try:
        asyncio.run(generate_audio(text))
        pygame.mixer.music.load("resposta.mp3")
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        pygame.mixer.music.unload()
        if os.path.exists("resposta.mp3"):
            os.remove("resposta.mp3")
    except Exception as e:
        logging.error(f"Erro no sistema de voz/áudio: {e}")

def listen_command():
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("\n[Microfone aberto. Pode falar...]")
        recognizer.adjust_for_ambient_noise(source, duration=0.2)
        try:
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=15)
            text = recognizer.recognize_google(audio, language="pt-BR")
            logging.info(f"Usuário (Voz): {text}")
            return text
        except (sr.WaitTimeoutError, sr.UnknownValueError):
            return None
        except Exception as e:
            logging.error(f"Erro crítico no microfone: {e}")
            return None

# =================================================================
# 6. LOOP PRINCIPAL
# =================================================================
def main():
    os.system('cls' if os.name == 'nt' else 'clear')
    print("="*40)
    print(" SISTEMA JARVIS INICIADO ".center(40, "="))
    print("="*40)
    
    speak("Sistemas online e monitoramento por logs ativo, parceria.")
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
            info_oculta = buscar_contexto_vetorial(user_input)
            comando_enriquecido = user_input + info_oculta
            
            precisa_ver = any(palavra in user_input.lower() for palavra in gatilhos_visao)
            
            logging.info(f"Processando comando: '{user_input}' (Visão ativa: {precisa_ver})")
            
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
            
            salvar_memoria_vetorial(user_input, clean_text)
            
        except Exception as e:
            logging.error(f"Falha de processamento neural no loop principal: {e}", exc_info=True)
            speak("Falha de processamento neural.")

if __name__ == "__main__":
    main()