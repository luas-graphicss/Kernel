# Protocolos de rede

[English](protocols.en.md)

O serviço de rede é um processo em U-mode, `kernel_services.network.main`. Ele contém o driver do `virtio-net`, a pilha IPv4 e os sockets, e fala Ethernet, ARP, IPv4, ICMP, UDP e TCP por uma interface com endereço estático. Esta página diz o que cada protocolo aceita, o que recusa e com que limites. A API que os outros processos usam está em `socket-service.md`.

O perfil é o de uma estação em uma rede local: sem IPv6, sem DHCP, sem DNS e sem encaminhamento. O que não aparece aqui como suportado não é suportado.

## Matriz

| Camada | Suportado | Recusado ou ausente |
| --- | --- | --- |
| Dispositivo | `virtio-net` moderno sobre VirtIO-MMIO, com a feature `MAC` e, quando oferecida, `STATUS`. A fila 0 recebe e a fila 1 transmite. Quadros de até 1514 bytes | Offload de checksum, segmentação pelo dispositivo, buffers agrupados, fila de controle, mais de um par de filas |
| Ethernet | Quadros Ethernet II para o endereço da interface ou para broadcast. Payload curto sai completado até 46 bytes | VLAN, quadro para outro endereço, remetente de grupo ou zerado, tipo diferente de ARP e IPv4 |
| ARP | Pedido e resposta para Ethernet e IPv4. Responde pelo próprio endereço. Aprende o remetente quando o pacote é para a interface ou quando o vizinho já era conhecido | Outro tipo de hardware ou de protocolo, operação desconhecida, remetente diferente do quadro, remetente fora da sub-rede, pacote que anuncia o endereço da interface |
| IPv4 | Cabeçalho de 20 bytes com checksum conferido. Entrega ao endereço da interface e ao broadcast da sub-rede. Envio com TTL 64, rota direta pela máscara e um gateway padrão opcional. Fragmentação no envio e reassembly na chegada. Entrega local para o próprio endereço e para `127.0.0.0/8` | Opções, encaminhamento, multicast, origem que não é uma estação ou que é o endereço da interface |
| ICMP | Echo nos dois sentidos. Destino inalcançável recebido, com os códigos de host, protocolo, porta e fragmentação necessária. Porta e protocolo inalcançáveis enviados | Redirect, tempo excedido, timestamp e os demais tipos: contados e descartados |
| UDP | Datagramas com checksum conferido quando o remetente o enviou. Portas de 1 a 65535 | Porta de destino zero, comprimento que não confere com o pacote |
| TCP | Abertura ativa e passiva, dados nos dois sentidos, janela, retransmissão por tempo e por três ACKs duplicados, controle de congestionamento, half-close, reset e `TIME_WAIT`. Opção de tamanho máximo de segmento | Escala de janela, SACK, timestamps, dados urgentes, keepalive |

## Dispositivo e enlace

O driver, `kernel_drivers.virtio_network.driver`, roda dentro do processo do serviço. Ele abre a sessão pedindo `VIRTIO_NET_F_MAC` e `VIRTIO_NET_F_STATUS` e recusa um dispositivo sem endereço ou sem a segunda fila com `UNSUPPORTED`. Nenhum offload é negociado: o cabeçalho de 12 bytes de cada quadro vai zerado, e todo checksum é calculado e conferido pela pilha.

Um buffer de 16 KiB, do próprio serviço, guarda quatro slots de recepção e quatro de transmissão, de 2048 bytes cada. O driver nomeia cada slot por handle e offset, como em `specs/abi/devices.md`, e nunca vê um endereço físico. Nenhum outro processo recebe a capability do dispositivo.

| Situação | Comportamento |
| --- | --- |
| Transmissor sem slot livre | O quadro espera em uma fila de 64 quadros. Com a fila cheia ele é descartado e contado |
| Enlace caído, informado pelo dispositivo | `network: link=down`. Envios devolvem `UNREACHABLE` até `network: link=up` |
| Dispositivo falho | Até três tentativas de reset e nova sessão, uma por segundo, com a linha `network: device=recovered resets=N`. Os quadros em espera são descartados, e a conectividade volta depois do reset |

## ARP

| Limite | Valor |
| --- | --- |
| Vizinhos conhecidos | 32, cada um por 60 s. Com a tabela cheia sai o mais próximo de expirar |
| Resoluções em andamento | 8 destinos, com até 4 datagramas em espera por destino |
| Tentativas | 3 pedidos, um por segundo. Depois disso o destino é `UNREACHABLE` |

