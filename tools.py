import os
import webbrowser
import pygetwindow as gw
import psutil
import pyautogui
import urllib.request
import urllib.parse
import json
import subprocess
import logging
import requests
from bs4 import BeautifulSoup
from googlesearch import search
import urllib3  
import concurrent.futures
import time
import subprocess
from datetime import datetime
import shutil
import sys

colecao_memoria_global = None
os.makedirs("logs_sistema", exist_ok=True)
arquivo_log = os.path.join("logs_sistema", "jarvis_tools.log")
_MEMORIA_DE_CODIGO = {}

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(arquivo_log, encoding='utf-8')]
)
DEFAULT_MAX_FILE_READ_CHARS = 150000
DEFAULT_MAX_WEB_SCRAPE_CHARS_PER_PAGE = 3000
DEFAULT_MAX_FILES_TO_SCAN_SUSPICIOUS = 1500
DIRETORIO_SEGURO = os.path.abspath(r"C:\Users\guipe\Documents\Niche")
# =================================================================
# SETOR 1: SISTEMA E HARDWARE
# Ferramentas para monitoramento de recursos e gerenciamento de processos.
# =================================================================

def verificar_uso_sistema() -> str:
    """Verifica e retorna o uso de CPU e Memória RAM do computador."""
    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory().percent
    logging.info(f"Verificação de uso do sistema: CPU {cpu}%, RAM {ram}%")
    return f"A CPU está em {cpu}% de uso. A memória RAM está em {ram}% de uso."

def listar_processos_pesados(quantidade: int = 5) -> str:
    """Lista os processos que mais estão consumindo memória RAM no computador no momento.
    O parâmetro quantidade define quantos processos retornar (padrão é 5)."""
    processos = []

    for proc in psutil.process_iter(['pid', 'name', 'memory_percent']):
        try:
            if proc.info['memory_percent'] is not None:
                processos.append(proc.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    processos = sorted(processos, key=lambda p: p['memory_percent'], reverse=True)

    resultado = f"Top {quantidade} processos consumindo mais RAM:\n"
    for p in processos[:quantidade]:
        resultado += f"- {p['name']} (PID: {p['pid']}): {p['memory_percent']:.1f}%\n"
    logging.info(f"Listados os {quantidade} processos mais pesados.")
    return resultado

def matar_processo(identificador: str) -> str:
    """Encerra um processo travado ou consumindo muita memória no Windows."""
    
    # NOVA LINHA: Proteção anti-rebote para evitar que o processo seja "morto" duas vezes no retry
    if _anti_rebote(f"kill_{identificador}"):
        logging.info(f"Comando de matar processo '{identificador}' ignorado pelo anti-rebote.")
        return f"Ação ignorada: O comando para encerrar '{identificador}' já foi disparado na tentativa anterior."

    encerrados = 0

    try:
        pid = int(identificador)
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['pid'] == pid:
                nome = proc.info['name']
                proc.kill()
                logging.info(f"Processo {nome} (PID {pid}) encerrado.")
                return f"Processo {nome} (PID {pid}) encerrado com sucesso."
        return f"Não encontrei o PID {pid} rodando."
    except ValueError:
        nome_alvo = identificador.lower()
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] and nome_alvo in proc.info['name'].lower():
                    proc.kill()
                    encerrados += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if encerrados > 0:
            logging.info(f"Foram encerrados {encerrados} processo(s) referentes a '{identificador}'.")
            return f"Foram encerrados {encerrados} processo(s) referentes a '{identificador}'. Você pode tentar verificar o consumo de RAM novamente."
        return f"Nenhum processo chamado '{identificador}' encontrado."

# =================================================================
# SETOR 2: NAVEGAÇÃO E ARQUIVOS
# Ferramentas para manipulação do explorador de arquivos e sites.
# =================================================================

def abrir_site(url: str) -> str:
    """Abre um site específico no navegador padrão do usuário."""
    if not url.startswith('http'):
        url = 'https://' + url
    webbrowser.open(url)
    logging.info(f"Site {url} aberto.")
    return f"Site {url} aberto com sucesso."

def abrir_pasta(caminho: str) -> str:
    """Abre uma pasta no Windows Explorer com tratamento seguro de erros."""
    try:
        os.startfile(caminho)
        logging.info(f"Pasta '{caminho}' aberta.")
        return f"Pasta aberta na tela com sucesso."
    except FileNotFoundError:
        logging.warning(f"Tentativa de abrir pasta inexistente: {caminho}")
        return "Aviso: A pasta solicitada não foi encontrada no sistema."
    except PermissionError:
        logging.warning(f"Acesso negado à pasta: {caminho}")
        return "Aviso: Não tenho permissão do sistema operacional para abrir esta pasta."
    except OSError:
        logging.error(f"Erro de SO ao tentar abrir a pasta: {caminho}")
        return "Aviso: Caminho inválido ou erro estrutural ao tentar abrir o diretório."

def listar_arquivos_pasta(caminho: str) -> str:
    """Retorna o conteúdo de um diretório sem expor rastreios de pilha."""
    try:
        arquivos = os.listdir(caminho)
        if not arquivos:
            logging.info(f"A pasta '{caminho}' está vazia.")
            return "A pasta está vazia."
        
        logging.info(f"Conteúdo da pasta '{caminho}' listado.")
        return f"Conteúdo do diretório: " + ", ".join(arquivos)
    
    except FileNotFoundError:
        return "Aviso: O diretório especificado não existe."
    except PermissionError:
        return "Aviso: Bloqueio de segurança. Não tenho permissão de leitura para esta pasta."
    except OSError:
        return "Aviso: Falha na leitura. O caminho pode estar mal formatado ou inacessível."
def ler_arquivo(caminho_arquivo: str) -> str:
    """
    Lê e retorna o conteúdo de um arquivo local (.py, .json, .log, .md, .txt, etc)
    para análise de código ou depuração de erros.
    """
    caminho_arquivo = caminho_arquivo.strip('\"').strip("\'")

    if not os.path.isfile(caminho_arquivo):
        logging.error(f"Erro: Arquivo não encontrado em '{caminho_arquivo}'.")
        return f"Erro: Não foi possível encontrar o arquivo no caminho '{caminho_arquivo}'."

    try:
        max_chars = int(os.getenv("MAX_FILE_READ_CHARS", str(DEFAULT_MAX_FILE_READ_CHARS)))
        
        with open(caminho_arquivo, 'r', encoding='utf-8') as arquivo:
            conteudo = arquivo.read(max_chars) # Otimização: Lê direto no limite
            
            # Checa se ainda tem bytes sobrando sem precisar carregá-los
            if arquivo.read(1): 
                logging.info(f"Arquivo '{caminho_arquivo}' muito grande, lendo os primeiros {max_chars} caracteres.")
                return f"Arquivo muito grande. Aqui estão os primeiros {max_chars} caracteres:\n\n{conteudo}"
            
            logging.info(f"Arquivo '{caminho_arquivo}' lido com sucesso.")
            return conteudo

    except UnicodeDecodeError:
        try:
            with open(caminho_arquivo, 'r', encoding='latin-1') as arquivo:
                logging.info(f"Arquivo '{caminho_arquivo}' lido com encoding latin-1 após falha UTF-8.")
                return arquivo.read(max_chars) 
        except Exception as e:
            logging.error(f"Falha na decodificação do arquivo '{caminho_arquivo}'. Erro: {e}")
            return f"Falha na decodificação. O arquivo pode não ser texto puro. Erro: {e}"

    except Exception as e:
        logging.error(f"Erro inesperado ao tentar ler o arquivo '{caminho_arquivo}': {e}")
        return f"Erro inesperado ao tentar ler o arquivo: {e}"
    
