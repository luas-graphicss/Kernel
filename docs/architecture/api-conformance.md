# Matriz de conformidade das APIs públicas

[English](api-conformance.en.md)

Cada linha é uma operação que o sistema oferece a um processo, a um programa ou a quem opera o console, com o estado dela e o teste que a exercita no convidado. O que não tem linha aqui não é suportado. A última seção lista o que mais se costuma esperar de um sistema e não existe neste.

A matriz de requisitos, em `requirements.md`, diz o que o projeto precisa entregar. Esta página diz o que cada interface faz hoje e onde isso é conferido.

## Como ler

| Estado | Significado |
| --- | --- |
| Suportada | Atende qualquer processo que apresente a capability que a operação exige |
| Restrita | Atende só o processo que supervisiona o serviço: o `init` ou o gerente do sistema. De outro processo devolve `ACCESS_DENIED` |

Uma evidência escrita como `suíte/cenário/caso` aponta um caso de um programa de teste que roda no convidado. O comando é `kernel-tool test --suite <suíte>`, ou `kernel-tool fault-test --suite <suíte>` para `device-reset`, `storage-crash` e `network-faults`. O resultado fica em `build/qemu-riscv64/reports/<suíte>.json`, na linha `test: suite=... case=<caso> checks=N result=ok` da transcrição do cenário. Sem o caso, a evidência é o cenário inteiro, conferido pelas linhas que ele precisa produzir. Um caminho de arquivo aponta um teste que roda no host com `pytest`.

Uma linha só vale com a suíte aprovada. O workflow de CI roda todas as suítes em cada pull request, e `tests/host/test_ci_workflow.py` reprova quando uma suíte registrada no `kernel-tool` fica sem etapa no workflow. O registro da execução de aceite, com as contagens de cada caso, está em `docs/acceptance/network-and-operational-environment.md`.

`tests/conformance/test_api_conformance.py` compara esta página com o código. Toda syscall, toda operação de serviço e todo comando do shell precisa de exatamente uma linha. Toda linha precisa de evidência, e toda evidência precisa nomear um cenário, um caso ou um arquivo que existe. Para um comando do shell, um dos cenários citados precisa digitar o comando.

## Syscalls: `kernel_protocol.syscalls.numbers`

ABI versão 0, descrita em `specs/abi/syscalls.md` e nas páginas que ela cita. Um número fora da tabela devolve `UNSUPPORTED`.

| Syscall | Estado | Evidência |
| --- | --- | --- |
| `process_exit` | Suportada | `processes/cases/exit-status-and-finalization` |
| `debug_write` | Suportada | `memory/cases/system-call-pointers` |
| `clock_now` | Suportada | `scheduling/cases/clock-limits` |
| `process_yield` | Suportada | `scheduling/cases/yield-to-an-equal` |
| `capability_close` | Suportada | `capabilities/cases/stale-and-forged-handles` |
| `capability_derive` | Suportada | `capabilities/cases/attenuated-delegation` |
| `capability_revoke` | Suportada | `capabilities/cases/revocation-with-descendants` |
| `capability_inspect` | Suportada | `capabilities/cases/attenuated-delegation` |
| `endpoint_create` | Suportada | `ipc/cases/endpoint-ownership` |
| `ipc_send` | Suportada | `ipc/cases/delivery-and-transfer`, `ipc/cases/queue-limits` |
| `ipc_receive` | Suportada | `ipc/cases/delivery-and-transfer`, `ipc/cases/deadlines` |
| `ipc_call` | Suportada | `ipc/cases/reply-correlation`, `ipc/cases/deadlines` |
| `ipc_reply` | Suportada | `ipc/cases/reply-correlation` |
| `buffer_create` | Suportada | `memory/cases/shared-buffers` |
| `buffer_map` | Suportada | `memory/cases/shared-buffers`, `capabilities/cases/mappings-follow-capabilities` |
| `buffer_unmap` | Suportada | `memory/cases/shared-buffers` |
| `process_spawn` | Suportada | `processes/cases/spawn-authority-and-validation` |
| `process_wait` | Suportada | `processes/cases/exit-status-and-finalization` |
| `process_kill` | Suportada | `processes/cases/exit-status-and-finalization`, `processes/cases/teardown-releases-resources` |
| `process_interrupt` | Suportada | `processes/cases/exit-status-and-finalization`, `ipc/cases/cancellation` |
| `system_counters` | Suportada | `memory/cases/system-call-pointers`, `processes/cases/teardown-releases-resources` |
| `device_list` | Suportada | `devices/cases/discovery-and-claims` |
| `device_claim` | Suportada | `devices/cases/discovery-and-claims` |
| `device_open` | Suportada | `devices/cases/feature-negotiation` |
| `device_config` | Suportada | `devices/cases/feature-negotiation` |
| `device_submit` | Suportada | `devices/cases/descriptor-validation` |
| `device_wait` | Suportada | `devices/cases/descriptor-validation`, `device-reset/stalled-device/device-reported-failure` |
| `device_reset` | Suportada | `devices/cases/feature-negotiation`, `device-reset/stalled-device/memory-pinned-until-reset` |
| `serial_write` | Suportada | `devices/cases/serial-port` |
| `serial_read` | Suportada | `devices/cases/serial-port` |
| `system_power` | Suportada | `system-journey/journey-first-boot`, `system-journey/journey-second-boot`, `applications/applications` |

