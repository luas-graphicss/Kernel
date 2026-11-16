# Perfil de recursos

Um perfil descreve a máquina, o layout de memória e os limites com que uma imagem é construída e testada. O arquivo é TOML e fica em `config/profiles/`. O único perfil é `qemu-riscv64`.

`kernel-tool` lê o perfil, passa layout e limites ao build nativo e monta a linha de comando do QEMU. O supervisor entrega os limites compilados à política Python, que os confronta com o que o DTB descreve.

## `[machine]`

| Campo | Significado |
| --- | --- |
| `emulator` | Nome do binário do emulador no pacote fixado |
| `machine` | Valor de `-machine` |
| `cpu` | Valor de `-cpu` |
| `harts` | Valor de `-smp` |
| `memory_mib` | RAM da máquina, em MiB |
| `accelerator` | Valor de `-accel` |
| `globals` | Lista de valores de `-global` |
| `firmware` | Nome do componente de firmware em `toolchain.lock.toml` |

## `[layout]`

Endereços e tamanhos em bytes.

| Campo | Significado |
| --- | --- |
| `kernel_base` | Endereço de linkagem do kernel |
| `user_region_base` | Base da região do processo de usuário |
| `user_region_bytes` | Tamanho dessa região |
| `supervisor_stack_bytes` | Stack do supervisor |
| `emergency_stack_bytes` | Stack usada só pelo relatório de trap fatal |
| `user_heap_bytes` | Heap do runtime da imagem de usuário |
| `user_stack_bytes` | Stack da imagem de usuário |

## `[limits]`

Valores a provar, não resultados medidos. Mudar um deles exige repetir os testes afetados.

| Campo | Valor | No limite |
| --- | --- | --- |
| `memory_bytes` | 256 MiB | Boot recusado se o DTB descrever menos |
| `processes` | 16 | Erro de capacidade, sem criação parcial |
| `supervisor_heap_bytes` | 8 MiB | Tratamento controlado; corrupção exige panic |
| `process_heap_bytes` | 4 MiB | Admissão recusada; sem crescimento automático |
| `capabilities_per_process` | 128 | Falha atômica na concessão |
| `delegation_depth` | 16 | Nova derivação rejeitada |
| `ipc_inline_payload_bytes` | 4 KiB | Usar buffer concedido ou rejeitar |
| `endpoint_messages` | 64 | Backpressure e deadline |
| `ipc_pending_bytes_per_process` | 1 MiB | Aplicado junto com o limite global |
| `ipc_pending_bytes_global` | 16 MiB | Aplicado junto com o limite por processo |

As cotas se acumulam sobre todos os recursos do mesmo processo. Dividir um pedido em várias mensagens não contorna o limite.

## `[deadlines]`

| Campo | Significado |
| --- | --- |
| `boot_seconds` | Tempo máximo de um cenário de boot no host antes de ser contado como falha |
