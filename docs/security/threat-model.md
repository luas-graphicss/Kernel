# Modelo de ameaças

Descreve contra o quê o kernel se protege, o que fica fora e como cada fronteira de entrada é limitada e testada. Vale para o perfil `qemu-riscv64`.

## Ativos

- Integridade do supervisor nativo, do interpretador supervisor e das políticas congeladas.
- Isolamento entre processos: memória, capabilities e recursos contabilizados.
- Dados persistidos e a garantia de `fsync`.
- Disponibilidade: CPU, memória, filas e a reserva do supervisor.
- Cadeia de build: toolchain, fontes fixadas e a imagem produzida.

## Atores

| Ator | Confiança |
| --- | --- |
| Aplicação em U-mode | Nenhuma. Pode ser maliciosa ou defeituosa |
| Serviço em U-mode | Limitada às capabilities que recebeu; responde pelos recursos que administra |
| Dispositivo do perfil | As respostas não são confiáveis e são validadas. Assume-se que ele só acessa a memória que os descritores nomeiam |
| Peer de rede | Nenhuma |
| Conteúdo de volume, imagem de boot e DTB | Não confiável até ser validado |
| Operador | Confiável: escolhe imagem, perfil e argumentos de boot |

Ficam fora do modelo: host comprometido, firmware malicioso, dispositivo físico malicioso, DMA não mediado e canais laterais de microarquitetura. Validar ponteiros em Python não resolve nenhum deles.

## Fronteiras de entrada

Cada fronteira tem limites, um resultado de erro definido e um teste negativo.

| Fronteira | Limites | Resultado de erro | Evidência |
| --- | --- | --- | --- |
| DTB entregue pelo firmware | 64 KiB, versão 17, blocos em ordem e sem sobreposição, profundidade 8, nomes de até 255 bytes, 16 faixas reservadas, uma faixa de RAM | `boot: device tree rejected reason=` e boot encerrado | Harness `tests/native/device_tree_test.c` com truncamento e mutações sob ASan e UBSan; cenários `device-tree-too-large` e `device-tree-without-memory` |
| Imagem de usuário em `/chosen` | Cabeçalho de 72 bytes, versão 2, base igual à da região de usuário, segmentos em múltiplos de 4096 bytes dentro da região e do módulo, entrada dentro do código presente no arquivo | `policy: rejected=boot-module reason=` e boot encerrado | Harness `tests/native/user_image_test.c`; cenário `incompatible-segment` |
| Argumentos de syscall | Número conhecido; handle resolvido na tabela de quem chama, com tipo e direitos conferidos; faixa de memória inteira mapeada no processo com a permissão da operação; 256 bytes por `debug_write` | Código de erro negado em `a0`, sem efeito parcial | Suítes `memory`, `capabilities` e `ipc` |
| Pedido de criação de processo | 296 bytes, versão 1, nome de módulo de 1 a 64 bytes, argumento de até 64 bytes, até 8 concessões; prioridade e cotas decididas pela política | Código de erro negado; nada do processo novo permanece | Suíte `processes`; cenário `spawn-failures`; `tests/conformance/test_spawn_request.py` |
| Mensagem de IPC | Cabeçalho de 24 bytes, payload de até 4 KiB, 64 mensagens por endpoint, 1 MiB pendente por remetente e 16 MiB no total; uma capability transferida por mensagem | Código de erro negado para quem envia; a mensagem recusada não entra na fila | Harness `tests/native/message_test.c`; suíte `ipc`; `tests/conformance/test_wire.py` |
| Programa em U-mode | Qualquer exceção que não seja `ecall` encerra o processo; a interrupção do timer só o suspende | Relatório `user: fault` e motivo `fault` para quem espera o processo | Cenário `user-fault`; suíte `memory` |
| Argumentos de boot | 255 bytes. A política lê `init=`, com um nome de módulo válido, e `trace=schedule`; o resto é ignorado | Nome inválido encerra o boot com `policy: rejected=init` | Harness do DTB; regra do nome em `tests/conformance/test_spawn_request.py` |