`system_power` exige `ADMIN` na capability do sistema. Os dois boots da jornada mostram o reinício e o desligamento pedidos pelo gerente, e `applications/applications` mostra a recusa a uma aplicação.

## Ciclo de vida dos serviços: `kernel_protocol.services.lifecycle`

Descrito em `specs/abi/device-services.md`. Vale para todo serviço do sistema.

| Operação | Estado | Evidência |
| --- | --- | --- |
| `REGISTER` | Suportada | `supervision/supervision-cases/dependency-order`, `bootstrap/boot` |
| `STOP` | Restrita | `supervision/supervision-cases/dependency-order`, `devices/services/service-authority` |

## Serviço de console: `kernel_protocol.services.console`

Descrito em `specs/abi/device-services.md`.

| Operação | Estado | Evidência |
| --- | --- | --- |
| `WRITE` | Suportada | `devices/services/console-service` |
| `READ_LINE` | Suportada | `devices/services/console-service`, `tests/conformance/test_console.py` |

## Serviço de entropia: `kernel_protocol.services.entropy`

Descrito em `specs/abi/device-services.md`. Sem `virtio-rng` o serviço não existe, como mostra o cenário `devices/without-entropy`, e o serviço de rede não inicia.

| Operação | Estado | Evidência |
| --- | --- | --- |
| `READ` | Suportada | `devices/services/entropy-service` |

## Serviço de blocos: `kernel_protocol.services.block`

Descrito em `specs/abi/device-services.md`.

| Operação | Estado | Evidência |
| --- | --- | --- |
| `ATTACH` | Suportada | `devices/services/block-service` |
| `READ` | Suportada | `devices/services/block-service` |
| `WRITE` | Suportada | `devices/services/block-service` |
| `FLUSH` | Suportada | `devices/services/block-service`, `storage/cases/durable-after-sync` |
| `DETACH` | Suportada | `devices/services/block-service` |
| `EVICT` | Restrita | `storage/cases/durable-after-sync`, `devices/services/service-authority` |

## Serviço de arquivos: `kernel_protocol.services.files`

Descrito em `specs/filesystem/file-service.md`. O formato do volume está em `specs/filesystem/volume-format.md`.

