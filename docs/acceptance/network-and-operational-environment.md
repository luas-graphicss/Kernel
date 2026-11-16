# Registro de aceite: rede e ambiente operacional

Resultado de uma execução completa das verificações do projeto sobre a árvore que acrescenta a rede IPv4, os sockets, o gerente do sistema, o shell e as aplicações. Os números vêm dos relatórios que a execução gravou em `build/qemu-riscv64/reports/`. O que não foi medido não aparece aqui.

## A execução

| Item | Valor |
| --- | --- |
| Data | 16 de novembro de 2026, das 22:55 às 22:59 UTC |
| Árvore | Branch `feat/network-and-operational-environment`, sobre o commit `155ac06` de `main` |
| Host | Linux 6.18.56 x86_64, 2 vCPUs Intel Xeon de 2,9 GHz e 4 GiB de RAM |
| Convidado | QEMU 9.2.4 com TCG, um hart e 256 MiB, perfil `qemu-riscv64` |
| Peer de rede | Pilha TCP/IP do Linux 6.18.56, a do próprio host, em um namespace de rede sem rota para fora |
| Build | Diretório vazio, com a toolchain de `toolchain.lock.toml` conferida por hash |

Os comandos são os do workflow de CI, na mesma ordem e sem nenhum pulado. As 26 etapas terminaram com status 0, em 274 s.

| Etapa | Resultado |
| --- | --- |
| `ruff format --check .` | 606 arquivos, nenhum a reformatar |
| `ruff check .` | Nenhuma ocorrência |
| `mypy --strict host src` | 306 arquivos, nenhum erro |
| `pytest tests/host tests/conformance` | 873 testes aprovados |
| `kernel-tool toolchain` | GCC 15.2.0-1, QEMU 9.2.4-1 e MicroPython 1.29.0 conferidos |
| `kernel-tool native-check` | 11 testes nativos hospedados sob sanitizers e a análise estática |
| `kernel-tool build` | Imagens geradas em 33 s |
| `kernel-tool test`, 14 suítes | 41 de 41 cenários |
| `kernel-tool fault-test`, 3 suítes | 3 de 3 cenários e os 4 estágios que rodam no host |
| `kernel-tool verify-filesystem --corpus tests/faults/storage` | 21 imagens com o veredito esperado |
| `kernel-tool verify-artifacts --reproduce` | Segunda compilação, em outro diretório, com imagens idênticas |

## Imagens testadas

| Imagem | Bytes | SHA-256 |
| --- | --- | --- |
| `kernel.elf` | 1.635.424 | `cc09636d934a288b365569f2deb9f03d84129f8fc7754ca442c22a31dee0dea0` |
| `kernel-selftest.elf` | 1.732.968 | `4e9f8529383f2db73b42411bd0d4b8b96b2c3da9214b81a88726fecd1ac60902` |
| `init.img` | 431.655 | `3d6b481c9238f76df368e76c04cada0efe3c8180f7191367bcc73e3488aad0a7` |
| `tests.img` | 622.799 | `6ac6f235dac4fc45a9b490d60d7fa6693e31619b347259a5c2a832572668df61` |
| `boot.img` | 65.536 | `f03917e4348677b13968d9da6ab95fc3fbc22bc59c7285d6c8ebd5cf5a354412` |

O relatório `artifacts.json` de qualquer execução traz os mesmos campos, para comparar.

## Suítes no QEMU

| Suíte | Cenários aprovados | Casos | Verificações | Tempo no QEMU |
| --- | --- | --- | --- | --- |
| `bootstrap` | 9 de 9 | 0 | 0 | 41,0 s |
| `memory` | 1 de 1 | 7 | 78 | 0,6 s |
| `processes` | 3 de 3 | 7 | 160 | 65,1 s |
| `capabilities` | 1 de 1 | 6 | 47 | 0,2 s |
| `ipc` | 1 de 1 | 9 | 83 | 0,6 s |
| `scheduling` | 2 de 2 | 7 | 37 | 1,4 s |
| `devices` | 3 de 3 | 11 | 91 | 0,9 s |
| `vfs` | 1 de 1 | 7 | 71 | 1,6 s |
| `storage` | 8 de 8 | 3 | 14 | 5,3 s |
| `network` | 1 de 1 | 7 | 71 | 13,1 s |
| `network-interop` | 2 de 2 | 14 | 14 | 7,5 s |
| `applications` | 1 de 1 | 0 | 0 | 5,0 s |
| `supervision` | 6 de 6 | 5 | 32 | 3,6 s |
| `system-journey` | 2 de 2 | 0 | 0 | 4,2 s |
| `device-reset` | 1 de 1 | 4 | 21 | 7,2 s |
| `storage-crash` | 1 de 1 | 0 | 0 | 0,8 s |
| `network-faults` | 1 de 1 | 5 | 26 | 2,6 s |
| Total | 44 de 44 | 92 | 745 | 160,5 s |

