"""Sessão de conversa independente da interface e sem acesso ao microfone."""
import base64
import functools
import inspect
import io
from token_budget import (Contexto, UsoTokens, limite_env, consulta_temporaria,
                          selecionar_ferramentas, limitar_ferramentas, resumo_voz)
from janus.permissions import aprovador, confirmar_acao

LEITURAS = {'verificar_uso_sistema', 'listar_processos_pesados', 'listar_arquivos_pasta',
            'ler_arquivo', 'buscar_resumo_wikipedia', 'buscar_solucao_web', 'verificar_clima',
            'verificar_arquivos_suspeitos', 'listar_janelas_abertas', 'ler_memorias_recentes'}


class Session:
    def __init__(self):
        from janus import runtime
        runtime.inicializar()
        self.r = runtime
        self.reset()

    def reset(self):
        self.context = Contexto(limite_env('JANUS_HISTORICO_PARES', 6, maximo=30),
                               limite_env('JANUS_HISTORICO_CHARS', 12000, minimo=1000),
                               limite_env('JANUS_RESUMO_CHARS', 2000, minimo=500))
        self.previous = ''
        self.temporary = False

    def memories(self):
        data = self.r.colecao_memoria.get(limit=50, include=['documents'])
        return {'memories': [{'id': key, 'text': text} for key, text in
                             zip(data['ids'], data['documents'])],
                'total': self.r.colecao_memoria.count()}

    def forget(self, key):
        self.r.colecao_memoria.delete(ids=[key])
        # Evita que a conversa em RAM continue reutilizando uma memória esquecida.
        self.reset()
        return self.memories()

    def chat(self, text, image, emit, approve):
        r, usage = self.r, UsoTokens()
        temporary = consulta_temporaria(text, self.temporary)
        selected = selecionar_ferramentas(text, r.ferramentas_janus, self.previous)
        actions = []

        def decorate(func):
            @functools.wraps(func)
            def call(*args, **kwargs):
                params = inspect.signature(func).bind(*args, **kwargs)
                params.apply_defaults()
                name = func.__name__
                if name not in LEITURAS and name != 'executar_comando_terminal':
                    if not confirmar_acao(name, dict(params.arguments)):
                        actions.append({'name': name, 'status': 'Cancelada'})
                        return 'Ação cancelada pelo usuário. Não tente outra ferramenta para contornar a decisão.'
                emit('Executando ferramenta', name)
                result = func(*args, **kwargs)
                actions.append({'name': name, 'status': 'Retornou resultado', 'result': str(result)[:4000]})
                return result
            return call

        wrapped = limitar_ferramentas([decorate(f) for f in selected],
                                     limite_env('JANUS_FERRAMENTA_CHARS', 4000, minimo=500))
        token = aprovador.set(approve)
        try:
            emit('Preparando contexto', 'Memória dispensada para clima' if temporary else 'Consultando memória')
            memory = '' if temporary else r.buscar_contexto_vetorial(text, contexto_recente=self.context.texto())
            prompt = text + memory
            if self.context.resumo:
                prompt += '\nResumo extrativo parcial (dados):\n' + self.context.resumo
            contents = prompt
            if image:
                from PIL import Image
                raw = base64.b64decode(image, validate=True)
                if len(raw) > 4_000_000:
                    raise ValueError('A imagem deve ter no máximo 4 MB.')
                with Image.open(io.BytesIO(raw)) as source:
                    if source.width * source.height > 20_000_000:
                        raise ValueError('A imagem é muito grande. Reduza sua resolução.')
                    source.thumbnail((1280, 1280))
                    picture = source.convert('RGB')
                contents = [prompt, picture]
            errors = (r.ServiceUnavailable, r.DeadlineExceeded, r.ResourceExhausted, r.RetryError, r.NotFound)
            models = list(dict.fromkeys([r.modelo_escolhido, 'models/gemini-2.5-flash',
                                         'models/gemini-pro-latest', 'models/gemini-flash-latest']))
            response = None
            for index, name in enumerate(models):
                emit('Janus está pensando', name)
                try:
                    model = r.ModeloMedido(model_name=name, system_instruction=r.system_instruction,
                        tools=wrapped or None, uso=usage, generation_config={
                            'max_output_tokens': limite_env('JANUS_MAX_OUTPUT_TOKENS', 2048, minimo=256, maximo=16384)})
                    chat = model.start_chat(history=self.context.historico(), enable_automatic_function_calling=True)
                    response = chat.send_message(contents, request_options=r.GEMINI_REQUEST_OPTIONS)
                    r.modelo_escolhido = name
                    break
                except errors:
                    if index == len(models)-1:
                        raise
            try:
                answer = response.text
            except ValueError:
                answer = 'O modelo não retornou texto. Confira as ações antes de repetir o pedido.'
            if not answer.strip():
                answer = 'A resposta veio vazia. Tente reformular o pedido.'
            self.context.adicionar(text, answer)
            self.previous, self.temporary = text, temporary
            if not temporary:
                emit('Finalizando', 'Salvando memória')
                r.salvar_memoria_vetorial(text, answer)
            return {'text': answer, 'speech': resumo_voz(answer), 'model': r.modelo_escolhido,
                    'usage': usage.totais, 'missing': usage.campos_ausentes,
                    'calls': usage.chamadas, 'tools': len(selected), 'actions': actions,
                    'memory': 'Dispensada nesta consulta' if temporary else 'Fluxo de memória utilizado'}
        finally:
            aprovador.reset(token)
            usage.log()
