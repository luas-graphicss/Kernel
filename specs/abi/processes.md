# Processos

Um processo é um espaço de endereçamento, uma tabela de capabilities e um runtime MicroPython privado. O modelo está no ADR 0004.

## Criação

`process_spawn` recebe a capability do sistema, com o direito `ADMIN`, e o endereço de um pedido de 296 bytes. Os inteiros são little-endian e sem sinal.

| Offset | Tamanho | Campo | Regra |
| --- | --- | --- | --- |
| 0 | 4 | `version` | `1`; outro valor devolve `UNSUPPORTED` |
| 4 | 4 | `priority` | De 0, a mais urgente, a 3 |
| 8 | 8 | `heap_bytes` | Múltiplo de 4096. Zero usa o heap declarado na imagem |
| 16 | 8 | `memory_bytes` | Múltiplo de 4096. Cota de memória além do que o runtime ocupa; dela saem os buffers que o processo cria |
| 24 | 4 | `name_length` | De 1 a 64 |
| 28 | 4 | `argument_length` | De 0 a 64 |
| 32 | 4 | `grant_count` | De 0 a 8 |
| 36 | 4 | reservado | Zero |
| 40 | 128 | `grants` | Oito pares de handle e direitos, 8 bytes por campo. Os pares não usados ficam zerados |
| 168 | 64 | `name` | Caminho do módulo do programa, completado com zeros |
| 232 | 64 | `argument` | Bytes entregues ao programa, completados com zeros |

O nome é um caminho de módulo congelado na imagem: partes de letras minúsculas, dígitos e `_`, separadas por `.`. Um campo fora dessas regras devolve `INVALID_ARGUMENT`.

Cada concessão segue as regras de transferência de `capabilities.md`: handle desconhecido devolve `INVALID_HANDLE`; direito que a capability não tem, falta de `DELEGATE` ou pedido de `RECEIVE` devolvem `ACCESS_DENIED`.

Depois da validação nativa, a política Python decide a admissão:

| Condição | Erro |
| --- | --- |
| Prioridade mais urgente que a de quem cria | `ACCESS_DENIED` |
| `heap_bytes` acima do limite por processo do perfil | `LIMIT_EXCEEDED` |
| 16 processos vivos | `LIMIT_EXCEEDED` |
| Orçamento de memória dos processos esgotado | `LIMIT_EXCEEDED` |
| Falta de frames acima da reserva do supervisor | `OUT_OF_MEMORY` |

A criação é atômica. O processo só aparece depois que espaço de endereçamento, runtime, concessões e o handle de quem criou existem; uma falha no meio devolve tudo. O cenário `spawn-failures` confere isso fazendo falhar, uma por vez, cada alocação de uma criação.

Quem cria recebe um handle de processo com `READ`, `ADMIN` e `DELEGATE`.

## Início

O programa nasce com um bloco de 256 bytes preparado pelo supervisor: limites do heap e da stack, a identidade do processo, os handles concedidos na ordem do pedido, o nome do módulo e o argumento. O runtime lê o bloco, importa o módulo e executa `main()`. Valor verdadeiro termina o processo com status 0; valor falso ou exceção, com status 1.

Os offsets do pedido e do bloco estão em `native/include/kernel/abi/process.h`. O codificador de referência do pedido é `kernel_protocol.wire.spawn`.

## Escalonamento

Há quatro prioridades. O supervisor executa o processo pronto mais urgente por um quantum de 10 ms, em round-robin dentro da prioridade. Um processo pronto que espera 8 seleções sobe uma prioridade até executar, e então volta à sua.

Quem bloqueia em `ipc_call`, ou em `ipc_send` com a fila cheia, empresta a prioridade ao dono do endpoint enquanto espera, por até 8 processos encadeados. A doação termina quando a espera termina e nunca passa da prioridade de quem doa.

A biblioteca cliente cria processos com prioridade 2 quando o chamador não escolhe outra. O `init` roda com prioridade 1.

## Espera e término

`process_wait` exige `READ` e devolve o status de término: o motivo nos 32 bits altos e o valor nos 32 bits baixos.

| Motivo | Código | Valor |
| --- | --- | --- |
| `exit` | 1 | Status passado a `process_exit` |
| `fault` | 2 | `scause` da exceção |
| `killed` | 3 | Zero |

Se o processo ainda vive, quem chama bloqueia até o término ou o deadline. Esperar um processo que, direta ou indiretamente, espera quem chama devolve `WOULD_DEADLOCK`. Uma cadeia de espera com mais de 8 processos devolve `LIMIT_EXCEEDED`.

`process_kill` exige `ADMIN` e encerra o processo; sobre um processo já encerrado devolve `BAD_STATE`. `process_interrupt` exige `ADMIN` e só vale para um processo bloqueado: a chamada em que ele esperava devolve `CANCELLED`. Sobre um processo que não está bloqueado, devolve `BAD_STATE`.

Ao terminar, por qualquer motivo, o processo perde mapeamentos, capabilities, mensagens pendentes e memória. Um frame privado é zerado antes de servir a outro processo. O status continua disponível em `process_wait` enquanto houver handle para o processo.

## Contadores

`system_counters` exige `READ` na capability do sistema e grava 16 inteiros de 64 bits, little-endian. Um buffer com menos de 128 bytes devolve `INVALID_ARGUMENT`.

| Índice | Contador |
| --- | --- |
| 0 | Frames utilizáveis |
| 1 | Frames livres |
| 2 | Frames da reserva do supervisor |
| 3 | Processos |
| 4 | Objetos |
| 5 | Capabilities |
| 6 | Endpoints |
| 7 | Mensagens pendentes |
| 8 | Bytes de IPC pendentes |
| 9 | Buffers |
| 10 | Eventos descartados |
| 11 | Falhas de processos |
| 12 | Trocas de contexto |
| 13 | Preempções |
| 14 | Alocações recusadas |
| 15 | Interrupções do timer |

As suítes comparam os contadores de recursos antes e depois de cada caso. A política faz o mesmo entre o início e o fim do `init`, e imprime `policy: resources=released` ou a lista do que mudou.
