# Base computacional confiável

Lista o que precisa estar correto para as garantias do kernel valerem. Um defeito em qualquer item abaixo pode violar isolamento ou integridade.

## Em execução

| Componente | Origem | Papel |
| --- | --- | --- |
| OpenSBI 1.5.1 `fw_dynamic` | Binário do pacote xPack QEMU `9.2.4-1`, fixado por hash | M-mode, PMP, interface SBI, redirecionamento de traps não delegadas |
| Supervisor nativo | `native/` | Boot, traps, validação do DTB e da imagem de usuário, alocador de frames e page tables Sv39, troca de contexto, timer, tabela de objetos e capabilities, IPC, buffers, ciclo de vida dos processos, validação das syscalls e console de emergência |
| Port do runtime, perfil supervisor | `ports/micropython/shared/` e `ports/micropython/supervisor/` | Ciclo de vida do interpretador, raízes do GC, bindings `_supervisor`, tratamento de exceção fatal |
| Núcleo do MicroPython 1.29.0 | `py/`, `shared/runtime/gchelper_native.c`, `shared/runtime/gchelper_rv64i.s`, `shared/libc/string0.c` do tarball fixado | VM, coletor, objetos, funções de memória e string |
| `libgcc` do GCC 15.2.0 | Multilib `rv64imac_zaamo_zalrsc/lp64` do compilador fixado | Rotinas auxiliares que o compilador emite; os membros ligados aparecem no relatório de `kernel-tool verify-artifacts` |
| Políticas congeladas | `src/kernel_core/` e `src/kernel_protocol/` | Validação do perfil de recursos, admissão e cotas dos processos, escalonamento e supervisão |

O perfil `user` do runtime, a biblioteca `kernel_client` e os serviços de `kernel_services` não pertencem à TCB do sistema. Eles rodam em U-mode, e o supervisor valida cada chamada que fazem. Serviços têm autoridade limitada, mas são confiáveis para os recursos que administram. O `init` nasce com a capability do sistema e responde pela criação dos demais processos.

## No build

GCC, binutils, `mpy-cross`, as ferramentas do MicroPython e o `kernel-tool` produzem a imagem. Qualquer um deles, adulterado, compromete o resultado. A mitigação é fixar versão e hash em `toolchain.lock.toml` e em `uv.lock`, e verificar o hash antes de usar.

QEMU faz o papel do hardware. Ele não é parte da TCB do convidado, mas todo resultado de teste depende dele.

## Como a TCB cresce

Um componente novo só entra aqui se o ADR 0002 justificar a inclusão nativa ou se for uma política que o supervisor precisa executar. Módulos opcionais do MicroPython ficam desligados até um requisito pedir. Cada binding novo do `_supervisor` é registrado no ADR 0002.
