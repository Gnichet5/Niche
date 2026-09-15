# Memória local do Janus

O Gemini continua responsável pela conversa e pelos embeddings. O banco Chroma
fica no computador ou no pen drive indicado por `JANUS_DB_PATH`, sem cópias
automáticas para o Google Drive. Armazenamento local não torna a IA offline:
texto continua sendo enviado ao Gemini para respostas e embeddings.

## Preparar o SanDisk

1. Feche todas as instâncias do assistente antes de copiar o banco.
2. Copie a pasta **inteira** `memoria_jarvis_v2` deste projeto para uma pasta
   nova no SanDisk. Preserve `chroma.sqlite3` e todas as subpastas dos índices.
   Não mescle bancos nem sobrescreva outra cópia existente.
3. Guarde a pasta original como backup até validar suas memórias.
4. No `.env` ao lado de `main.py`, defina o caminho real, por exemplo:
   `JANUS_DB_PATH=E:/Janus/memoria_jarvis_v2`.
5. Inicie o Janus e confira o caminho informado no log. Peça para listar memórias.
6. Feche o Janus antes de ejetar o pen drive ou fazer uma nova cópia de backup.

A letra `E:` é apenas um exemplo. Se o Windows mudar a letra da unidade,
atualize a configuração. Um caminho configurado que não existe ou não contém
o banco interrompe a inicialização, sem criar uma memória vazia em outro lugar.
Não use o mesmo banco em dois processos ao copiar ou remover a unidade.

Sem `JANUS_DB_PATH`, o Janus mantém o banco atual ao lado de `main.py`,
independentemente da pasta de onde foi iniciado. `JARVIS_DB_PATH`, configuração
antiga do Drive, é ignorada e pode ser removida do `.env`.

Os arquivos existentes de memória não foram movidos, apagados ou modificados
por esta alteração. A regra do `.gitignore` evita novos arquivos de memória;
arquivos que já estavam rastreados pelo Git continuam rastreados.

## Lista de ferramentas

`tools.FERRAMENTAS_JANUS` é a lista explícita enviada ao Gemini, inclusive nos
modelos de contingência. Funções auxiliares não são expostas. Para adicionar
uma ferramenta, implemente a função e inclua-a nessa lista. Esta etapa mantém
todas as funções públicas no registro. A seleção por pedido é feita localmente
em `token_budget.py`; pedidos ambíguos usam o registro completo.

## Economia de tokens

- Histórico: seis pares recentes, com teto de 12 mil caracteres. Pares antigos
  viram um resumo **extrativo local**, limitado a 2 mil caracteres. Esse resumo
  conserva trechos, não é uma síntese semântica e pode perder detalhes antigos.
  Os resultados brutos das ferramentas e as imagens não voltam nos próximos
  turnos. O histórico em RAM termina ao fechar o Janus.
- Voz: lê a primeira frase da resposta, limitada a 200 caracteres, sem consultar
  o Gemini outra vez. A resposta completa continua aparecendo no console.
- Ferramentas: seleção por termos do pedido e, em continuações curtas, do pedido
  anterior. Se não houver correspondência, todas ficam disponíveis. Saídas têm
  teto de 4 mil caracteres; trechos limitados são identificados. Resultados
  repetidos com os mesmos argumentos são reutilizados dentro do mesmo pedido,
  inclusive ao trocar de modelo, para não duplicar efeitos. Para refazer uma
  consulta ou ação idêntica, faça um novo pedido.
- Arquivos: leitura paginada, até 3 mil caracteres por chamada. O retorno indica
  o próximo `inicio` para continuar. Web: mil caracteres por página por padrão.
- Memória: recuperação de até três candidatos, filtro pela distância retornada
  pelo Chroma e remoção de duplicatas ou conteúdo já presente no histórico.
  São enviados até 1.600 caracteres. A distância máxima padrão é 0,8, ajustável
  e dependente da métrica da coleção; não é uma porcentagem de confiança.
  Perguntas com menos de três palavras não fazem busca vetorial automática.
  Novos registros usam até 1.500 caracteres da pergunta e da resposta; registros
  anteriores não são alterados. O modelo de embeddings continua o mesmo.
- Tela: somente pedidos explícitos como “olhe a tela” ou “print da tela”
  capturam o monitor principal, com dimensão máxima de 1280 pixels por lado.
- Geração: teto padrão de 2.048 tokens de saída por chamada e oito respostas
  por pedido. O limite também interrompe sequências longas de ferramentas.

Todos os ajustes ficam no `.env`; veja `.env.example`. Os limites de contexto
são de **caracteres**, não contagens exatas de tokens. Não há estimativa de
economia percentual antes de medir o uso real.

### Medição

O log `[Tokens]` soma os metadados das respostas recebidas do Gemini, incluindo
as chamadas intermediárias de ferramentas e respostas de modelos de contingência.
Mostra entrada, saída, raciocínio, cache e total informado pela API. Cache e
raciocínio não devem ser somados novamente ao total. Campos ausentes do SDK
ficam em zero; respostas sem metadados são contadas separadamente.
Embeddings e requisições que falharam sem retornar metadados não estão incluídos.
Os registros ficam no console, sem salvar o conteúdo dos pedidos em outro arquivo.

Verificação local: `python -m unittest test_memory_config test_token_budget -v`.
