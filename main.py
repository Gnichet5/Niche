import os
import shutil
import sys
import asyncio
import inspect
import uuid
import logging
import faulthandler
import threading
import time
import platform
import threading
import chromadb
from chromadb import Documents, EmbeddingFunction, Embeddings
from chromadb.config import Settings
import speech_recognition as sr
import google.generativeai as genai
from google.api_core import retry as google_retry
from google.api_core.exceptions import ServiceUnavailable, DeadlineExceeded, ResourceExhausted, RetryError
import edge_tts
import pygame
import tools
from PIL import ImageGrab
from dotenv import load_dotenv
from google.api_core.exceptions import ServiceUnavailable, DeadlineExceeded, ResourceExhausted, RetryError, NotFound

faulthandler.enable()

# =================================================================
# 0. CONFIGURAÇÃO DE LOGS (BACKGROUND)
# =================================================================
os.makedirs("logs_sistema", exist_ok=True)
arquivo_log = os.path.join("logs_sistema", "jarvis_runtime.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        # Grava os logs fisicamente no arquivo
        logging.FileHandler(arquivo_log, encoding='utf-8')
        # Removido o StreamHandler para limpar a interface do usuário
    ]
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
Você é JARVIS, um engenheiro de software autônomo e assistente virtual avançado.
Suas respostas faladas devem ser concisas e em português.

[PROTOCOLO DE ENGENHARIA E RACIOCÍNIO - ZERO SHOT]
Quando solicitado para programar, refatorar ou criar sistemas, você DEVE seguir este ciclo rigorosamente ANTES de dar a resposta final:
1. MAPEAMENTO: Use 'mapear_arquitetura_projeto' para entender a estrutura local.
2. CONTEXTO: Leia os arquivos necessários e use 'gerenciar_memoria_codigo' para salvar trechos na RAM.
3. AÇÃO: Use 'criar_arquivo' ou 'editar_arquivo' para construir o código.
4. AUTO-CURA (MANDATÓRIO): Use EXCLUSIVAMENTE a ferramenta 'testar_script_python' para rodar e testar o código. Se falhar, leia o traceback, arrume o código e teste novamente até funcionar.

[REGRAS DE CONTENÇÃO - NEGATIVE PROMPTING]
- NUNCA use 'executar_comando_terminal' para rodar scripts Python (.py). Essa ferramenta é restrita a comandos de infraestrutura e SO (ex: pip install, ping, dir).
- Para testar ou executar qualquer código Python, você é OBRIGADO a usar 'testar_script_python'.