def organizar_downloads(caminho: str = None) -> str:
    """
    Organiza automaticamente os arquivos da pasta Downloads do usuário,
    movendo-os para subpastas categorizadas.
    """
    import shutil

    if not caminho:
        caminho = os.path.join(os.path.expanduser('~'), 'Downloads')
    if _anti_rebote(f"org_downloads_{caminho}"):
        logging.info(f"Organização da pasta '{caminho}' ignorada pelo anti-rebote.")
        return "Ação ignorada: A faxina nesta pasta já foi iniciada ou concluída nos últimos instantes."
    
    if not os.path.exists(caminho):
        return f"A pasta '{caminho}' não existe ou está inacessível."

    categorias = {
        "Imagens": ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp'],
        "Documentos": ['.pdf', '.doc', '.docx', '.txt', '.xls', '.xlsx', '.csv', '.ppt', '.pptx'],
        "Instaladores": ['.exe', '.msi', '.bat'],
        "Compactados": ['.zip', '.rar', '.7z', '.tar'],
        "Mídia": ['.mp3', '.mp4', '.mkv', '.avi', '.mov', '.flv'],
        "Códigos": ['.py', '.js', '.html', '.css', '.json', '.sql', '.ts', '.java', '.c', '.cpp', '.php', '.rb']
    }

    arquivos_movidos = 0

    try:
        for arquivo in os.listdir(caminho):
            caminho_arquivo = os.path.join(caminho, arquivo)
            
            if os.path.isfile(caminho_arquivo):
                _, extensao = os.path.splitext(arquivo)
                extensao = extensao.lower()
                
                pasta_destino_nome = "Outros"
                for categoria, extensoes in categorias.items():
                    if extensao in extensoes:
                        pasta_destino_nome = categoria
                        break
                        
                pasta_destino_caminho = os.path.join(caminho, pasta_destino_nome)
                if not os.path.exists(pasta_destino_caminho):
                    os.makedirs(pasta_destino_caminho)
                    
                shutil.move(caminho_arquivo, os.path.join(pasta_destino_caminho, arquivo))
                arquivos_movidos += 1

        if arquivos_movidos > 0:
            logging.info(f"Foram organizados {arquivos_movidos} arquivos na pasta de Downloads.")
            return f"Faxina concluída! Foram organizados {arquivos_movidos} arquivos na pasta de Downloads."
        else:
            logging.info("A pasta de downloads já está limpa e organizada.")
            return "A pasta de downloads já está limpa e organizada."

    except Exception as e:
        logging.error(f"Erro ao organizar a pasta: {e}")
        return f"Erro ao organizar a pasta: {e}"

def criar_arquivo(caminho_relativo: str, conteudo: str) -> str:
    """Cria um novo arquivo de texto de forma segura dentro da sandbox."""
    
    if _anti_rebote(f"criar_{caminho_relativo}", cooldown_segundos=30):
        return "Ação ignorada: O comando de criação já foi disparado na tentativa anterior."

    caminho_limpo = caminho_relativo.strip('\"').strip("\'")
    caminho_absoluto = os.path.abspath(os.path.join(DIRETORIO_SEGURO, caminho_limpo))
    
    # Sandboxing
    if not caminho_absoluto.startswith(DIRETORIO_SEGURO):
        logging.warning(f"Path Traversal bloqueado na criação: {caminho_absoluto}")
        return "Acesso negado: Tentativa de criar arquivo fora do diretório seguro."

    if os.path.exists(caminho_absoluto):
        return "Erro: Este arquivo já existe. Utilize a ferramenta de edição."

    # Human-in-the-Loop
    print("\n" + "+" * 60)
    print(" ALERTA DE SEGURANÇA: CRIAÇÃO DE ARQUIVO ".center(60, " "))
    print("+" * 60)
    print(f"Alvo: {caminho_absoluto}")
    print(f"Tamanho do conteúdo: {len(conteudo)} caracteres.")
    print("-" * 60)
    
    confirmacao = input("Permitir a criação deste arquivo? (S/N): ").strip().lower()

    if confirmacao != 's':
        logging.warning("Criação de arquivo bloqueada pelo usuário.")
        return "Acesso negado: Criação cancelada pelo usuário."

    try:
        diretorio = os.path.dirname(caminho_absoluto)
        if not os.path.exists(diretorio):
            os.makedirs(diretorio)

        with open(caminho_absoluto, 'w', encoding='utf-8') as f:
            f.write(conteudo)
            
        logging.info(f"Arquivo '{caminho_limpo}' criado com sucesso.")
        return f"Arquivo '{caminho_limpo}' criado com sucesso no diretório seguro."
        
    except Exception as e:
        logging.error(f"Erro ao criar arquivo '{caminho_absoluto}': {e}")
        return f"Erro crítico durante a criação: {e}"

def editar_arquivo(caminho_relativo: str, novo_conteudo: str) -> str:
    """Edita um arquivo existente com restrição de diretório e backup automático versionado."""
    
    if _anti_rebote(f"editar_{caminho_relativo}", cooldown_segundos=30):
        return "Ação ignorada: O comando de edição já foi disparado na tentativa anterior."

    caminho_limpo = caminho_relativo.strip('\"').strip("\'")
    caminho_absoluto = os.path.abspath(os.path.join(DIRETORIO_SEGURO, caminho_limpo))
    
    # Sandboxing
    if not caminho_absoluto.startswith(DIRETORIO_SEGURO):
        logging.warning(f"Path Traversal bloqueado na edição: {caminho_absoluto}")
        return "Acesso negado: Tentativa de editar arquivo fora do diretório seguro."

    if not os.path.exists(caminho_absoluto):
        return "Erro: Arquivo não encontrado. Utilize a ferramenta de criar arquivo primeiro."

    # Human-in-the-Loop
    print("\n" + "!" * 60)
    print(" ALERTA DE SEGURANÇA: SOBRESCRITA DE ARQUIVO ".center(60, " "))
    print("!" * 60)
    print(f"Alvo: {caminho_absoluto}")
    print(f"Atenção: O conteúdo atual será totalmente substituído por um novo bloco de {len(novo_conteudo)} caracteres.")
    print("-" * 60)
    
    confirmacao = input("Permitir a modificação deste arquivo? (S/N): ").strip().lower()

    if confirmacao != 's':
        logging.warning("Edição de arquivo bloqueada pelo usuário.")
        return "Acesso negado: O usuário cancelou a modificação do arquivo."

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        caminho_backup = f"{caminho_absoluto}.{timestamp}.bak"
        shutil.copy2(caminho_absoluto, caminho_backup)
        logging.info(f"Backup de segurança criado: {caminho_backup}")
        
        # Escrita
        with open(caminho_absoluto, 'w', encoding='utf-8') as f:
            f.write(novo_conteudo)
            
        logging.info(f"Arquivo '{caminho_limpo}' editado com sucesso.")
        return f"Arquivo '{caminho_limpo}' atualizado com sucesso. O backup de segurança foi salvo com a extensão .{timestamp}.bak"
        
    except Exception as e:
        logging.error(f"Erro crítico ao editar arquivo '{caminho_absoluto}': {e}")
        return f"Erro crítico durante a edição: {e}"

