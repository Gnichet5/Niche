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
from datetime import datetime, timezone
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
import time
from PIL import ImageGrab
from dotenv import load_dotenv
from google.api_core.exceptions import ServiceUnavailable, DeadlineExceeded, ResourceExhausted, RetryError, NotFound
from faster_whisper import WhisperModel
import re

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
Você é Janus, um engenheiro de software autônomo e assistente virtual avançado.
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

[OTIMIZAÇÃO DE VOZ - MANDATÓRIO]
Você opera em duas vias. Todo o seu raciocínio, códigos e explicações longas devem ser escritos normalmente. Porém, no FINAL de toda resposta, você DEVE obrigatoriamente incluir uma tag [VOZ] contendo uma única frase curta e natural (máximo 150 caracteres) que será sintetizada em áudio para mim.
Exemplo:
Aqui está a análise do código... (texto longo)
[VOZ] Finalizei a análise do script e corrigi o erro de sintaxe, parceiro. [/VOZ]

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
    func for nome, func in inspect.getmembers(tools, inspect.isfunction)
    if func.__module__ == tools.__name__ and not nome.startswith('_')
]
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
logging.info("Carregando motor auditivo neural (Whisper)...")
try:
    # O modelo "small" é o ponto de equilíbrio perfeito entre rapidez e precisão para pt-BR.
    # O 'device="auto"' tenta usar placa de vídeo se tiver, senão roda solto na CPU.
    whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
    logging.info("✅ Ouvido Neural ONLINE!")
except Exception as e:
    logging.error(f"Falha ao carregar Whisper. Usando Google nativo como fallback: {e}")
    whisper_model = None

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
    if not text:
        return
    logging.info(f"Janus (Voz): {text}")
    try:
        asyncio.run(generate_audio(text))
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
        
        # --- A MÁGICA ACONTECE AQUI ---
        # Dá 2 segundos de tolerância de silêncio para você respirar/pensar
        recognizer.pause_threshold = 2.0 
        
        try:
            # 1. Captura o áudio (aumentamos o limite da frase para 30 segundos)
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=30)
            
            # 2. Transcrição com Whisper
            if whisper_model:
                nome_temp = "temp_comando_voz.wav"
                with open(nome_temp, "wb") as f:
                    f.write(audio.get_wav_data())
                
                segments, info = whisper_model.transcribe(
                    nome_temp, 
                    beam_size=5, 
                    language="pt", 
                    vad_filter=True
                )
                
                text = "".join([segment.text for segment in segments]).strip()
                
                if os.path.exists(nome_temp):
                    os.remove(nome_temp)
                
                if text:
                    logging.info(f"Usuário (Whisper): {text}")
                    return text
                return None
                
            else:
                text = recognizer.recognize_google(audio, language="pt-BR")
                logging.info(f"Usuário (Google): {text}")
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
GEMINI_TIMEOUT_SEGUNDOS = 120  # Tempo expandido para permitir testes locais pesados (ex: Torch/Whisper)

# Retry ajustado para comportar a execução de ferramentas complexas
RETRY_CURTO_GEMINI = google_retry.Retry(
    initial=1.0,
    maximum=4.0,
    multiplier=2.0,
    deadline=60.0,
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

# Distância máxima (métrica L2 padrão do Chroma) pra uma memória ser considerada
# relevante o suficiente pra entrar no contexto. Comece permissivo (None = sem filtro)
# enquanto calibra: rode um tempo, olhe os valores de "[Córtex] Distâncias" no log,
# e defina esse número pouco acima da distância típica de resultados que fazem sentido.
DISTANCIA_MAXIMA_RELEVANCIA = 0.75 # ex: 0.8 depois de calibrado

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
            n_results=min(max_resultados, colecao_memoria.count()),
            include=["documents", "distances", "metadatas"]
        )
        
        documentos = resultados["documents"][0] if resultados["documents"] else []
        distancias = resultados["distances"][0] if resultados.get("distances") else []

        if documentos:
            logging.info(f"[Córtex] Distâncias dos {len(documentos)} candidato(s): {[round(d, 3) for d in distancias]}")

        # Filtra por relevância: descarta memórias vetorialmente distantes demais
        # da pergunta atual (evita injetar contexto que não tem nada a ver).
        if DISTANCIA_MAXIMA_RELEVANCIA is not None and distancias:
            documentos_relevantes = [
                doc for doc, dist in zip(documentos, distancias)
                if dist <= DISTANCIA_MAXIMA_RELEVANCIA
            ]
        else:
            documentos_relevantes = documentos

        if documentos_relevantes:
            contexto = " | ".join(documentos_relevantes)
            logging.info(f"[Córtex] Resgatou {len(documentos_relevantes)} lembrança(s) relevante(s) de {len(documentos)} candidata(s).")
            return f"\n\n[INFORMAÇÃO OCULTA DE SISTEMA - CONTEXTO DO PASSADO: {contexto}]"
        elif documentos:
            logging.info("[Córtex] Candidatos encontrados, mas nenhum passou no filtro de relevância.")
    except Exception as e:
        logging.error(f"[Córtex] Erro na busca: {e}")
    return ""