Um caso é uma linha `test: suite=... case=... checks=N result=ok` da transcrição, e N é quantas verificações o programa de teste fez dentro do convidado. Os cenários sem casos são conferidos pelo `kernel-tool`, que exige as linhas que a transcrição precisa ter e reprova as que ela não pode ter.

As nove suítes que já existiam, `device-reset`, `storage-crash`, o corpus de volumes e a reprodução das imagens passaram na mesma execução, sobre a mesma árvore.

## Rede contra o peer

### `network`

Um boot, 13,1 s.

| Caso | Verificações |
| --- | --- |
| `interface-and-echo` | 10 |
| `datagrams` | 13 |
| `streams` | 15 |
| `listening` | 7 |
| `deadlines-cancellation-and-backpressure` | 8 |
| `socket-quota` | 5 |
| `access-rights` | 13 |

O envio de 20.480 bytes chegou ao peer com SHA-256 `6c6d0a81798e4cd4515a9862dcaf81a08c83e7e6b5b85bac3177fd69ee8e082a`. Na conexão que o peer abriu, os 16.384 bytes voltaram iguais, com SHA-256 `42bb8d620d204120a5b6676bd04868478eef3647bb22d6eec4e6830ca72c11d0`.

### `network-interop`

Dois boots com os mesmos sete casos: `interop-clean-link`, em 2,5 s, e `interop-impaired-link`, em 5,0 s, com 3% de perda, 2% de duplicação e 10% de reordenação a partir da seed 7. Os dados de cada transferência saem de uma seed fixa, quem recebe calcula o hash e o `kernel-tool` compara com o esperado. Os valores foram os mesmos nos dois enlaces.

| Caso | Bytes | Conferência |
| --- | --- | --- |
| `upload-verified-by-the-peer` | 131.072 | SHA-256 `fd3151cf480b2df6a75c3e5e5e75d037c13fa3105a9c367b7f8642e63f009b7c` |
| `download-verified-by-checksum` | 131.072 | CRC-32 `862839fd` |
| `relay-through-the-guest` | 65.536 | SHA-256 `194a75d0303b675a20876910e727ddb778de719ac1786232f1ab1b9b621e3d10` |
| `inbound-connection` | 65.536 | SHA-256 `aae5ad71c082c551f0778f33b9d30ded11136d2becabb1e626d1b588a54a4049` |
| `fragmented-datagrams` | 4 datagramas de 3.072 | Os 4 entregues inteiros |
| `slow-reader` | 32.768 | SHA-256 `bcc4256d1bd2c78edf1321ffd51a4dd43f4799b30f6977d1cd98931779c6e3fb` |
| `buffers-returned` | 0 | Nenhum byte em buffer depois das transferências |

No enlace degradado, a estação descartou 19 quadros a caminho do convidado e 22 a caminho do peer. O convidado retransmitiu 42 segmentos e recebeu 61 fora de ordem. No enlace limpo, os dois contadores ficaram em zero.

### `network-faults`

Um boot, 2,6 s, e um estágio no host que confere o que foi injetado.

| Caso | Verificações | O que aconteceu |
| --- | --- | --- |
| `malformed-traffic` | 4 | 31 espécimes em 32 quadros, cada um contado pelo parser da sua camada. Nenhum socket e nenhum buffer ficaram para trás, e o serviço respondeu ao echo em seguida |
| `connection-flood` | 6 | 32 pedidos de conexão forjados contra uma fila de aceitação de 4. Os excedentes foram recusados e contados, nenhum chegou à aplicação, e um peer real conectou depois: 8.192 bytes, SHA-256 `d197b0c12fff2c87d994e76373edd4cf7f4b204692aeb6d331718f6c0cca46a8` |
| `link-blackout` | 4 | 1,5 s de enlace caído no meio de uma transferência. 7 quadros se perderam a caminho do peer, o convidado retransmitiu e a transferência terminou |
| `device-reset` | 4 | `network: link=down`, `network: device=recovered resets=1` e `network: link=up`, com echo respondido depois |
| `service-restart-with-a-waiting-client` | 8 | O cliente à espera foi avisado, a instância nova recusou as sessões da antiga e alcançou o peer |

| Parser | Espécimes | Contadores |
| --- | --- | --- |
| Ethernet | 2 | `frames-malformed` |
| ARP | 5 | `arp-malformed` |
| IPv4 | 6 | `ipv4-malformed`, `ipv4-bad-checksum`, `ipv4-options-refused` |
| Fragmentos | 3 | `fragments-invalid` |
| ICMP | 3 | `icmp-malformed` |
| UDP | 5 | `udp-malformed`, `udp-bad-checksum` |
| TCP | 7 | `tcp-malformed`, `tcp-bad-checksum` |

