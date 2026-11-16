# ADR 0003: Runtime Python do convidado

Estado: aceita.

## Contexto

O convidado não tem Linux, POSIX nem CPython. O interpretador precisa rodar freestanding, com heap fixo, módulos escolhidos no build e um coletor que conheça as raízes vivas em registradores e stacks.

## Decisão

O runtime é o MicroPython 1.29.0, fixado por hash em `toolchain.lock.toml`, com um port próprio em `ports/micropython/`. O port upstream `qemu` não é usado: ele roda em M-mode com semihosting e não atende ao modelo de privilégios do projeto.

Há dois perfis do mesmo source lock, sem fork do interpretador:

- `supervisor`: roda em S-mode dentro da imagem do kernel, com heap fixo de 8 MiB.
- `user`: roda em U-mode como imagem separada, com heap e stack próprios dentro da região do processo.

Nos dois perfis:

- Só módulos congelados em bytecode no build. O compilador e o REPL ficam desligados, e `eval`, `exec`, `compile`, `open` e `input` não existem.
- `MICROPY_ENABLE_EXTERNAL_IMPORT` fica ligado porque é esse caminho de importação que resolve módulos e pacotes congelados. Nada de fora da imagem é carregado: `mp_import_stat` responde que nenhum caminho existe, `MICROPY_PERSISTENT_CODE_LOAD` fica desligado e `sys.path` contém só `.frozen`.
- A configuração parte de `MICROPY_CONFIG_ROM_LEVEL_MINIMUM` e habilita recurso por recurso em `ports/micropython/shared/mpconfigshared.h`.
- Inteiros longos usam MPZ. Ponto flutuante fica desligado.
- NLR usa a implementação nativa `py/nlrrv64.c`.
- A coleta usa `gc_helper_collect_regs_and_stack`, de `shared/runtime/gchelper_native.c`: lê `s0` a `s11` com `shared/runtime/gchelper_rv64i.s` e varre a stack até o topo registrado. Finalizadores ficam desligados.
- A checagem de stack do interpretador fica ligada, com margem de 2048 bytes. Recursão sem fim termina em `RuntimeError` e a stack continua utilizável.
- Exceção não tratada no supervisor imprime o traceback e encerra o boot com falha.

Nenhuma libc hospedada entra no link. As funções de memória e string vêm de `shared/libc/string0.c` do próprio MicroPython, e `libgcc` é a única biblioteca do compilador. `kernel-tool verify-artifacts` falha se o mapa de linkagem mostrar outra origem.

## Consequências

O convidado não tem `typing`, `dataclasses`, `enum`, `asyncio` nem `struct`. O código de `src/` usa anotações que o compilador do MicroPython descarta e nenhum import de CPython. As diferenças aceitas estão em `docs/architecture/runtime-differences.md`.

Aprovação do `mypy` não prova que um módulo roda no convidado. A prova é o bytecode gerado pelo `mpy-cross` fixado e a execução no QEMU.

Um runtime privado por processo cabe no perfil: a suíte `processes` mantém 16 processos vivos, 15 deles com o heap máximo de 4 MiB, e a reserva de frames do supervisor continua livre.

## Hipóteses a confirmar

- O perfil `user` carrega programas que não estão congelados. Falta decidir entre compilar no processo ou carregar `.mpy` validado.
- Ponto flutuante entra no perfil `user` junto com a ABI `lp64d`. A troca de contexto já salva o estado FP de cada processo.
- As pausas do GC supervisor cabem no orçamento de trabalho entre pontos seguros.
