"""Políticas locais de contexto: sem chamadas de IA para selecionar ou resumir."""
import functools
import inspect
import json
import logging
import os
import re
import unicodedata


def limite_env(nome, padrao, minimo=1, maximo=100000):
    try:
        return max(minimo, min(maximo, int(os.getenv(nome, str(padrao)))))
    except ValueError:
        return padrao


def limitar(texto, limite):
    texto = str(texto)
    aviso = "\n[trecho limitado]"
    return texto if len(texto) <= limite else texto[:max(0, limite-len(aviso))] + aviso[:limite]


def normalizar(texto):
    return ''.join(c for c in unicodedata.normalize('NFKD', texto.lower())
                   if not unicodedata.combining(c))


def resumo_voz(texto, limite=200):
    texto = re.sub(r'```.*?```', ' Código disponível no texto. ', texto, flags=re.S)
    texto = re.sub(r'\s+', ' ', texto.replace('*', '').replace('#', '')).strip()
    primeira = re.split(r'(?<=[.!?])\s+', texto)[0]
    if len(primeira) <= limite:
        return primeira
    return primeira[:limite-1].rsplit(' ', 1)[0] + '…'


class Contexto:
    """Retém pares completos e um resumo extrativo limitado dos pares antigos."""
    def __init__(self, max_pares=6, max_chars=12000, resumo_chars=2000):
        self.pares = []
        self.resumo = ''
        self.max_pares, self.max_chars, self.resumo_chars = max_pares, max_chars, resumo_chars

    def adicionar(self, pergunta, resposta):
        self.pares.append((limitar(pergunta, self.max_chars // 2),
                           limitar(resposta, self.max_chars // 2)))
        while len(self.pares) > self.max_pares or sum(len(a)+len(b) for a,b in self.pares) > self.max_chars:
            a, b = self.pares.pop(0)
            extrato = f'Usuário: {limitar(a, 300)}\nJanus: {limitar(b, 400)}\n'
            self.resumo = (self.resumo + extrato)[-self.resumo_chars:]

    def historico(self):
        return [dict(role=role, parts=[texto]) for par in self.pares
                for role, texto in zip(('user', 'model'), par)]

    def texto(self):
        return self.resumo + '\n' + '\n'.join(a+'\n'+b for a,b in self.pares)


GRUPOS = (
    (r'clima|temperatura|chover|chuva|previsao', ('verificar_clima',)),
    (r'cpu|ram|processo|lento|travando|travado|desempenho', ('verificar_uso_sistema', 'listar_processos_pesados', 'matar_processo')),
    (r'arquivo|pasta|download|diretorio|\.py\b|\.txt\b|\.log\b', ('abrir_pasta', 'listar_arquivos_pasta', 'ler_arquivo', 'organizar_downloads', 'verificar_arquivos_suspeitos')),
    (r'janela|minimizar|maximizar', ('listar_janelas_abertas', 'gerenciar_janela')),
    (r'pesquis|busqu|buscar|internet|web|site|google|wikipedia|noticia', ('buscar_solucao_web', 'buscar_resumo_wikipedia', 'pesquisar_no_google', 'abrir_site')),
    (r'musica|spotify|youtube|volume|midia|playlist|mutar', ('tocar_musica', 'controlar_midia')),
    (r'aplicativo|programa|abrir|abra|ambiente|expediente|nuvem|vscode|excel|chrome', ('abrir_aplicativo', 'abrir_site', 'abrir_pasta', 'orquestrar_ambiente')),
    (r'terminal|comando|instal|pip|npm|script|powershell', ('executar_comando_terminal', 'ler_arquivo')),
    (r'memoria|lembr|preferencia|conversamos', ('ler_memorias_recentes',)),
)


def selecionar_ferramentas(pergunta, registro, anterior=''):
    texto = normalizar(pergunta)
    if re.fullmatch(r'(oi|ola|obrigad[oa]|bom dia|boa tarde|boa noite)[!. ]*', texto):
        return []
    # Continuação curta: mantém o contexto de seleção do último pedido.
    if len(texto.split()) <= 5 and anterior:
        texto += ' ' + normalizar(anterior)
    nomes = {nome for padrao, grupo in GRUPOS if re.search(padrao, texto) for nome in grupo}
    # Pedido desconhecido: conserva as capacidades em vez de bloquear uma ação.
    return [f for f in registro if not nomes or f.__name__ in nomes]


def limitar_ferramentas(registro, max_chars=4000):
    """Cache por pedido evita repetir efeitos quando um modelo de fallback assume."""
    cache = {}
    def envolver(func):
        @functools.wraps(func)
        def chamada(*args, **kwargs):
            argumentos = inspect.signature(func).bind(*args, **kwargs)
            argumentos.apply_defaults()
            chave = (func.__name__, json.dumps(argumentos.arguments, sort_keys=True, default=str))
            if chave not in cache:
                # Não repete uma ação de resultado incerto após uma exceção.
                cache[chave] = 'Execução iniciada, resultado incerto. Não repita automaticamente.'
                cache[chave] = limitar(func(*args, **kwargs), max_chars)
            return cache[chave]
        return chamada
    return [envolver(f) for f in registro]


def filtrar_memorias(resultados, contexto='', limite=1600, distancia_max=0.8):
    docs = (resultados.get('documents') or [[]])[0]
    distancias = (resultados.get('distances') or [[]])[0]
    vistos, saida = set(), []
    contexto = normalizar(contexto).replace('jarvis respondeu', 'janus respondeu')
    for doc, distancia in zip(docs, distancias):
        if not doc or distancia is None or distancia > distancia_max:
            continue
        chave = normalizar(doc).replace('jarvis respondeu', 'janus respondeu')
        partes = re.split(r'usuario disse:|\| janus respondeu:', chave)
        if chave in vistos or chave in contexto or all(p.strip() in contexto for p in partes if p.strip()):
            continue
        vistos.add(chave)
        saida.append(limitar(doc, 800))
    return limitar('\n'.join(saida), limite) if saida else ''


class UsoTokens:
    def __init__(self):
        self.chamadas = 0
        self.totais = dict(entrada=0, saida=0, raciocinio=0, cache=0, total=0)
        self.sem_metadados = 0

    def registrar(self, resposta):
        self.chamadas += 1
        uso = getattr(resposta, 'usage_metadata', None)
        if uso is None:
            self.sem_metadados += 1
            return
        campos = dict(entrada='prompt_token_count', saida='candidates_token_count',
                      raciocinio='thoughts_token_count', cache='cached_content_token_count',
                      total='total_token_count')
        for chave, campo in campos.items():
            self.totais[chave] += getattr(uso, campo, 0) or 0

    def log(self):
        logging.info('[Tokens] chamadas=%s uso=%s sem_metadados=%s; não inclui embeddings nem requisições sem resposta',
                     self.chamadas, self.totais, self.sem_metadados)
