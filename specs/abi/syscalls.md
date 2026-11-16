# Syscalls

ABI versão 0. Ela existe para provar a entrada em U-mode e o retorno por trap, e muda sem aviso até a versão 1.

## Convenção

Um processo em U-mode executa `ecall` com:

| Registrador | Conteúdo |
| --- | --- |
| `a7` | Número da syscall |
| `a0` a `a5` | Argumentos |
| `a0` na volta | Resultado maior ou igual a zero, ou código de erro negado |

Todos os outros registradores voltam com o valor que tinham. A execução continua na instrução seguinte ao `ecall`.

## Tabela

| Número | Nome | Argumentos | Resultado |
| --- | --- | --- | --- |
| 0 | `process_exit` | `a0`: status | Não retorna |
| 1 | `debug_write` | `a0`: endereço do buffer, `a1`: comprimento | Bytes escritos |

Qualquer outro número devolve `-UNSUPPORTED`.

### `process_exit`

Encerra o processo. O supervisor guarda os 32 bits baixos de `a0` como status e devolve o controle à política que iniciou o processo.

### `debug_write`

Escreve bytes no console de diagnóstico do supervisor.

- Comprimento acima de 256: `-MESSAGE_TOO_LARGE`, nada é escrito.
- Faixa `[endereço, endereço + comprimento)` fora da região do processo, ou soma que estoura 64 bits: `-BAD_ADDRESS`, nada é escrito.
- Comprimento zero é válido e devolve 0.

Esta syscall existe enquanto o serviço de console não existe. Ela não recebe capability, e por isso sai da tabela quando o console passar a ser um endpoint de IPC.

## Traps que não são syscall

Qualquer outra exceção vinda de U-mode encerra o processo. O supervisor registra causa, `sepc` e `stval`, imprime `user: fault` e devolve o resultado à política. O processo não é retomado.

Os números estão em `native/include/kernel/abi/syscalls.h`.
