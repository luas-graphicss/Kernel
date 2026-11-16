# Máquina de referência, workload e budgets iniciais

Define onde e com que carga as medições do projeto são feitas, e os limites que os testes aplicam hoje. Resultados obtidos com TCG não são extrapolados para hardware físico.

## Máquina de referência

| Dimensão | Valor |
| --- | --- |
| Emulador | QEMU 9.2.4, pacote xPack `9.2.4-1`, fixado por hash em `toolchain.lock.toml` |
| Acelerador | TCG, um hart |
| Máquina | `virt,aia=none,acpi=off`, CPU `rv64,h=off,v=off`, `virtio-mmio.force-legacy=false` |
| Firmware | OpenSBI 1.5.1 `fw_dynamic`, do mesmo pacote |
| RAM do convidado | 256 MiB |
| Dispositivos | Porta serial NS16550. Conforme o cenário, um `virtio-rng-device` ligado a `rng-builtin` e um `virtio-blk-device` por disco: a imagem de boot, somente leitura, com o serial `kernel-boot`, e o volume de dados, com o serial `kernel-data`. Nos cenários com rede, um `virtio-net-device` ligado por um netdev `dgram`, em sockets Unix, à estação de teste do host |
| Imagem | `kernel.elf` com `init.img` como módulo de boot, do perfil `qemu-riscv64`. As suítes de programas usam `tests.img` |
| Layout | Kernel em `0x80200000`, heap do supervisor de 8 MiB e, em cada processo, região virtual de usuário de 16 MiB em `0x40000000` |

A fonte desses valores é `config/profiles/qemu-riscv64.toml`. O ADR 0001 explica a escolha.

## Host das medições

As primeiras medições vieram de um host Linux x86_64 com 2 vCPUs Intel Xeon de 2,5 GHz e 4 GiB de RAM, sem aceleração de hardware para o convidado. A linha de base com dispositivos e volume persistente veio de um host com 2 vCPUs Intel Xeon de 2,9 GHz e 4 GiB de RAM. A linha de base com rede e ambiente operacional veio de um host com a mesma configuração e Linux 6.18, cuja pilha TCP/IP é o peer das suítes de rede. Toda medição nova registra o host junto.

O tempo é o do host, medido pelo `kernel-tool` em volta de cada execução do QEMU, e inclui a inicialização do emulador e do OpenSBI. O convidado lê o próprio tempo monotônico no contador `time`, com a frequência que o DTB informa, e o usa para quantum e deadlines. Esse tempo não entra nas medidas desta página.

## Workload de referência

As suítes do `kernel-tool test`:

- `bootstrap`, cenário `boot`, três vezes: boot completo, política Python, admissão e execução do `init`, que inicia o `echo` e os serviços de console, entropia, bloco e arquivos, confere cada um e os encerra. O cenário roda com a porta serial, a fonte de entropia, a imagem de boot e um volume de dados descartável.
- `bootstrap`, cenário `runtime-selftest`: sondas de raízes do coletor em `s0` a `s11` e em um slot de stack, casos de inteiros, bytes, exceções, imports, bindings e coleta sob pressão, 10.000 transições do corpus e reinícios repetidos do interpretador.
- `bootstrap`, sete cenários de falha: DTB grande demais, DTB sem memória, RAM insuficiente, segmento incompatível, falha em U-mode e trap no supervisor, com o runtime parado e com o heap dele esgotado.
- `memory`, `processes`, `capabilities`, `ipc`, `scheduling`, `devices`, `vfs` e `storage`: os programas de `tests/guest/programs/suites/`, um boot por cenário. Os discos são imagens descartáveis que o `kernel-tool` cria para a execução.
- `processes`, cenário `cycles`: 100 ciclos de aquecimento e 10.000 medidos. Cada ciclo cria um processo do serviço `echo`, troca duas chamadas com ele e espera o término.
- `fault-test --suite device-reset`, cenário `stalled-device`: um dispositivo de bloco que para de responder, até o deadline do pedido e o reset.
- `fault-test --suite storage-crash`: o registro de escritas e flushes de um boot, 66 pontos de crash em 11 transações e 1.000 sequências geradas a partir da seed 1. A montagem de cada imagem roda no host.
- `verify-filesystem --corpus tests/faults/storage`: as 21 imagens do corpus.
- `network`: os programas de `tests/guest/programs/suites/network`, em um boot, contra a estação de teste: echo, datagramas, conexões nos dois sentidos, um envio de 20 KiB conferido por hash e uma conexão de 16 KiB iniciada pelo peer.
- `network-interop`, dois cenários, um com o enlace limpo e outro com 3% de perda, 2% de duplicação e 10% de reordenação, gerados a partir da seed 7: envio e recepção de 128 KiB, ida e volta de 64 KiB pelo convidado, conexão de 64 KiB iniciada pelo peer, quatro datagramas fragmentados de 3072 bytes e 32 KiB para um peer que lê devagar.
- `applications`: 28 comandos digitados no shell, com 13 pedidos de início de programas de `tests/guest/apps`, um deles recusado pelo limite.
- `supervision`: cinco casos sobre um conjunto de serviços de teste, um boot sem dispositivo de rede e quatro boots com configurações recusadas.
- `system-journey`: dois boots sobre o mesmo volume de dados, com 28 e 7 comandos digitados no shell e uma transferência de 6240 bytes por TCP gravada em arquivo.
- `fault-test --suite network-faults`: 31 espécimes malformados em 32 quadros, 32 pedidos de conexão forjados, 1,5 s de enlace caído, um reset do dispositivo de rede e um reinício do serviço com um cliente à espera.