def adicionar_ao_arquivo(caminho_relativo: str, conteudo: str) -> str:
    """Adiciona conteúdo ao final de um arquivo existente de forma segura."""
    
    if _anti_rebote(f"append_{caminho_relativo}", cooldown_segundos=15):
        return "Ação ignorada: O comando de adição já foi disparado na tentativa anterior."

    caminho_limpo = caminho_relativo.strip('\"').strip("\'")
    caminho_absoluto = os.path.abspath(os.path.join(DIRETORIO_SEGURO, caminho_limpo))
    if not caminho_absoluto.startswith(DIRETORIO_SEGURO):
        logging.warning(f"Path Traversal bloqueado no append: {caminho_absoluto}")
        return "Acesso negado: Tentativa de alterar arquivo fora do diretório seguro."
    print("\n" + "~" * 60)
    print(" ALERTA: ADIÇÃO DE CONTEÚDO (APPEND) ".center(60, " "))
    print("~" * 60)
    print(f"Alvo: {caminho_absoluto}")
    print(f"Serão inseridos {len(conteudo)} caracteres ao final do arquivo.")
    print("-" * 60)
    
    confirmacao = input("Permitir a adição? (S/N): ").strip().lower()

    if confirmacao != 's':
        logging.warning("Adição bloqueada pelo usuário.")
        return "Acesso negado: O usuário cancelou a modificação."

    try:
        with open(caminho_absoluto, 'a', encoding='utf-8') as f:
            f.write("\n" + conteudo)
            
        logging.info(f"Conteúdo adicionado com sucesso em '{caminho_limpo}'.")
        return f"Conteúdo adicionado com sucesso ao final do arquivo '{caminho_limpo}'."
        
    except Exception as e:
        logging.error(f"Erro crítico no append '{caminho_absoluto}': {e}")
        return f"Erro crítico durante a adição: {e}"

def mapear_arquitetura_projeto(caminho_relativo: str = ".") -> str:
    """
    Mapeia a árvore de diretórios e arquivos de um projeto.
    Ignora automaticamente pastas de dependências e compilação pesadas para fornecer 
    à IA uma visão clara da estrutura do código.
    """
    caminho_limpo = caminho_relativo.strip('\"').strip("\'")
    caminho_absoluto = os.path.abspath(os.path.join(DIRETORIO_SEGURO, caminho_limpo))
    
    # Sandboxing de segurança
    if not caminho_absoluto.startswith(DIRETORIO_SEGURO):
        logging.warning(f"Path Traversal bloqueado no mapeamento: {caminho_absoluto}")
        return "Acesso negado: Tentativa de mapear fora do diretório seguro."
        
    if not os.path.exists(caminho_absoluto):
        return f"Erro: O diretório '{caminho_limpo}' não existe."
    pastas_ignoradas = {
        '.git', 'node_modules', '.next', 'vendor', 
        'venv', '.venv', '__pycache__', 'target', 
        'bin', 'build', 'dist', '.idea', '.vscode'
    }
    
    arvore = []
    
    try:
        for root, dirs, files in os.walk(caminho_absoluto):
            dirs[:] = [d for d in dirs if d not in pastas_ignoradas]
            
            nivel = root.replace(caminho_absoluto, '').count(os.sep)
            indentacao = ' ' * 4 * nivel
            pasta_atual = os.path.basename(root)
            
            if nivel == 0:
                arvore.append(f"📁 {pasta_atual if pasta_atual else 'Raiz'}/")
            else:
                arvore.append(f"{indentacao}📂 {pasta_atual}/")
            
            subindentacao = ' ' * 4 * (nivel + 1)
            for f in files:
                if not f.endswith(('.pyc', '.class', '.exe', '.dll', '.so')):
                    arvore.append(f"{subindentacao}📄 {f}")
        
        resultado = "\n".join(arvore)
        
        # Proteção contra estouro de limite de tokens do modelo
        if len(resultado) > 12000:
            resultado = resultado[:12000] + "\n... [Árvore truncada devido ao tamanho extremo]"
            
        logging.info(f"Mapeamento de arquitetura concluído para '{caminho_limpo}'.")
        return f"--- ARQUITETURA DO PROJETO ({caminho_limpo}) ---\n{resultado}"

    except Exception as e:
        logging.error(f"Erro ao mapear arquitetura em '{caminho_absoluto}': {e}")
        return f"Erro crítico ao tentar mapear a arquitetura: {e}"
# =================================================================
# SETOR 3: GERENCIAMENTO DE JANELAS
# Ferramentas para controle da interface visual do sistema operacional.
# =================================================================

def listar_janelas_abertas() -> str:
    """Retorna uma lista com os nomes das janelas visíveis no Windows."""
    todas_janelas = gw.getAllTitles()
    janelas_visiveis = [j for j in todas_janelas if j.strip() != ""]
    if janelas_visiveis:
        logging.info("Janelas abertas listadas.")
        return "Janelas abertas: " + ", ".join(janelas_visiveis)
    logging.info("Nenhuma janela visível encontrada.")
    return "Nenhuma janela visível."