Um pacote ARP só ensina um vizinho quando o endereço de hardware declarado é o do quadro que o trouxe e o endereço IPv4 é o de uma estação da sub-rede que não é a própria interface.

## IPv4

| Regra | Efeito quando violada |
| --- | --- |
| Versão 4, cabeçalho e comprimento total dentro do quadro | Descartado, `ipv4-malformed` |
| Cabeçalho de exatamente 20 bytes | Descartado, `ipv4-options-refused` |
| Checksum do cabeçalho | Descartado, `ipv4-bad-checksum` |
| Origem que nomeia uma estação e não é a interface | Descartado, `ipv4-bad-source` |
| Destino igual ao endereço da interface ou ao broadcast | Descartado, `ipv4-foreign` |
| Protocolo 1, 6 ou 17 | Protocolo inalcançável para a origem, `ipv4-protocol-unsupported` |

O MTU da interface vai de 576 a 1500 bytes e vem da configuração. Um destino fora da sub-rede segue para o gateway; sem gateway ele é `UNREACHABLE` na hora, sem pedido ARP.

Um datagrama maior que o MTU sai fragmentado em pedaços múltiplos de 8 bytes. A pilha não marca `DF`. Na chegada:

| Limite do reassembly | Valor |
| --- | --- |
| Datagramas em montagem | 16 |
| Bytes em montagem | 1 MiB, à parte do orçamento dos sockets |
| Tempo de vida de uma montagem | 30 s |

Um fragmento repetido com os mesmos bytes é tolerado. Fragmentos que se sobrepõem com bytes diferentes, que discordam sobre o fim, que ficam fora do limite de 8 bytes, vazios ou além de 65.535 bytes invalidam a montagem inteira, com `fragments-invalid`. Quando falta espaço sai a montagem mais antiga, com `fragments-evicted`; uma montagem que expira conta `fragments-expired`. Uma montagem sozinha não toma o orçamento inteiro.

## ICMP

| Mensagem | Tratamento |
| --- | --- |
| Echo request recebido | Respondido quando é para o endereço da interface e leva até 1472 bytes. Limite de 8 respostas em rajada, com uma nova a cada 100 ms; o excesso conta `icmp-rate-limited` |
| Echo reply recebido | Entregue ao pedido de echo que o espera, identificado pela sessão e pela sequência |
| Destino inalcançável recebido | Só é aceito se cita um datagrama que esta estação enviou; senão conta `icmp-malformed`. Porta ou protocolo inalcançável encerra uma conexão TCP em abertura e marca o socket UDP de origem. Fragmentação necessária reduz o tamanho de segmento da conexão citada, até o piso de 64 bytes |
| Destino inalcançável enviado | Porta inalcançável para UDP sem socket, protocolo inalcançável para protocolo desconhecido. Mesmo limite de rajada do echo |

## UDP

Um socket de datagramas guarda até 16 datagramas e 64 KiB. Um datagrama que chega com a fila cheia é descartado, com `udp-queue-full`. Um datagrama para porta sem socket conta `udp-no-listener` e gera porta inalcançável. As portas efêmeras vão de 49152 a 65535, e a primeira tentada é sorteada.

Pelo serviço de sockets um datagrama enviado leva até 4026 bytes e um recebido entrega até 4022; acima do MTU ele sai fragmentado.

## TCP

A conexão é uma máquina de estados explícita, com os estados `closed`, `syn-sent`, `syn-received`, `established`, `fin-wait-1`, `fin-wait-2`, `close-wait`, `closing`, `last-ack` e `time-wait`. A aritmética de sequência é modular em 32 bits.

