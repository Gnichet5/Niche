import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from janus.engine import Session
from token_budget import Contexto, UsoTokens


class EngineTests(unittest.TestCase):
    def make_session(self, action, chat_factory):
        session = Session.__new__(Session)
        session.context = Contexto()
        session.previous, session.temporary = '', False
        class FakeError(Exception): pass
        session.r = SimpleNamespace(ferramentas_janus=[action], modelo_escolhido='fake',
            system_instruction='test', GEMINI_REQUEST_OPTIONS={},
            ServiceUnavailable=FakeError, DeadlineExceeded=FakeError, ResourceExhausted=FakeError,
            RetryError=FakeError, NotFound=FakeError, ModeloMedido=chat_factory,
            buscar_contexto_vetorial=lambda *a,**k:'', salvar_memoria_vetorial=lambda *a:None)
        return session

    def test_acao_negada_nao_executa(self):
        executions=[]
        def abrir_aplicativo(nome_app: str):
            executions.append(nome_app)
            return 'aberto'
        def model(**kwargs):
            def send(*args,**kw):
                result=kwargs['tools'][0](nome_app='calc')
                return SimpleNamespace(text=result)
            return SimpleNamespace(start_chat=lambda **kw:SimpleNamespace(send_message=send))
        session=self.make_session(abrir_aplicativo,model)
        response=session.chat('Abra a calculadora',None,lambda *a:None,lambda *a:False)
        self.assertEqual(executions,[])
        self.assertIn('cancelada',response['text'])

    def test_clima_nao_acessa_banco(self):
        def verificar_clima(cidade:str): return '28 graus'
        def model(**kwargs):
            return SimpleNamespace(start_chat=lambda **kw:SimpleNamespace(
                send_message=lambda *a,**k:SimpleNamespace(text='28 graus')))
        session=self.make_session(verificar_clima,model)
        def fail(*a,**k): self.fail('Clima não deve acessar a memória')
        session.r.buscar_contexto_vetorial=session.r.salvar_memoria_vetorial=fail
        response=session.chat('Qual o clima em Camaçari?',None,lambda *a:None,lambda *a:False)
        self.assertEqual(response['memory'],'Dispensada nesta consulta')
        self.assertTrue(session.context.pares)


if __name__ == '__main__': unittest.main()