def gerenciar_janela(titulo_janela: str, acao: str) -> str:
    """Controla janelas. Ação deve ser: 'focar', 'minimizar', 'maximizar' ou 'fechar'."""
    try:
        janelas_encontradas = gw.getWindowsWithTitle(titulo_janela)
        if not janelas_encontradas:
            logging.warning(f"Não encontrei a janela '{titulo_janela}'.")
            return f"Não encontrei a janela '{titulo_janela}'."

        janela = janelas_encontradas[0]

        if acao == 'focar':
            if janela.isMinimized:
                janela.restore()
            janela.activate()
            logging.info(f"Foco na janela '{janela.title}'.")
            return f"Foco na janela '{janela.title}'."
        elif acao == 'minimizar':
            janela.minimize()
            logging.info(f"Minimizou '{janela.title}'.")
            return f"Minimizou '{janela.title}'."
        elif acao == 'maximizar':
            janela.maximize()
            logging.info(f"Maximizou '{janela.title}'.")
            return f"Maximizou '{janela.title}'."
        elif acao == 'fechar':
            janela.close()
            logging.info(f"Fechou '{janela.title}'.")
            return f"Fechou '{janela.title}'."
        else:
            logging.warning(f"Ação '{acao}' inválida para gerenciar janela.")
            return "Ação inválida. Use 'focar', 'minimizar', 'maximizar' ou 'fechar'."
    except Exception as e:
        logging.error(f"Erro ao gerenciar janela '{titulo_janela}' com ação '{acao}': {str(e)}")
        return f"Erro ao gerenciar janela: {str(e)}"

# =================================================================
# SETOR 4: BUSCA E INFORMAÇÃO
# Ferramentas para consumo de dados externos da internet.
# =================================================================

def pesquisar_no_google(termo: str) -> str:
    """Abre uma nova guia no navegador fazendo uma pesquisa no Google sobre o termo solicitado."""
    url = f"https://www.google.com/search?q={urllib.parse.quote(termo)}"
    webbrowser.open(url)
    logging.info(f"Pesquisa no Google aberta para: {termo}")
    return f"Guia de pesquisa aberta para: {termo}"

def buscar_resumo_wikipedia(termo: str) -> str:
    """Busca um resumo explicativo na Wikipedia para responder a dúvidas do usuário sem abrir o navegador."""
    try:
        url = f"https://pt.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(termo)}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Jarvis_Assistant/1.0'})
        with urllib.request.urlopen(req) as response:
            dados = json.loads(response.read().decode())
            resumo = dados.get('extract', 'Nenhum resumo encontrado para este termo.')
            logging.info(f"Resumo da Wikipedia encontrado para: {termo}")
            return resumo
    except Exception as e:
        logging.error(f"Não foi possível encontrar informações diretas sobre '{termo}' na Wikipedia. Erro: {e}")
        return f"Não foi possível encontrar informações diretas sobre '{termo}' na Wikipedia."

import concurrent.futures

def _extrair_texto_url(url, headers, max_chars):
    """Função auxiliar para baixar links em paralelo."""
    try:
        response = requests.get(url, headers=headers, timeout=8)
        soup = BeautifulSoup(response.text, 'html.parser')
        conteudo_tags = soup.find_all(['p', 'pre', 'code', 'article', 'main', 'section', 'div'], 
                                       class_=['content', 'post-content', 'article-body', 'entry-content', 'main-content', 'text-content'])
        
        texto_extraido = ""
        for tag in conteudo_tags:
            for script_or_style in tag(["script", "style"]):
                script_or_style.decompose()
            texto_extraido += tag.get_text(separator=' ', strip=True) + "\n"

        logging.info(f"Conteúdo raspado da URL {url}.")
        return f"--- Fonte: {url} ---\n{texto_extraido[:max_chars]}\n\n"
    except Exception as e:
        logging.error(f"Erro ao raspar a página {url}: {e}")
        return f"Erro ao raspar a página {url}: {e}\n\n"

def buscar_solucao_web(pergunta: str) -> str:
    """Pesquisa qualquer tipo de informação na internet de forma assíncrona."""
    logging.info(f"JARVIS pesquisando na web por: {pergunta}")
    resultados_texto = f"Resultados da pesquisa para: {pergunta}\n\n"

    try:
        links = list(search(pergunta, num=3, stop=3, pause=2))

        if not links:
            return "Nenhum resultado encontrado no Google."

        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        max_scrape_chars = int(os.getenv("MAX_WEB_SCRAPE_CHARS_PER_PAGE", str(DEFAULT_MAX_WEB_SCRAPE_CHARS_PER_PAGE)))

        # Otimização: Uso de Threads para requisições paralelas
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futuros = [executor.submit(_extrair_texto_url, url, headers, max_scrape_chars) for url in links]
            for futuro in concurrent.futures.as_completed(futuros):
                resultados_texto += futuro.result()

        return resultados_texto

    except Exception as e:
        logging.critical(f"Erro crítico na ferramenta de busca web para '{pergunta}': {e}")
        return f"Erro crítico na ferramenta de busca web: {e}"

def verificar_clima(cidade: str) -> str:
    """
    Busca a previsão do tempo atual e condições climáticas reais para qualquer cidade.
    Acione esta ferramenta sempre que o usuário perguntar sobre o clima, temperatura ou se vai chover.
    """
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    cidade_formatada = urllib.parse.quote(cidade)

    try:
        url = f"https://pt.wttr.in/{cidade_formatada}?format=%C+|+Temperatura:+%t+|+Sensação:+%f+|+Umidade:+%h"
        resposta = requests.get(url, timeout=5, verify=False)

        if resposta.status_code == 200:
            logging.info(f"Dados meteorológicos de {cidade} obtidos com sucesso.")
            return f"Dados meteorológicos de {cidade}: {resposta.text}"
        logging.warning(f"Falha ao buscar dados climáticos para {cidade}. Código: {resposta.status_code}")
        return f"Falha ao buscar dados (Código {resposta.status_code})."
    except Exception as e:
        logging.error(f"Erro de conexão ao verificar o clima para {cidade}: {e}")
        return f"Erro de conexão ao verificar o clima: {e}"

# =================================================================
# SETOR 5: SEGURANÇA
# Ferramentas de análise e prevenção local.
# =================================================================

def verificar_arquivos_suspeitos(caminho: str) -> str:
    """Examina uma pasta e suas subpastas em busca de executáveis não usuais ou scripts maliciosos."""
    extensoes_perigosas = ['.exe', '.bat', '.cmd', '.vbs', '.ps1', '.msi', '.scr', '.js', '.jar']
    arquivos_encontrados = []

    if not os.path.exists(caminho):
        logging.error(f"O caminho {caminho} não foi encontrado no sistema.")
        return f"O caminho {caminho} não foi encontrado no sistema."

    try:
        contador = 0
        max_files_scan = int(os.getenv("MAX_FILES_TO_SCAN_SUSPICIOUS", str(DEFAULT_MAX_FILES_TO_SCAN_SUSPICIOUS)))

        for raiz, _, arquivos in os.walk(caminho):
            for arquivo in arquivos:
                contador += 1
                if contador > max_files_scan:
                    alerta = f"Análise interrompida no limite de {max_files_scan} arquivos."
                    if arquivos_encontrados:
                        logging.warning(f"{alerta} Suspeitos até o momento encontrados.")
                        return f"{alerta} Suspeitos até o momento: " + ", ".join(arquivos_encontrados)
                    logging.info(f"{alerta} Nenhum suspeito nos arquivos analisados.")
                    return f"{alerta} Nenhum suspeito nos arquivos analisados."

                _, ext = os.path.splitext(arquivo)
                if ext.lower() in extensoes_perigosas:
                    arquivos_encontrados.append(os.path.join(raiz, arquivo))

        if not arquivos_encontrados:
            logging.info(f"Escaneamento de '{caminho}' concluído. Nenhum arquivo perigoso encontrado.")
            return "Escaneamento concluído. Nenhum arquivo com extensão perigosa foi encontrado."

        resultado = f"Atenção, {len(arquivos_encontrados)} arquivos executáveis/scripts encontrados:\n"
        resultado += "\n".join(arquivos_encontrados)
        logging.warning(f"Arquivos suspeitos encontrados em '{caminho}'.")
        return resultado

    except Exception as e:
        logging.error(f"Erro de permissão ou falha ao escanear a pasta '{caminho}': {str(e)}")
        return f"Erro de permissão ou falha ao escanear a pasta: {str(e)}"

