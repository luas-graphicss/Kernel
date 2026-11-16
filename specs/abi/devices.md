# Dispositivos

O supervisor descobre os dispositivos no DTB, é o único que toca os registradores e as filas, e entrega cada dispositivo a um driver em U-mode por capability. O driver decide que pedido fazer. O supervisor valida o pedido e escreve ele mesmo os endereços físicos que o dispositivo vai ler. As decisões estão no ADR 0008.

## Descoberta

No boot o supervisor procura no DTB:

- um controlador de interrupções `sifive,plic-1.0.0` ou `riscv,plic0` com contexto de interrupção externa de S-mode;
- a porta serial `ns16550a` que já serve de console de boot, se ela declara interrupção;
- até oito transportes `virtio,mmio`.

Uma descrição malformada encerra o boot com `boot: rejected=devices reason=` e o motivo: mais de um controlador, mais de 1023 fontes, transporte sem interrupção ou sem registradores, interrupção fora das fontes do controlador, mais de oito transportes. Sem controlador para S-mode o boot segue, sem nenhum dispositivo.

Um transporte só é registrado se os registradores começam em uma página, ficam fora da RAM e da região de usuário, respondem com a assinatura do VirtIO-MMIO versão 2 e informam um modelo diferente de zero. Cada dispositivo registrado aparece em uma linha `boot: device=` com o slot, o tipo, o modelo e a interrupção.

| Slot | Dispositivo |
| --- | --- |
| 0 | Porta serial |
| 1 a 8 | Transportes VirtIO, em ordem crescente de endereço |

## Capability de dispositivo

| Chamada | Regra |
| --- | --- |
| `device_list(sistema, endereço, capacidade)` | Exige `READ` na capability do sistema e um buffer de pelo menos 144 bytes. Grava uma entrada de 16 bytes por dispositivo presente e devolve quantas gravou |
| `device_claim(sistema, slot)` | Exige `ADMIN` na capability do sistema. Devolve um handle do dispositivo com `READ`, `WRITE`, `ADMIN` e `DELEGATE` |

Entrada da lista, com quatro inteiros de 32 bits: slot, tipo, modelo e estado. O tipo é 1 para a porta serial e 2 para VirtIO. O modelo é o identificador de dispositivo do VirtIO: 2 para bloco, 4 para entropia.

Um dispositivo tem um dono por vez. `device_claim` devolve `BAD_STATE` enquanto existir alguma capability do dispositivo, em qualquer processo, e `INVALID_ARGUMENT` para um slot vazio. A capability pode ser derivada e concedida como qualquer outra; o `init` reivindica cada dispositivo e concede ao driver só `READ`, `WRITE` e `ADMIN`.

| Direito | Permite |
| --- | --- |
| `READ` | `device_config`, `device_wait`, `serial_read` |
| `WRITE` | `device_submit`, `serial_write` |
| `ADMIN` | `device_open`, `device_reset` |

Uma chamada de VirtIO sobre a porta serial, ou o contrário, devolve `UNSUPPORTED`.

## Estados de um dispositivo VirtIO

| Valor | Estado | Significado |
| --- | --- | --- |
| 0 | `closed` | Sem sessão. Pode ser aberto |
| 1 | `ready` | Negociado, aceita pedidos |
| 2 | `failed` | O dispositivo violou o protocolo ou pediu reset. Só `device_reset` o tira daí |
| 3 | `quarantined` | O reset não foi confirmado. Não volta a ser usado até o próximo boot |

A porta serial aparece sempre como `ready`.

## Sessão

`device_open(dispositivo, features, endereço da sessão)` exige `ADMIN`. `features` só pode ter os bits 0 a 23, que são os bits próprios de cada tipo de dispositivo; qualquer outro devolve `INVALID_ARGUMENT`.