### Capturas

A captura registra o que a interface do convidado viu: cada quadro que ele enviou e cada quadro entregue a ele. Os forjados entram na conta dos entregues ao convidado.

| Captura | Quadros | Entregues ao convidado | Entregues ao peer | Perdidos para o convidado | Perdidos para o peer | Forjados |
| --- | --- | --- | --- | --- | --- | --- |
| `network-cases.pcap` | 286 | 107 | 179 | 0 | 0 | 0 |
| `interop-clean-link.pcap` | 991 | 422 | 569 | 0 | 0 | 0 |
| `interop-impaired-link.pcap` | 1.145 | 507 | 627 | 19 | 22 | 0 |
| `applications.pcap` | 0 | 0 | 0 | 0 | 0 | 0 |
| `journey-first-boot.pcap` | 29 | 13 | 16 | 0 | 0 | 0 |
| `journey-second-boot.pcap` | 0 | 0 | 0 | 0 | 0 | 0 |
| `network-faults.pcap` | 157 | 100 | 50 | 0 | 7 | 64 |

Cada quadro fica cortado em 96 bytes. As capturas só têm os endereços de teste de `10.0.2.0/24` e dados gerados pelos testes: nenhum tráfego do host passa pela estação, e por isso não houve dado a remover. O CI anexa as capturas de cada run em `reports/captures/`, com o hash de cada uma no relatório da suíte.

## Aplicações, supervisão e jornada

### `applications`

Um boot, 5,0 s, com 28 comandos digitados no shell: 24 terminaram com `status=ok` e 4 com a recusa que o cenário espera.

| Situação | Linha da transcrição |
| --- | --- |
| Argumentos entregues, sem memória da execução anterior | `counter: runs=1 arguments=2` e, na segunda execução, `counter: runs=1 arguments=0` |
| Só as capabilities da política | `authority: capabilities=5 send-only-endpoints=1 administration=refused shell-modules=0 files=read-write network=granted` |
| Exceção, erro de sintaxe e arquivo ausente | `system: application=N state=exited reason=exit value=1` nos três |
| Laço sem cooperação | `wait 7 1` termina com `TIMED_OUT`, e `kill 7` leva a `reason=killed` |
| Heap esgotado | `system: application=8 state=exited reason=exit value=1`, com o shell em uso depois |
| Limite de aplicações | Quatro em execução, e a quinta recusada com `LIMIT_EXCEEDED` |
| Parada com aplicações em execução | `system: shutdown=applications stopped=4` e `system: shutdown=complete clean=1` |

### `supervision`

| Caso de `supervision-cases` | Verificações |
| --- | --- |
| `dependency-order` | 6 |
| `readiness-and-degraded-state` | 7 |
| `restart-with-a-pending-request` | 8 |
| `restart-budget` | 6 |
| `restart-window` | 5 |

No cenário `network-absent`, o serviço de rede gastou as 3 tentativas e ficou em `state=degraded restarts=3 window-seconds=60`. O sistema seguiu em `state=degraded`: `ps` e `ls` responderam, e `net` devolveu `BAD_STATE`.

Os quatro cenários de configuração terminaram com `kernel: status=failed` e sem nenhum serviço iniciado:

| Cenário | Linha da recusa |
| --- | --- |
| `configuration-missing` | `system: configuration=rejected reason=missing-document subject=boot/system/config` |
| `configuration-circular` | `system: configuration=rejected reason=dependency-cycle subject=console` |
| `configuration-excessive` | `system: configuration=rejected reason=out-of-range subject=service.network.heap_bytes` |
| `configuration-inconsistent` | `system: configuration=rejected reason=gateway-off-link subject=interface.gateway` |

### `system-journey`

Dois boots sobre o mesmo volume de dados.

No primeiro, em 3,7 s, foram 28 comandos. 24 terminaram com `status=ok`. Três terminaram com a falha esperada: `cat` de um arquivo que não existe, com `NOT_FOUND`; `rm` na imagem de boot, com `READ_ONLY`; `wait` de uma aplicação presa em uma conexão, com `TIMED_OUT`. O último foi `shutdown restart`. `fetch.py` gravou em `data/journey/greeting` os 6.240 bytes recebidos por TCP, e `wordcount.py` contou `lines=240 words=1200 bytes=6240`. `sync` respondeu `durable=1` para os dois volumes graváveis. A parada encerrou a aplicação presa, parou os cinco serviços na ordem inversa com `clean=1` e terminou em `kernel: power=restart`.

