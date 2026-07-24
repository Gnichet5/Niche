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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
DEFAULT_MAX_FILE_READ_CHARS = 150000
DEFAULT_MAX_WEB_SCRAPE_CHARS_PER_PAGE = 3000
DEFAULT_MAX_FILES_TO_SCAN_SUSPICIOUS = 1500

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
    """Encerra um processo travado ou consumindo muita memória no Windows.
    Aceita o nome do processo (ex: 'chrome.exe', 'node.exe') ou o número do PID."""
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
    """Abre uma pasta no Windows Explorer. Ex: 'C:\\Users\\guipe\\Documents'"""
    try:
        os.startfile(caminho)
        logging.info(f"Pasta '{caminho}' aberta.")
        return f"Pasta '{caminho}' aberta na tela."
    except Exception as e:
        logging.error(f"Erro ao tentar abrir a pasta '{caminho}': {str(e)}")
        return f"Erro ao tentar abrir a pasta: {str(e)}"

def listar_arquivos_pasta(caminho: str) -> str:
    """Retorna uma lista com os nomes de todos os arquivos e subpastas dentro de um diretório."""
    try:
        arquivos = os.listdir(caminho)
        if not arquivos:
            logging.info(f"A pasta '{caminho}' está vazia.")
            return "A pasta está vazia."
        logging.info(f"Conteúdo da pasta '{caminho}' listado.")
        return f"Conteúdo de '{caminho}': " + ", ".join(arquivos)
    except Exception as e:
        logging.error(f"Não foi possível ler a pasta '{caminho}'. Erro: {str(e)}")
        return f"Não foi possível ler a pasta. Erro: {str(e)}"

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
        with open(caminho_arquivo, 'r', encoding='utf-8') as arquivo:
            conteudo = arquivo.read()

            max_chars = int(os.getenv("MAX_FILE_READ_CHARS", str(DEFAULT_MAX_FILE_READ_CHARS)))
            if len(conteudo) > max_chars:
                logging.info(f"Arquivo '{caminho_arquivo}' muito grande, lendo os primeiros {max_chars} caracteres.")
                return f"Arquivo muito grande. Aqui estão os primeiros {max_chars} caracteres:\n\n{conteudo[:max_chars]}"
            logging.info(f"Arquivo '{caminho_arquivo}' lido com sucesso.")
            return conteudo

    except UnicodeDecodeError:
        try:
            with open(caminho_arquivo, 'r', encoding='latin-1') as arquivo:
                logging.info(f"Arquivo '{caminho_arquivo}' lido com encoding latin-1 após falha UTF-8.")
                return arquivo.read()
        except Exception as e:
            logging.error(f"Falha na decodificação do arquivo '{caminho_arquivo}'. O arquivo pode não ser texto puro. Erro: {e}")
            return f"Falha na decodificação. O arquivo pode não ser texto puro. Erro: {e}"

    except Exception as e:
        logging.error(f"Erro inesperado ao tentar ler o arquivo '{caminho_arquivo}': {e}")
        return f"Erro inesperado ao tentar ler o arquivo: {e}"

def organizar_downloads(caminho: str = None) -> str:
    """
    Organiza automaticamente os arquivos da pasta Downloads do usuário,
    movendo-os para subpastas categorizadas (Imagens, Documentos, Instaladores, Códigos, etc).
    """
    import shutil

    if not caminho:
        caminho = os.path.join(os.path.expanduser('~'), 'Downloads')
    
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

def buscar_solucao_web(pergunta: str) -> str:
    """
    Pesquisa qualquer tipo de informação na internet (notícias, atualidades, dúvidas gerais ou erros de código),
    acessa os primeiros resultados e retorna o conteúdo da página para a IA analisar e responder.
    """
    logging.info(f"JARVIS pesquisando na web por: {pergunta}")
    resultados_texto = f"Resultados da pesquisa para: {pergunta}\n\n"

    try:
        links = list(search(pergunta, num=3, stop=3, pause=2))

        if not links:
            logging.info(f"Nenhum resultado encontrado no Google para '{pergunta}'.")
            return "Nenhum resultado encontrado no Google."

        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        
        max_scrape_chars = int(os.getenv("MAX_WEB_SCRAPE_CHARS_PER_PAGE", str(DEFAULT_MAX_WEB_SCRAPE_CHARS_PER_PAGE)))

        for i, url in enumerate(links):
            resultados_texto += f"--- Fonte {i+1}: {url} ---\n"
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

                resultados_texto += texto_extraido[:max_scrape_chars] + "\n\n"
                logging.info(f"Conteúdo raspado da URL {url}.")
            except Exception as e:
                logging.error(f"Erro ao raspar a página {url}: {e}")
                resultados_texto += f"Erro ao raspar a página {url}: {e}\n\n"

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