O supervisor reinicia o dispositivo e negocia: exige `VIRTIO_F_VERSION_1`, aceita só os bits pedidos que o dispositivo oferece, confere que o dispositivo manteve `FEATURES_OK` e programa a fila 0 com 16 descritores. Um dispositivo sem a versão 1, que recusa as features ou cuja fila é menor é marcado como falho no próprio registrador de status, e a chamada devolve `UNSUPPORTED`.

| Condição | Erro |
| --- | --- |
| Outro processo tem a sessão, ou o dispositivo não está `closed` | `BAD_STATE` |
| O reset não foi confirmado | `IO_ERROR`, e o dispositivo vai para quarentena |
| Bloco da sessão sem permissão de escrita | `BAD_ADDRESS` |

O bloco da sessão tem 24 bytes: features aceitas, em 8 bytes, geração da sessão, em 8, e tamanho da fila, em 4. A geração muda a cada reset.

Quem abriu a sessão é o único que usa `device_config`, `device_submit` e `device_wait`. Outro processo com a mesma capability recebe `BAD_STATE`.

`device_config(dispositivo, offset, endereço, comprimento)` exige `READ` e copia de 1 a 256 bytes do espaço de configuração do dispositivo. O supervisor repete a leitura até quatro vezes se o dispositivo mudar a configuração no meio, e devolve `BAD_STATE` se ela não estabilizar.

## Pedidos

`device_submit(dispositivo, endereço do pedido)` exige `WRITE`. O pedido tem 104 bytes.

| Offset | Tamanho | Campo | Regra |
| --- | --- | --- | --- |
| 0 | 4 | `queue` | Zero |
| 4 | 4 | `segment_count` | De 1 a 4 |
| 8 | 24 por segmento | `segments` | Até quatro |

Segmento:

| Offset | Tamanho | Campo | Regra |
| --- | --- | --- | --- |
| 0 | 8 | `buffer` | Handle de um buffer de quem chama |
| 8 | 4 | `offset` | Início dentro do buffer |
| 12 | 4 | `length` | Pelo menos 1, sem passar do fim do buffer |
| 16 | 4 | `flags` | Bit 0: o dispositivo escreve neste segmento. Os outros bits são zero |
| 20 | 4 | reservado | Zero |

O driver nomeia memória por handle e offset. Ele nunca informa nem recebe um endereço físico.

| Condição | Erro |
| --- | --- |
| Handle que não é de um buffer do processo | `INVALID_HANDLE` |
| Buffer sem `WRITE` em segmento que o dispositivo escreve, ou sem `READ` nos demais | `ACCESS_DENIED` |
| Faixa fora do buffer, comprimento zero, flag desconhecida ou campo reservado preenchido | `INVALID_ARGUMENT` |
| Segmento de leitura depois de um segmento de escrita | `INVALID_ARGUMENT` |
| Quatro pedidos entre os em andamento e os concluídos ainda não entregues | `LIMIT_EXCEEDED` |
| Dispositivo que não está `ready` | `BAD_STATE` |

Um pedido aceito fixa cada buffer, grava os descritores na fila, que fica em memória do supervisor e não é mapeada em nenhum processo, e avisa o dispositivo. A chamada devolve um token maior que zero, que não se repete naquele dispositivo. Um pedido recusado não fixa nada.

`device_wait(dispositivo, endereço da conclusão, deadline)` exige `READ` e entrega uma conclusão de 16 bytes: o token, em 8 bytes, e quantos bytes o dispositivo escreveu, em 4. Devolve 1. Sem conclusão pronta a chamada espera até o deadline, e então devolve `TIMED_OUT`. Com o dispositivo fora de `ready` e nada a entregar, devolve `BAD_STATE`.

## O que o supervisor confere do dispositivo

A cada interrupção do transporte o supervisor lê a fila de conclusões. Ele nunca relê a tabela de descritores: a cadeia de cada pedido fica em memória privada do supervisor, e um dispositivo que reescreva a tabela não muda o que é liberado.

O dispositivo é marcado como `failed`, com a linha `device: slot=N state=failed reason=`, quando:

| Motivo | Condição |
| --- | --- |
| `used-ring-violation` | Mais conclusões do que pedidos em andamento; conclusão que não nomeia a cabeça de um pedido em andamento, o que inclui uma conclusão repetida e um índice fora da fila; bytes escritos acima do que o pedido permitia |
| `device-needs-reset` | O dispositivo levantou o bit de reset no registrador de status |

As conclusões válidas anteriores à violação continuam entregues. Os buffers dos pedidos sem conclusão continuam fixados.

## Reset e quarentena

`device_reset(dispositivo)` exige `ADMIN`. O supervisor escreve zero no status e espera, por um número limitado de leituras, o dispositivo confirmar.

- Confirmado: os buffers de todos os pedidos em andamento são soltos, as conclusões não entregues são descartadas, a fila é zerada, a geração aumenta e o dispositivo volta a `closed`, sem dono de sessão.
- Não confirmado: o dispositivo vai para `quarantined`, com a linha `device: slot=N state=quarantined reason=reset-not-acknowledged`, e a chamada devolve `IO_ERROR`. Os buffers continuam fixados e os frames deles não voltam a ser usados. `device_open` e `device_reset` passam a devolver `BAD_STATE`.

O mesmo reset acontece sozinho quando o processo que tem a sessão perde a última capability do dispositivo, por fechar ou por terminar.

## Memória fixada

Um buffer fixado pode perder o dono. Os mapeamentos somem e o buffer deixa de existir para os processos, mas os frames só voltam ao alocador quando o último pedido que os usa é concluído ou o dispositivo confirma um reset. Os contadores 17 a 19 de `processes.md` mostram pedidos em andamento, buffers fixados e dispositivos em quarentena.

## Porta serial

| Chamada | Regra |
| --- | --- |
| `serial_write(dispositivo, endereço, comprimento)` | Exige `WRITE`. Até 256 bytes; acima disso, `MESSAGE_TOO_LARGE`. Devolve quantos bytes o transmissor aceitou agora, que pode ser menos que o pedido e pode ser zero. Não espera |
| `serial_read(dispositivo, endereço, capacidade, deadline)` | Exige `READ`. Capacidade de 1 a 256. Devolve os bytes já recebidos, até a capacidade, ou espera o primeiro byte até o deadline e então devolve `TIMED_OUT` |

A recepção enche um buffer de 256 bytes dentro da interrupção. Bytes que chegam com o buffer cheio são descartados e contados.

O console de emergência não passa por estas chamadas. O supervisor continua escrevendo diagnóstico e panic direto no transmissor, por polling, com ou sem driver.

## Interrupções externas

Uma interrupção externa só é aceita enquanto um processo executa em U-mode ou enquanto o supervisor espera sem processo pronto. O tratamento atende até 16 fontes por vez, executa o tratador nativo do dispositivo, acorda o processo que esperava e devolve a fonte ao controlador. Uma fonte sem tratador é desligada no controlador. Nada disso executa Python nem aloca memória.

## Limites

| Limite | Valor |
| --- | --- |
| Dispositivos | 9: a porta serial e 8 transportes |
| Filas por dispositivo | 1, com 16 descritores |
| Pedidos em andamento mais conclusões não entregues | 4 por dispositivo |
| Segmentos por pedido | 4 |
| Espaço de configuração legível | 256 bytes |
| Transferência serial | 256 bytes por chamada |

Os valores estão em `native/include/kernel/abi/devices.h` e em `kernel_protocol.devices.layout`. A suíte `devices` cobre descoberta e posse, negociação, validação de pedidos, pedidos de bloco, entropia, porta serial e término de um driver com pedidos em andamento. `kernel-tool fault-test --suite device-reset` cobre deadline com reset, memória fixada até o reset, término com pedido em andamento e falha informada pelo dispositivo. Os testes nativos `virtio_queue_test.c`, `virtio_device_test.c` e `device_inventory_test.c` cobrem a fila, a sessão e a descoberta fora do emulador.