def salvar_memoria_vetorial(pergunta, resposta, tipo="casual", importancia=1):
    """
    Grava uma interação no córtex vetorial com metadata estruturada.

    tipo: categoria da memória (ex: "casual", "fato", "preferencia").
          Por enquanto tudo entra como "casual" — a classificação automática
          (decidir o que realmente vale virar memória de longo prazo) é a
          próxima camada a implementar.
    importancia: escala 1-5, usada futuramente pra priorizar retenção/consolidação.
    """
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

            metadata = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tipo": tipo,
                "importancia": importancia,
            }

            # 1. Salva muito rápido no SSD local
            with _db_io_lock:
                colecao_memoria.add(
                    ids=[doc_id],
                    documents=[texto_memoria],
                    embeddings=[vetor],
                    metadatas=[metadata]
                )
            logging.info(f"[Córtex] Nova memória salva no SSD (tipo={tipo}, importância={importancia}).")
            
            # 2. UPLOAD SILENCIOSO PARA A NUVEM!
            sync_local_para_nuvem()
    except Exception as e:
        logging.error(f"Falha ao gravar memória vetorial: {e}")

# =================================================================
# 5.6 CONSOLIDAÇÃO DE MEMÓRIA (O "SONO" DO JARVIS)
# =================================================================
# Mescla memórias muito parecidas em uma síntese só, e poda memórias
# casuais antigas/pouco importantes. Roda por ociosidade (thread em
# background) ou sob demanda (comando manual "consolidar memória").

OCIOSIDADE_LIMITE_SEGUNDOS = 600          # 10 min sem comando = sistema "ocioso"
INTERVALO_MINIMO_ENTRE_CONSOLIDACOES = 6 * 3600  # não repete antes de 6h
SIMILARIDADE_MINIMA_CONSOLIDACAO = 0.92   # cosseno; alto de propósito p/ só mesclar quase-duplicatas
PODA_DIAS_LIMITE = 30                     # casuais mais velhas que isso são candidatas a poda
PODA_IMPORTANCIA_MAXIMA = 2               # só poda quem tem importância baixa (1-2)
MINIMO_MEMORIAS_PARA_CONSOLIDAR = 5       # não vale a pena rodar em bases muito pequenas

_ultimo_comando_timestamp = time.time()
_ultima_consolidacao_timestamp = 0.0
_consolidacao_lock = threading.Lock()


def _cosseno(v1, v2):
    produto_escalar = sum(a * b for a, b in zip(v1, v2))
    norma1 = sum(a * a for a in v1) ** 0.5
    norma2 = sum(b * b for b in v2) ** 0.5
    if norma1 == 0 or norma2 == 0:
        return 0.0
    return produto_escalar / (norma1 * norma2)


def _agrupar_por_similaridade(ids, docs, embeddings, metadatas):
    """Agrupamento guloso: cada item entra no primeiro cluster com que for
    similar o bastante; senão vira o representante de um cluster novo."""
    clusters = []  
    for i in range(len(ids)):
        encaixou = False
        for cluster in clusters:
            representante = cluster[0]
            if _cosseno(embeddings[i], embeddings[representante]) >= SIMILARIDADE_MINIMA_CONSOLIDACAO:
                cluster.append(i)
                encaixou = True
                break
        if not encaixou:
            clusters.append([i])
    return clusters