| Operação | Estado | Evidência |
| --- | --- | --- |
| `ROOT` | Restrita | `vfs/cases`, `devices/services/service-authority` |
| `EVICT` | Restrita | `applications/applications`, `devices/services/service-authority` |
| `ENTER` | Suportada | `vfs/cases/namespaces-and-rights` |
| `LEAVE` | Suportada | `vfs/cases/open-handles` |
| `SUBSPACE` | Suportada | `vfs/cases/namespaces-and-rights`, `vfs/cases/path-resolution` |
| `DROP` | Suportada | `vfs/cases/namespaces-and-rights` |
| `STATUS` | Suportada | `vfs/cases/boot-image`, `vfs/cases/files-and-directories` |
| `OPEN` | Suportada | `vfs/cases/files-and-directories`, `vfs/cases/path-resolution` |
| `CLOSE` | Suportada | `vfs/cases/open-handles` |
| `READ` | Suportada | `vfs/cases/files-and-directories`, `vfs/cases/boot-image` |
| `WRITE` | Suportada | `vfs/cases/files-and-directories`, `storage/cases/volume-full` |
| `TRUNCATE` | Suportada | `vfs/cases/files-and-directories` |
| `SYNC` | Suportada | `storage/cases/durable-after-sync`, `storage/persistence-verify` |
| `STAT` | Suportada | `vfs/cases/files-and-directories` |
| `LIST` | Suportada | `vfs/cases/files-and-directories` |
| `MAKE_DIRECTORY` | Suportada | `vfs/cases/files-and-directories` |
| `REMOVE` | Suportada | `vfs/cases/files-and-directories`, `vfs/cases/open-handles` |
| `RENAME` | Suportada | `vfs/cases/files-and-directories` |

A durabilidade de `SYNC` depois de uma queda é conferida fora do convidado, por `storage-crash/flush-trace`, pelas imagens de `tests/faults/storage` e por `tests/conformance/test_filesystem_recovery.py`.

## Serviço de sockets: `kernel_protocol.services.network`

Descrito em `specs/network/socket-service.md`. Um processo sem um acesso emitido pelo serviço não abre socket nem alcança o dispositivo: é o que `network/network-cases/access-rights` confere com um processo que recebe só o endpoint.

| Operação | Estado | Evidência |
| --- | --- | --- |
| `ROOT` | Restrita | `network/network-cases/access-rights` |
| `EVICT` | Restrita | `network/network-cases/access-rights`, `applications/applications` |
| `ENTER` | Suportada | `network/network-cases/access-rights` |
| `LEAVE` | Suportada | `network/network-cases/socket-quota` |
| `RESTRICT` | Suportada | `network/network-cases/access-rights` |
| `STATUS` | Suportada | `network/network-cases/interface-and-echo`, `network/network-cases/socket-quota` |
| `NEIGHBORS` | Suportada | `network/network-cases/interface-and-echo` |
| `ECHO` | Suportada | `network/network-cases/interface-and-echo` |
| `OPEN` | Suportada | `network/network-cases/socket-quota`, `network/network-cases/access-rights` |
| `BIND` | Suportada | `network/network-cases/datagrams`, `network/network-cases/listening` |
| `LISTEN` | Suportada | `network/network-cases/listening` |
| `ACCEPT` | Suportada | `network/network-cases/listening`, `network/network-cases/deadlines-cancellation-and-backpressure` |
| `CONNECT` | Suportada | `network/network-cases/streams` |
| `SEND` | Suportada | `network/network-cases/streams`, `network-interop/interop-impaired-link/upload-verified-by-the-peer` |
| `RECEIVE` | Suportada | `network/network-cases/streams`, `network-interop/interop-impaired-link/download-verified-by-checksum` |
| `SEND_TO` | Suportada | `network/network-cases/datagrams` |
| `RECEIVE_FROM` | Suportada | `network/network-cases/datagrams`, `network-interop/interop-clean-link/fragmented-datagrams` |
| `FINISH` | Suportada | `network/network-cases/streams`, `network/network-cases/listening` |
| `CLOSE` | Suportada | `network/network-cases/socket-quota` |
| `DESCRIBE` | Suportada | `network/network-cases/streams` |
| `REVOKE` | Suportada | `network/network-cases/access-rights` |

## Protocolos de rede

O que cada camada aceita e recusa está em `specs/network/protocols.md`. O peer das suítes é a pilha TCP/IP do Linux do host, em uma rede isolada.

