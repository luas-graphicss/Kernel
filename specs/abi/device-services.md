# Serviços de dispositivo

Os drivers são processos em U-mode que o `init` inicia a partir do manifesto em `kernel_services.init.manifest`. Cada um recebe a capability de um dispositivo, descrita em `devices.md`, e a oferece a outros processos por um endpoint de IPC. As mensagens seguem `messages.md`, e os formatos estão em `kernel_protocol.services`.

| Serviço | Programa | Dispositivo | Prioridade |
| --- | --- | --- | --- |
| Console | `kernel_services.console.main` | Porta serial | 1 |
| Entropia | `kernel_services.entropy.main` | VirtIO modelo 4 | 2 |
| Blocos | `kernel_services.block.main`, um processo por disco | VirtIO modelo 2 | 1 |
| Arquivos | `kernel_services.filesystem.main` | Nenhum: recebe os endpoints dos serviços de blocos | 2 |

O serviço de arquivos está em `specs/filesystem/file-service.md`.

Quando o boot recebe `init=kernel_services.manager.main`, quem inicia estes serviços é o gerente do sistema, com a prioridade, o heap e a política de reinício da configuração. Ele inicia também o serviço de rede, `kernel_services.network.main`, que recebe o dispositivo VirtIO de modelo 1 e traz o driver dentro do próprio processo. O gerente está em `specs/system/control-service.md` e a rede em `specs/network/`. O ciclo de vida abaixo vale para os dois casos.

## Ciclo de vida

As operações 1 a 15 são do ciclo de vida, iguais em todos os serviços. As de cada serviço começam em 16.

| Número | Operação | Sentido | Conteúdo |
| --- | --- | --- | --- |
| 1 | `REGISTER` | Do serviço para o `init`, pelo endpoint de registro | Transfere o endpoint do serviço. O serviço de blocos envia também o número de série do disco |
| 2 | `STOP` | Do `init` para o serviço | Vazio. O serviço encerra o que tem em andamento, responde e termina com status 0 |

O argumento de início de um serviço traz a identidade do processo que o supervisiona, em 8 bytes. `STOP` e as operações de administração só são aceitas desse processo; de qualquer outro devolvem `ACCESS_DENIED`. A identidade vem dos metadados que o supervisor preenche em cada mensagem, não do payload.

O `init` espera o registro por até 20 segundos e a parada por até 20 segundos. Um serviço que não registra é encerrado e aparece como `failed`; um que não atende à parada é encerrado com `process_kill`.

Uma resposta de erro leva a flag de erro da mensagem e o código em 4 bytes. Um pedido com uma capability que a operação não espera devolve `INVALID_ARGUMENT`, e a capability é fechada. Uma operação desconhecida devolve `UNSUPPORTED`.

## Blocos

Cada cliente entrega ao serviço um buffer seu, e as transferências acontecem dentro desse buffer. Os dados não passam pelo payload das mensagens.

| Número | Operação | Pedido | Resposta |
| --- | --- | --- | --- |
| 16 | `ATTACH` | Vazio, com a capability de um buffer com `READ` e `WRITE` | Geometria |
| 17 | `READ` | Transferência | Vazia. Os setores ficam no buffer |
| 18 | `WRITE` | Transferência | Vazia |
| 19 | `FLUSH` | Vazio | Vazia, depois de o dispositivo confirmar o flush |
| 20 | `DETACH` | Vazio | Vazia. O serviço fecha o buffer do cliente |
| 21 | `EVICT` | Identidade de um cliente | Vazia. Só o supervisor do serviço |

Geometria, 44 bytes:

| Offset | Tamanho | Campo |
| --- | --- | --- |
| 0 | 8 | Setores do disco |
| 8 | 4 | Bytes por setor: 512 |
| 12 | 4 | Flags: `0x1` somente leitura, `0x2` tem flush |
| 16 | 8 | Instância do serviço |
| 24 | 20 | Número de série do disco, completado com zeros |

