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
| Imagem | `kernel.elf` com `init.img` como módulo de boot, do perfil `qemu-riscv64` |
| Layout | Kernel em `0x80200000`, região de usuário de 8 MiB em `0x81000000` e heap do supervisor de 8 MiB |

A fonte desses valores é `config/profiles/qemu-riscv64.toml`. O ADR 0001 explica a escolha.

## Host das medições

As primeiras medições vieram de um host Linux x86_64 com 2 vCPUs Intel Xeon de 2,5 GHz e 4 GiB de RAM, sem aceleração de hardware para o convidado. Toda medição nova registra o host junto.

O tempo é o do host, medido pelo `kernel-tool` em volta de cada execução do QEMU, e inclui a inicialização do emulador e do OpenSBI. O convidado ainda não lê nenhuma fonte de tempo. Quando ler, tempo do host e tempo monotônico do convidado serão registrados em separado.

## Workload de referência

A suíte `bootstrap` do `kernel-tool test`:

- `boot`, três vezes: boot completo, política Python, admissão e execução do `init`, que aloca 4.096 blocos de 1 KiB mantendo 16 vivos e confere um checksum.
- `runtime-selftest`: sondas de raízes do coletor em `s0` a `s11` e em um slot de stack, casos de inteiros, bytes, exceções, imports, bindings e coleta sob pressão, 10.000 transições do corpus e reinícios repetidos do interpretador.
- Seis cenários de falha: DTB grande demais, DTB sem memória, RAM insuficiente, segmento incompatível, falha em U-mode e trap no supervisor.

## Budgets iniciais

São limites que reprovam o teste quando estourados. Não são resultados medidos nem metas de produto.

| Recurso | Budget | Onde é aplicado |
| --- | --- | --- |
| Tempo de um boot até o status final | 60 s | `deadlines.boot_seconds` do perfil |
| Tempo do autoteste do runtime | 600 s | `deadlines.selftest_seconds` do perfil |
| DTB aceito | 64 KiB | Validação do DTB no boot |
| Memória física do perfil | 256 MiB | O boot recusa a máquina com menos RAM |
| Heap do supervisor | 8 MiB | Layout de linkagem, conferido pela política no boot |
| Região de usuário | 8 MiB | Layout de linkagem; a imagem é recusada se não couber |
| Heap e stack do `init` | 1 MiB e 64 KiB | Cabeçalho da imagem de usuário |
| Processos | 16 | Admissão no modelo de processos |
| Escrita de depuração | 256 bytes por chamada | Chamada `debug write` |

Os demais limites do perfil, de capabilities, IPC e heap por processo, estão em `specs/abi/resource-profile.md` e passam a ser aplicados quando os mecanismos existirem.

## Primeira linha de base

Medida em um clone limpo, no host descrito acima.

| Medida | Valor |
| --- | --- |
| Cenário `boot` | 5,3 s para as três execuções |
| Cenário `runtime-selftest` | 44,2 s |
| Cada cenário de falha | Menos de 0,2 s |
| Build completo | 25 s |
| `kernel.elf` | 1.160.112 bytes no arquivo e 145.948 bytes nos segmentos carregáveis: 80.140 de código, 63.808 de dados somente leitura e 2.000 de dados |
| `kernel-selftest.elf` | 1.249.112 bytes no arquivo |
| `init.img` | 118.104 bytes |

Os hashes das imagens e o inventário de ferramentas ficam nos relatórios `bootstrap.json` e `artifacts.json`. Eles mudam a cada commit e por isso não são copiados para cá.

## Regras

- Mudar um budget exige atualizar o perfil, repetir os testes afetados e registrar a nova linha de base aqui.
- Um limite não sobe para esconder vazamento ou regressão.
- Outliers ficam no relatório. A média não substitui o pior caso.