def consolidar_memoria():
    """Executa uma passada de consolidação: mescla memórias quase-duplicadas
    e poda memórias casuais antigas/pouco importantes. Thread-safe e seguro
    pra rodar tanto em background quanto por comando manual."""
    global _ultima_consolidacao_timestamp

    if not _consolidacao_lock.acquire(blocking=False):
        logging.info("[Consolidação] Já existe uma consolidação em andamento, pulando.")
        return "Já estou consolidando a memória, parceiro. Aguarde essa rodada terminar."

    try:
        if not colecao_memoria or colecao_memoria.count() < MINIMO_MEMORIAS_PARA_CONSOLIDAR:
            logging.info("[Consolidação] Poucas memórias no banco ainda, pulando esta rodada.")
            return "Ainda não tenho memórias suficientes pra valer a pena consolidar."

        logging.info("[Consolidação] Iniciando rotina de consolidação...")
        dados = colecao_memoria.get(include=["embeddings", "documents", "metadatas"])
        ids = dados["ids"]
        docs = dados["documents"]
        embeddings = dados["embeddings"]
        metadatas = [m or {} for m in dados["metadatas"]]

        ids_para_deletar = set()
        entradas_para_adicionar = []  
        clusters = _agrupar_por_similaridade(ids, docs, embeddings, metadatas)
        clusters_mesclados = 0
        for cluster in clusters:
            if len(cluster) < 2:
                continue  # nada pra mesclar

            textos_originais = [docs[i] for i in cluster]
            importancia_maxima = max(int(metadatas[i].get("importancia", 1)) for i in cluster)

            prompt_sintese = (
                "As frases abaixo são memórias parecidas registradas por um assistente de IA. "
                "Funda tudo em UMA única frase factual e concisa em português, preservando os "
                "detalhes que se repetem ou se complementam, sem inventar nada novo. "
                "Responda APENAS com a frase final.\n\n" + "\n".join(f"- {t}" for t in textos_originais)
            )
            try:
                resposta_sintese = modelo_resumo.generate_content(
                    prompt_sintese,
                    generation_config={"max_output_tokens": 150, "temperature": 0.2},
                    request_options=GEMINI_REQUEST_OPTIONS
                )
                texto_consolidado = resposta_sintese.text.strip()
            except Exception as e:
                logging.warning(f"[Consolidação] Falha ao sintetizar cluster, mantendo original mais recente: {e}")
                continue 

            novo_vetor = _sanitizar_vetor(
                genai.embed_content(
                    model=EMBEDDING_MODEL,
                    content=texto_consolidado,
                    output_dimensionality=EMBEDDING_DIMENSAO
                )["embedding"]
            )

            for i in cluster:
                ids_para_deletar.add(ids[i])

            entradas_para_adicionar.append((
                str(uuid.uuid4()),
                texto_consolidado,
                novo_vetor,
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "tipo": "consolidado",
                    "importancia": importancia_maxima,
                    "origem_quantidade": len(cluster),
                }
            ))
            clusters_mesclados += 1

        # --- 2. PODA DE CASUAIS ANTIGAS E POUCO IMPORTANTES ---
        agora = datetime.now(timezone.utc)
        podadas = 0
        for i, mid in enumerate(ids):
            if mid in ids_para_deletar:
                continue  # já foi pro cluster de mesclagem, não poda de novo
            meta = metadatas[i]
            if meta.get("tipo") != "casual":
                continue
            if int(meta.get("importancia", 1)) > PODA_IMPORTANCIA_MAXIMA:
                continue
            timestamp_str = meta.get("timestamp")
            if not timestamp_str:
                continue  # memória legada sem timestamp: não mexe, fica pra auditoria manual
            try:
                data_memoria = datetime.fromisoformat(timestamp_str)
            except ValueError:
                continue
            idade_dias = (agora - data_memoria).days
            if idade_dias >= PODA_DIAS_LIMITE:
                ids_para_deletar.add(mid)
                podadas += 1

        # --- 3. APLICA AS MUDANÇAS NO BANCO ---
        with _db_io_lock:
            if ids_para_deletar:
                colecao_memoria.delete(ids=list(ids_para_deletar))
            for novo_id, texto, vetor, meta in entradas_para_adicionar:
                colecao_memoria.add(ids=[novo_id], documents=[texto], embeddings=[vetor], metadatas=[meta])

        sync_local_para_nuvem()
        _ultima_consolidacao_timestamp = time.time()

        resumo = (
            f"[Consolidação] Concluída: {clusters_mesclados} grupo(s) mesclado(s), "
            f"{podadas} memória(s) casual(is) antiga(s) podada(s). "
            f"Total antes: {len(ids)}, total depois: {len(ids) - len(ids_para_deletar) + len(entradas_para_adicionar)}."
        )
        logging.info(resumo)
        return f"Consolidação concluída: mesclei {clusters_mesclados} grupo(s) de memórias parecidas e podei {podadas} memória(s) antiga(s) sem importância."

    except Exception as e:
        logging.error(f"[Consolidação] Erro durante a rotina: {e}", exc_info=True)
        return "Tive um erro tentando consolidar a memória. Os detalhes estão no log."
    finally:
        _consolidacao_lock.release()


