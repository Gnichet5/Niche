import os
import sys
import asyncio
import inspect
import uuid
import logging
import faulthandler

import platform

import chromadb
from chromadb import Documents, EmbeddingFunction, Embeddings
from chromadb.config import Settings
import speech_recognition as sr
import google.generativeai as genai
import edge_tts
import pygame
import tools
from PIL import ImageGrab
from dotenv import load_dotenv
faulthandler.enable()

# =================================================================
# 0. CONFIGURAÇÃO DE LOGS
# =================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

# =================================================================
# 1. CONFIGURAÇÃO INICIAL
# =================================================================
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
EMBEDDING_MODEL = "models/gemini-embedding-2"
EMBEDDING_DIM = 768 

logging.info("Ligando Córtex Vetorial (ChromaDB)...")
colecao_memoria = None


class CustomGeminiEmbedding(EmbeddingFunction):
    """
    Usada apenas para satisfazer a interface do Chroma (get_or_create_collection
    exige uma embedding_function). A geração real do vetor para os inserts é feita
    manualmente em salvar_memoria_vetorial(), com sanitização, para nunca deixar
    um objeto malformado (proto.Repeated, dimensão errada, NaN) chegar ao hnswlib.
    """
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self.model_name = EMBEDDING_MODEL

    def __call__(self, input: Documents) -> Embeddings:
        vetores = []
        for texto in input:
            resultado = genai.embed_content(
                model=self.model_name,
                content=texto, 
                output_dimensionality=EMBEDDING_DIM
            )
            vetores.append(_sanitizar_vetor(resultado["embedding"]))
        return vetores


def _sanitizar_vetor(vetor):
    """Converte para list[float] puro e valida dimensão/NaN antes de tocar no hnswlib."""
    vetor = [float(x) for x in vetor]
    if len(vetor) != EMBEDDING_DIM:
        raise ValueError(f"Dimensão de embedding inesperada: {len(vetor)} (esperado {EMBEDDING_DIM})")
    if any(v != v for v in vetor): 
        raise ValueError("Embedding contém NaN.")
    return vetor


try:
    DB_PATH = os.path.abspath(os.getenv("JARVIS_DB_PATH", "./memoria_jarvis_v2"))
    os.makedirs(DB_PATH, exist_ok=True)
    logging.info(f"Caminho do banco: {DB_PATH}")
    settings_chroma = Settings(anonymized_telemetry=False)
    if platform.system() == "Windows":
        settings_chroma = Settings(
            anonymized_telemetry=False,
            chroma_api_impl="chromadb.api.segment.SegmentAPI"
        )

    chroma_client = chromadb.PersistentClient(path=DB_PATH, settings=settings_chroma)
    gemini_ef = CustomGeminiEmbedding(api_key=api_key)

    colecao_memoria = chroma_client.get_or_create_collection(
        name="historico_conversas",
        embedding_function=gemini_ef
    )
    logging.info(f"Córtex Vetorial online. Lembranças: {colecao_memoria.count()}")
except Exception as e:
    logging.error(f"Falha ao iniciar memória vetorial: {e}", exc_info=True)
    colecao_memoria = None


def salvar_memoria_vetorial(pergunta, resposta):
    if not pergunta or not resposta:
        return
    if not colecao_memoria:
        logging.warning("Tentativa de gravar memória, mas o Córtex (ChromaDB) está desconectado.")
        return

    resposta_limpa = resposta[:800] + "... [truncado]" if len(resposta) > 800 else resposta
    documento = f"Usuário perguntou: {pergunta} | JARVIS respondeu: {resposta_limpa}"

    try:
        resultado = genai.embed_content(
            model=EMBEDDING_MODEL,
            content=documento,
            output_dimensionality=EMBEDDING_DIM
        )
        vetor = _sanitizar_vetor(resultado["embedding"])

        colecao_memoria.add(
            documents=[documento],
            embeddings=[vetor], 
            metadatas=[{"tipo": "interacao"}],
            ids=[str(uuid.uuid4())]
        )
        logging.info("[Córtex] Nova interação gravada com sucesso.")
    except Exception as e:
        logging.warning(f"[Córtex] Falha ao gravar interação: {e}")


