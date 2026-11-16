# Mensagens

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

A implementação de referência é `kernel_protocol.wire.message`.
