# ADR 0002: Fronteira entre Python e código nativo

[English](0002-python-native-boundary.en.md)

Estado: aceita.

## Contexto

O projeto é Python-first, mas um kernel real precisa de mecanismos que continuam corretos quando um processo Python trava, esgota memória ou envia dados malformados. Sem uma regra escrita, a camada nativa cresce até virar uma segunda implementação das políticas.

## Decisão

Python decide. Código nativo executa e valida.

Ficam em C17 freestanding e Assembly RISC-V: boot, entrada e saída de traps, troca de contexto, MMU, validação de acesso à memória de usuário, primitivas de IPC, enforcement de capabilities e transporte de dispositivos. Assembly cobre só o que exige instrução ou convenção de máquina: ponto de entrada, vetor de traps, entrada em U-mode e leitura de registradores para o GC.

Ficam em Python: escalonamento, admissão de processos, cotas, supervisão, VFS, filesystem, protocolos de rede, comportamento dos drivers e aplicações.

Uma inclusão nativa nova precisa de pelo menos um destes motivos: depende de privilégio, acessa memória física ou registradores, protege a segurança de memória, faz parte da ABI ou integra o interpretador. Conveniência e desempenho não medido não bastam.

O supervisor nativo não depende de Python para tratar uma trap, liberar recurso ou encerrar processo. Python não executa em hard IRQ.

A superfície exposta ao Python do supervisor é o módulo `_supervisor`. Os argumentos são handles de processo, tamanhos, contagens e códigos de erro, e o lado nativo confere cada um antes de usar. Cada binding novo entra nesta tabela com o motivo.

| Binding | Devolve | Motivo |
| --- | --- | --- |
| `machine()` | Hart de boot, base e tamanho da RAM | Fatos do DTB, que só o código nativo lê e valida |
| `limits()` | Limites do perfil compilado e tamanho do heap do supervisor | O perfil faz parte da ABI e o heap vem do layout de linkagem |
| `user_region()` | Base e tamanho da região virtual de usuário | Layout de linkagem da imagem de usuário |
| `arguments()` | Texto de `bootargs` do DTB | Fato do DTB. A política lê dali o programa inicial, em `init=`, e o pedido de trace, em `trace=schedule` |
| `memory()` | Tamanho do frame e quantidade de frames utilizáveis, livres e da reserva do supervisor | Estado do alocador físico, de onde sai o orçamento de memória dos processos |
| `counters()` | Os contadores de recursos e de atividade de `specs/abi/processes.md` | Estado dos mecanismos nativos. A política compara os recursos antes e depois do `init` |
| `prepare_program()` | `ok`, `absent` ou o motivo da rejeição da imagem de usuário | Validação de bytes não confiáveis antes de a política admitir um processo |
| `footprint(heap_bytes)` | Frames privados de um processo com esse heap, ou zero se ele não couber na região | Depende do layout da imagem e das page tables |
| `spawn(program, heap_bytes, memory_frames, capabilities, ipc_pending_bytes)` | Handle do primeiro processo, ou um código de erro negado | Depende de privilégio: cria o espaço de endereçamento, o runtime e a capability do sistema |
| `pending_spawn()` | Pedido de criação em espera, já validado: quem pediu, programa, prioridade, heap, memória e quantidade de concessões | A política decide a admissão sem ler memória de usuário |
| `admit_spawn(memory_frames, capabilities, ipc_pending_bytes)` | Handle do processo criado, ou um código de erro negado | Conclui a criação em espera com as cotas que a política escolheu |
| `reject_spawn(error)` | Nada | Entrega a quem pediu o erro que a política escolheu |
| `run(handle, quantum_nanoseconds)` | Motivo da volta, `preempted`, `yielded`, `blocked`, `exited`, `spawn` ou `stale`, e dois valores que dependem dele | Depende de privilégio: troca o espaço de endereçamento, arma o timer, entra em U-mode e atende as syscalls |
| `next_event()` | Próximo evento da fila limitada, com o tipo e o processo, ou `None` | Processos ficam prontos ou terminam dentro dos mecanismos nativos |
| `events_overflowed()` | Se a fila descartou algum evento desde a última consulta | A política refaz o próprio estado pela tabela nativa quando perde eventos |
| `idle()` | Se havia alguma espera com deadline para aguardar | Espera o timer com `wfi` quando nenhum processo está pronto |
| `kill(handle)` | Zero ou um código de erro negado | Encerra o processo e libera o que ele ocupava |
| `release(handle)` | Zero ou um código de erro negado | Devolve o slot do processo depois que a política contabilizou o término |
| `process_state(handle)` | Estado do processo na tabela nativa | A política confere uma decisão antiga contra o estado real |

O runtime de usuário tem uma superfície nativa própria, o módulo `_process`. Ele monta os argumentos e executa `ecall`. Não é uma fronteira de segurança: o supervisor valida cada chamada como descreve `specs/abi/syscalls.md`.

## Consequências

Toda chamada entre os dois lados tem custo e precisa de validação nos dois sentidos. Os bindings devolvem inteiros, booleanos, textos, tuplas e `None`. Endereços físicos aparecem só como fatos para orçamento e diagnóstico: nenhum binding aceita endereço como argumento.

O interpretador supervisor e as políticas congeladas pertencem à TCB. Um erro de política ali tem o mesmo peso de um erro em C.

## Hipóteses a confirmar

- O custo de IPC com políticas em Python cabe no quantum de 10 ms. Medir antes de mover qualquer política para C.
- Handles opacos geracionais bastam para o Python referenciar objetos nativos sem tabela paralela de ownership.
