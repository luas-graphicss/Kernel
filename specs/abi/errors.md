# Códigos de erro

Um único conjunto de códigos vale para syscalls, mensagens e modelos Python. Os valores são inteiros pequenos e estáveis dentro de uma versão da ABI.

| Código | Nome | Quando ocorre |
| --- | --- | --- |
| 0 | `OK` | Operação concluída |
| 1 | `INVALID_ARGUMENT` | Argumento fora do formato ou da faixa: mensagem truncada, campo reservado diferente de zero, quantidade negativa |
| 2 | `INVALID_HANDLE` | Handle com índice inexistente, geração antiga, slot livre ou bits reservados preenchidos |
| 3 | `BAD_STATE` | Transição de ciclo de vida que o objeto não permite no estado atual |
| 4 | `LIMIT_EXCEEDED` | Cota do processo, orçamento global ou capacidade de tabela esgotados |
| 5 | `BAD_ADDRESS` | Faixa de memória de usuário fora da região do processo |
| 6 | `MESSAGE_TOO_LARGE` | Payload acima do limite da operação |
| 7 | `UNSUPPORTED` | Número de syscall, operação ou versão desconhecidos |

Uma syscall devolve o resultado em `a0`: valor maior ou igual a zero em caso de sucesso, ou o código negado em caso de erro. `debug_write` com ponteiro inválido devolve `-5`.

Em Python os mesmos valores estão em `kernel_protocol.errors.codes`, e as funções dos modelos levantam `KernelError` com o código. Em C estão em `native/include/kernel/abi/errors.h`. O teste `tests/conformance/test_abi_constants.py` compara os dois.

Uma operação que falha não deixa efeito parcial. Quem recebe `LIMIT_EXCEEDED` encontra as contas como estavam antes da chamada.