Mantenha um tom de inteligência artificial elegante e perspicaz. Não use emojis.
"""

# =================================================================
# SISTEMA DE SINCRONIZAÇÃO (NUVEM <-> LOCAL)
# =================================================================
CAMINHO_NUVEM = os.getenv("JARVIS_DB_PATH") # Lê o caminho do Drive
CAMINHO_LOCAL = os.path.abspath("./memoria_jarvis_v2")

# Lock para garantir que nunca haja dois syncs rodando ao mesmo tempo
# (ex: usuário manda 2 comandos rápidos antes do upload anterior terminar)
_sync_lock = threading.Lock()
_db_io_lock = threading.Lock()

def _copiar_incremental(origem, destino):
    """
    Sincroniza arquivos entre nuvem e SSD. 
    Ignora a verificação de data (mtime) pois o Google Drive corrompe metadados temporais 
    quando usamos copyfile. Força a cópia de arquivos SQLite para garantir integridade.
    """
    arquivos_copiados = 0
    arquivos_com_erro = 0
    for pasta_atual, _subpastas, arquivos in os.walk(origem):
        destino_pasta = os.path.join(destino, os.path.relpath(pasta_atual, origem))
        os.makedirs(destino_pasta, exist_ok=True)

        for nome_arquivo in arquivos:
            src = os.path.join(pasta_atual, nome_arquivo)
            dst = os.path.join(destino_pasta, nome_arquivo)

            try:
                precisa_copiar = True
                if os.path.exists(dst):
                    stat_src = os.stat(src)
                    stat_dst = os.stat(dst)
                    if stat_src.st_size == stat_dst.st_size and not nome_arquivo.endswith('.sqlite3'):
                        precisa_copiar = False

                if precisa_copiar:
                    with _db_io_lock:
                        if os.path.exists(dst):
                            try:
                                os.remove(dst)
                            except OSError:
                                pass
                        
                        shutil.copyfile(src, dst)
                    arquivos_copiados += 1
            except OSError as e:
                arquivos_com_erro += 1
                logging.warning(f"[Sync] Pulei '{nome_arquivo}' (será tentado de novo no próximo sync): {e}")
                continue

    if arquivos_com_erro:
        logging.warning(f"[Sync] {arquivos_com_erro} arquivo(s) pulado(s) nesta rodada, tentarei novamente depois.")

    return arquivos_copiados

def sync_nuvem_para_local():
    """Baixa o banco do Drive para o SSD ao ligar o sistema (incremental)."""
    if CAMINHO_NUVEM and os.path.exists(CAMINHO_NUVEM):
        logging.info(f"[Sync] Puxando backup da Nuvem ({CAMINHO_NUVEM}) para o SSD...")
        try:
            with _sync_lock:
                n = _copiar_incremental(CAMINHO_NUVEM, CAMINHO_LOCAL)
            logging.info(f"[Sync] Download concluído ({n} arquivo(s) atualizados). Sistema rodando localmente.")
        except Exception as e:
            logging.error(f"[Sync] Erro ao baixar da nuvem: {e}")


def _sync_local_para_nuvem_worker():
    """Faz o upload incremental de forma protegida por lock."""
    if not _sync_lock.acquire(blocking=False):
        # Já existe um sync em andamento (ex: comando anterior ainda subindo) - pula esta rodada,
        # a próxima chamada vai pegar o estado mais atual do disco de qualquer forma.
        logging.info("[Sync] Upload anterior ainda em andamento, pulando esta rodada.")
        return
    try:
        os.makedirs(CAMINHO_NUVEM, exist_ok=True)
        inicio = time.time()
        n = _copiar_incremental(CAMINHO_LOCAL, CAMINHO_NUVEM)
        duracao = time.time() - inicio
        logging.info(f"[Sync] Upload para o Google Drive concluído ({n} arquivo(s), {duracao:.1f}s).")
    except Exception as e:
        logging.error(f"[Sync] Erro ao subir para a nuvem: {e}")
    finally:
        _sync_lock.release()


def sync_local_para_nuvem():
    """
    Sobe o banco do SSD para o Drive após criar uma nova memória.
    Roda em background (thread daemon) para NÃO travar o loop principal
    enquanto o Google Drive sincroniza o arquivo.
    """
    if CAMINHO_NUVEM and os.path.exists(CAMINHO_LOCAL):
        logging.info("[Sync] Espelhando memórias novas para a Nuvem (em segundo plano)...")
        threading.Thread(target=_sync_local_para_nuvem_worker, daemon=True).start()

# =================================================================
# 2. CÓRTEX VETORIAL (MEMÓRIA DE LONGO PRAZO)
# =================================================================
logging.info("Ligando Córtex Vetorial (ChromaDB)...")

# 1. Primeiro puxamos o arquivo da nuvem para o SSD!
sync_nuvem_para_local()

# 2. Garantimos que a pasta local existe
os.makedirs(CAMINHO_LOCAL, exist_ok=True)

# 3. Configuramos o ChromaDB para rodar ESTRITAMENTE na pasta local
try:
    settings_chroma = Settings(anonymized_telemetry=False)
    if platform.system() == "Windows":
        settings_chroma = Settings(
            anonymized_telemetry=False,
            chroma_api_impl="chromadb.api.segment.SegmentAPI"
        )
    
    # IMPORTANTE: path=CAMINHO_LOCAL ao invés de DB_PATH
    chroma_client = chromadb.PersistentClient(path=CAMINHO_LOCAL, settings=settings_chroma)
    colecao_memoria = chroma_client.get_or_create_collection(name="historico_conversas")
    tools.colecao_memoria_global = colecao_memoria
    logging.info("✅ CÓRTEX VETORIAL ONLINE! (Lendo do SSD físico)")
except Exception as e:
    logging.error(f"Falha ao iniciar memória vetorial: {e}")
    colecao_memoria = None

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
            generation_config={"max_output_tokens": 100, "temperature": 0.3},
            request_options=GEMINI_REQUEST_OPTIONS
        )
        resumo = resposta.text.strip()
        if resumo and len(resumo) <= limite_caracteres * 1.5:
            return resumo
    except Exception as e:
        logging.debug(f"Falha ao sintetizar texto para voz: {e}")

    return "Conteúdo extenso processado e exibido na tela, parceiro."

def _reproduzir_e_limpar(arquivo_mp3):
    """Roda o áudio em background e limpa o arquivo depois."""
    try:
        pygame.mixer.music.load(arquivo_mp3)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        pygame.mixer.music.unload()
        os.remove(arquivo_mp3)
    except Exception as e:
        logging.warning(f"Erro na thread de áudio: {e}")

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
            # Otimização: dispara a thread e libera o microfone na hora
            threading.Thread(target=_reproduzir_e_limpar, args=("resposta.mp3",), daemon=True).start()
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
# 5.5 FUNÇÕES DE MEMÓRIA VETORIAL (CÓRTEX)
# =================================================================
EMBEDDING_MODEL = "models/gemini-embedding-2"
EMBEDDING_DIMENSAO = 768  # precisa bater com a dimensionalidade da collection já existente no ChromaDB
GEMINI_TIMEOUT_SEGUNDOS = 20  # evita ficar preso em retry infinito quando a API retorna 503 (alta demanda)

# Retry curto e explícito: o "timeout" sozinho às vezes é ignorado pelo ChatSession
# em algumas versões da lib deprecada google-generativeai, então forçamos aqui
# um teto real de ~15s de tentativas antes de desistir.
RETRY_CURTO_GEMINI = google_retry.Retry(
    initial=1.0,
    maximum=4.0,
    multiplier=2.0,
    deadline=15.0,
    predicate=google_retry.if_exception_type(ServiceUnavailable, ResourceExhausted),
)
GEMINI_REQUEST_OPTIONS = {"timeout": GEMINI_TIMEOUT_SEGUNDOS, "retry": RETRY_CURTO_GEMINI}

def _sanitizar_vetor(vetor):
    """Garante que o vetor seja uma lista simples de floats."""
    if isinstance(vetor, list):
        if len(vetor) > 0 and isinstance(vetor[0], list):
            return [float(v) for v in vetor[0]]
        return [float(v) for v in vetor]
    return vetor

def buscar_contexto_vetorial(pergunta_atual, max_resultados=2):
    try:
        if not colecao_memoria or colecao_memoria.count() == 0:
            return ""
        
        # Lê direto do SSD, zero lag de nuvem!
        logging.info("[Córtex] Iniciando varredura vetorial local (SSD)...")
        vetor_busca = _sanitizar_vetor(
            genai.embed_content(
                model=EMBEDDING_MODEL,
                content=pergunta_atual,
                output_dimensionality=EMBEDDING_DIMENSAO
            )["embedding"]
        )
        
        resultados = colecao_memoria.query(
            query_embeddings=[vetor_busca],
            n_results=min(max_resultados, colecao_memoria.count())
        )
        
        if resultados["documents"] and resultados["documents"][0]:
            contexto = " | ".join(resultados["documents"][0])
            logging.info(f"[Córtex] Resgatou {len(resultados['documents'][0])} lembrança(s).")
            return f"\n\n[INFORMAÇÃO OCULTA DE SISTEMA - CONTEXTO DO PASSADO: {contexto}]"
    except Exception as e:
        logging.error(f"[Córtex] Erro na busca: {e}")
    return ""

def salvar_memoria_vetorial(pergunta, resposta):
    try:
        if colecao_memoria:
            doc_id = str(uuid.uuid4())
            texto_memoria = f"Usuário disse: {pergunta} | JARVIS respondeu: {resposta}"
            
            vetor = _sanitizar_vetor(
                genai.embed_content(
                    model=EMBEDDING_MODEL,
                    content=texto_memoria,
                    output_dimensionality=EMBEDDING_DIMENSAO
                )["embedding"]
            )
            
            # 1. Salva muito rápido no SSD local
            with _db_io_lock:
                colecao_memoria.add(
                    ids=[doc_id],
                    documents=[texto_memoria],
                    embeddings=[vetor]
                )
            logging.info("[Córtex] Nova memória salva no SSD.")
            
            # 2. UPLOAD SILENCIOSO PARA A NUVEM!
            sync_local_para_nuvem()
    except Exception as e:
        logging.error(f"Falha ao gravar memória vetorial: {e}")

# =================================================================
# 6. LOOP PRINCIPAL (COM TELEMETRIA EXTREMA)
# =================================================================
def main():
    global chat, modelo_escolhido
    os.system("cls" if os.name == "nt" else "clear")
    print("=" * 40)
    print(" SISTEMA JARVIS INICIADO ".center(40, "="))
    print("=" * 40)

    speak("Sistemas online e monitoramento por logs ativo, parceria.")
    gatilhos_visao = ["tela", "olhe", "veja", "isso", "print", "erro", "código"]

    while True:
        print("\n" + "-" * 40)
        entrada_inicial = input("[ENTER para falar] ou [Digite seu comando]: ")
        
        logging.info("[RASTREAMENTO] Passo 1: Capturando entrada do usuário...")
        user_input = listen_command() if entrada_inicial == "" else entrada_inicial

        if not user_input:
            logging.info("[RASTREAMENTO] Nenhuma entrada de texto/voz detectada. Reiniciando loop.")
            continue

        if user_input.lower() in ["desligar", "sair", "encerrar"]:
            logging.info("[RASTREAMENTO] Comando de desligamento recebido.")
            speak("Desligando sistemas. Até breve.")
            if _sync_lock.locked():
                logging.info("[Sync] Aguardando upload em segundo plano terminar antes de encerrar...")
                # Espera o worker liberar o lock (com timeout de segurança)
                for _ in range(100):  # até ~10s
                    if _sync_lock.acquire(blocking=False):
                        _sync_lock.release()
                        break
                    time.sleep(0.1)
            pygame.mixer.quit()
            break

        try:
            logging.info(f"[RASTREAMENTO] Passo 2: Buscando '{user_input}' na Memória Vetorial (ChromaDB)...")
            info_oculta = buscar_contexto_vetorial(user_input)
            if info_oculta:
                logging.info("[RASTREAMENTO] Passo 3: Busca no banco concluída com sucesso.")
            else:
                logging.info("[RASTREAMENTO] Passo 3: Busca no banco concluída sem resultados/contexto.")
            
            comando_enriquecido = user_input + info_oculta
            precisa_ver = any(palavra in user_input.lower() for palavra in gatilhos_visao)

            logging.info(f"[RASTREAMENTO] Passo 4: Invocando API do Gemini (Visão={precisa_ver})...")
            if precisa_ver:
                logging.info("[RASTREAMENTO] Passo 4.1: Tirando print da tela (ImageGrab)...")
                print_tela = ImageGrab.grab(all_screens=True)
                conteudo_envio = [comando_enriquecido, print_tela]
            else:
                conteudo_envio = comando_enriquecido
                
            logging.info("[RASTREAMENTO] Passo 4.2: Enviando requisição HTTP para a API da Google...")
            
            # === SISTEMA DE RESILIÊNCIA: FILA DE MODELOS (FALLBACK) ===
            modelos_fallback = [modelo_escolhido, "models/gemini-2.5-flash", "models/gemini-pro-latest", "models/gemini-flash-latest"]
            
            # Remove duplicatas mantendo a ordem de prioridade
            fila_tentativas = list(dict.fromkeys(modelos_fallback))
            
            response = None
            ultimo_erro = None
            
            for modelo_tentativa in fila_tentativas:
                try:
                    if modelo_tentativa != modelo_escolhido:
                        logging.warning(f"[Contingência] Tráfego alto! Trocando para o modelo: {modelo_tentativa}...")
                        
                        # Instancia o novo modelo
                        fallback_model = genai.GenerativeModel(
                            model_name=modelo_tentativa,
                            system_instruction=system_instruction,
                            tools=skills_do_jarvis
                        )
                        # Clona o histórico do chat atual para o novo modelo não perder o contexto da conversa
                        chat_tentativa = fallback_model.start_chat(history=chat.history, enable_automatic_function_calling=True)
                    else:
                        chat_tentativa = chat

                    # Tenta enviar a mensagem
                    response = chat_tentativa.send_message(
                        conteudo_envio,
                        request_options=GEMINI_REQUEST_OPTIONS
                    )
                    
                    # Se sobreviveu sem dar erro 503, consolida o modelo novo como o oficial e sai do loop
                    chat = chat_tentativa
                    modelo_escolhido = modelo_tentativa
                    break 

                except (ServiceUnavailable, DeadlineExceeded, ResourceExhausted, RetryError, NotFound) as e:
                    logging.warning(f"[Gemini] Falha ou modelo inativo ({type(e).__name__}) em {modelo_tentativa}. Pulando para o próximo...")
                    ultimo_erro = e
                    continue # Vai para a próxima iteração tentar o próximo modelo da fila
            
            if not response:
                # Se esgotou a fila inteira e nenhum respondeu, aí sim joga o erro pro except vermelho final
                raise ultimo_erro 
            
            logging.info(f"[RASTREAMENTO] Passo 5: Resposta do Gemini recebida com sucesso via {modelo_escolhido}!")

            try:
                texto_resposta = response.text
            except ValueError:
                texto_resposta = "Comando executado, meu parceiro."

            clean_text = texto_resposta.replace("*", "").replace("#", "")
            
            logging.info("[RASTREAMENTO] Passo 6: Sintetizando áudio da resposta (Edge TTS)...")
            speak(clean_text)

            logging.info("[RASTREAMENTO] Passo 7: Gravando nova interação no ChromaDB...")
            salvar_memoria_vetorial(user_input, clean_text)
            
            logging.info("[RASTREAMENTO] Passo 8: Ciclo completo com sucesso! Liberando para próxima instrução.")

        except (ServiceUnavailable, DeadlineExceeded, ResourceExhausted, RetryError) as e:
            logging.error(f"[Gemini] API indisponível ou sobrecarregada (alta demanda): {e}")
            speak("A API do Gemini está sobrecarregada no momento. Tente novamente em instantes.")
        except Exception as e:
            logging.error(f"Falha de processamento neural no loop principal: {e}", exc_info=True)
            speak("Falha de processamento neural.")

if __name__ == "__main__":
    main()