| Protocolo | Estado | Evidência |
| --- | --- | --- |
| Driver `virtio-net` | Suportado, sem offload | `network/network-cases/interface-and-echo`, `network-faults/network-faults/device-reset` |
| Ethernet II | Suportado, sem VLAN | `network-faults/network-faults/malformed-traffic`, `tests/conformance/test_network_link.py` |
| ARP | Suportado | `network/network-cases/interface-and-echo`, `tests/conformance/test_network_link.py` |
| IPv4 | Suportado, sem opções e sem encaminhamento | `network/network-cases/datagrams`, `tests/conformance/test_network_malformed.py` |
| Fragmentação e reassembly | Suportados, com limites | `network-interop/interop-clean-link/fragmented-datagrams`, `tests/conformance/test_network_reassembly.py` |
| ICMP echo e destino inalcançável | Suportados | `network/network-cases/interface-and-echo`, `network/network-cases/datagrams` |
| UDP | Suportado | `network/network-cases/datagrams` |
| TCP | Suportado, sem escala de janela, SACK e timestamps | `network/network-cases/streams`, `network/network-cases/listening`, `tests/conformance/test_network_tcp.py` |
| TCP com perda, duplicação e reordenação | Suportado | `network-interop/interop-impaired-link/upload-verified-by-the-peer`, `network-interop/interop-impaired-link/relay-through-the-guest` |
| Peer que lê devagar e devolução de buffers | Suportados | `network-interop/interop-impaired-link/slow-reader`, `network-interop/interop-impaired-link/buffers-returned` |
| Flood de pedidos de conexão | Contido pela fila de aceitação | `network-faults/network-faults/connection-flood` |
| Enlace caído e retorno | Suportado | `network-faults/network-faults/link-blackout` |
| Reinício do serviço com cliente à espera | Suportado | `network-faults/network-faults/service-restart-with-a-waiting-client` |

## Serviço de controle: `kernel_protocol.services.control`

Descrito em `specs/system/control-service.md`. O gerente só atende o shell: uma aplicação não recebe o endpoint de controle, e `applications/applications` confere que ela não é atendida por nenhum handle que tenha ou adivinhe.

| Operação | Estado | Evidência |
| --- | --- | --- |
| `STATUS` | Suportada | `system-journey/journey-first-boot`, `supervision/network-absent` |
| `ENDPOINT` | Suportada | `system-journey/journey-first-boot` |
| `ACCESS` | Suportada | `system-journey/journey-first-boot` |
| `LAUNCH` | Suportada | `applications/applications` |
| `APPLICATIONS` | Suportada | `applications/applications` |
| `SIGNAL` | Suportada | `applications/applications` |
| `WAIT` | Suportada | `applications/applications` |
| `MEMORY` | Suportada | `system-journey/journey-first-boot` |
| `POWER` | Suportada | `system-journey/journey-first-boot`, `system-journey/journey-second-boot` |

A codificação de cada pedido e resposta é conferida em `tests/conformance/test_control_protocol.py`.

## Supervisão e configuração

Descritas em `specs/system/control-service.md` e em `specs/system/configuration.md`.

| Comportamento | Estado | Evidência |
| --- | --- | --- |
| Início na ordem das dependências e parada na ordem inversa | Suportado | `supervision/supervision-cases/dependency-order` |
| Serviço que não fica pronto e estado degradado visível | Suportado | `supervision/supervision-cases/readiness-and-degraded-state`, `supervision/network-absent` |
| Reinício com pedido pendente | Suportado | `supervision/supervision-cases/restart-with-a-pending-request` |
| Limite de reinícios por janela | Suportado | `supervision/supervision-cases/restart-budget`, `supervision/supervision-cases/restart-window` |
| Configuração ausente recusada sem nada aplicado | Suportado | `supervision/configuration-missing` |
| Dependência circular recusada | Suportado | `supervision/configuration-circular` |
| Valor acima do limite recusado | Suportado | `supervision/configuration-excessive` |
| Configuração inconsistente recusada | Suportado | `supervision/configuration-inconsistent` |
| Documento validado inteiro antes de qualquer efeito | Suportado | `tests/conformance/test_configuration.py`, `tests/conformance/test_service_supervision.py` |
| Parada ordenada com aplicações em execução | Suportado | `applications/applications`, `system-journey/journey-first-boot` |