def abrir_aplicativo(nome_app: str) -> str:
    """Busca dinamicamente e abre um aplicativo instalado no computador varrendo o Menu Iniciar."""
    nome_busca = nome_app.lower().strip()

    pastas_iniciar = [
        os.path.join(os.environ.get('PROGRAMDATA', 'C:\\ProgramData'), r'Microsoft\Windows\Start Menu\Programs'),
        os.path.join(os.environ.get('APPDATA'), r'Microsoft\Windows\Start Menu\Programs')
    ]

    apps_nativos = {
        'calculadora': 'calc',
        'bloco de notas': 'notepad',
        'paint': 'mspaint',
        'prompt de comando': 'cmd',
        'terminal': 'wt',
        'powershell': 'powershell',
        'painel de controle': 'control',
        'configurações': 'ms-settings:',
        'vscode': 'code',
        'excel': 'excel',
        'word': 'winword',
        'powerpoint': 'powerpnt',
        'chrome': 'chrome',
        'firefox': 'firefox',
        'edge': 'msedge',
        'spotify': 'spotify',
        'vlc': 'vlc',
        'explorador de arquivos': 'explorer'
    }

    if nome_busca in apps_nativos:
        try:
            subprocess.run(f"start {apps_nativos[nome_busca]}", shell=True, check=True)
            logging.info(f"Aplicativo de sistema '{nome_busca}' acionado via subprocess.")
            return f"Aplicativo de sistema '{nome_busca}' acionado."
        except subprocess.CalledProcessError as e:
            logging.error(f"Erro ao iniciar aplicativo nativo '{nome_busca}': {e}")
            return f"Erro ao iniciar aplicativo nativo: {e}"

    for pasta in pastas_iniciar:
        if not os.path.exists(pasta):
            continue

        for raiz, _, arquivos in os.walk(pasta):
            for arquivo in arquivos:
                if arquivo.lower().endswith(('.lnk', '.exe')):
                    nome_atalho_ou_exe = os.path.splitext(arquivo)[0].lower()

                    if nome_busca in nome_atalho_ou_exe or nome_atalho_ou_exe in nome_busca:
                        caminho_completo = os.path.join(raiz, arquivo)
                        try:
                            subprocess.run(f"start \"\" \"{caminho_completo}\"", shell=True, check=True)
                            logging.info(f"Aplicativo '{os.path.splitext(arquivo)[0]}' localizado e aberto via subprocess.")
                            return f"Aplicativo '{os.path.splitext(arquivo)[0]}' localizado e aberto com sucesso."
                        except subprocess.CalledProcessError as e:
                            logging.error(f"Encontrei o atalho/executável, mas houve bloqueio ao abrir '{os.path.splitext(arquivo)[0]}': {e}")
                            return f"Encontrei o atalho/executável, mas houve bloqueio: {e}"

    try:
        subprocess.run(f"start {nome_busca}", shell=True, check=True)
        logging.info(f"Enviada a requisição de '{nome_busca}' direto para o sistema via subprocess.")
        return f"Enviada a requisição de '{nome_busca}' direto para o sistema. Verifique a tela."
    except subprocess.CalledProcessError as e:
        logging.error(f"Não consegui localizar nenhum software chamado '{nome_app}'. Erro: {e}")
        return f"Não consegui localizar nenhum software chamado '{nome_app}'. Por favor, verifique o nome ou caminho."
    except Exception as e:
        logging.error(f"Erro inesperado ao tentar abrir o aplicativo '{nome_app}': {e}")
        return f"Erro inesperado ao tentar abrir o aplicativo: {e}"

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
    Executa um comando diretamente no terminal/prompt do sistema operacional.
    O JARVIS pode usar isso para instalar pacotes (pip install), verificar processos,
    ou rodar scripts. Requer aprovação manual do usuário antes de rodar.

    Args:
        comando (str): O comando de terminal a ser executado.
    """
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
    """
    Acessa o banco de dados vetorial e lista as últimas lembranças (memórias) armazenadas do usuário.
    Acione esta ferramenta SEMPRE que o usuário perguntar "o que você lembra", "quais suas memórias" ou 
    pedir para listar o histórico recente.
    """
    import chromadb
    import os
    import platform
    import logging
    from chromadb.config import Settings

    try:
        DB_PATH = os.getenv("JARVIS_DB_PATH", "./memoria_jarvis_v2")
        
        if not os.path.exists(DB_PATH):
            return "O banco de dados de memória ainda não foi criado no disco local/nuvem."
        
        # Sincronizando as mesmas configurações de leitura usadas no main.py
        settings_chroma = Settings(anonymized_telemetry=False)
        if platform.system() == "Windows":
            settings_chroma = Settings(
                anonymized_telemetry=False,
                chroma_api_impl="chromadb.api.segment.SegmentAPI"
            )

        chroma_client = chromadb.PersistentClient(path=DB_PATH, settings=settings_chroma)
        colecao_memoria = chroma_client.get_collection(name="historico_conversas")
        dados = colecao_memoria.get(limit=quantidade)
        
        if not dados or not dados.get('documents'):
            return "Minha memória está vazia no momento."
            
        resposta = f"Aqui estão as {quantidade} memórias (interações) extraídas diretamente do banco de dados vetorial:\n\n"
        for i, doc in enumerate(dados['documents']):
            resposta += f"Registro {i+1}: {doc}\n"          
        logging.info(f"O JARVIS auditou e listou as {quantidade} memórias mais recentes.")
        return resposta
        
    except Exception as e:
        logging.error(f"Falha na ferramenta de leitura de memória vetorial: {e}")
        return f"Tentei acessar o banco de memórias, mas ocorreu um erro técnico na leitura: {e}"