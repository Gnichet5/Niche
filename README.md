# Janus

Assistente pessoal com Gemini, memória Chroma local e uma interface de conversa
servida no próprio computador. O navegador não recebe a chave de API.

## Iniciar a interface

No PowerShell, na pasta do projeto:

```powershell
.\venv\Scripts\python.exe main.py
```

Abra **http://127.0.0.1:8765** no navegador. O servidor fica restrito a esse
computador. A inicialização do Gemini e do banco ocorre no primeiro pedido.
Feche o console antigo antes de iniciar a interface. Para parar, use Ctrl+C.

Porta alternativa: `python main.py --port 8766`.
Console clássico: `python main.py --cli`.

Caso esteja instalando em outro ambiente: instale `requirements.txt` no ambiente
virtual e configure `GEMINI_API_KEY` no `.env` da raiz. A interface não acrescenta
dependências Python nem exige Node/npm para executar.

## Uso

- Digite e pressione Enter; Shift+Enter insere uma nova linha.
- As sugestões apenas preenchem a mensagem. Envie quando quiser.
- “Imagem” anexa PNG/JPEG/WebP de até 4 MB ao próximo pedido. A interface não
  captura a tela automaticamente. A imagem anexada é enviada ao Gemini.
- “Voz” lê a frase curta usando a voz do navegador, sem nova consulta ao Gemini.
- “Ditar” depende do reconhecimento de voz do navegador e da permissão de
  microfone. O serviço do navegador pode processar áudio remotamente. Revise o
  texto antes de enviar. Se não houver suporte, continue digitando.
- Ações que alteram o computador pedem aprovação na interface. A aprovação
  expira em três minutos; não usa `input()` no terminal.
- “Memórias” lista até 50 registros reais. “Esquecer” pede confirmação, remove
  o registro permanentemente e limpa o contexto da conversa em RAM.
- “Nova conversa” limpa o contexto da sessão, preservando o banco de memórias.
  Conversas completas não são arquivadas no navegador: recarregar a página
  perde as mensagens visíveis, embora o contexto do servidor permaneça até
  iniciar uma nova conversa ou reiniciar o processo.
- Apenas um pedido roda por vez. Use uma aba para controlar a sessão.
- “Contexto e consumo” mostra tokens, modelo e resultados das ferramentas.

## Estrutura

```text
main.py                 entrada da aplicação (--cli ou interface)
janus/
  server.py             HTTP local, jobs e fila de aprovação
  engine.py             sessão de conversa da interface
  runtime.py            integração Gemini, memória e console existente
  permissions.py        contrato de aprovação console/navegador
web/
  index.html            estrutura da interface
  style.css             design Conversa, responsivo, claro/escuro
  app.js                interação e comunicação com o servidor local
tools.py                registro e implementações das ferramentas
token_budget.py         políticas de contexto e medição
memory_config.py        caminho do banco local/pen drive
weather_service.py      meteorologia
tests/                  testes do servidor e da sessão
test_*.py               testes existentes preservados
```

Os módulos existentes permanecem na raiz para preservar compatibilidade e o
caminho da memória. O `main.py` anterior foi extraído para `janus/runtime.py`,
com inicialização explícita. Áudio do console só é inicializado no modo CLI.
Os scripts `watchdog.py`, `detector.py` e `diagnostico.py` são utilitários legados:
não são iniciados pela interface. O watchdog atual não está integrado ao novo
servidor e não deve ser usado para supervisioná-lo.

Memória no SanDisk e limites de contexto: veja [MEMORIA.md](MEMORIA.md).
O banco, o `.env` e os registros existentes não são movidos pela nova estrutura.

## Testes sem chamadas pagas

```powershell
.\venv\Scripts\python.exe -m unittest test_memory_config test_token_budget test_weather_service -v
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

Os testes usam serviços simulados para validar fila, aprovação, proteção da API,
memória e contexto. Para validar a integração real, envie um pedido pela interface;
isso usa sua API Gemini. Não exponha este servidor na internet.