# =================================================================
# SETOR 6: MÍDIA E APLICATIVOS
# Ferramentas de execução de programas e controle de áudio/mídia.
# =================================================================

_CACHE_ATALHOS = {}
_REGISTRO_EXECUCOES = {}

def _anti_rebote(id_comando: str, cooldown_segundos: int = 15) -> bool:
    """Bloqueia a execução de um mesmo comando crítico em um curto intervalo de tempo."""
    agora = time.time()
    if id_comando in _REGISTRO_EXECUCOES:
        if (agora - _REGISTRO_EXECUCOES[id_comando]) < cooldown_segundos:
            return True
            
    _REGISTRO_EXECUCOES[id_comando] = agora
    return False

def abrir_aplicativo(nome_app: str) -> str:
    """Busca dinamicamente e abre um aplicativo utilizando cache em memória."""
    global _CACHE_ATALHOS
    nome_busca = nome_app.lower().strip()

    apps_nativos = {
        'calculadora': 'calc', 'bloco de notas': 'notepad', 'paint': 'mspaint',
        'prompt de comando': 'cmd', 'terminal': 'wt', 'powershell': 'powershell',
        'painel de controle': 'control', 'configurações': 'ms-settings:',
        'vscode': 'code', 'excel': 'excel', 'word': 'winword', 'powerpoint': 'powerpnt',
        'chrome': 'chrome', 'firefox': 'firefox', 'edge': 'msedge',
        'spotify': 'spotify', 'vlc': 'vlc', 'explorador de arquivos': 'explorer'
    }

    if nome_busca in apps_nativos:
        try:
            subprocess.run(f"start {apps_nativos[nome_busca]}", shell=True, check=True)
            return f"Aplicativo de sistema '{nome_busca}' acionado."
        except subprocess.CalledProcessError as e:
            return f"Erro ao iniciar aplicativo nativo: {e}"

    # Otimização: Varre o disco apenas se o cache estiver vazio
    if not _CACHE_ATALHOS:
        logging.info("Construindo cache de atalhos do sistema na RAM...")
        pastas_iniciar = [
            os.path.join(os.environ.get('PROGRAMDATA', 'C:\\ProgramData'), r'Microsoft\Windows\Start Menu\Programs'),
            os.path.join(os.environ.get('APPDATA', ''), r'Microsoft\Windows\Start Menu\Programs')
        ]
        
        for pasta in pastas_iniciar:
            if not os.path.exists(pasta):
                continue
            for raiz, _, arquivos in os.walk(pasta):
                for arquivo in arquivos:
                    if arquivo.lower().endswith(('.lnk', '.exe')):
                        nome_atalho = os.path.splitext(arquivo)[0].lower()
                        _CACHE_ATALHOS[nome_atalho] = os.path.join(raiz, arquivo)

    # Consulta no dicionário (RAM) em vez do HD
    caminho_completo = None
    nome_encontrado = None
    
    for nome_atalho, caminho in _CACHE_ATALHOS.items():
        if nome_busca in nome_atalho or nome_atalho in nome_busca:
            caminho_completo = caminho
            nome_encontrado = nome_atalho
            break

    if caminho_completo:
        try:
            subprocess.run(f"start \"\" \"{caminho_completo}\"", shell=True, check=True)
            logging.info(f"Aplicativo '{nome_encontrado}' aberto via cache.")
            return f"Aplicativo '{nome_encontrado}' localizado e aberto com sucesso."
        except subprocess.CalledProcessError as e:
            return f"Encontrei o atalho/executável, mas houve bloqueio: {e}"

    # Fallback original
    try:
        subprocess.run(f"start {nome_busca}", shell=True, check=True)
        return f"Enviada a requisição de '{nome_busca}' direto para o sistema."
    except Exception as e:
        return f"Não consegui localizar nenhum software chamado '{nome_app}'. Erro: {e}"
    
def tocar_musica(pesquisa: str, plataforma: str = 'spotify') -> str:
    """Busca e prepara para tocar uma música, artista ou playlist no Spotify ou YouTube."""
    termo_formatado = urllib.parse.quote(pesquisa)

    if 'spotify' in plataforma.lower():
        url = f"https://open.spotify.com/search/{termo_formatado}"
        webbrowser.open(url)
        logging.info(f"Comando executado. Abrindo a busca por '{pesquisa}' no Spotify Web.")
        return f"Comando executado. Abrindo a busca por '{pesquisa}' no Spotify Web."
    else:
        url = f"https://www.youtube.com/results?search_query={termo_formatado}"
        webbrowser.open(url)
        logging.info(f"Comando executado. Abrindo a busca por '{pesquisa}' no YouTube.")
        return f"Comando executado. Abrindo a busca por '{pesquisa}' no YouTube."

def controlar_midia(acao: str) -> str:
    """Controla a reprodução de mídia e o volume do sistema operacional.
    Ações suportadas obrigatoriamente: 'play_pause', 'proxima', 'anterior', 'aumentar_volume', 'diminuir_volume', 'mutar'."""
    acoes_validas = {
        'play_pause': 'playpause',
        'proxima': 'nexttrack',
        'anterior': 'prevtrack',
        'aumentar_volume': 'volumeup',
        'diminuir_volume': 'volumedown',
        'mutar': 'volumemute'
    }

    if acao not in acoes_validas:
        logging.warning(f"Ação '{acao}' não reconhecida pelo controlador de mídia.")
        return f"Ação '{acao}' não reconhecida pelo controlador de mídia. Ações válidas: play_pause, proxima, anterior, aumentar_volume, diminuir_volume, mutar."

    tecla = acoes_validas[acao]

    if 'volume' in acao and acao != 'mutar':
        for _ in range(5):
            pyautogui.press(tecla)
        logging.info(f"Comando de {acao} executado em bloco.")
        return f"Comando de {acao} executado em bloco para maior percepção."

    pyautogui.press(tecla)
    logging.info(f"Comando de mídia '{acao}' executado com sucesso.")
    return f"Comando de mídia '{acao}' executado com sucesso."