No segundo, em 0,6 s, foram 7 comandos, todos com `status=ok`. A nota gravada antes do reinício voltou com os mesmos 27 bytes, `wordcount.py` repetiu `lines=240 words=1200 bytes=6240` sobre o arquivo transferido, e o sistema desligou com `kernel: status=ok`.

## Critérios de aceite

| Critério | Evidência desta execução |
| --- | --- |
| Os protocolos funcionam com um peer externo real, dentro do perfil de rede documentado | `network`, com 71 verificações, e `network-interop/interop-clean-link`, contra a pilha do Linux 6.18.56 |
| Transferências nos dois sentidos preservam o conteúdo sob perda e reordenação | `network-interop/interop-impaired-link`: os mesmos hashes do enlace limpo, com 41 quadros descartados |
| Parsers e reassembly têm custo limitado, e pacotes malformados não derrubam o serviço nem o kernel | `network-faults/malformed-traffic`; `tests/conformance/test_network_malformed.py` e `test_network_reassembly.py` |
| Um peer ou um processo não esgota recursos globais | `network/socket-quota`, `network/deadlines-cancellation-and-backpressure`, `network-faults/connection-flood` e os casos `slow-reader` e `buffers-returned` de `network-interop` |
| Aplicações são iniciadas, observadas, encerradas e aguardadas pelo shell, com o isolamento mantido | `applications` |
| Todo comando do shell executa uma operação real e devolve um status | Os 15 comandos são digitados em pelo menos um cenário aprovado, o que `tests/conformance/test_api_conformance.py` exige |
| A supervisão respeita dependências, limites de reinício e autoridade mínima | `supervision`, com 32 verificações e o cenário `network-absent` |
| A jornada de boot, programas, arquivos, rede, `sync`, parada e reinício passa inteira | `system-journey`, nos dois boots |
| Cada interface pública tem estado e evidência | `docs/architecture/api-conformance.md`, conferida contra o código pelo mesmo teste |
| As suítes anteriores continuam aprovadas | As 11 linhas da tabela de suítes que não são desta entrega, o corpus de volumes e a reprodução das imagens |

## Falha encontrada antes desta execução

Uma execução completa anterior, no mesmo dia, reprovou `network-faults` no caso `service-restart-with-a-waiting-client`: o serviço contava duas conexões onde o teste esperava uma. A captura mostrou a causa. A conexão aceita no fim de `connection-flood` ainda estava fechando quando o caso seguinte derrubou o enlace. O FIN do convidado se perdeu no escuro, e a conexão ficou à espera da retransmissão. A pilha se comportou como o TCP prevê; o erro era a ordem dos casos. `connection-flood` e `link-blackout` agora só terminam quando o serviço informa zero conexões.

Depois da correção, e antes da execução registrada aqui, `network-faults` rodou 10 vezes seguidas e as suítes `network`, `network-interop`, `applications`, `supervision` e `system-journey` rodaram 3 vezes cada, sem nenhuma falha.

## Falha encontrada depois desta execução

O primeiro run do CI do pull request reprovou a suíte `network` no runner. Um caso falhou, `interface-and-echo`, na verificação `an echo that gets no answer ends at its deadline`: o echo para `192.0.2.1`, um endereço de fora da rede, não terminou pelo prazo. Os outros seis casos da suíte e as 16 etapas anteriores passaram, e as nove seguintes não rodaram.

A diferença estava no host, e não no convidado. Um namespace de rede novo herda do host o encaminhamento IPv4. Com ele ligado, o peer deixa de descartar o pacote para fora da rede e responde com um ICMP de rede inalcançável, que encerra o echo antes do prazo. A máquina desta execução tem o encaminhamento desligado. Ligá-lo nela reproduziu a reprovação do runner, na mesma verificação.

A estação agora desliga o encaminhamento no namespace antes de criar a interface, e três testes de host cobrem a mudança. As imagens do convidado são as mesmas: a correção fica só no `kernel-tool`. Depois dela rodaram, sobre as imagens desta execução:

| Encaminhamento no host | O que rodou | Resultado |
| --- | --- | --- |
| Ligado | `network`, `network-interop`, `applications`, `system-journey` e `network-faults` | 7 de 7 cenários |
| Desligado | `network` | 1 de 1 cenário |
| Desligado | `ruff format --check .`, `ruff check .`, `mypy --strict host src` e `pytest tests/host tests/conformance` | Nenhuma ocorrência, e 876 testes aprovados |

As tabelas das outras seções são da execução original, que tinha 873 testes.

## O que este registro não cobre

- Os tempos são de um host e de TCG. Não valem para hardware físico.
- A interoperabilidade foi conferida contra uma pilha só, a do Linux 6.18.56.
- O fuzzing dos parsers continua aberto, como diz a linha R-19 de `docs/architecture/requirements.md`.
- O resultado do CI no runner `ubuntu-24.04` fica no pull request, e não nesta página.