## Budgets iniciais

São limites que reprovam o teste quando estourados. Não são resultados medidos nem metas de produto.

| Recurso | Budget | Onde é aplicado |
| --- | --- | --- |
| Tempo de um boot até o status final | 60 s | `deadlines.boot_seconds` do perfil |
| Tempo do autoteste do runtime | 600 s | `deadlines.selftest_seconds` do perfil |
| Tempo do cenário `cycles` | 900 s | `deadlines.soak_seconds` do perfil |
| Tempo de uma sessão com rede ou com o shell | 300 s | `deadlines.session_seconds` do perfil |
| DTB aceito | 64 KiB | Validação do DTB no boot |
| Memória física do perfil | 256 MiB | O boot recusa a máquina com menos RAM |
| Heap do supervisor | 8 MiB | Layout de linkagem, conferido pela política no boot |
| Região de usuário | 16 MiB de endereços virtuais por processo | Layout de linkagem; a imagem é recusada se não couber |
| Heap e stack padrão de um processo | 1 MiB e 64 KiB | Cabeçalho da imagem de usuário |
| Heap por processo | 4 MiB | Admissão pela política |
| Processos | 16 | Admissão pela política e tabela nativa |
| Quantum | 10 ms | Supervisor Python, a cada execução de um processo |
| Capabilities por processo | 128 | Tabela de capabilities |
| Payload de uma mensagem | 4 KiB | Validação da mensagem no envio |
| Mensagens pendentes por endpoint | 64 | Fila do endpoint |
| Bytes de IPC pendentes | 1 MiB por processo e 16 MiB no total | Cota de IPC no envio |
| Escrita de depuração | 256 bytes por chamada | Chamada `debug write` |
| Transportes VirtIO | 8 | Inventário dos dispositivos do DTB |
| Pedidos em andamento por dispositivo | 4, de até 4 segmentos cada | Fila de pedidos do supervisor |
| Entrada do console | 256 bytes em espera e linhas de até 255 bytes | Porta serial do supervisor e disciplina de linha |
| Caminho | 1024 bytes, 32 componentes e nomes de até 255 bytes | Serviço de arquivos, antes de consultar o volume |
| Volume persistente | De 8 a 65.536 blocos de 4096 bytes | Verificação na montagem |
| Imagem de boot | 64 arquivos de até 256 KiB | Validação da imagem na montagem |
| Sockets | 64 no total e 16 por processo | Serviço de rede, na abertura |
| Conexões TCP | 96 | Serviço de rede, contando as que abrem, fecham e esperam em `time-wait` |
| Bytes em buffers de sockets | 1 MiB para todos os sockets | Orçamento único do serviço de rede |
| Reassembly | 16 datagramas, 1 MiB e 30 s | Pilha IPv4, à parte do orçamento dos sockets |
| Aplicações em execução | 4, com heap de 2 MiB cada | `[access.application]` de `config/system/system.conf` |
| Reinícios de um serviço | 2 ou 3 a cada 60 s | `[service.*]` de `config/system/system.conf` |
| Linha do shell | 255 bytes e 16 palavras | Shell, antes de executar o comando |

