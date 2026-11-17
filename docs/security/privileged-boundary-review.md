# Revisão da fronteira privilegiada

[English](privileged-boundary-review.en.md)

Leitura do código que roda em S-mode e decide o que um processo pode fazer. A revisão foi feita em 17 de novembro de 2026, sobre a árvore do release candidato 1.0.0rc1, por quem escreveu as ferramentas de homologação. Não é uma auditoria independente.

## Método

Cada arquivo abaixo foi lido inteiro ou no trecho indicado, procurando: valor vindo de um processo usado como índice, tamanho ou endereço sem conferência; soma ou multiplicação de tamanhos que possa estourar; uso de memória de usuário sem validação; estado do kernel alcançável por um handle antigo; memória devolvida ao alocador enquanto um dispositivo ainda a enxerga.

A leitura se apoia em três verificações automáticas, que cobrem o que uma leitura não cobre:

- os testes nativos hospedados de `tests/native/`, sob AddressSanitizer e UndefinedBehaviorSanitizer;
- os alvos nativos de fuzzing de `tests/fuzz/native/`, com os mesmos sanitizers, para o DTB, a imagem de usuário, o cabeçalho de mensagem e o pedido de criação de processo;
- as suítes adversariais no QEMU: `memory`, `capabilities`, `ipc`, `devices` e `device-reset`.

## O que foi lido

| Área | Arquivos | O que foi conferido |
| --- | --- | --- |
| Traps | `native/arch/riscv64/traps/trap_vector.S`, `trap.c`, `native/arch/riscv64/context/user_context.S` | Uma trap vinda do supervisor usa a stack de emergência e termina em pânico com diagnóstico, sem depender do `sp` que falhou. Uma trap vinda de usuário salva os registradores inteiros, os de ponto flutuante e o estado da trap no frame do processo, que fica em memória do kernel. O `sstatus` com que um processo entra em U-mode é montado sem `SPP`, `SUM` e `MXR` |
| Despacho de syscalls | `native/supervisor/processes/syscall.c`, `native/include/kernel/abi/syscalls.h` | Número fora da tabela responde `UNSUPPORTED`. Os 31 números têm tratador, sem lacuna na tabela. `debug_write` limita o tamanho antes de copiar para a stack |
| Memória de usuário | `native/supervisor/memory/address_space.c`, `range.c` | A faixa é conferida contra a região do processo sem somar endereço e tamanho. A cópia anda página a página pela tabela do processo e exige as permissões da operação. O supervisor não desreferencia ponteiro de usuário |
| Buffers e mapeamentos | `native/supervisor/memory/buffer.c`, `native/supervisor/processes/syscall_memory.c` | Tamanho limitado e contado na cota. Memória zerada na alocação. Mapeamento só na janela do processo e só com a capability e os direitos pedidos |
| DMA | `native/supervisor/processes/syscall_device.c`, `native/supervisor/devices/virtio/device.c`, trechos de `queue.c` | Um segmento nomeia um buffer por capability, com direito de leitura ou de escrita conforme o sentido, e um deslocamento conferido contra o tamanho do buffer. O endereço físico é calculado pelo supervisor. O buffer fica fixado até a conclusão ou o reset confirmado, e os frames de um buffer destruído só voltam ao alocador sem fixação. O índice e o tamanho que o dispositivo devolve são conferidos; um valor inválido marca o dispositivo como falho |
| IPC | `native/supervisor/processes/syscall_ipc.c`, `native/supervisor/ipc/message.c` | Tamanho da mensagem limitado antes da cópia. Cabeçalho validado campo a campo. O destino de uma resposta é conferido de novo na entrega, porque o mapeamento pode ter mudado enquanto o processo esperava |
| Capabilities e handles | `capability_require` em `native/supervisor/objects/kernel_objects.c`, trechos de `slot_table.c` | Toda operação resolve o handle no espaço do chamador, confere o tipo do objeto e exige os direitos. O handle carrega a geração do slot, e bits reservados são recusados |
| Raízes do coletor | `ports/micropython/shared/memory/collector.c`, `ports/micropython/supervisor/platform.c`, `ports/micropython/supervisor/bindings/` | A coleta varre registradores e stack. Os bindings não guardam objeto Python em variável estática de C |
| Bindings do supervisor | `ports/micropython/supervisor/bindings/processes.c`, `machine.c`, `module.c` | Só a política congelada os chama. O nome de programa é validado com o tamanho em `spawn_initial`, e os handles passam pela busca com geração |

## Resultado

Nenhum defeito de isolamento, de aritmética de tamanhos ou de ownership foi encontrado nos trechos lidos.

Observações que não são defeitos e ficam registradas:

1. Várias syscalls conferem que o destino é gravável, executam a operação e só então gravam o resultado, sem conferir o retorno da gravação. Isso é correto porque o kernel não é preemptível e nada desfaz um mapeamento entre a conferência e a gravação. Um kernel com mais de um hart ou com preempção em S-mode precisa rever esses pontos.
2. `buffer_unpin` decrementa o contador sem conferir se ele já é zero. Os chamadores são balanceados, e os testes hospedados passam sob sanitizers. Uma conferência ali transformaria um erro futuro em pânico em vez de estouro silencioso.
3. O console não serializa linhas de processos diferentes. Não afeta isolamento; está descrito em `docs/operations/diagnostics.md`.

## O que esta revisão não cobre

- O MicroPython, o OpenSBI e o QEMU, que são código de terceiros. Os avisos conhecidos de cada versão fixada estão em `config/release/advisories.toml`.
- Os serviços e drivers em Python, que rodam em U-mode e estão sujeitos às mesmas barreiras de qualquer processo.
- O alocador de frames, as tabelas de páginas, o ciclo de vida de processos e o registro de dispositivos foram lidos só nos pontos chamados pelos caminhos acima. Eles têm testes hospedados e suítes no QEMU, e não tiveram leitura linha a linha.
- Canais laterais, falhas de hardware e mais de um hart, que estão fora do modelo de ameaça.
