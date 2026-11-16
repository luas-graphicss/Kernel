# Códigos de erro

Um único conjunto de códigos vale para syscalls, mensagens e modelos Python. Os valores são inteiros pequenos e estáveis dentro de uma versão da ABI.

| Código | Nome | Quando ocorre |
| --- | --- | --- |
| 0 | `OK` | Operação concluída |
| 1 | `INVALID_ARGUMENT` | Argumento fora do formato ou da faixa: mensagem truncada, campo reservado diferente de zero, quantidade negativa |
| 2 | `INVALID_HANDLE` | Handle com índice inexistente, geração antiga, slot livre, bits reservados preenchidos ou objeto de outro tipo |
| 3 | `BAD_STATE` | Transição de ciclo de vida que o objeto não permite no estado atual |
| 4 | `LIMIT_EXCEEDED` | Cota do processo, orçamento global, capacidade de tabela, profundidade de derivação ou cadeia de espera esgotados |
| 5 | `BAD_ADDRESS` | Faixa de memória que o processo não tem mapeada com a permissão que a operação precisa |
| 6 | `MESSAGE_TOO_LARGE` | Payload acima do limite da operação ou do buffer de quem recebe |
| 7 | `UNSUPPORTED` | Número de syscall, operação ou versão desconhecidos |
| 8 | `ACCESS_DENIED` | A capability existe, mas não tem o direito que a operação exige |
| 9 | `TIMED_OUT` | O deadline passou antes de a operação terminar |
| 10 | `CANCELLED` | A espera foi interrompida por `process_interrupt` |
| 11 | `PEER_CLOSED` | O outro lado morreu, fechou o endpoint ou não espera mais a resposta |
| 12 | `OUT_OF_MEMORY` | Faltou memória física acima da reserva do supervisor |
| 13 | `WOULD_DEADLOCK` | A espera fecharia um ciclo entre processos |

Uma syscall devolve o resultado em `a0`: valor maior ou igual a zero em caso de sucesso, ou o código negado em caso de erro. `debug_write` com ponteiro inválido devolve `-5`.

Em Python os mesmos valores estão em `kernel_protocol.errors.codes`. As funções dos modelos e da biblioteca cliente levantam `KernelError` com o código. Em C estão em `native/include/kernel/abi/errors.h`. O teste `tests/conformance/test_abi_constants.py` compara os dois lados, e faz o mesmo com números de syscall, direitos, limites de processo e formatos.

Uma operação que falha não deixa efeito parcial. Quem recebe `LIMIT_EXCEEDED` encontra as contas como estavam antes da chamada.