Os demais limites do perfil estão em `specs/abi/resource-profile.md`. Os de dispositivos e de arquivos estão em `specs/abi/devices.md` e em `specs/filesystem/`, os de rede em `specs/network/protocols.md` e os do sistema em `specs/system/configuration.md`.

## Primeira linha de base

Medida em um clone limpo, no host descrito acima, antes de existirem memória virtual, processos preemptivos e IPC.

| Medida | Valor |
| --- | --- |
| Cenário `boot` | 5,3 s para as três execuções |
| Cenário `runtime-selftest` | 44,2 s |
| Cada cenário de falha | Menos de 0,2 s |
| Build completo | 25 s |
| `kernel.elf` | 1.160.112 bytes no arquivo e 145.948 bytes nos segmentos carregáveis: 80.140 de código, 63.808 de dados somente leitura e 2.000 de dados |
| `kernel-selftest.elf` | 1.249.112 bytes no arquivo |
| `init.img` | 118.104 bytes |

## Linha de base com processos e IPC

Medida em um host com a mesma configuração: Linux x86_64, 2 vCPUs Intel Xeon de 2,5 GHz e 4 GiB de RAM.

| Medida | Valor |
| --- | --- |
| Cenário `boot` | 0,4 s para as três execuções |
| Cenário `runtime-selftest` | 48,0 s |
| Cenário `runtime-trap` | 2,0 s |
| Cada um dos outros cenários de falha | Menos de 0,2 s |
| Suítes `memory`, `capabilities` e `ipc` | 0,6 s, 0,2 s e 0,5 s |
| Suíte `processes`, cenários `cases` e `spawn-failures` | 1,9 s e 0,3 s |
| Cenário `cycles` | 69,1 s |
| Suíte `scheduling`, cenários `cases` e `schedule-trace` | 1,3 s e 0,1 s |
| Build completo | 35 s |
| `kernel.elf` | 1.503.960 bytes no arquivo. Segmentos carregáveis: 104.998 bytes de código, 76.032 de dados somente leitura e 1.034.464 sem conteúdo no arquivo, das tabelas estáticas do supervisor |
| `kernel-selftest.elf` | 1.601.504 bytes no arquivo |
| `init.img` | 136.424 bytes |
| `tests.img` | 226.078 bytes |

O `init` desta medição não repete a carga de alocação da primeira: ele inicia o serviço `echo`, confere uma resposta e termina. Os dois valores do cenário `boot` não são comparáveis.

## Linha de base com dispositivos e volume persistente

Medida em um clone limpo, em um host Linux x86_64 com 2 vCPUs Intel Xeon de 2,9 GHz e 4 GiB de RAM. O host é outro, e os tempos não são comparáveis com os das linhas anteriores.

| Medida | Valor |
| --- | --- |
| Cenário `boot` | 0,7 s para as três execuções |
| Cenário `runtime-selftest` | 36,9 s |
| Cenário `runtime-trap` | 2,5 s |
| Cada um dos outros cenários de falha | 0,1 s |
| Suítes `memory`, `capabilities` e `ipc` | 0,6 s, 0,2 s e 0,5 s |
| Suíte `processes`, cenários `cases` e `spawn-failures` | 1,5 s e 0,3 s |
| Cenário `cycles` | 58,7 s |
| Suíte `scheduling`, cenários `cases` e `schedule-trace` | 1,2 s e 0,1 s |
| Suíte `devices`, cenários `cases`, `services` e `without-entropy` | 0,2 s, 0,4 s e 0,2 s |
| Suíte `vfs` | 1,7 s |
| Suíte `storage`, cenário `cases` | 3,6 s |
| Suíte `storage`, cenários `persistence-write` e `persistence-verify` | 0,4 s cada |
| Suíte `storage`, cada um dos outros cinco cenários | 0,2 s |
| `fault-test --suite device-reset`, cenário `stalled-device` | 7,1 s |
| `fault-test --suite storage-crash`, cenário `flush-trace` | 0,6 s |
| `fault-test --suite storage-crash`, imagens montadas | 226 da matriz de 66 pontos de crash, 8.000 das 1.000 sequências, com 3.457 commits, e 424 do registro de um boot, com 51 eventos e 7 gerações |
| Build completo | 30 s |
| `kernel.elf` | 1.626.976 bytes no arquivo. Segmentos carregáveis: 115.508 bytes de código, 77.008 de dados somente leitura e 1.039.664 sem conteúdo no arquivo, das tabelas estáticas do supervisor |
| `kernel-selftest.elf` | 1.724.504 bytes no arquivo |
| `init.img` | 245.584 bytes |
| `tests.img` | 396.990 bytes |
| `boot.img` | 49.152 bytes |

