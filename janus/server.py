"""Servidor local com fila única, jobs assíncronos e aprovação no navegador."""
import copy
import json
import logging
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / 'web'


class App:
    def __init__(self, factory=None):
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.session = None
        self.factory = factory
        self.job = {'state': 'idle'}
        self.decision = threading.Event()
        self.approved = False

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.job)

    def emit(self, status, detail=''):
        with self.lock:
            self.job.update(status=status, detail=detail)

    def approve(self, name, arguments):
        with self.lock:
            self.approved = False
            self.decision.clear()
            self.job.update(state='approval', approval={'id': secrets.token_hex(12),
                            'name': name, 'arguments': arguments}, status='Aguardando sua aprovação')
        self.decision.wait(180)
        with self.lock:
            approved = self.approved
            self.job.update(state='running', approval=None)
        return approved

    def decide(self, approval_id, allow):
        with self.lock:
            pending = self.job.get('approval')
            if self.job['state'] != 'approval' or not pending or pending['id'] != approval_id:
                raise ValueError('Esta aprovação já expirou.')
            self.approved = allow
            self.job.update(state='running', approval=None)
            self.decision.set()

    def start(self, kind, data):
        with self.lock:
            if self.job['state'] in ('running', 'approval'):
                raise ValueError('Aguarde a solicitação atual terminar.')
            self.job = {'id': secrets.token_hex(12), 'kind': kind, 'state': 'running',
                        'status': 'Preparando Janus', 'detail': ''}
            threading.Thread(target=self.work, args=(kind, data), daemon=True).start()
            return self.job['id']

    def work(self, kind, data):
        try:
            if self.session is None:
                if self.factory is None:
                    from janus.engine import Session
                    self.factory = Session
                self.session = self.factory()
            if kind == 'chat':
                result = self.session.chat(data['text'], data.get('image'), self.emit, self.approve)
            elif kind == 'memories':
                result = self.session.memories()
            elif kind == 'forget':
                result = self.session.forget(data['id'])
            else:
                self.session.reset()
                result = {'reset': True}
            with self.lock:
                self.job.update(state='done', result=result, status='Pronto')
        except Exception as e:
            logging.exception('Falha no pedido da interface')
            with self.lock:
                self.job.update(state='error', error=str(e)[:1000], status='Não foi possível concluir')


def make_server(port=8765, app=None):
    app = app or App()

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, body, content='application/json; charset=utf-8'):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def trusted(self, api=False):
            hosts = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            if self.headers.get('Host') not in hosts:
                self.reply(403, {'error': 'Host não autorizado.'})
                return False
            origin = self.headers.get('Origin')
            if origin and origin not in {'http://' + h for h in hosts}:
                self.reply(403, {'error': 'Origem não autorizada.'})
                return False
            if api and not secrets.compare_digest(self.headers.get('X-Janus-Token', ''), app.token):
                self.reply(403, {'error': 'Reabra a interface para atualizar sua sessão.'})
                return False
            return True

        def do_GET(self):
            if not self.trusted(self.path.startswith('/api/')):
                return
            if self.path == '/api/status':
                return self.reply(200, app.snapshot())
            files = {'/': ('index.html', 'text/html; charset=utf-8'),
                     '/neural-background.js': ('neural-background.js', 'text/javascript; charset=utf-8'),
                     '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                     '/style.css': ('style.css', 'text/css; charset=utf-8')}
            if self.path not in files:
                return self.reply(404, {'error': 'Não encontrado'})
            name, mime = files[self.path]
            body = (WEB / name).read_bytes()
            if name == 'index.html':
                body = body.replace(b'__JANUS_TOKEN__', app.token.encode())
            self.reply(200, body, mime)

        def do_POST(self):
            if not self.trusted(True):
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 5_500_000:
                    return self.reply(413, {'error': 'Solicitação muito grande.'})
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError('Corpo inválido.')
                if self.path == '/api/approval':
                    if not isinstance(data.get('allow'), bool):
                        raise ValueError('Decisão inválida.')
                    app.decide(data.get('id'), data['allow'])
                    return self.reply(200, {'ok': True})
                kinds = {'/api/chat': 'chat', '/api/memories': 'memories', '/api/forget': 'forget', '/api/reset': 'reset'}
                if self.path not in kinds:
                    return self.reply(404, {'error': 'Não encontrado'})
                if kinds[self.path] == 'chat':
                    if not isinstance(data.get('text'), str) or not 1 <= len(data['text'].strip()) <= 20000:
                        raise ValueError('Escreva uma mensagem de até 20 mil caracteres.')
                    if data.get('image') is not None and not isinstance(data['image'], str):
                        raise ValueError('Imagem inválida.')
                if kinds[self.path] == 'forget' and (not isinstance(data.get('id'), str) or len(data['id']) > 200):
                    raise ValueError('Memória inválida.')
                self.reply(202, {'id': app.start(kinds[self.path], data)})
            except (ValueError, TypeError) as e:
                self.reply(400, {'error': str(e)})

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    server.app = app
    return server


def run(port=8765):
    logging.basicConfig(level=logging.INFO)
    server = make_server(port)
    print(f'Janus disponível em http://127.0.0.1:{server.server_port} — Ctrl+C para encerrar.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.app.decision.set()
        server.server_close()