## Aplicações

Descritas em `specs/system/applications.md`. A API do programa é `kernel_apps.runtime.current()`, com `arguments`, `files` e `network`.

| Comportamento | Estado | Evidência |
| --- | --- | --- |
| Programa lido do volume e executado em processo próprio | Suportado | `applications/applications`, `system-journey/journey-first-boot` |
| Argumentos entregues, sem memória da execução anterior | Suportado | `applications/applications` |
| Só as capabilities da política, sem administração | Suportado | `applications/applications` |
| Exceção, erro de sintaxe e arquivo ausente com status 1 | Suportado | `applications/applications` |
| Laço sem cooperação encerrado, heap esgotado contido | Suportado | `applications/applications` |
| Limite de aplicações em execução | Suportado | `applications/applications` |
| Arquivos e rede usados por um programa | Suportado | `system-journey/journey-first-boot`, `system-journey/journey-second-boot` |

## Shell: `kernel_apps.shell.commands.table`

Descrito em `docs/operations/system-operation.md`. Todo comando termina com uma linha `shell: command=<nome> status=...`, e um nome fora da tabela devolve `UNSUPPORTED`.

| Comando | Estado | Evidência |
| --- | --- | --- |
| `help` | Suportado | `system-journey/journey-first-boot` |
| `run` | Suportado | `applications/applications`, `system-journey/journey-first-boot` |
| `ps` | Suportado | `applications/applications`, `supervision/network-absent` |
| `kill` | Suportado | `applications/applications` |
| `wait` | Suportado | `applications/applications`, `system-journey/journey-first-boot` |
| `mem` | Suportado | `system-journey/journey-first-boot` |
| `ls` | Suportado | `system-journey/journey-first-boot`, `system-journey/journey-second-boot` |
| `cat` | Suportado | `system-journey/journey-first-boot`, `system-journey/journey-second-boot` |
| `mkdir` | Suportado | `system-journey/journey-first-boot` |
| `write` | Suportado | `system-journey/journey-first-boot` |
| `rm` | Suportado | `system-journey/journey-first-boot`, `system-journey/journey-second-boot` |
| `sync` | Suportado | `system-journey/journey-first-boot`, `system-journey/journey-second-boot` |
| `net` | Suportado | `system-journey/journey-first-boot`, `supervision/network-absent` |
| `ping` | Suportado | `system-journey/journey-first-boot` |
| `shutdown` | Suportado | `system-journey/journey-first-boot`, `system-journey/journey-second-boot` |

A divisão da linha em palavras e os limites dela são conferidos em `tests/conformance/test_shell_words.py`. A recusa de uma linha que passou do limite do console está em `tests/conformance/test_shell_interpreter.py`, e a limpeza de um `write` recusado em `tests/conformance/test_shell_write.py`.

## Fora do suportado

Nada desta lista tem implementação parcial escondida: a interface não existe, e quem a procura recebe `UNSUPPORTED`, `ImportError` ou a ausência do nome.

| Área | Não existe |
| --- | --- |
| Processos | `fork`, `exec`, sinais, threads e mais de um hart. Um processo nasce por `process_spawn`, de uma imagem que o sistema já tem |
| Shell | Pipes, redirecionamento, variáveis, curingas, histórico e autenticação de quem está na porta serial |
| Arquivos | Diretório corrente, symlinks e hard links |
| Rede | IPv6, DHCP, DNS, encaminhamento, multicast, VLAN, opções IPv4, tráfego cifrado e socket por nome ou por caminho |
| TCP | Escala de janela, SACK, timestamps, dados urgentes e keepalive |
| Python | `open`, `input`, `compile`, `sys.argv`, `sys.exit`, `typing` e import de módulo a partir de um arquivo do volume. As demais diferenças estão em `runtime-differences.md` |
| Configuração | Releitura com o sistema em execução e mudança de valor a quente |