def _monitor_ociosidade():
    """Thread em background: dispara consolidação automática quando o
    sistema fica ocioso por tempo suficiente, respeitando o intervalo
    mínimo entre rodadas."""
    while True:
        time.sleep(60)
        try:
            ocioso_ha = time.time() - _ultimo_comando_timestamp
            desde_ultima_consolidacao = time.time() - _ultima_consolidacao_timestamp
            if (ocioso_ha >= OCIOSIDADE_LIMITE_SEGUNDOS
                    and desde_ultima_consolidacao >= INTERVALO_MINIMO_ENTRE_CONSOLIDACOES):
                logging.info(f"[Consolidação] Sistema ocioso há {int(ocioso_ha)}s. Disparando consolidação automática...")
                consolidar_memoria()
        except Exception as e:
            logging.error(f"[Consolidação] Erro no monitor de ociosidade: {e}")

def selecionar_ferramentas(texto_usuario, historico):
    """Roteador Dinâmico: Reduz tokens de entrada enviando só as ferramentas necessárias."""
    texto = texto_usuario.lower()
    nomes_selecionados = {'ler_memorias_recentes', 'executar_comando_terminal'} # Base
    
    if any(p in texto for p in ["código", "python", "script", "arquivo", "pasta", "erro", "log", "bug", "projeto", "mapear", "criar", "editar"]):
        nomes_selecionados.update({'criar_arquivo', 'editar_arquivo', 'adicionar_ao_arquivo', 'ler_arquivo', 'listar_arquivos_pasta', 'mapear_arquitetura_projeto', 'testar_script_python', 'diagnosticar_erros_logs', 'analisar_otimizar_codigo', 'extrair_informacoes_documento', 'gerenciar_memoria_codigo'})
        
    if any(p in texto for p in ["processo", "memória", "cpu", "matar", "janela", "abrir", "fechar", "minimizar", "aplicativo", "sistema", "download"]):
        nomes_selecionados.update({'verificar_uso_sistema', 'listar_processos_pesados', 'matar_processo', 'listar_janelas_abertas', 'gerenciar_janela', 'abrir_pasta', 'organizar_downloads', 'abrir_aplicativo', 'orquestrar_ambiente'})
        
    if any(p in texto for p in ["pesquisar", "google", "site", "clima", "tempo", "wikipedia", "solução", "internet"]):
        nomes_selecionados.update({'abrir_site', 'pesquisar_no_google', 'buscar_resumo_wikipedia', 'buscar_solucao_web', 'verificar_clima'})
        
    if any(p in texto for p in ["música", "tocar", "volume", "pausar", "próxima", "áudio", "microfone", "ouvir"]):
        nomes_selecionados.update({'tocar_musica', 'controlar_midia', 'diagnosticar_audio'})
    for mensagem in historico:
        for part in getattr(mensagem, 'parts', []):
            if getattr(part, 'function_call', None):
                nomes_selecionados.add(part.function_call.name)
                
    ferramentas_filtradas = [func for func in skills_do_jarvis if func.__name__ in nomes_selecionados]
    logging.info(f"[Roteador Dinâmico] Enviando {len(ferramentas_filtradas)} de {len(skills_do_jarvis)} ferramentas disponíveis.")
    return ferramentas_filtradas
