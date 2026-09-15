import http.client
import json
import threading
import time
import unittest
from janus.server import App, make_server


class FakeSession:
    def chat(self, text, image, emit, approve):
        emit('Testando')
        if text == 'aprovar':
            return {'approved': approve('abrir_aplicativo', {'nome_app': 'calculadora'})}
        return {'text': text}
    def reset(self): pass
    def memories(self): return {'memories': [], 'total': 0}
    def forget(self, key): return self.memories()


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.app = App(FakeSession)
        self.server = make_server(0, self.app)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.app.decision.set()
        self.server.shutdown()
        self.server.server_close()

    def request(self, method, path, data=None, authorized=True, origin=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        headers = {'X-Janus-Token': self.app.token} if authorized else {}
        if origin: headers['Origin'] = origin
        conn.request(method, path, json.dumps(data) if data is not None else None, headers)
        response = conn.getresponse()
        result = response.status, response.read()
        conn.close()
        return result

    def wait_state(self, states):
        for _ in range(100):
            job = self.app.snapshot()
            if job['state'] in states: return job
            time.sleep(.01)
        self.fail('Job não terminou')

    def test_html_e_assets(self):
        status, page = self.request('GET', '/', authorized=False)
        self.assertEqual(status, 200)
        self.assertIn(self.app.token.encode(), page)
        self.assertNotIn(b'__JANUS_TOKEN__', page)
        self.assertEqual(self.request('GET', '/app.js')[0], 200)
        self.assertEqual(self.request('GET', '/.env')[0], 404)

    def test_api_protegida(self):
        self.assertEqual(self.request('POST', '/api/chat', {'text':'oi'}, authorized=False)[0], 403)
        self.assertEqual(self.request('POST', '/api/chat', {'text':'oi'}, origin='https://evil.example')[0], 403)
        self.assertIsNone(self.app.session)

    def test_chat_e_validacao(self):
        self.assertEqual(self.request('POST', '/api/chat', {'text':''})[0], 400)
        self.assertEqual(self.request('POST', '/api/chat', {'text':'Olá'})[0], 202)
        self.assertEqual(self.wait_state({'done'})['result']['text'], 'Olá')

    def test_aprovacao_e_fila(self):
        self.request('POST', '/api/chat', {'text':'aprovar'})
        job = self.wait_state({'approval'})
        self.assertEqual(self.request('POST', '/api/chat', {'text':'outra'})[0], 400)
        self.assertEqual(self.request('POST', '/api/approval', {'id':'errado','allow':True})[0], 400)
        self.assertEqual(self.request('POST', '/api/approval', {'id':job['approval']['id'],'allow':False})[0], 200)
        self.assertFalse(self.wait_state({'done'})['result']['approved'])


if __name__ == '__main__': unittest.main()