def buscar_contexto_vetorial(pergunta_atual, max_resultados=2):
    try:
        if not colecao_memoria or colecao_memoria.count() == 0:
            return ""

        vetor_busca = _sanitizar_vetor(
            genai.embed_content(
                model=EMBEDDING_MODEL,
                content=pergunta_atual,
                output_dimensionality=EMBEDDING_DIM
            )["embedding"]
        )

        resultados = colecao_memoria.query(
            query_embeddings=[vetor_busca],
            n_results=min(max_resultados, colecao_memoria.count())
        )

        if resultados["documents"] and resultados["documents"][0]:
            contexto = " | ".join(resultados["documents"][0])
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
        if "generateContent" in m.supported_generation_methods:
            modelos_compativeis.append(m.name)
            logging.info(f"[API] Modelo compatível detectado: {m.name}")
    exclusoes = [
        "preview", "image", "tts", "computer-us", "robotics",
        "lyria", "gemma", "customtools", "clip", "embed"
    ]
    modelos_validos = [
        m for m in modelos_compativeis
        if not any(bloqueio in m for bloqueio in exclusoes)
    ]

    # Ordem de preferência: modelos estáveis (não-preview) mais recentes primeiro.
    # "flash" antes de "pro" por ser mais rápido/barato para um assistente de voz
    # em tempo real; inverta a ordem se preferir priorizar qualidade sobre latência.
    preferencias = [
        "gemini-3.5-flash",
        "gemini-3-flash",
        "gemini-flash-latest",
        "gemini-2.5-flash",
        "gemini-pro-latest",
        "flash",
        "pro",
    ]

    for pref in preferencias:
        encontrado = next((mod for mod in modelos_validos if pref in mod), None)
        if encontrado:
            modelo_escolhido = encontrado
            break
    if not modelo_escolhido and modelos_validos:
        modelo_escolhido = modelos_validos[0]
    if not modelo_escolhido and modelos_compativeis:
        modelo_escolhido = modelos_compativeis[0]
    if not modelo_escolhido:
        modelo_escolhido = "models/gemini-2.5-flash"

    logging.info(f"Modelo final selecionado com sucesso: {modelo_escolhido}")
except Exception as e:
    logging.warning(f"Erro ao listar modelos dinamicamente: {e}. Usando fallback.")
    modelo_escolhido = "models/gemini-2.5-flash"

# =================================================================
# 4. ABSORÇÃO DINÂMICA DE SKILLS (REFLECTION)
# =================================================================
logging.info("Absorvendo skills locais do tools.py...")
skills_do_jarvis = [
    func for _, func in inspect.getmembers(tools, inspect.isfunction)
    if func.__module__ == tools.__name__
]
logging.info(f"{len(skills_do_jarvis)} skills carregadas com sucesso.")

try:
    model = genai.GenerativeModel(
        model_name=modelo_escolhido,
        system_instruction=system_instruction,
        tools=skills_do_jarvis
    )
    chat = model.start_chat(enable_automatic_function_calling=True)
    modelo_resumo = genai.GenerativeModel(model_name=modelo_escolhido)
except Exception as e:
    logging.critical(f"Erro fatal ao instanciar o modelo do Gemini: {e}", exc_info=True)
    exit(1)

# =================================================================
# 5. FUNÇÕES DE ÁUDIO E MICROFONE
# =================================================================
async def generate_audio(text, filename="resposta.mp3"):
    communicate = edge_tts.Communicate(text, "pt-BR-AntonioNeural", rate="+10%")
    await communicate.save(filename)


def sintetizar_para_voz(texto, limite_caracteres=200):
    """
    Gera uma síntese curta e natural do texto para a fala, em vez de um
    aviso genérico. Se a chamada falhar por qualquer motivo, cai num
    fallback seguro (nunca deixa o assistente sem resposta falada).
    """
    try:
        prompt = (
            "Resuma o texto abaixo em UMA frase curta, natural e direta, em português, "
            f"com no máximo {limite_caracteres} caracteres. Mantenha o tom de um assistente "
            "de IA elegante e perspicaz (estilo JARVIS). Responda APENAS com a frase-resumo, "
            "sem aspas e sem introduções como 'aqui está o resumo'.\n\n"
            f"Texto original:\n{texto}"
        )
        resposta = modelo_resumo.generate_content(
            prompt,
            generation_config={"max_output_tokens": 100, "temperature": 0.3}
        )
        resumo = resposta.text.strip()
        if resumo and len(resumo) <= limite_caracteres * 1.5:
            return resumo
    except Exception as e:
        logging.debug(f"Falha ao sintetizar texto para voz: {e}")

    return "Conteúdo extenso processado e exibido na tela, parceiro."


def speak(text):
    if len(text) > 200 or text.count("\n") > 1:
        texto_para_falar = sintetizar_para_voz(text)
        print("\n" + "=" * 40)
        print("[JARVIS - Resposta completa exibida no console]")
        print(text)
        print("=" * 40)
    else:
        texto_para_falar = text

    logging.info(f"JARVIS (Voz): {texto_para_falar}")

    try:
        asyncio.run(generate_audio(texto_para_falar))
        if os.path.exists("resposta.mp3"):
            pygame.mixer.music.load("resposta.mp3")
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
            pygame.mixer.music.unload()
            os.remove("resposta.mp3")
    except Exception as e:
        logging.warning(f"Aviso de áudio (bloqueio de SSL/rede ignorado): {e}")


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
    os.system("cls" if os.name == "nt" else "clear")
    print("=" * 40)
    print(" SISTEMA JARVIS INICIADO ".center(40, "="))
    print("=" * 40)

    speak("Sistemas online e monitoramento por logs ativo, parceria.")
    gatilhos_visao = ["tela", "olhe", "veja", "isso", "print", "erro", "código"]

    while True:
        print("\n" + "-" * 40)
        entrada_inicial = input("[ENTER para falar] ou [Digite seu comando]: ")
        user_input = listen_command() if entrada_inicial == "" else entrada_inicial

        if not user_input:
            continue

        if user_input.lower() in ["desligar", "sair", "encerrar"]:
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