# Matriz de requisitos

Cada requisito tem a fase em que é entregue pela primeira vez e a evidência que permite marcá-lo como aceito. Sem a evidência, o requisito continua aberto.

| ID | Requisito | Fase | Evidência de aceite |
| --- | --- | --- | --- |
| R-01 | A imagem inicia pelo OpenSBI fixado, sem kernel convidado e sem semihosting | 1 | Cenário `boot` de `kernel-tool test --suite bootstrap`; `kernel-tool verify-artifacts` confirma ELF estático, sem símbolo indefinido |
| R-02 | Políticas Python congeladas executam em S-mode com heap fixo | 1 | Linhas `policy:` do cenário `boot`; cenário `runtime-selftest` |
| R-03 | O coletor preserva raízes em registradores e stacks | 1 | Sondas nativas `gc-roots` do cenário `runtime-selftest` |
| R-04 | Um programa Python entra em U-mode pelo runtime de usuário e retorna por trap | 1 | Linhas `init:` do cenário `boot`, seguidas de `policy: reaped=init reason=exit value=0` |
| R-05 | Os contratos compartilhados se comportam igual em CPython e no MicroPython alvo | 1, corpus completo na 5 | Digests do corpus comparados no cenário `runtime-selftest`; diferenças aceitas em `runtime-differences.md` |
| R-06 | O DTB é validado com limites antes de qualquer uso | 1, dispositivos na 3 | `kernel-tool native-check`, com `device_tree_test.c` e `device_inventory_test.c`; cenários `device-tree-too-large` e `device-tree-without-memory` |
| R-07 | Falha de boot e trap inesperada produzem diagnóstico e status final | 1 | Cenários `insufficient-memory`, `incompatible-segment`, `user-fault` e `supervisor-trap` |
| R-08 | Um ambiente limpo reproduz a imagem a partir de versões e hashes registrados | 1, encerramento na 5 | `kernel-tool verify-artifacts --reproduce` |
| R-09 | Identidade geracional: um handle liberado nunca volta a valer | 1 no modelo, 2 no supervisor | `tests/conformance`, 10.000 transições com invariantes; `tests/native/object_table_test.c` e `capability_test.c`; suíte `capabilities` |
| R-10 | Seleção de processos por prioridade, round-robin e aging | 1 no modelo, 2 com preempção | `tests/conformance`; suíte `scheduling`, com o trace de escalonamento do boot |
| R-11 | Contabilização atômica de recursos por processo e global | 1 no modelo, 2 no supervisor | `tests/conformance`; cotas nas suítes `memory` e `capabilities`; cenários `spawn-failures` e `cycles` da suíte `processes` |
| R-12 | CI separa sucesso, falha e infraestrutura indisponível | 1 | Códigos de saída do `kernel-tool` no workflow |
| R-13 | MMU Sv39, frames, W^X e ownership | 2 | Suíte `memory`; `tests/native/address_space_test.c` e `frame_pool_test.c` |
| R-14 | Processos preemptivos com contexto completo, incluindo FP | 2 | Suíte `processes`: laço sem cooperação preemptado e encerrado, registradores inteiros e FP preservados entre processos |
| R-15 | Capabilities, IPC e cotas aplicados pelo supervisor | 2 | Suítes `capabilities` e `ipc`; `tests/native/message_test.c` |
| R-16 | Hard IRQ sem Python, timer e GC seguro | 1 e 2 | Caminho do timer descrito no ADR 0004; cenários `supervisor-trap` e `runtime-trap`; coleta intensiva preemptada na suíte `processes`; interrupções externas atendidas só por tratadores nativos, em `specs/abi/devices.md`. A medição de pausas continua aberta |
| R-17 | DMA mediado, VirtIO e reset de dispositivo | 3 para bloco, entropia e console; rede na 4 | Suíte `devices`; `kernel-tool fault-test --suite device-reset`; `tests/native/virtio_queue_test.c` e `virtio_device_test.c` |
| R-18 | VFS e volume persistente com contrato de `fsync` | 3 | Suítes `vfs` e `storage`; `kernel-tool fault-test --suite storage-crash`, com a matriz de crash, 1.000 sequências geradas e o replay do log de escritas; `kernel-tool verify-filesystem --corpus tests/faults/storage`; `tests/conformance/test_filesystem_*.py` |
| R-19 | Rede IPv4, ICMP, UDP e TCP | 4 | Interoperabilidade e fuzzing dos parsers |
| R-20 | Shell, configuração e supervisão de serviços | 2 a 4 | Jornada operacional no convidado |
| R-21 | Proveniência, licenças e distribuição | Base na 1, encerramento na 5 | Inventário de versões, hashes e SPDX |