def orquestrar_ambiente(cenario: str) -> str:
    """
    Prepara o ambiente de trabalho abrindo os programas, terminais e sites necessários 
    para um cenário específico (ex: 'expediente', 'nuvem', 'encerrar').
    """
    cenario = cenario.lower()

    if "expediente" in cenario or "serin" in cenario or "desenvolvimento" in cenario:
        os.system("start code")
        webbrowser.open("https://github.com")
        webbrowser.open("https://stackoverflow.com")
        logging.info("Ambiente de expediente ativado.")
        return "Ambiente de expediente ativado. VS Code e painéis de desenvolvimento abertos."

    elif "nuvem" in cenario or "cloud" in cenario or "escola" in cenario:
        webbrowser.open("https://aws.amazon.com/pt/console/")
        os.system("start cmd.exe /k echo [Ambiente AWS CLI Pronto]")
        logging.info("Modo Escola da Nuvem ativado.")
        return "Modo Escola da Nuvem ativado. Console da AWS e terminal prontos."
        
    elif "limpar" in cenario or "encerrar" in cenario or "fim" in cenario:
        processos_a_encerrar = ['code.exe', 'node.exe', 'python.exe', 'npm.exe', 'git.exe']
        for proc_name in processos_a_encerrar:
            os.system(f"taskkill /F /IM {proc_name} /T >nul 2>&1")
        logging.info("Ambiente limpo. Processos de desenvolvimento encerrados.")
        return "Ambiente limpo. Processos de desenvolvimento e relacionados encerrados."
        
    else:
        logging.warning(f"Cenário '{cenario}' não reconhecido.")
        return f"Cenário '{cenario}' não reconhecido. Opções: Expediente, Nuvem ou Encerrar."

# =================================================================
# SETOR 7: AUTO REPARO
# Ferramentas de execução de comandos de terminal
# =================================================================

def executar_comando_terminal(comando: str) -> str:
    """
    Executa comandos de INFRAESTRUTURA no terminal (ex: pip install, ping, tasklist).
    PROIBIDO: Não utilize esta ferramenta para executar ou testar scripts Python (.py).
    Para rodar código Python local, utilize EXCLUSIVAMENTE a ferramenta 'testar_script_python'.
    Requer aprovação manual do usuário antes de rodar.
    Inclui proteção anti-rebote.
    """
    # NOVA LINHA: Evita que o fallback do Gemini rode o mesmo comando 2x seguidas
    if _anti_rebote(f"cmd_{comando}"):
        logging.info(f"Comando '{comando}' ignorado pelo anti-rebote (duplicata de fallback).")
        return "Comando ignorado para evitar execução duplicada pelo sistema de contingência."

    # Pausa o loop e pede aprovação no console
    print("\n" + "!" * 50)
    print(" ALERTA DE SEGURANÇA: AVALIAÇÃO DE COMANDO ".center(50, " "))
    print("!" * 50)
    print(f"O JARVIS elaborou um plano e deseja rodar o seguinte comando:\n\n>  {comando}\n")

    confirmacao = input("Permitir a execução? (S/N): ").strip().lower()

    if confirmacao != 's':
        logging.warning("Execução de comando bloqueada pelo usuário.")
        return "Acesso negado: O usuário cancelou a execução deste comando por motivos de segurança."

    logging.info(f"Permissão concedida. Executando comando: {comando}")

    try:
        resultado = subprocess.run(
            comando,
            shell=True,
            check=False,
            text=True,
            capture_output=True,
            timeout=60
        )

        saida_padrao = resultado.stdout.strip()
        saida_erro = resultado.stderr.strip()

        if resultado.returncode == 0:
            logging.info(f"Comando '{comando}' executado com sucesso.")
            return f"Comando executado com sucesso.\nSaída:\n{saida_padrao}"
        else:
            logging.error(f"Erro ao executar comando '{comando}' (Código {resultado.returncode}). Erro: {saida_erro}")
            return f"Erro ao executar comando (Código {resultado.returncode}).\nErro:\n{saida_erro}\nSaída parcial:\n{saida_padrao}"

    except subprocess.TimeoutExpired:
        logging.error(f"Erro: O comando '{comando}' demorou mais de 60 segundos e foi abortado por segurança.")
        return "Erro: O comando demorou mais de 60 segundos e foi abortado por segurança."
    except Exception as e:
        logging.critical(f"Erro crítico ao tentar acessar o terminal para '{comando}': {str(e)}")
        return f"Erro crítico ao tentar acessar o terminal: {str(e)}"

# =================================================================
# SETOR 8: MEMÓRIA E COGNIÇÃO
# Ferramentas para o assistente auditar a própria base de dados vetorial.
# =================================================================

def ler_memorias_recentes(quantidade: int = 5) -> str:
    """Audita a base de dados vetorial usando a conexão já ativa na RAM."""
    global colecao_memoria_global
    
    if not colecao_memoria_global:
        return "O banco de dados de memória ainda não foi inicializado pelo sistema principal."
        
    try:
        dados = colecao_memoria_global.get(limit=quantidade, include=["documents", "metadatas"])

        if not dados or not dados.get('documents'):
            return "Minha memória está vazia no momento."

        metadatas = dados.get('metadatas') or [{}] * len(dados['documents'])

        resposta = f"Aqui estão as {quantidade} memórias extraídas da sessão ativa:\n\n"
        for i, doc in enumerate(dados['documents']):
            meta = metadatas[i] or {}
            timestamp = meta.get('timestamp', 'sem data')
            tipo = meta.get('tipo', 'indefinido')
            resposta += f"Registro {i+1} [{tipo} | {timestamp}]: {doc}\n"
        logging.info(f"O JARVIS auditou e listou as {quantidade} memórias mais recentes.")
        return resposta
        
    except Exception as e:
        logging.error(f"Falha na ferramenta de leitura de memória vetorial: {e}")
        return f"Tentei acessar o banco de memórias, mas ocorreu um erro técnico: {e}"
# =================================================================
# SETOR 9: ANÁLISE E INTELIGÊNCIA
# Ferramentas para interpretação, diagnóstico de logs, otimização de código e extração de dados.
# =================================================================

def _caminho_sandbox(caminho_relativo: str) -> str:
    """Valida se o caminho solicitado pela IA está dentro do DIRETORIO_SEGURO."""
    caminho_limpo = caminho_relativo.strip('\"').strip("\'")
    caminho_absoluto = os.path.abspath(os.path.join(DIRETORIO_SEGURO, caminho_limpo))
    if not caminho_absoluto.startswith(DIRETORIO_SEGURO):
        raise PermissionError(f"Acesso negado: Tentativa de leitura fora da sandbox ({caminho_absoluto}).")
    if not os.path.isfile(caminho_absoluto):
        raise FileNotFoundError(f"Erro: O arquivo '{caminho_limpo}' não foi encontrado.")
    return caminho_absoluto

