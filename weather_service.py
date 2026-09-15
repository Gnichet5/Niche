"""Consulta meteorológica compacta no Open-Meteo, sem chave de API."""
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from token_budget import normalizar


def _get_json(url, params):
    # HTTPS padrão do Python usa também os certificados do Windows.
    request = urllib.request.Request(url + '?' + urllib.parse.urlencode(params),
                                     headers={'User-Agent': 'Janus/1.0'})
    with urllib.request.urlopen(request, timeout=10) as resposta:
        return json.load(resposta)


def _estado(texto):
    return re.sub(r'^estado (?:de|do|da) ', '', normalizar(texto.strip()))


def consultar_clima(cidade, estado='', pais=''):
    try:
        params = {'name': cidade.strip(), 'count': 10, 'language': 'pt', 'format': 'json'}
        if pais.strip():
            params['countryCode'] = pais.strip().upper()
        locais = _get_json('https://geocoding-api.open-meteo.com/v1/search', params).get('results', [])
        if estado.strip():
            locais = [local for local in locais
                      if _estado(local.get('admin1', '')) == _estado(estado)]
        if not locais:
            return 'Cidade não encontrada. Informe cidade, estado por extenso e país (código de duas letras).'
        # A busca pode devolver bairros/distritos homônimos do mesmo município.
        # Para uma consulta por cidade, conserva o primeiro resultado do serviço.
        unicos = {}
        for local in locais:
            chave = (normalizar(local['name']), _estado(local.get('admin1', '')),
                     local.get('country_code', ''))
            unicos.setdefault(chave, local)
        locais = list(unicos.values())
        if len(locais) > 1:
            opcoes = '; '.join(f"{l['name']}, {l.get('admin1', '')}, {l.get('country_code', '')}"
                               for l in locais[:5])
            return 'Localidade ambígua. Peça ao usuário o estado e país antes de consultar: ' + opcoes
        local = locais[0]
        dados = _get_json('https://api.open-meteo.com/v1/forecast', {
            'latitude': local['latitude'], 'longitude': local['longitude'],
            'current': 'temperature_2m,apparent_temperature,relative_humidity_2m',
            'daily': 'temperature_2m_max,temperature_2m_min,precipitation_probability_max',
            'temperature_unit': 'celsius', 'timezone': 'auto', 'forecast_days': 3,
        })
        atual, diario = dados['current'], dados['daily']
        def valor(v):
            return 'indisponível' if v is None else str(v)
        linhas = [
            f"Fonte: Open-Meteo (https://open-meteo.com/). Local: {local['name']}, "
            f"{local.get('admin1', '')}, {local.get('country', '')}.",
            f"Horário local: {atual['time']} ({dados.get('timezone', '')}). "
            f"Temperatura: {valor(atual.get('temperature_2m'))} °C; "
            f"sensação: {valor(atual.get('apparent_temperature'))} °C; "
            f"umidade: {valor(atual.get('relative_humidity_2m'))}%.",
        ]
        for i, dia in enumerate(diario['time']):
            linhas.append(f"{dia}: mínima {valor(diario['temperature_2m_min'][i])} °C; "
                          f"máxima {valor(diario['temperature_2m_max'][i])} °C; "
                          f"probabilidade máxima de precipitação {valor(diario['precipitation_probability_max'][i])}%.")
        return '\n'.join(linhas)
    except (urllib.error.URLError, OSError) as e:
        return f'Serviço meteorológico indisponível: {e}. Não há dados confirmados para este pedido.'
    except (KeyError, TypeError, ValueError, IndexError):
        return 'O serviço meteorológico retornou dados incompletos. Não estime o clima sem dados.'
