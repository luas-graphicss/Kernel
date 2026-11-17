# Serviço de sockets

[English](socket-service.en.md)

O serviço de rede entrega sockets a outros processos por IPC. Um processo só abre um socket se recebeu uma capability de acesso, e cada acesso carrega um conjunto de direitos. Não existe socket por nome, por variável de ambiente nem por caminho de arquivo. As mensagens seguem `specs/abi/messages.md`, os formatos estão em `kernel_protocol.services.network` e a biblioteca cliente é `kernel_client.sockets`. Os protocolos que trafegam por baixo estão em `protocols.md`.

## Acesso e sessão

Um cliente precisa de duas capabilities, as duas com `SEND`: o endpoint do serviço e um acesso. O acesso é um endpoint criado pelo próprio serviço. Ele não recebe pedidos comuns; serve para provar a posse.

Para entrar, o cliente envia a mensagem `ENTER`, sem resposta, ao endpoint do acesso e em seguida chama `ENTER` no endpoint do serviço. O serviço confere que a chamada veio do mesmo processo que enviou a mensagem, pela identidade que o supervisor grava em cada mensagem, e cria uma sessão. A resposta tem 20 bytes: a instância do serviço, em 8, o token da sessão, em 8, e os direitos do acesso, em 4.

Chamar `ENTER` sem ter enviado a mensagem ao acesso, ou enviá-la a um endpoint que o serviço não criou, devolve `ACCESS_DENIED`.

| Bit | Direito | Permite |
| --- | --- | --- |
| `0x01` | `connect` | Abrir um socket de fluxo e conectar |
| `0x02` | `listen` | Abrir um socket de fluxo e escutar |
| `0x04` | `datagram` | Abrir um socket de datagramas |
| `0x08` | `echo` | Enviar echo request |
| `0x10` | `inspect` | Ler o estado da interface, os contadores e os vizinhos |
| `0x20` | `delegate` | Criar acessos restritos |

`RESTRICT` cria um acesso novo com um subconjunto dos direitos da sessão e devolve a capability dele, que o cliente pode conceder a outro processo. Pedir um direito que a sessão não tem devolve `ACCESS_DENIED`; pedir nenhum direito ou um bit desconhecido devolve `INVALID_ARGUMENT`. `REVOKE` desfaz um acesso que a própria sessão criou: os acessos derivados dele também caem, e toda sessão aberta por eles termina, com os sockets fechados e as esperas encerradas com `CANCELLED`. `LEAVE` termina a sessão de quem chama da mesma forma.

O processo que supervisiona o serviço tem duas operações só dele. `ROOT` devolve o acesso com todos os direitos, do qual os outros são derivados. `EVICT` termina as sessões de um processo, e é chamada quando uma aplicação termina. De qualquer outro processo as duas devolvem `ACCESS_DENIED`.

## Pedidos

Todo pedido, fora `ENTER`, `ROOT` e `EVICT`, começa com 16 bytes: a instância do serviço, em 8, e o sujeito, em 8. O sujeito é o token da sessão ou o handle de um socket. Os inteiros são little-endian.

| Condição | Erro |
| --- | --- |
| Instância de antes de um reinício, token ou handle desconhecido, ou de outro processo | `INVALID_HANDLE` |
| Corpo com tamanho diferente do da operação | `INVALID_ARGUMENT` |
| Pedido com uma capability | `INVALID_ARGUMENT`, e a capability é fechada |
| Operação desconhecida | `UNSUPPORTED` |
| Sessão sem o direito da operação | `ACCESS_DENIED` |
| Operação de fluxo em socket de datagramas, ou o contrário | `NOT_FOUND` |