| Mecanismo | Comportamento |
| --- | --- |
| Número de sequência inicial e porta efêmera | Sorteados com bytes do serviço de entropia. Sem entropia o serviço de rede não inicia |
| Tamanho de segmento | MTU menos 40 bytes, anunciado no `SYN`. O valor anunciado pelo peer é respeitado; sem anúncio vale 536 |
| Janela | Buffers de 16 KiB para envio e para recepção, por conexão. Janela zero é sondada por temporizador, e a leitura reabre a janela com um ACK |
| Fora de ordem | Até 16 segmentos guardados por conexão. O excesso é descartado, com `tcp-out-of-order-refused` |
| Tempo de retransmissão | Estimado pelo tempo de ida e volta, entre 200 ms e 60 s, com valor inicial de 1 s e dobra a cada expiração |
| Desistência | 8 retransmissões de dados ou 4 da abertura. A conexão termina com `TIMED_OUT`, ou com `UNREACHABLE` se o caminho informou erro |
| Congestionamento | Slow start, congestion avoidance, retransmissão rápida no terceiro ACK duplicado e recuperação rápida com ACK parcial. Janela inicial de 2 a 4 segmentos |
| Reset | Segmento para porta sem socket recebe `RST`, com limite de 16 em rajada e um novo a cada 50 ms. Um `RST` aceitável encerra a conexão com `CONNECTION_RESET`, ou com `CONNECTION_REFUSED` durante a abertura |
| ACK inválido | Um ACK de bytes nunca enviados não muda o estado e conta `tcp-unacceptable` |
| Fechamento | `FIN` em cada sentido, com half-close. Quem fecha primeiro fica 60 s em `time-wait` |
| Fila de aceitação | Até 8 conexões por socket em escuta. Pedidos além disso são descartados, com `tcp-backlog-full`, e o peer retransmite |

Um socket fechado com dados ainda não confirmados continua a entrega em segundo plano. Se o peer não confirma nada por 3 s, a conexão é abortada com `RST`.

## Limites do serviço

| Limite | Valor |
| --- | --- |
| Sockets | 64 no total e 16 por processo |
| Conexões TCP | 96, contando as que estão em abertura, em fechamento e em `time-wait` |
| Bytes em buffers de sockets | 1 MiB para todos os sockets |
| Quadros na fila de saída | 64 |
| Datagramas em entrega local | 32 |

Quando o orçamento de bytes acaba, uma escrita TCP aceita menos bytes ou nenhum, e um datagrama novo é descartado. Nenhum processo consegue mais que a sua cota abrindo vários sockets: o orçamento é um só.

## Contadores

O comando `net counters` e a operação `STATUS` mostram os contadores do serviço. Cada pacote recusado incrementa o contador da regra que o recusou:

`frames-received`, `frames-sent`, `frames-malformed`, `frames-foreign`, `frames-unsupported`, `frames-unsent`, `arp-malformed`, `arp-requests-answered`, `arp-unresolved`, `arp-queue-refused`, `ipv4-malformed`, `ipv4-bad-checksum`, `ipv4-options-refused`, `ipv4-foreign`, `ipv4-bad-source`, `ipv4-protocol-unsupported`, `ipv4-unroutable`, `ipv4-too-large`, `fragments-received`, `fragments-invalid`, `fragments-expired`, `fragments-evicted`, `datagrams-reassembled`, `icmp-malformed`, `icmp-echo-answered`, `icmp-rate-limited`, `icmp-unsupported`, `udp-malformed`, `udp-bad-checksum`, `udp-no-listener`, `udp-queue-full`, `udp-delivered`, `tcp-malformed`, `tcp-bad-checksum`, `tcp-no-socket`, `tcp-backlog-full`, `tcp-resets-sent`, `tcp-resets-received`, `tcp-segments-retransmitted`, `tcp-out-of-order`, `tcp-out-of-order-refused`, `tcp-unacceptable`, `tcp-connections-opened` e `tcp-connections-failed`.

## Evidência

Os valores estão em `kernel_services.network.limits`. A pilha é Python puro e roda igual em CPython, onde `tests/conformance/test_network_link.py`, `test_network_reassembly.py`, `test_network_tcp.py` e `test_network_malformed.py` a exercitam com dois lados ligados por um fio simulado, com perda, duplicação, reordenação e relógio controlado.

No QEMU, a suíte `network` cobre interface, echo, datagramas, conexões, escuta, cotas e direitos. A suíte `network-interop` troca dados com a pilha TCP/IP do Linux nos dois sentidos, por um enlace limpo e por um com 3% de perda, 2% de duplicação e 10% de reordenação, e confere cada transferência por hash. `kernel-tool fault-test --suite network-faults` injeta 31 espécimes malformados, de Ethernet a TCP, 32 pedidos de conexão forjados, 1,5 s de enlace caído e um reset do dispositivo. Os resultados registrados estão em `docs/acceptance/network-and-operational-environment.md`.
