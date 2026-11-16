# Syscalls

ABI versão 0. Ela muda sem aviso até a versão 1.

## Convenção

Um processo em U-mode executa `ecall` com:

| Registrador | Conteúdo |
| --- | --- |
| `a7` | Número da syscall |
| `a0` a `a5` | Argumentos |
| `a0` na volta | Resultado maior ou igual a zero, ou código de erro negado |

Todos os outros registradores, inteiros e de ponto flutuante, voltam com o valor que tinham. A execução continua na instrução seguinte ao `ecall`.

O supervisor não confia em quem chama nem na biblioteca cliente:

- Um handle é procurado na tabela de capabilities do processo que chama. Handle desconhecido ou de outro tipo de objeto devolve `-INVALID_HANDLE`. Falta de direito devolve `-ACCESS_DENIED`.
- Um ponteiro só é aceito se a faixa inteira estiver mapeada no processo com a permissão que a operação precisa. Caso contrário a chamada devolve `-BAD_ADDRESS` e não tem efeito. Pedidos e mensagens são copiados para o supervisor antes de serem interpretados.
- Um deadline é um instante absoluto do relógio de `clock_now`, em nanossegundos. `0xFFFFFFFFFFFFFFFF` significa sem deadline. Uma chamada que precisaria esperar e recebe um deadline que já passou devolve `-TIMED_OUT` sem bloquear.

## Tabela

| Número | Nome | Argumentos | Resultado |
| --- | --- | --- | --- |
| 0 | `process_exit` | `a0`: status | Não retorna |
| 1 | `debug_write` | `a0`: endereço do buffer, `a1`: comprimento | Bytes escritos |
| 2 | `clock_now` | Nenhum | Nanossegundos desde o boot |
| 3 | `process_yield` | Nenhum | 0 |
| 4 | `capability_close` | `a0`: handle | 0 |
| 5 | `capability_derive` | `a0`: handle, `a1`: direitos | Handle da capability derivada |
| 6 | `capability_revoke` | `a0`: handle | Quantidade de capabilities invalidadas |
| 7 | `capability_inspect` | `a0`: handle | Tipo, direitos e profundidade |
| 8 | `endpoint_create` | Nenhum | Handle do endpoint |
| 9 | `ipc_send` | `a0`: endpoint, `a1`: endereço da mensagem, `a2`: comprimento, `a3`: capability a transferir ou 0, `a4`: deadline | 0 |
| 10 | `ipc_receive` | `a0`: endpoint, `a1`: endereço do buffer, `a2`: capacidade, `a3`: endereço dos metadados, `a4`: deadline | Comprimento da mensagem |
| 11 | `ipc_call` | `a0`: endpoint, `a1`: endereço da mensagem, `a2`: comprimento, `a3`: endereço da resposta, `a4`: capacidade da resposta, `a5`: endereço do bloco de controle | Comprimento da resposta |
| 12 | `ipc_reply` | `a0`: capability de resposta, `a1`: endereço da mensagem, `a2`: comprimento, `a3`: capability a transferir ou 0 | 0 |
| 13 | `buffer_create` | `a0`: tamanho em bytes | Handle do buffer |
| 14 | `buffer_map` | `a0`: handle, `a1`: direitos do mapeamento, `a2`: endereço da descrição | 0 |
| 15 | `buffer_unmap` | `a0`: endereço do mapeamento | 0 |
| 16 | `process_spawn` | `a0`: capability do sistema, `a1`: endereço do pedido | Handle do processo |
| 17 | `process_wait` | `a0`: handle do processo, `a1`: deadline | Status de término |
| 18 | `process_kill` | `a0`: handle do processo | 0 |
| 19 | `process_interrupt` | `a0`: handle do processo | 0 |
| 20 | `system_counters` | `a0`: capability do sistema, `a1`: endereço do buffer, `a2`: tamanho do buffer | Quantidade de contadores |

Qualquer outro número devolve `-UNSUPPORTED`.

As chamadas 4 a 7 estão descritas em `capabilities.md`, as chamadas 8 a 12 em `messages.md`, as chamadas 13 a 15 em `buffers.md` e as chamadas 16 a 20 em `processes.md`.

## Processo e tempo

### `process_exit`

Encerra o processo. O supervisor guarda os 32 bits baixos de `a0` como status, libera o que o processo ocupava e entrega o status a quem o espera.

### `debug_write`

Escreve bytes no console de diagnóstico do supervisor.

- Comprimento acima de 256: `-MESSAGE_TOO_LARGE`, nada é lido nem escrito.
- Faixa `[endereço, endereço + comprimento)` que o processo não pode ler, ou soma que estoura 64 bits: `-BAD_ADDRESS`, nada é escrito.
- Comprimento zero é válido e devolve 0.

Esta syscall existe enquanto o serviço de console não existe. Ela não recebe capability, e por isso sai da tabela quando o console passar a ser um endpoint de IPC.

### `clock_now`

Devolve o tempo monotônico desde o boot, em nanossegundos. O valor vem do contador `time` e da frequência que o DTB informa, e nunca diminui.

### `process_yield`

Devolve o processador. O processo continua pronto e volta para o fim da fila da sua prioridade.

## Traps que não são syscall

Qualquer outra exceção vinda de U-mode encerra o processo. O supervisor imprime `user: fault` com a causa, `scause`, `sepc`, `stval` e o índice do processo, e libera o que ele ocupava. Quem espera o processo recebe o motivo `fault` e o valor de `scause`. O processo não é retomado.

A interrupção do timer não é erro. Ela suspende o processo no fim do quantum, e ele volta à fila com o contexto intacto.

Os números estão em `native/include/kernel/abi/syscalls.h` e em `kernel_protocol.syscalls.numbers`.