Transferência, 16 bytes: primeiro setor, em 8 bytes, quantidade de setores, em 4, e offset dentro do buffer do cliente, em 4.

| Condição | Erro |
| --- | --- |
| `ATTACH` sem buffer, ou com buffer sem `READ` e `WRITE` | `INVALID_ARGUMENT` |
| Quinto cliente | `LIMIT_EXCEEDED` |
| Transferência ou flush sem `ATTACH` | `BAD_STATE` |
| Setores fora do disco | `INVALID_ARGUMENT` |
| Faixa fora do buffer do cliente | `INVALID_ARGUMENT`, devolvido pelo supervisor ao driver |
| Escrita em disco somente leitura | `READ_ONLY` |
| Flush em disco sem o comando | `UNSUPPORTED` |
| O dispositivo informou falha | `IO_ERROR` |
| O dispositivo não respondeu em 5 segundos | `IO_ERROR` em leitura; `UNKNOWN_OUTCOME` em escrita e flush |

Um dispositivo que não responde é reiniciado pelo driver antes de a resposta sair, o que solta a memória do pedido. Se o reset também falha, o dispositivo fica em quarentena e todo pedido seguinte devolve `IO_ERROR`.

A biblioteca cliente, `kernel_client.blocks`, trata do mesmo jeito um serviço de blocos que morre ou não responde: `IO_ERROR` em leitura e `UNKNOWN_OUTCOME` em escrita e flush. Nenhum pedido é repetido sozinho.

O flag de flush é o que autoriza um volume a aceitar escrita. Sem ele o serviço de arquivos monta o volume somente leitura.

## Console

| Número | Operação | Pedido | Resposta |
| --- | --- | --- | --- |
| 16 | `WRITE` | Até 1024 bytes de texto | Quantos bytes foram aceitos, em 4 bytes |
| 17 | `READ_LINE` | Tempo de espera em nanossegundos, em 8 bytes. `0xFFFFFFFFFFFFFFFF` espera sem limite | A linha, sem o fim de linha |

Saída: cada `\n` sai como `\r\n`. O serviço escreve enquanto o transmissor aceita e desiste depois de 1 segundo; a resposta diz quantos bytes do pedido saíram, e o cliente decide se reenvia o resto. Um pedido acima de 1024 bytes devolve `MESSAGE_TOO_LARGE`.

Entrada: o serviço monta linhas a partir dos bytes recebidos e os ecoa.

| Byte recebido | Efeito |
| --- | --- |
| `\r`, `\n` ou `\r\n` | Termina a linha |
| Backspace ou delete | Apaga o último caractere, inteiro mesmo quando ele ocupa vários bytes de UTF-8 |
| `0x15` | Apaga a linha |
| Outro byte de controle | Descartado |
| Byte além de 255 na linha | Descartado, com um sinal sonoro no eco |

Até quatro linhas completas esperam por um leitor. As seguintes são descartadas e contadas.

Um só leitor espera por vez. Um `READ_LINE` novo encerra o anterior com `CANCELLED`. Sem linha até o fim da espera, a resposta é `TIMED_OUT`.

O console de emergência do supervisor não depende deste serviço.

## Entropia

| Número | Operação | Pedido | Resposta |
| --- | --- | --- | --- |
| 16 | `READ` | Quantidade de bytes, de 1 a 256, em 4 bytes | Os bytes entregues pelo dispositivo |

Uma quantidade fora da faixa devolve `INVALID_ARGUMENT`. Um dispositivo que não responde em 2 segundos é reiniciado, e o pedido devolve `IO_ERROR`.

Sem dispositivo de entropia o serviço não existe. O `init` informa `init: entropy=unavailable`, e nenhum outro componente entrega bytes no lugar dele.

## Evidência

A suíte `devices` cobre os drivers e, no cenário `services`, os três serviços e a recusa de quem não tem autoridade. O cenário `without-entropy` inicia o sistema sem o dispositivo de entropia. `tests/conformance/test_console.py` cobre a disciplina de linha e `tests/conformance/test_services.py`, o manifesto.