| Número | Operação | Sujeito | Corpo | Resposta |
| --- | --- | --- | --- | --- |
| 16 | `ROOT` | Nenhum | Vazio | Vazia, com a capability do acesso completo |
| 17 | `EVICT` | Nenhum | Identidade do processo, em 8 bytes | Vazia |
| 18 | `ENTER` | Nenhum | Vazio | Sessão, 20 bytes |
| 19 | `LEAVE` | Sessão | Vazio | Vazia |
| 20 | `RESTRICT` | Sessão | Direitos, em 4 | Identidade do acesso, em 4, com a capability dele |
| 21 | `STATUS` | Sessão | Vazio | Interface |
| 22 | `NEIGHBORS` | Sessão | Vazio | 10 bytes por vizinho: endereço e hardware |
| 23 | `ECHO` | Sessão | Endereço, em 4, espera, em 8, e bytes de dados, em 2 | Tempo de ida e volta em nanossegundos, em 8 |
| 24 | `OPEN` | Sessão | Tipo, em 4: 1 fluxo, 2 datagramas | Handle do socket, em 8 |
| 25 | `BIND` | Socket | Porta, em 2. Em socket de datagramas, zero pede uma porta efêmera | Porta atribuída, em 2 |
| 26 | `LISTEN` | Socket | Fila de aceitação, em 2, de 1 a 8 | Vazia |
| 27 | `ACCEPT` | Socket | Espera, em 8 | Handle novo, em 8, endereço, em 4, e porta, em 2 |
| 28 | `CONNECT` | Socket | Endereço, em 4, porta, em 2, e espera, em 8 | Vazia |
| 29 | `SEND` | Socket | Espera, em 8, e os dados | Bytes aceitos, em 4 |
| 30 | `RECEIVE` | Socket | Espera, em 8, e limite, em 4 | Os dados. Vazia no fim do fluxo |
| 31 | `SEND_TO` | Socket | Endereço, em 4, porta, em 2, e os dados | Bytes enviados, em 4 |
| 32 | `RECEIVE_FROM` | Socket | Espera, em 8, e limite, em 4 | Endereço, em 4, porta, em 2, tamanho do datagrama, em 4, e os dados |
| 33 | `FINISH` | Socket | Vazio | Vazia |
| 34 | `CLOSE` | Socket | Vazio | Vazia |
| 35 | `DESCRIBE` | Socket | Vazio | Descrição, 22 bytes |
| 36 | `REVOKE` | Sessão | Identidade do acesso, em 4 | Vazia |

Interface, 32 bytes mais 8 por contador:

| Offset | Tamanho | Campo |
| --- | --- | --- |
| 0 | 6 | Endereço de hardware |
| 6 | 4 | Endereço IPv4 |
| 10 | 4 | Gateway, ou zero |
| 14 | 2 | MTU |
| 16 | 1 | Prefixo |
| 17 | 1 | Enlace: 1 ativo |
| 18 | 2 | Sockets abertos |
| 20 | 2 | Conexões TCP |
| 22 | 4 | Bytes em buffers |
| 26 | 4 | Resets do dispositivo |
| 30 | 2 | Quantidade de contadores, na ordem de `protocols.md` |

Descrição de um socket: tipo, em 1 byte, estado, em 1, porta local, em 2, endereço remoto, em 4, porta remota, em 2, bytes prontos para leitura, em 4, bytes que cabem para escrita, em 4, e o último erro, em 4.

| Valor | Estado |
| --- | --- |
| 0 | `new` |
| 1 | `bound` |
| 2 | `listening` |
| 3 | `connecting` |
| 4 | `connected` |
| 5 | `peer-finished`: o peer encerrou o envio |
| 6 | `finished`: este lado encerrou o envio |
| 7 | `closed` |

## Regras por operação

| Operação | Condição | Erro |
| --- | --- | --- |
| `OPEN` | 16 sockets no processo ou 64 no serviço | `LIMIT_EXCEEDED` |
| `BIND` | Socket de fluxo com porta zero, ou que já tem porta, escuta ou conexão | `INVALID_ARGUMENT` |
| `BIND` | Socket de datagramas que já tem porta | `BAD_STATE` |
| `BIND` de datagramas, `LISTEN` | Porta já usada por outro socket | `ALREADY_EXISTS` |
| `LISTEN` | Socket sem porta, ou que já escuta ou tem conexão | `BAD_STATE` |
| `LISTEN` | Fila de aceitação fora de 1 a 8 | `INVALID_ARGUMENT` |
| `ACCEPT` | Socket que não escuta | `BAD_STATE` |
| `CONNECT` | Socket que já escuta ou tem conexão | `BAD_STATE` |
| `CONNECT`, `SEND_TO`, `ECHO` | Endereço que não nomeia uma estação, ou porta zero | `INVALID_ARGUMENT` |
| `CONNECT` | O peer respondeu com reset | `CONNECTION_REFUSED` |
| `CONNECT`, `SEND_TO`, `ECHO` | Sem rota, enlace caído, vizinho que não respondeu ou erro informado pelo caminho | `UNREACHABLE` |
| `SEND` | Nenhum byte, ou mais de 4032 bytes em um pedido | `INVALID_ARGUMENT` |
| `SEND` | Depois de `FINISH`, ou sem conexão estabelecida | `BAD_STATE` |
| `SEND`, `RECEIVE` | A conexão foi encerrada por reset | `CONNECTION_RESET` |
| `SEND`, `RECEIVE` | O peer não confirmou dentro das retransmissões | `TIMED_OUT` |
| `SEND_TO` | Mais de 4026 bytes | `MESSAGE_TOO_LARGE` |
| `RECEIVE_FROM` | Um datagrama anterior voltou com porta inalcançável | `CONNECTION_REFUSED`, uma vez |
| `ECHO` | Mais de 1024 bytes de dados | `INVALID_ARGUMENT` |