# =================================================================
# 6. LOOP PRINCIPAL (COM TELEMETRIA EXTREMA)
# =================================================================
def main():
    global chat, modelo_escolhido, _ultimo_comando_timestamp
    os.system("cls" if os.name == "nt" else "clear")
    print("=" * 40)
    print(" SISTEMA JANUS INICIADO ".center(40, "="))
    print("=" * 40)

    threading.Thread(target=_monitor_ociosidade, daemon=True).start()
    logging.info("[Consolidação] Monitor de ociosidade iniciado em background.")

    speak("Sistemas online e monitoramento por logs ativo, parceria.")
    gatilhos_visao = ["tela", "olhe", "veja", "isso", "print", "erro", "código"]

    while True:
        with open("heartbeat.txt", "w") as f:
            f.write(str(time.time()))
        print("\n" + "-" * 40)
        entrada_inicial = input("[ENTER para falar] ou [Digite seu comando]: ")
        
        logging.info("[RASTREAMENTO] Passo 1: Capturando entrada do usuário...")
        user_input = listen_command() if entrada_inicial == "" else entrada_inicial

        if not user_input:
            logging.info("[RASTREAMENTO] Nenhuma entrada de texto/voz detectada. Reiniciando loop.")
            continue

        _ultimo_comando_timestamp = time.time()

        if user_input.lower() in ["consolidar memória", "consolidar memoria", "consolide sua memória", "consolide sua memoria"]:
            logging.info("[RASTREAMENTO] Comando manual de consolidação recebido.")
            resultado = consolidar_memoria()
            speak(resultado)
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
                logging.info("[RASTREAMENTO] Passo 4.1: Tirando print da tela e comprimindo imagem...")
                from PIL import Image # Import injetado localmente
                
                # 1. Pega apenas o monitor principal (evita bordas vazias de all_screens)
                print_tela = ImageGrab.grab()
                
                # 2. Redimensiona para o máximo de 1024px de largura (mantendo proporção)
                largura_base = 1024
                if print_tela.size[0] > largura_base:
                    proporcao = (largura_base / float(print_tela.size[0]))
                    altura_nova = int((float(print_tela.size[1]) * float(proporcao)))
                    print_tela = print_tela.resize((largura_base, altura_nova), Image.Resampling.LANCZOS)
                
                # 3. Converte para tons de cinza (Mata o peso das cores, legibilidade de texto intacta)
                print_tela = print_tela.convert('L') 
                
                conteudo_envio = [comando_enriquecido, print_tela]
            else:
                conteudo_envio = comando_enriquecido
                
            logging.info("[RASTREAMENTO] Passo 4.2: Enviando requisição HTTP para a API da Google...")
            
            ferramentas_turno = selecionar_ferramentas(user_input, chat.history) # <-- ROTEADOR AQUI
            
            # === SISTEMA DE RESILIÊNCIA: FILA DE MODELOS (FALLBACK) ===
            modelos_fallback = [modelo_escolhido, "models/gemini-2.5-flash", "models/gemini-pro-latest", "models/gemini-flash-latest"]
            fila_tentativas = list(dict.fromkeys(modelos_fallback))
            response = None
            ultimo_erro = None
            
            for modelo_tentativa in fila_tentativas:
                try:
                    if modelo_tentativa != modelo_escolhido:
                        logging.warning(f"[Contingência] Tráfego alto! Trocando para o modelo: {modelo_tentativa}...")
                        fallback_model = genai.GenerativeModel(
                            model_name=modelo_tentativa,
                            system_instruction=system_instruction,
                            tools=ferramentas_turno # <-- MUDANÇA AQUI (Usa as filtradas)
                        )
                        chat_tentativa = fallback_model.start_chat(history=chat.history, enable_automatic_function_calling=True)
                    else:
                        chat_tentativa = chat

                    response = chat_tentativa.send_message(
                        conteudo_envio,
                        request_options=GEMINI_REQUEST_OPTIONS
                    )
                    
                    chat = chat_tentativa
                    modelo_escolhido = modelo_tentativa
                    break 

                except (ServiceUnavailable, DeadlineExceeded, ResourceExhausted, RetryError, NotFound) as e:
                    logging.warning(f"[Gemini] Falha ou modelo inativo ({type(e).__name__}) em {modelo_tentativa}. Pulando para o próximo...")
                    ultimo_erro = e
                    continue
            
            if not response:
                raise ultimo_erro 
            
            logging.info(f"[RASTREAMENTO] Passo 5: Resposta do Gemini recebida com sucesso via {modelo_escolhido}!")

            try:
                texto_resposta = response.text
            except ValueError:
                texto_resposta = "Comando executado, meu parceiro."

            # --- MÁGICA DA EXTRAÇÃO DA VOZ (BLINDADA) ---
            # Remove blocos de código sujos e quebras vazias antes de tentar capturar a tag
            texto_limpo = texto_resposta.strip()
            
            # O Regex agora ignora espaços em branco ao redor da tag
            match_voz = re.search(r'\[VOZ\]\s*(.*?)\s*\[/VOZ\]', texto_limpo, re.DOTALL | re.IGNORECASE)
            
            if match_voz:
                texto_voz = match_voz.group(1).strip()
                # Tira a tag [VOZ] (e tudo dentro dela) da resposta que vai pra tela
                texto_tela = re.sub(r'\[VOZ\].*?\[/VOZ\]', '', texto_limpo, flags=re.DOTALL | re.IGNORECASE).strip()
            else:
                texto_voz = "Comando processado, aguardando instruções."
                texto_tela = texto_limpo

            # Limpa firulas de markdown do texto da tela sem estragar blocos de código
            texto_tela_exibicao = texto_tela.replace("`", "") 
            
            print("\n" + "=" * 40)
            print("[Janus - Resposta completa exibida no console]")
            print(texto_tela_exibicao)
            print("=" * 40)
            
            if match_voz:
                texto_voz = match_voz.group(1).strip()
                texto_tela = texto_resposta.replace(match_voz.group(0), "").strip()
            else:
                texto_voz = "Processamento concluído."
                texto_tela = texto_resposta

            texto_tela_limpo = texto_tela.replace("*", "").replace("#", "")
            
            print("\n" + "=" * 40)
            print("[Janus - Resposta completa exibida no console]")
            print(texto_tela_limpo)
            print("=" * 40)
            
            logging.info("[RASTREAMENTO] Passo 6: Sintetizando áudio da resposta (Edge TTS)...")
            speak(texto_voz) 

            logging.info("[RASTREAMENTO] Passo 7: Gravando nova interação no ChromaDB...")
            salvar_memoria_vetorial(user_input, texto_tela_limpo) # <-- SALVA SÓ A TELA
            logging.info("[RASTREAMENTO] Passo 8: Ciclo completo com sucesso! Liberando para próxima instrução.")
            # === PASSO 9: PODA DE MEMÓRIA (GARBAGE COLLECTOR DE IMAGENS) ===
            logging.info("[RASTREAMENTO] Passo 9: Otimizando histórico de contexto (Poda Visual)...")
            novo_historico = []
            for msg in chat.history[-20:]: 
                partes_limpas = [p for p in msg.parts if not hasattr(p, 'inline_data')]
                
                if partes_limpas:
                    nova_msg = type(msg)(role=msg.role, parts=partes_limpas)
                    novo_historico.append(nova_msg)
            chat.history = novo_historico
                
        except (ServiceUnavailable, DeadlineExceeded, ResourceExhausted, RetryError, NotFound) as e:    
            logging.error(f"[Gemini] API indisponível ou sobrecarregada (alta demanda): {e}")
            speak("A API do Gemini está sobrecarregada no momento. Tente novamente em instantes.")
        except Exception as e:
            logging.error(f"Falha de processamento neural no loop principal: {e}", exc_info=True)
            speak("Falha de processamento neural.")

if __name__ == "__main__":
    main()