def diagnosticar_erros_logs(caminho_log: str) -> str:
    """Diagnostica erros, avisos e padrões críticos em arquivos de log."""
    try:
        caminho_seguro = _caminho_sandbox(caminho_log)
    except (PermissionError, FileNotFoundError) as e:
        return str(e)

    try:
        erros, avisos, excepcoes = [], [], []
        total_linhas = 0

        # Otimização: Leitura iterativa (não explode a RAM com logs gigantes)
        try:
            arquivo = open(caminho_seguro, 'r', encoding='utf-8')
        except UnicodeDecodeError:
            arquivo = open(caminho_seguro, 'r', encoding='latin-1')

        with arquivo as f:
            for num, linha in enumerate(f, 1):
                total_linhas += 1
                l_upper = linha.upper()
                if "ERROR" in l_upper or "CRITICAL" in l_upper or "FATAL" in l_upper:
                    erros.append((num, linha.strip()))
                elif "WARNING" in l_upper or "WARN" in l_upper:
                    avisos.append((num, linha.strip()))
                elif "EXCEPTION" in l_upper or "TRACEBACK" in l_upper:
                    excepcoes.append((num, linha.strip()))

        relatorio = f"--- DIAGNÓSTICO DE LOGS: {os.path.basename(caminho_seguro)} ---\n"
        relatorio += f"Total de linhas analisadas: {total_linhas}\n"
        relatorio += f"Erros/Críticos detectados: {len(erros)}\n"
        relatorio += f"Exceções/Tracebacks detectados: {len(excepcoes)}\n"
        relatorio += f"Avisos (Warnings) detectados: {len(avisos)}\n\n"

        if erros:
            relatorio += "--- PRINCIPAIS ERROS DETECTADOS ---\n"
            for num, err in erros[-10:]:
                relatorio += f"Linha {num}: {err}\n"
            relatorio += "\n"

        if excepcoes:
            relatorio += "--- EXCEÇÕES / TRACEBACKS ---\n"
            for num, exc in excepcoes[-5:]:
                relatorio += f"Linha {num}: {exc}\n"
            relatorio += "\n"

        if avisos and not erros:
            relatorio += "--- AMOSTRA DE AVISOS ---\n"
            for num, av in avisos[-5:]:
                relatorio += f"Linha {num}: {av}\n"
            relatorio += "\n"

        if not erros and not excepcoes and not avisos:
            relatorio += "Nenhum erro, exceção ou aviso relevante foi encontrado no log."

        return relatorio

    except Exception as e:
        return f"Erro ao analisar o arquivo de log: {e}"


def analisar_otimizar_codigo(caminho_codigo: str) -> str:
    """Analisar a estrutura de um script e apontar métricas, potenciais gargalos e oportunidades de refatoração."""
    import ast
    try:
        caminho_seguro = _caminho_sandbox(caminho_codigo)
    except (PermissionError, FileNotFoundError) as e:
        return str(e)

    try:
        # Prevenção de estouro de memória e quebra de Encoding
        try:
            with open(caminho_seguro, 'r', encoding='utf-8') as f:
                conteudo = f.read(150000)
        except UnicodeDecodeError:
            with open(caminho_seguro, 'r', encoding='latin-1') as f:
                conteudo = f.read(150000)

        linhas = conteudo.splitlines()
        total_linhas = len(linhas)
        linhas_codigo = [l for l in linhas if l.strip() and not l.strip().startswith('#')]
        linhas_comentario = [l for l in linhas if l.strip().startswith('#')]

        funcoes = []
        classes = []
        sintaxe_valida = True
        erro_sintaxe = ""

        try:
            arvore = ast.parse(conteudo, filename=caminho_seguro)
            for node in ast.walk(arvore):
                if isinstance(node, ast.FunctionDef):
                    funcoes.append(node.name)
                elif isinstance(node, ast.ClassDef):
                    classes.append(node.name)
        except SyntaxError as se:
            sintaxe_valida = False
            erro_sintaxe = f"Erro de sintaxe na linha {se.lineno}: {se.msg}"

        relatorio = f"--- ANÁLISE DE ESTRUTURA E OTIMIZAÇÃO: {os.path.basename(caminho_seguro)} ---\n"
        relatorio += f"Sintaxe Válida: {'Sim' if sintaxe_valida else 'Não'}\n"
        relatorio += f"Total de Linhas (Amostra lida): {total_linhas} (Código: {len(linhas_codigo)}, Comentários/Docs: {len(linhas_comentario)})\n"
        relatorio += f"Classes encontradas ({len(classes)}): {', '.join(classes) if classes else 'Nenhuma'}\n"
        relatorio += f"Funções encontradas ({len(funcoes)}): {', '.join(funcoes) if funcoes else 'Nenhuma'}\n\n"

        if not sintaxe_valida:
            relatorio += f"ATENÇÃO: {erro_sintaxe}\n\n"

        relatorio += "--- CONTEÚDO DO CÓDIGO PARA REVISÃO E OTIMIZAÇÃO ---\n"
        relatorio += conteudo[:5000]
        if len(conteudo) > 5000:
            relatorio += "\n\n[Conteúdo truncado para análise...]"

        return relatorio

    except Exception as e:
        return f"Erro ao analisar o arquivo de código: {e}"


def extrair_informacoes_documento(caminho_documento: str, foco: str = None) -> str:
    """Processa textos longos e documentos para sintetizar e extrair informações relevantes ou específicas."""
    try:
        caminho_seguro = _caminho_sandbox(caminho_documento)
    except (PermissionError, FileNotFoundError) as e:
        return str(e)

    try:
        try:
            with open(caminho_seguro, 'r', encoding='utf-8') as f:
                conteudo = f.read(150000)
        except UnicodeDecodeError:
            with open(caminho_seguro, 'r', encoding='latin-1') as f:
                conteudo = f.read(150000)

        total_caracteres = len(conteudo)
        palavras = conteudo.split()
        total_palavras = len(palavras)

        linhas = conteudo.splitlines()
        paragrafos = [p for p in conteudo.split('\n\n') if p.strip()]

        relatorio = f"--- EXTRAÇÃO DE DOCUMENTO: {os.path.basename(caminho_seguro)} ---\n"
        relatorio += f"Total de Palavras: {total_palavras} | Caracteres: {total_caracteres} | Parágrafos: {len(paragrafos)}\n"

        if foco:
            termo_foco = foco.lower()
            ocorrencias = [l.strip() for l in linhas if termo_foco in l.lower()]
            relatorio += f"Foco de Busca: '{foco}' ({len(ocorrencias)} ocorrências encontradas)\n\n"
            if ocorrencias:
                relatorio += "--- EXTRATOS RELACIONADOS AO FOCO ---\n"
                for oc in ocorrencias[:10]:
                    relatorio += f"- {oc}\n"
                relatorio += "\n"
        else:
            relatorio += "\n"

        relatorio += "--- AMOSTRA DO CONTEÚDO PARA SÍNTESE EXECUTIVA ---\n"
        relatorio += conteudo[:4000]
        if len(conteudo) > 4000:
            relatorio += "\n\n[Documento truncado para síntese...]"

        return relatorio

    except Exception as e:
        return f"Erro ao processar o documento: {e}"

