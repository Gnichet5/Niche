import os
import webbrowser
import pygetwindow as gw
import psutil
import pyautogui
import urllib.request
import urllib.parse
import json

# =================================================================
# SETOR 1: SISTEMA E HARDWARE
# Ferramentas para monitoramento de recursos e gerenciamento de processos.
# =================================================================

def verificar_uso_sistema() -> str:
    """Verifica e retorna o uso de CPU e Memória RAM do computador."""
    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory().percent
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
            return f"Foram encerrados {encerrados} processo(s) referentes a '{identificador}'."
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
    return f"Site {url} aberto com sucesso."

def abrir_pasta(caminho: str) -> str:
    """Abre uma pasta no Windows Explorer. Ex: 'C:\\Users\\guipe\\Documents'"""
    try:
        os.startfile(caminho)
        return f"Pasta '{caminho}' aberta na tela."
    except Exception as e:
        return f"Erro ao tentar abrir a pasta: {str(e)}"

def listar_arquivos_pasta(caminho: str) -> str:
    """Retorna uma lista com os nomes de todos os arquivos e subpastas dentro de um diretório."""
    try:
        arquivos = os.listdir(caminho)
        if not arquivos:
            return "A pasta está vazia."
        return f"Conteúdo de '{caminho}': " + ", ".join(arquivos)
    except Exception as e:
        return f"Não foi possível ler a pasta. Erro: {str(e)}"

def ler_arquivo(caminho_arquivo: str) -> str:
    """
    Lê e retorna o conteúdo de um arquivo local (.py, .json, .log, .md, .txt, etc) 
    para análise de código ou depuração de erros.
    """
    import os
    
    # Remove aspas caso o usuário cole o caminho do Windows com elas
    caminho_arquivo = caminho_arquivo.strip('"').strip("'")
    
    if not os.path.isfile(caminho_arquivo):
        return f"Erro: Não foi possível encontrar o arquivo no caminho '{caminho_arquivo}'."
        
    try:
        with open(caminho_arquivo, 'r', encoding='utf-8') as arquivo:
            conteudo = arquivo.read()
            
            if len(conteudo) > 150000:
                return f"Arquivo muito grande. Aqui estão os primeiros 150 mil caracteres:\n\n{conteudo[:150000]}"
            return conteudo
            
    except UnicodeDecodeError:
        try:
            with open(caminho_arquivo, 'r', encoding='latin-1') as arquivo:
                return arquivo.read()
        except Exception as e:
            return f"Falha na decodificação. O arquivo pode não ser texto puro. Erro: {e}"
            
    except Exception as e:
        return f"Erro inesperado ao tentar ler o arquivo: {e}"
# =================================================================
# SETOR 3: GERENCIAMENTO DE JANELAS
# Ferramentas para controle da interface visual do sistema operacional.
# =================================================================

def listar_janelas_abertas() -> str:
    """Retorna uma lista com os nomes das janelas visíveis no Windows."""
    todas_janelas = gw.getAllTitles()
    janelas_visiveis = [j for j in todas_janelas if j.strip() != ""]
    return "Janelas abertas: " + ", ".join(janelas_visiveis) if janelas_visiveis else "Nenhuma janela visível."

def gerenciar_janela(titulo_janela: str, acao: str) -> str:
    """Controla janelas. Ação deve ser: 'focar', 'minimizar', 'maximizar' ou 'fechar'."""
    try:
        janelas_encontradas = gw.getWindowsWithTitle(titulo_janela)
        if not janelas_encontradas:
            return f"Não encontrei a janela '{titulo_janela}'."
            
        janela = janelas_encontradas[0]
        
        if acao == 'focar':
            if janela.isMinimized:
                janela.restore()
            janela.activate()
            return f"Foco na janela '{janela.title}'."
        elif acao == 'minimizar':
            janela.minimize()
            return f"Minimizou '{janela.title}'."
        elif acao == 'maximizar':
            janela.maximize()
            return f"Maximizou '{janela.title}'."
        elif acao == 'fechar':
            janela.close()
            return f"Fechou '{janela.title}'."
        else:
            return "Ação inválida."
    except Exception as e:
        return f"Erro ao gerenciar janela: {str(e)}"

# =================================================================
# SETOR 4: BUSCA E INFORMAÇÃO
# Ferramentas para consumo de dados externos da internet.
# =================================================================

def pesquisar_no_google(termo: str) -> str:
    """Abre uma nova guia no navegador fazendo uma pesquisa no Google sobre o termo solicitado."""
    url = f"https://www.google.com/search?q={urllib.parse.quote(termo)}"
    webbrowser.open(url)
    return f"Guia de pesquisa aberta para: {termo}"

