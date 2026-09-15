import ast
import inspect
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from token_budget import (Contexto, UsoTokens, limitar, limite_env, resumo_voz,
                          selecionar_ferramentas, limitar_ferramentas, filtrar_memorias,
                          consulta_temporaria)


def carregar_funcao(nome, arquivo='tools.py', **globais):
    arvore = ast.parse(Path(arquivo).read_text(encoding='utf-8-sig'))
    func = next(n for n in arvore.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == nome)
    namespace = dict(globais)
    exec(compile(ast.Module(body=[func], type_ignores=[]), arquivo, 'exec'), namespace)
    return namespace[nome]


class EconomiaTests(unittest.TestCase):
    def test_clima_dispensa_memoria_inclusive_continuacao(self):
        self.assertTrue(consulta_temporaria('Qual a previsão de tempo para Camaçari?'))
        self.assertTrue(consulta_temporaria('E amanhã?', True))
        self.assertTrue(consulta_temporaria('E em Salvador?', True))
        self.assertFalse(consulta_temporaria('Abra o Excel', True))
        self.assertFalse(consulta_temporaria('Qual a temperatura da CPU?', True))
        self.assertFalse(consulta_temporaria('Lembre que gosto de clima frio', True))

    def test_voz_pula_introducao_sem_remover_falhas(self):
        texto = 'Aqui estão os dados meteorológicos atuais para Camaçari. Camaçari está com 28,4 °C.'
        self.assertEqual(resumo_voz(texto), 'Camaçari está com 28,4 °C.')
        self.assertEqual(resumo_voz('A consulta falhou. Tente novamente.'), 'A consulta falhou.')

    def test_uso_diferenca_nao_e_atribuida_a_raciocinio(self):
        uso = UsoTokens()
        uso.registrar(SimpleNamespace(usage_metadata=SimpleNamespace(
            prompt_token_count=1148, candidates_token_count=261, total_token_count=1758)))
        self.assertEqual(uso.totais['nao_discriminados'], 349)
        self.assertIsNone(uso.totais['raciocinio'])
        self.assertEqual(uso.campos_ausentes['raciocinio'], 1)

    def test_uso_cache_nao_e_somado_duas_vezes(self):
        uso = UsoTokens()
        uso.registrar(SimpleNamespace(usage_metadata=dict(prompt_token_count=100,
            candidates_token_count=20, thoughts_token_count=30,
            cached_content_token_count=80, total_token_count=150)))
        self.assertEqual(uso.totais['raciocinio'], 30)
        self.assertEqual(uso.totais['nao_discriminados'], 0)

    def test_historico_limitado_e_pares_completos(self):
        contexto = Contexto(max_pares=2, max_chars=1000, resumo_chars=100)
        for i in range(20):
            contexto.adicionar(f'Pedido {i}', 'Resposta ' + str(i))
        self.assertEqual(len(contexto.pares), 2)
        self.assertLessEqual(len(contexto.resumo), 100)
        self.assertEqual([m['role'] for m in contexto.historico()], ['user', 'model'] * 2)
        self.assertIn('Pedido 19', contexto.texto())

    def test_historico_enorme_respeita_orcamento(self):
        contexto = Contexto(max_chars=1000)
        contexto.adicionar('x' * 50000, 'y' * 50000)
        self.assertLessEqual(sum(len(a)+len(b) for a,b in contexto.pares), 1000)

    def test_voz_local_remove_codigo_e_limita(self):
        self.assertEqual(resumo_voz('Tudo pronto. Detalhes adicionais.'), 'Tudo pronto.')
        self.assertLessEqual(len(resumo_voz('palavra ' * 200)), 200)
        self.assertNotIn('print', resumo_voz('```python\nprint(1)\n```'))

    def test_selecao_clima_continuacao_e_fallback(self):
        def verificar_clima(): pass
        def abrir_site(): pass
        registro = [verificar_clima, abrir_site]
        self.assertEqual(selecionar_ferramentas('Vai chover amanhã?', registro), [verificar_clima])
        self.assertEqual(selecionar_ferramentas('E amanhã?', registro, 'qual o clima'), [verificar_clima])
        self.assertEqual(selecionar_ferramentas('Olá!', registro), [])
        self.assertEqual(selecionar_ferramentas('pedido ambíguo', registro), registro)

    def test_wrapper_preserva_schema_e_nao_repete_acao(self):
        chamadas = []
        def acao(nome: str, vezes: int = 1) -> str:
            chamadas.append(nome)
            return 'x' * 10000
        wrapped, = limitar_ferramentas([acao], 100)
        self.assertEqual(inspect.signature(wrapped), inspect.signature(acao))
        self.assertLessEqual(len(wrapped('teste')), 100)
        wrapped(nome='teste', vezes=1)
        self.assertEqual(chamadas, ['teste'])

    def test_wrapper_nao_repete_falha_incerta(self):
        chamadas = []
        def acao():
            chamadas.append(1)
            raise RuntimeError('incerto')
        wrapped, = limitar_ferramentas([acao])
        with self.assertRaises(RuntimeError): wrapped()
        self.assertIn('incerto', wrapped())
        self.assertEqual(len(chamadas), 1)

    def test_memoria_filtra_distancia_duplicata_e_historico(self):
        antiga = 'Usuário disse: meu editor | JARVIS respondeu: VS Code'
        dados = {'documents': [[antiga, 'preferência nova', 'preferência nova', 'irrelevante']],
                 'distances': [[.1, .2, .2, 5.0]]}
        self.assertEqual(filtrar_memorias(dados, 'meu editor\nVS Code'), 'preferência nova')
        self.assertEqual(filtrar_memorias({'documents': [[]], 'distances': [[]]}), '')

    def test_memoria_tem_teto(self):
        dados = {'documents': [['a' * 3000, 'b' * 3000]], 'distances': [[.1, .1]]}
        self.assertLessEqual(len(filtrar_memorias(dados, limite=500)), 500)

    def test_uso_soma_todas_respostas(self):
        uso = UsoTokens()
        resposta = SimpleNamespace(usage_metadata=SimpleNamespace(prompt_token_count=100,
                                  candidates_token_count=10, total_token_count=110))
        uso.registrar(resposta)
        uso.registrar(resposta)
        uso.registrar(SimpleNamespace())
        self.assertEqual(uso.totais['total'], 220)
        self.assertEqual(uso.chamadas, 3)
        self.assertEqual(uso.sem_metadados, 1)

    def test_leitura_paginada_utf8_e_latin1(self):
        ler = carregar_funcao('ler_arquivo', os=os, limite_env=limite_env, DEFAULT_MAX_FILE_READ_CHARS=3000)
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / 'texto.txt'
            arquivo.write_text('abcdefghijklmnop', encoding='utf-8')
            self.assertTrue(ler(str(arquivo), 5, 4).endswith('fghi'))
            self.assertIn('Próximo inicio: 9', ler(str(arquivo), 5, 4))
            arquivo.write_bytes('ação'.encode('latin-1'))
            self.assertTrue(ler(str(arquivo)).endswith('ação'))
            self.assertIn('Fim do arquivo', ler(str(arquivo), 500))

    def test_modelo_mede_subchamadas_e_interrompe_loop(self):
        class FakeModel:
            def __init__(self, **kwargs): pass
            def generate_content(self, *args, **kwargs):
                return SimpleNamespace(usage_metadata=None)
        classe = carregar_funcao('ModeloMedido', 'janus/runtime.py',
                                genai=SimpleNamespace(GenerativeModel=FakeModel),
                                limite_env=lambda *a, **k: 2)
        uso = UsoTokens()
        modelo = classe(uso=uso)
        modelo.generate_content('primeira')
        modelo.generate_content('resultado da ferramenta')
        with self.assertRaises(RuntimeError): modelo.generate_content('loop')
        self.assertEqual(uso.chamadas, 2)


if __name__ == '__main__':
    unittest.main()
