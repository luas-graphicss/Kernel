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

Volumes, caminhos, respostas de dispositivos e pacotes de rede entram nesta tabela junto com o mecanismo que os introduz.

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
- Nenhuma interrupção é aceita em S-mode, e o caminho do timer não executa Python nem aloca.
- O ELF do kernel é estático, não tem símbolo indefinido e só liga `libgcc` além dos objetos do projeto.

## Riscos residuais

- O isolamento foi exercitado só no QEMU com TCG e um hart. Nenhuma placa física foi testada.
- `debug_write` não exige capability: qualquer processo escreve no console de diagnóstico, 256 bytes por chamada.
- O `init` nasce com a capability do sistema. Um defeito nele alcança a criação de processos e a leitura dos contadores.
- O hash de um download prova que o arquivo é o que o lock registrou, não que o upstream é confiável.
- TCG não reproduz temporização nem falhas de hardware real.