def gerenciar_memoria_codigo(acao: str, chave: str = "", conteudo: str = "") -> str:
    """
    Um 'clipboard' interno para a IA armazenar e consultar trechos de código,
    assinaturas de funções ou resumos de arquivos enquanto trabalha em múltiplos arquivos.
    Ações permitidas: 'salvar', 'consultar', 'listar', 'limpar'.
    """
    global _MEMORIA_DE_CODIGO
    acao = acao.lower().strip()

    if acao == 'salvar':
        if not chave or not conteudo:
            return "Erro: Para 'salvar', você deve fornecer uma 'chave' (ex: nome do arquivo) e o 'conteudo'."
        _MEMORIA_DE_CODIGO[chave] = conteudo
        logging.info(f"Contexto de código salvo na RAM sob a chave '{chave}'.")
        return f"Contexto salvo com sucesso na chave '{chave}'. Tamanho: {len(conteudo)} caracteres."
    
    elif acao == 'consultar':
        if not chave:
            return "Erro: Forneça a 'chave' que deseja consultar."
        if chave in _MEMORIA_DE_CODIGO:
            return f"--- CONTEÚDO DA CHAVE '{chave}' ---\n{_MEMORIA_DE_CODIGO[chave]}"
        return f"Aviso: Nenhuma memória de código encontrada para a chave '{chave}'."
    
    elif acao == 'listar':
        if not _MEMORIA_DE_CODIGO:
            return "A memória de contexto de código está vazia no momento."
        chaves = ", ".join(_MEMORIA_DE_CODIGO.keys())
        return f"Chaves atualmente armazenadas no seu bloco de notas: {chaves}"
    
    elif acao == 'limpar':
        if chave:
            if chave in _MEMORIA_DE_CODIGO:
                del _MEMORIA_DE_CODIGO[chave]
                return f"Chave '{chave}' removida da memória de trabalho."
            return f"A chave '{chave}' não existe."
        else:
            _MEMORIA_DE_CODIGO.clear()
            logging.info("Memória de código global (RAM) limpa.")
            return "Toda a memória de contexto temporária foi apagada."
    else:
        return "Ação inválida. Use uma das opções: 'salvar', 'consultar', 'listar' ou 'limpar'."
    
def testar_script_python(caminho_relativo: str) -> str:
    """
    A ÚNICA ferramenta permitida para executar, testar e debugar scripts Python.
    Executa o script dentro da sandbox e captura a saída ou o erro (Traceback).
    OBRIGATÓRIO usar esta ferramenta para TDD (Test-Driven Development) e Auto-Cura.
    """
    if _anti_rebote(f"testar_{caminho_relativo}", cooldown_segundos=10):
        return "Ação ignorada: O teste já foi disparado na tentativa anterior."
    
    try:
        caminho_seguro = _caminho_sandbox(caminho_relativo)
    except (PermissionError, FileNotFoundError) as e:
        return str(e)
        
    # Human-in-the-Loop
    print("\n" + "*" * 60)
    print(" ALERTA: EXECUÇÃO DE TESTE DE CÓDIGO (AUTO-CURA) ".center(60, " "))
    print("*" * 60)
    print(f"Alvo: {caminho_seguro}")
    print("-" * 60)
    
    confirmacao = input("Permitir execução do script para teste? (S/N): ").strip().lower()
    if confirmacao != 's':
        logging.warning("Teste de código bloqueado pelo usuário.")
        return "Acesso negado: Teste cancelado pelo usuário."
        
    logging.info(f"Executando teste no script: {caminho_seguro}")
    try:
        # Roda o script usando o mesmo executável Python do sistema
        resultado = subprocess.run([sys.executable, caminho_seguro], capture_output=True, text=True, timeout=15)
        
        saida_padrao = resultado.stdout.strip()
        saida_erro = resultado.stderr.strip()
        
        if resultado.returncode == 0:
            return f"✅ TESTE BEM-SUCEDIDO!\nSaída:\n{saida_padrao}"
        else:
            # O pulo do gato: A IA recebe uma instrução de correção junto com o erro
            return f"❌ FALHA NO TESTE (Código {resultado.returncode}).\nTraceback:\n{saida_erro}\n\n[INSTRUÇÃO PARA IA]: Analise o Traceback acima, utilize a ferramenta 'editar_arquivo' para corrigir a falha e chame 'testar_script_python' novamente até o teste passar."
            
    except subprocess.TimeoutExpired:
        logging.error(f"Erro: O script '{caminho_seguro}' entrou em loop infinito ou demorou demais.")
        return "⏱️ ERRO: O script demorou mais de 15 segundos e foi interrompido. Verifique se há loops infinitos ou esperas de input (I/O bloqueante)."
    except Exception as e:
        return f"⚠️ Erro inesperado ao tentar rodar o teste: {e}"

def diagnosticar_audio() -> str:
    """
    Executa um diagnóstico rápido nos dispositivos de microfone do sistema.
    Use esta ferramenta quando o usuário relatar problemas para falar, quando você não estiver ouvindo,
    ou quando pedirem para você verificar o seu sistema de áudio/voz.
    """
    import speech_recognition as sr
    import logging
    
    resultado = "=== DIAGNÓSTICO DO SISTEMA DE ESCUTA ===\n\n"
    
    try:
        mic_list = sr.Microphone.list_microphone_names()
        if not mic_list:
            resultado += "[FALHA CRÍTICA] NENHUM MICROFONE DETECTADO PELO SISTEMA OPERACIONAL.\n"
            return resultado
            
        resultado += "Microfones mapeados pelo sistema:\n"
        for i, nome in enumerate(mic_list):
            resultado += f"- Dispositivo {i}: {nome}\n"
            
        resultado += "\nTestando canal de escuta padrão...\n"
        with sr.Microphone() as source:
            resultado += "[SUCESSO] O canal de áudio padrão do Windows foi aberto e o hardware está operante.\n"
            
        logging.info("Ferramenta de diagnóstico de áudio executada com sucesso.")
        
    except OSError as e:
        resultado += f"\n[FALHA DE DRIVER] O Windows está bloqueando o acesso ao dispositivo ou ele está em uso exclusivo por outro app. Erro: {e}\n"
    except Exception as e:
        resultado += f"\n[ERRO CRÍTICO] Falha inesperada ao testar o hardware: {e}\n"
        
    return resultado