def buscar_resumo_wikipedia(termo: str) -> str:
    """Busca um resumo explicativo na Wikipedia para responder a dúvidas do usuário sem abrir o navegador."""
    try:
        url = f"https://pt.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(termo)}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Jarvis_Assistant/1.0'})
        with urllib.request.urlopen(req) as response:
            dados = json.loads(response.read().decode())
            return dados.get('extract', 'Nenhum resumo encontrado para este termo.')
    except Exception:
        return f"Não foi possível encontrar informações diretas sobre '{termo}' na Wikipedia."

# =================================================================
# SETOR 5: SEGURANÇA
# Ferramentas de análise e prevenção local.
# =================================================================

def verificar_arquivos_suspeitos(caminho: str) -> str:
    """Examina uma pasta e suas subpastas em busca de executáveis não usuais ou scripts maliciosos."""
    extensoes_perigosas = ['.exe', '.bat', '.cmd', '.vbs', '.ps1', '.msi', '.scr']
    arquivos_encontrados = []
    
    if not os.path.exists(caminho):
        return f"O caminho {caminho} não foi encontrado no sistema."
        
    try:
        contador = 0
        for raiz, _, arquivos in os.walk(caminho):
            for arquivo in arquivos:
                contador += 1
                if contador > 1500: 
                    alerta = "Análise interrompida no limite de 1500 arquivos."
                    if arquivos_encontrados:
                        return f"{alerta} Suspeitos até o momento: " + ", ".join(arquivos_encontrados)
                    return f"{alerta} Nenhum suspeito nos arquivos analisados."
                    
                _, ext = os.path.splitext(arquivo)
                if ext.lower() in extensoes_perigosas:
                    arquivos_encontrados.append(os.path.join(raiz, arquivo))
                    
        if not arquivos_encontrados:
            return "Escaneamento concluído. Nenhum arquivo com extensão perigosa foi encontrado."
        
        resultado = f"Atenção, {len(arquivos_encontrados)} arquivos executáveis/scripts encontrados:\n"
        resultado += "\n".join(arquivos_encontrados)
        return resultado
        
    except Exception as e:
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
        'painel de controle': 'control',
        'configurações': 'ms-settings:',
        'vscode': 'code'
    }
    
    if nome_busca in apps_nativos:
        os.system(f"start {apps_nativos[nome_busca]}")
        return f"Aplicativo de sistema '{nome_busca}' acionado."

    for pasta in pastas_iniciar:
        if not os.path.exists(pasta):
            continue
            
        for raiz, _, arquivos in os.walk(pasta):
            for arquivo in arquivos:
                if arquivo.lower().endswith('.lnk'):
                    nome_atalho = arquivo[:-4].lower() 
                    
                    if nome_busca in nome_atalho or nome_atalho in nome_busca:
                        caminho_completo = os.path.join(raiz, arquivo)
                        try:
                            os.startfile(caminho_completo)
                            return f"Aplicativo '{arquivo[:-4]}' localizado e aberto com sucesso."
                        except Exception as e:
                            return f"Encontrei o atalho, mas houve bloqueio: {e}"
                            
    try:
        os.system(f"start {nome_busca}")
        return f"Enviada a requisição de '{nome_busca}' direto para o sistema."
    except:
        return f"Não consegui localizar nenhum software chamado '{nome_app}'."

def tocar_musica(pesquisa: str, plataforma: str = 'spotify') -> str:
    """Busca e prepara para tocar uma música, artista ou playlist no Spotify ou YouTube."""
    import webbrowser
    import urllib.parse
    
    termo_formatado = urllib.parse.quote(pesquisa)
    
    # Removemos a tentativa de abrir o app nativo para evitar o falso positivo do Windows
    if 'spotify' in plataforma.lower():
        url = f"https://open.spotify.com/search/{termo_formatado}"
        webbrowser.open(url)
        return f"Comando executado. Abrindo a busca por '{pesquisa}' no Spotify Web."
    else:
        url = f"https://www.youtube.com/results?search_query={termo_formatado}"
        webbrowser.open(url)
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
        return f"Ação '{acao}' não reconhecida pelo controlador de mídia."
        
    tecla = acoes_validas[acao]
    
    if 'volume' in acao and acao != 'mutar':
        for _ in range(5):
            pyautogui.press(tecla)
        return f"Comando de {acao} executado em bloco para maior percepção."
        
    pyautogui.press(tecla)
    return f"Comando de mídia '{acao}' executado com sucesso."