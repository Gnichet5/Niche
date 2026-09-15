import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from weather_service import consultar_clima


class ClimaTests(unittest.TestCase):
    def setUp(self):
        self.local = {'name': 'Camaçari', 'admin1': 'Estado de Bahia', 'country': 'Brasil',
                      'country_code': 'BR', 'latitude': -12.69, 'longitude': -38.32}
        self.previsao = {'timezone': 'America/Bahia',
                        'current': {'time': '2026-09-15T10:00', 'temperature_2m': 25,
                                    'apparent_temperature': 27, 'relative_humidity_2m': 70},
                        'daily': {'time': ['2026-09-15', '2026-09-16', '2026-09-17'],
                                  'temperature_2m_max': [28, 29, 30],
                                  'temperature_2m_min': [20, 21, 22],
                                  'precipitation_probability_max': [60, 20, None]}}

    @patch('weather_service._get_json')
    def test_previsao_localizada(self, get):
        get.side_effect = [{'results': [self.local, dict(self.local)]}, self.previsao]
        resultado = consultar_clima('Camaçari', 'Bahia', 'BR')
        self.assertIn('Camaçari', resultado)
        self.assertIn('2026-09-17', resultado)
        self.assertIn('indisponível', resultado)
        self.assertEqual(get.call_count, 2)
        self.assertLess(len(resultado), 1500)

    @patch('weather_service._get_json')
    def test_ambiguidade_nao_adivinha(self, get):
        get.return_value = {'results': [self.local, dict(self.local, admin1='Outro estado')]}
        self.assertIn('ambígua', consultar_clima('Camaçari'))
        self.assertEqual(get.call_count, 1)

    @patch('weather_service._get_json')
    def test_cidade_ausente(self, get):
        get.return_value = {}
        self.assertIn('não encontrada', consultar_clima('inexistente'))

    @patch('weather_service._get_json')
    def test_erro_http_nao_inventa_dados(self, get):
        get.side_effect = HTTPError('https://example.com', 403, 'Forbidden', {}, None)
        self.assertIn('Não há dados confirmados', consultar_clima('Camaçari'))

    @patch('weather_service._get_json')
    def test_resposta_incompleta(self, get):
        get.side_effect = [{'results': [self.local]}, {}]
        self.assertIn('dados incompletos', consultar_clima('Camaçari'))


if __name__ == '__main__':
    unittest.main()
