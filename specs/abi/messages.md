# Mensagens

[English](messages.en.md)

Toda mensagem de IPC começa por um cabeçalho de 24 bytes, seguido do payload. Os inteiros são little-endian e sem sinal. O formato é definido campo a campo: nenhum lado serializa structs C nem objetos Python.

## Cabeçalho

| Offset | Tamanho | Campo | Regra |
| --- | --- | --- | --- |
| 0 | 2 | `version` | `1` |
| 2 | 2 | `flags` | Só os bits definidos abaixo |
| 4 | 4 | `operation` | Número da operação no protocolo do serviço |
| 8 | 4 | `payload_bytes` | De 0 a 4096 |
| 12 | 4 | reservado | Zero |
| 16 | 8 | `correlation` | Escolhido por quem chama; a resposta repete o valor |

Flags:

| Bit | Nome | Significado |
| --- | --- | --- |
| 0 | `FLAG_REPLY` | A mensagem responde a uma chamada |
| 1 | `FLAG_ERROR` | A resposta carrega um código de erro; só vale junto com `FLAG_REPLY` |

## Validação na recepção

Quem recebe valida nesta ordem e para no primeiro erro:

1. Menos de 24 bytes: `INVALID_ARGUMENT`.
2. `version` diferente de 1: `UNSUPPORTED`.
3. Bit de flag desconhecido, `FLAG_ERROR` sem `FLAG_REPLY` ou campo reservado diferente de zero: `INVALID_ARGUMENT`.
4. `payload_bytes` acima de 4096: `MESSAGE_TOO_LARGE`.
5. Comprimento total diferente de `24 + payload_bytes`: `INVALID_ARGUMENT`.

Bytes a mais são rejeitados, não ignorados.

## O que o cabeçalho não diz

A identidade do remetente e as capabilities transferidas não viajam no payload. O supervisor as entrega como metadados da mensagem. Um handle escrito no payload é só um número.

`correlation` associa resposta e chamada; não prova que a operação ocorreu uma única vez. Operações com efeito definem identificador próprio ou idempotência no protocolo do serviço.

## Endpoints

`endpoint_create` devolve um endpoint que pertence ao processo que o criou. Só o dono recebe: `ipc_receive` de outro processo devolve `ACCESS_DENIED`, e o direito `RECEIVE` não é derivado nem transferido.

A fila de um endpoint guarda até 64 mensagens, entregues na ordem de chegada. Os bytes de cada mensagem pendente contam na cota de IPC de quem enviou, de 1 MiB, e no orçamento global de 16 MiB. Um envio acima da cota devolve `LIMIT_EXCEEDED` e não enfileira nada.

## Envio

`ipc_send` exige `SEND`. O supervisor copia a mensagem, aplica a validação acima e recusa uma mensagem com `FLAG_REPLY`. Uma mensagem recusada nunca entra na fila.

Com a fila cheia, quem envia bloqueia até abrir espaço ou até o deadline. O dono de uma fila cheia que envia para si mesmo recebe `WOULD_DEADLOCK` em vez de bloquear. Um endpoint sem dono devolve `PEER_CLOSED`, e quem esperava espaço é acordado com esse erro quando o dono morre.

A capability indicada para transferência segue as regras de `capabilities.md`. Se a transferência é recusada, a mensagem não é enfileirada.

## Recepção

`ipc_receive` exige `RECEIVE`. Com a fila vazia, bloqueia até chegar uma mensagem ou até o deadline. A mensagem é copiada para o buffer indicado, e o supervisor grava 32 bytes de metadados:

| Offset | Tamanho | Campo |
| --- | --- | --- |
| 0 | 8 | Identidade do remetente |
| 8 | 8 | Handle da capability transferida, ou 0 |
| 16 | 8 | Handle da capability de resposta, ou 0 quando a mensagem não veio de `ipc_call` |
| 24 | 8 | Comprimento da mensagem |

Se o buffer é menor que a mensagem, a chamada devolve `MESSAGE_TOO_LARGE`. Se o buffer ou a área de metadados não pode ser escrita, devolve `BAD_ADDRESS`. Nos dois casos a mensagem continua na fila.

## Chamada e resposta

`ipc_call` envia a mensagem e bloqueia até a resposta. O bloco de controle tem 24 bytes:

| Offset | Tamanho | Campo | Sentido |
| --- | --- | --- | --- |
| 0 | 8 | Deadline | Entrada |
| 8 | 8 | Capability a transferir, ou 0 | Entrada |
| 16 | 8 | Capability recebida com a resposta, ou 0 | Saída |

O servidor recebe, junto com a mensagem, uma capability de resposta de uso único. `ipc_reply` exige `FLAG_REPLY` e o mesmo `correlation` da chamada; outra combinação devolve `INVALID_ARGUMENT` e a chamada continua pendente. Uma resposta maior que a capacidade informada por quem chamou devolve `MESSAGE_TOO_LARGE`. A resposta é copiada direto para a memória de quem chamou, e a capability de resposta é consumida.

Uma chamada sempre termina de uma destas formas:

| Situação | Quem chama recebe | Efeito |
| --- | --- | --- |
| Resposta entregue | Comprimento da resposta | A capability de resposta é consumida |
| Deadline expira | `TIMED_OUT` | Uma chamada ainda na fila é retirada. Uma resposta posterior falha com `PEER_CLOSED` no servidor |
| `process_interrupt` sobre quem chama | `CANCELLED` | O mesmo do deadline |
| O servidor morre ou fecha o endpoint | `PEER_CLOSED` | Nada mais é entregue |
| Chamada ao próprio endpoint, ou a quem espera quem chama | `WOULD_DEADLOCK` | Nada é enfileirado |
| Cadeia de espera com mais de 8 processos | `LIMIT_EXCEEDED` | Nada é enfileirado |

Quando a resposta e o deadline disputam, os dois lados veem o mesmo desfecho: ou a resposta foi entregue e `ipc_reply` devolve 0, ou quem chama recebe `TIMED_OUT` e `ipc_reply` devolve `PEER_CLOSED`.

A implementação de referência do formato é `kernel_protocol.wire.message`. Os offsets dos metadados e do bloco de controle estão em `native/include/kernel/abi/ipc.h`. A suíte `ipc` do `kernel-tool test` cobre mensagens malformadas, entrega e transferência, limites de fila, morte do outro lado, cancelamento, deadlines, correlação, ownership do endpoint e recusa de deadlock.