| Dispositivos descritos no DTB | Um controlador de interrupções com até 1023 fontes, uma porta serial, oito transportes VirtIO; interrupções dentro das fontes do controlador; registradores em página própria, fora da RAM e da região de usuário | `boot: rejected=devices reason=` e boot encerrado; transporte que não se identifica fica fora da lista | Harness `tests/native/device_inventory_test.c` com mutações sob ASan e UBSan; suíte `devices` |
| Pedido a um dispositivo | 104 bytes, de 1 a 4 segmentos; cada segmento nomeia um buffer do processo por handle, com o direito da direção e a faixa dentro do buffer; segmentos de leitura antes dos de escrita; 4 pedidos em andamento | Código de erro negado; nenhum buffer fica fixado | Harness `tests/native/virtio_device_test.c`; caso `descriptor-validation` da suíte `devices` |
| Respostas de um dispositivo | Conclusão que nomeia a cabeça de um pedido em andamento e escreve no máximo o que o pedido permitia; configuração lida só quando estável; confirmação de reset em um número limitado de leituras | Dispositivo parado, com `device: slot=N state=failed reason=`, ou em quarentena; a memória continua fixada | Harness `tests/native/virtio_queue_test.c` e `virtio_device_test.c`; `kernel-tool fault-test --suite device-reset` |
| Entrada da porta serial | 256 bytes recebidos em espera; linha de até 255 bytes; quatro linhas em espera; bytes de controle sem significado descartados | Descarte contabilizado; sinal sonoro no eco | `tests/conformance/test_console.py`; cenário `services` da suíte `devices` |
| Pedido a um serviço | Formato exato de cada operação; operações de administração só para o processo que supervisiona o serviço, identificado pelo supervisor; capability inesperada fechada | Resposta de erro; nada muda | Caso `service-authority` da suíte `devices`; suíte `vfs` |
| Caminho | 1024 bytes, 32 componentes, nomes de até 255 bytes de UTF-8 válido sem byte zero; `..` não passa da raiz do namespace | `ACCESS_DENIED`, `INVALID_ARGUMENT` ou `LIMIT_EXCEEDED`, antes de qualquer consulta ao volume | `tests/conformance/test_namespace_paths.py`; casos `path-resolution` e `namespaces-and-rights` da suíte `vfs` |
| Volume persistente | De 8 a 65.536 blocos; árvore inteira verificada na montagem: ponteiros, checksums, gerações, números de nó, profundidade 32, nenhum bloco referenciado duas vezes | Montagem indisponível com `CORRUPTED` ou `UNSUPPORTED`, ou somente leitura; o volume nunca é formatado | `kernel-tool verify-filesystem --corpus tests/faults/storage`, com 21 imagens; `tests/conformance/test_filesystem_format.py` e `test_filesystem_recovery.py`; cenários `unformatted-device`, `unknown-format-version` e `damaged-newest-root` da suíte `storage` |
| Imagem de boot | Cabeçalho e tabela com checksum; até 64 arquivos de até 256 KiB; arquivos contíguos e sem sobra; interface e runtime iguais aos do sistema | Montagem indisponível; arquivo que não confere devolve `CORRUPTED` na leitura | `tests/host/test_boot_image.py`; caso `boot-image` da suíte `vfs` |

Pacotes de rede entram nesta tabela junto com a pilha de rede.

## Invariantes testáveis

- Um DTB inválido encerra o boot antes de o interpretador iniciar. Uma imagem de usuário inválida o encerra antes de qualquer processo existir.
- Um processo não lê, escreve nem executa memória de outro processo, do supervisor, livre ou de dispositivos. O acesso é uma falha de página que encerra só esse processo.
- Uma syscall com ponteiro para memória que o processo não mapeou, ou mapeou sem a permissão necessária, devolve `BAD_ADDRESS` e não lê nem escreve nada.
- Um handle liberado nunca volta a resolver, mesmo depois de o slot ser reutilizado.
- Derivar ou transferir uma capability nunca amplia direitos, e o inteiro de um handle escrito em um payload não transfere autoridade.
- Um frame privado é zerado antes de servir a outro processo.
- Cobrar um recurso é atômico: ou todos os limites passam, ou nada muda. A soma das contas é igual ao uso global.
- Uma criação de processo que falha em qualquer alocação devolve tudo o que já tinha reservado.
- Depois de 10.000 ciclos de processo e IPC, os contadores de frames livres, objetos, capabilities, endpoints, mensagens e buffers são os mesmos do fim do aquecimento.
- Nenhuma interrupção é aceita em S-mode, e os caminhos do timer e das interrupções externas não executam Python nem alocam.
- Um driver nunca informa nem recebe um endereço físico, e a fila de um dispositivo não é mapeada em nenhum processo.
- A memória cedida a um pedido de dispositivo não volta ao alocador enquanto o dispositivo puder alcançá-la. Um reset não confirmado a deixa em quarentena.
- Um caminho nunca resolve para fora da raiz do namespace que o cliente recebeu, e um namespace derivado nunca tem mais direitos que a origem.
- Um handle de arquivo só vale para o processo que abriu, na instância do serviço que o emitiu.
- Um `SYNC` confirmado sobrevive à perda de qualquer escrita ainda não seguida de flush. Depois de um crash, a montagem mostra um commit inteiro.
- Um volume que não passa na verificação não é montado para escrita, e nenhum volume é criado, formatado ou reparado para o boot seguir.
- Nenhuma camada repete sozinha uma operação com efeito cujo resultado não conhece.
- O ELF do kernel é estático, não tem símbolo indefinido e só liga `libgcc` além dos objetos do projeto.

## Riscos residuais

- O isolamento foi exercitado só no QEMU com TCG e um hart. Nenhuma placa física foi testada.
- `debug_write` não exige capability: qualquer processo escreve no console de diagnóstico, 256 bytes por chamada.
- O serviço de arquivos é confiável para os volumes que administra, e cada driver para o dispositivo que recebeu. Um defeito em um deles corrompe ou expõe os dados que passam por ele, mas não alcança a memória de outros processos.
- CRC-32 detecta corrupção acidental. Ele não autentica um volume contra quem o altera de propósito e recalcula os checksums.
- A durabilidade foi demonstrada no `virtio-blk` do QEMU, contra perda, reordenação e corte de escritas ainda não seguidas de flush. Um disco que confirme um flush que não fez está fora do que foi testado.
- Frames em quarentena só voltam no boot seguinte. Falhas repetidas de reset reduzem a memória disponível.
- A entropia vem do dispositivo `virtio-rng` do QEMU. Sem ele o sistema não oferece entropia, e a qualidade dos bytes é a do host.
- O `init` nasce com a capability do sistema. Um defeito nele alcança a criação de processos e a leitura dos contadores.
- O hash de um download prova que o arquivo é o que o lock registrou, não que o upstream é confiável.
- TCG não reproduz temporização nem falhas de hardware real.