Um socket de datagramas sem porta recebe uma porta efêmera no primeiro `SEND_TO` ou `RECEIVE_FROM`. `RECEIVE_FROM` entrega um datagrama inteiro por chamada. Se ele é maior que o limite pedido, os dados vêm cortados e o campo de tamanho diz quanto o datagrama tinha; o resto é descartado.

`FINISH` encerra só o envio. O socket continua recebendo até o peer encerrar o lado dele. `CLOSE` libera o socket na hora; os bytes já aceitos e ainda não confirmados continuam a ser entregues em segundo plano.

## Espera, deadline, cancelamento e backpressure

A espera de uma operação é um tempo relativo, em nanossegundos. Zero não espera: sem resultado pronto a resposta é `TIMED_OUT`. `0xFFFFFFFFFFFFFFFF` espera sem limite.

`ACCEPT`, `CONNECT`, `SEND`, `RECEIVE`, `RECEIVE_FROM` e `ECHO` podem esperar. O serviço guarda o pedido e responde quando há resultado, quando a espera acaba ou quando o pedido é cancelado. Ele continua atendendo os outros clientes enquanto isso.

| Situação | Resultado para quem espera |
| --- | --- |
| A espera acabou | `TIMED_OUT`. Uma conexão em abertura é abandonada |
| O mesmo processo repete a operação no mesmo socket | O pedido anterior termina com `CANCELLED` |
| O socket é fechado, a sessão termina ou o acesso é revogado | `CANCELLED` |
| O serviço recebe `STOP` | `CANCELLED` |
| 64 pedidos já esperam no serviço | `LIMIT_EXCEEDED` |
| O cliente morreu antes da resposta | O efeito é desfeito: a conexão aceita é fechada, e os bytes lidos continuam no buffer |

`SEND` devolve quantos bytes entraram no buffer de envio da conexão, que pode ser menos do que o pedido. Só quando nenhum byte cabe a chamada espera. O buffer tem 16 KiB por conexão, dentro do orçamento de 1 MiB do serviço, de modo que um peer que nunca lê para quem envia sem consumir a memória dos outros sockets. Um `RECEIVE` só tira os bytes do buffer depois de a resposta ser entregue.

## Reinício do serviço

Cada instância do serviço tem uma identidade. Depois de um reinício, um token ou handle da instância anterior devolve `INVALID_HANDLE`, e o acesso antigo deixa de existir: a biblioteca informa `ACCESS_DENIED` a quem tenta entrar com ele. Nenhuma conexão atravessa o reinício, e nada é repetido sozinho. Quem esperava uma resposta recebe `PEER_CLOSED`.

## Biblioteca cliente

`kernel_client.sockets.Network(serviço, acesso)` entra no serviço e oferece `status`, `neighbors`, `echo`, `restrict`, `revoke`, `stream`, `datagram` e `leave`. `StreamSocket` tem `bind`, `listen`, `accept`, `connect`, `send`, `send_all`, `receive`, `finish`, `describe` e `close`. `DatagramSocket` tem `bind`, `send_to`, `receive_from`, `describe` e `close`. Toda falha levanta `KernelError` com o código.

```python
from kernel_apps import runtime
from kernel_services.network.ipv4.address import parse_address

network = runtime.current().network
stream = network.stream()
stream.connect(parse_address("10.0.2.2"), 17, 10_000_000_000)
data = stream.receive(2048, 10_000_000_000)
stream.close()
```

## Evidência

A suíte `network` cobre esta página no QEMU, contra um peer real: `interface-and-echo`, `datagrams`, `streams`, `listening`, `deadlines-cancellation-and-backpressure`, `socket-quota` e `access-rights`. O último caso confere a restrição e a revogação de acessos, a recusa de handles forjados e de outra instância, e inicia um processo que tem o endpoint do serviço e nenhum acesso: ele não abre socket nem alcança o dispositivo. O caso `service-restart-with-a-waiting-client` de `network-faults` cobre o reinício.