## Linha de base com rede e ambiente operacional

Medida em um diretório de build vazio, em um host Linux 6.18 x86_64 com 2 vCPUs Intel Xeon de 2,9 GHz e 4 GiB de RAM. A execução inteira, com as contagens de cada caso, está em `docs/acceptance/network-and-operational-environment.md`.

| Medida | Valor |
| --- | --- |
| Cenário `boot` | 0,7 s para as três execuções |
| Cenário `runtime-selftest` | 37,1 s |
| Cenário `runtime-trap` | 2,6 s |
| Cada um dos outros cenários de falha | 0,1 s |
| Suítes `memory`, `capabilities` e `ipc` | 0,6 s, 0,2 s e 0,6 s |
| Suíte `processes`, cenários `cases` e `spawn-failures` | 1,6 s e 0,3 s |
| Cenário `cycles` | 63,3 s |
| Suíte `scheduling`, cenários `cases` e `schedule-trace` | 1,2 s e 0,2 s |
| Suíte `devices`, cenários `cases`, `services` e `without-entropy` | 0,2 s, 0,4 s e 0,3 s |
| Suíte `vfs` | 1,6 s |
| Suíte `storage`, cenário `cases` | 3,3 s |
| Suíte `storage`, cenários `persistence-write` e `persistence-verify` | 0,4 s cada |
| Suíte `storage`, cada um dos outros cinco cenários | De 0,2 s a 0,3 s |
| Suíte `network` | 13,1 s |
| Suíte `network-interop`, cenários `interop-clean-link` e `interop-impaired-link` | 2,5 s e 5,0 s |
| Suíte `applications` | 5,0 s |
| Suíte `supervision`, cenário `supervision-cases` | 2,4 s |
| Suíte `supervision`, cenário `network-absent` | 0,3 s |
| Suíte `supervision`, cada um dos quatro cenários de configuração recusada | 0,2 s |
| Suíte `system-journey`, primeiro e segundo boot | 3,7 s e 0,6 s |
| `fault-test --suite device-reset`, cenário `stalled-device` | 7,2 s |
| `fault-test --suite storage-crash`, cenário `flush-trace` | 0,8 s |
| `fault-test --suite storage-crash`, imagens montadas | 226 da matriz de 66 pontos de crash, 8.000 das 1.000 sequências, com 3.457 commits, e 424 do registro de um boot, com 51 eventos e 7 gerações |
| `fault-test --suite network-faults` | 2,6 s |
| Build completo | 33 s |
| `kernel.elf` | 1.635.424 bytes no arquivo. Segmentos carregáveis: 116.350 bytes de código, 77.176 de dados somente leitura e 1.043.120 sem conteúdo no arquivo, das tabelas estáticas do supervisor |
| `kernel-selftest.elf` | 1.732.968 bytes no arquivo |
| `init.img` | 431.655 bytes |
| `tests.img` | 622.799 bytes |
| `boot.img` | 65.536 bytes |

Os hashes das imagens e o inventário de ferramentas ficam nos relatórios `bootstrap.json` e `artifacts.json`. Eles mudam a cada commit e por isso não são copiados para cá.

## Regras

- Mudar um budget exige atualizar o perfil, repetir os testes afetados e registrar a nova linha de base aqui.
- Um limite não sobe para esconder vazamento ou regressão.
- Outliers ficam no relatório. A média não substitui o pior caso.
