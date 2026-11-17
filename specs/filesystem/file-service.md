# Serviço de arquivos

[English](file-service.en.md)

O serviço de arquivos é um processo em U-mode, `kernel_services.filesystem.main`. Ele monta os volumes, resolve caminhos e entrega arquivos e diretórios por mensagens de IPC. Um cliente só alcança o que está abaixo da raiz do namespace que recebeu.

As mensagens seguem `specs/abi/messages.md`. Os números de operação e os formatos estão em `kernel_protocol.services.files`, e a biblioteca cliente em `kernel_client.files`.

## Montagens

| Nome | Origem | Modo |
| --- | --- | --- |
| `tmp` | Volume de 64 blocos em memória, criado a cada início do serviço | Leitura e escrita, sem persistência |
| `boot` | Disco `kernel-boot`, no formato de `boot-image.md` | Somente leitura |
| `data` | Disco `kernel-data`, no formato de `volume-format.md` | O que a recuperação decidir |

O `init` identifica cada disco pelo número de série que o dispositivo informa e entrega ao serviço o endpoint do serviço de blocos correspondente. Um disco ausente não é montado. Um disco que não monta fica registrado com o erro, e o serviço inicia com as outras montagens.

A raiz do serviço é um diretório que só lista as montagens. Nada é criado, renomeado ou removido nela: `READ_ONLY`.

## Namespaces e sessões

Um namespace é um diretório raiz e um conjunto de direitos. O cliente o recebe como capability de um endpoint.

| Bit | Direito | Permite |
| --- | --- | --- |
| `0x1` | `NAMESPACE_READ` | Abrir para leitura, listar e consultar |
| `0x2` | `NAMESPACE_WRITE` | Criar, escrever, truncar, renomear e remover |
| `0x4` | `NAMESPACE_DELEGATE` | Criar namespaces menores |

Para usar um namespace, o cliente envia a operação `ENTER` pela capability do namespace e depois chama `ENTER` no endpoint do serviço. O supervisor informa quem enviou cada mensagem, e é isso que liga as duas. A resposta traz a instância do serviço, o token da sessão e os direitos. Toda operação seguinte leva a instância e o token ou o handle de um arquivo aberto.

`SUBSPACE` cria um namespace com raiz em um diretório abaixo do atual e com direitos que o atual já tem. Pedir mais devolve `ACCESS_DENIED`. O novo namespace chega como capability e pode ser concedido a outro processo. `DROP` o destrói, junto com os namespaces criados a partir dele, as sessões e os arquivos abertos por elas. `LEAVE` encerra a sessão.

O namespace raiz, com todos os direitos, é entregue só ao supervisor do serviço, pela operação `ROOT`.

| Limite | Valor |
| --- | --- |
| Namespaces | 16 |
| Sessões | 16 |
| Arquivos e diretórios abertos | 64 |
| Pedidos de entrada em espera | 16 |

No limite, a operação devolve `LIMIT_EXCEEDED`.

## Caminhos

Um caminho é uma sequência de nomes separados por `/`, resolvida a partir da raiz do namespace.

- Componentes vazios e `.` são ignorados.
- `..` remove o componente anterior. Subir acima da raiz do namespace devolve `ACCESS_DENIED`; o serviço não consulta o volume para decidir isso.
- Cada nome segue as regras de `volume-format.md`: até 255 bytes de UTF-8 válido, sem byte zero. Um nome inválido devolve `INVALID_ARGUMENT`.
- Um caminho tem até 1024 bytes e até 32 componentes depois de resolvido. Acima disso, `LIMIT_EXCEEDED`.

Não há diretório corrente, symlinks nem hard links.

## Operações

| Número | Operação | Sujeito | Pedido | Resposta |
| --- | --- | --- | --- | --- |
| 16 | `ROOT` | Nenhum | Vazio | Capability do namespace raiz. Só o supervisor |
| 17 | `EVICT` | Nenhum | Identidade de um processo | Encerra as sessões desse processo. Só o supervisor |
| 18 | `ENTER` | Nenhum | Vazio | Instância, sessão e direitos |
| 19 | `LEAVE` | Sessão | Vazio | Vazia |
| 20 | `SUBSPACE` | Sessão | Direitos e caminho | Número do namespace e a capability dele |
| 21 | `DROP` | Sessão | Número do namespace | Vazia |
| 22 | `STATUS` | Sessão | Vazio | Estado de cada montagem |
| 23 | `OPEN` | Sessão | Flags e caminho | Handle, tipo e tamanho |
| 24 | `CLOSE` | Arquivo | Vazio | Vazia |
| 25 | `READ` | Arquivo | Offset e quantidade | Bytes lidos |
| 26 | `WRITE` | Arquivo | Offset e dados | Bytes aceitos |
| 27 | `TRUNCATE` | Arquivo | Tamanho | Vazia |
| 28 | `SYNC` | Arquivo | Vazio | Vazia |
| 29 | `STAT` | Sessão | Caminho | Tipo e tamanho |
| 30 | `LIST` | Arquivo | Cursor | Próximo cursor e entradas |
| 31 | `MAKE_DIRECTORY` | Sessão | Caminho | Vazia |
| 32 | `REMOVE` | Sessão | Caminho | Vazia |
| 33 | `RENAME` | Sessão | Dois caminhos | Vazia |

Um pedido com sujeito começa com a instância do serviço e o token ou handle, 8 bytes cada. Uma resposta de erro leva a flag de erro da mensagem e o código em 4 bytes.

### Abrir

| Flag | Valor | Efeito |
| --- | --- | --- |
| `OPEN_READ` | `0x01` | Leitura |
| `OPEN_WRITE` | `0x02` | Escrita e truncamento |
| `OPEN_CREATE` | `0x04` | Cria o arquivo se o caminho não existe |
| `OPEN_EXCLUSIVE` | `0x08` | Com `OPEN_CREATE`, `ALREADY_EXISTS` se o caminho existe |
| `OPEN_TRUNCATE` | `0x10` | Esvazia o arquivo ao abrir. Exige `OPEN_WRITE` |
| `OPEN_DIRECTORY` | `0x20` | Abre um diretório para listar |

Um diretório só abre com `OPEN_DIRECTORY`, sem flags de mudança. Abrir um arquivo como diretório devolve `NOT_A_DIRECTORY`, e o contrário, `IS_A_DIRECTORY`. As flags de leitura exigem `NAMESPACE_READ` e as de mudança, `NAMESPACE_WRITE`. Abrir para mudança em uma montagem somente leitura devolve `READ_ONLY`.

### Ler, escrever e listar

Uma mensagem carrega até 4032 bytes de dados. `READ` devolve menos que o pedido no fim do arquivo e nada depois dele. `WRITE` devolve quantos bytes aceitou, que podem ser menos que os enviados quando o volume enche; nenhum byte aceito devolve `NO_SPACE`. Escrever além do fim estende o arquivo, e o intervalo não escrito lê como zeros. Ler ou escrever zero bytes é válido.

`LIST` devolve as entradas em ordem de nome, com tipo e tamanho, a partir do cursor. A resposta traz o cursor da página seguinte, ou `0xFFFFFFFF` no fim.

### O que um handle garante

Um handle vale para o processo que abriu, na instância do serviço que o emitiu. Em qualquer outro caso a operação devolve `INVALID_HANDLE`. O handle nomeia o arquivo, não o caminho: renomear o arquivo não afeta quem o tem aberto.

Remover um arquivo aberto tira o nome do diretório na hora. Quem o tem aberto continua lendo o conteúdo até fechar; escrever ou truncar devolve `NOT_FOUND`. Os blocos são liberados quando o último handle fecha.

Vários clientes podem abrir o mesmo arquivo. O serviço atende um pedido de cada vez, então cada operação enxerga o resultado inteiro das anteriores.

## Atomicidade e durabilidade

Uma operação aceita muda o volume em memória. Ela não é durável até um commit, e `CLOSE` não faz commit.

`SYNC` em qualquer arquivo ou diretório aberto faz o commit da montagem inteira, como descreve `volume-format.md`, e só responde depois do flush que segue a publicação do root. É o `fsync` deste sistema: quando a resposta chega, tudo o que foi aceito naquela montagem até ali sobrevive a uma queda de energia. O commit também acontece quando o serviço para de forma ordenada, e pode acontecer antes, quando o volume precisa liberar blocos.

Depois de um crash, a montagem mostra o resultado de um commit inteiro: todas as operações até ele, e nenhuma depois.

| Operação | Entre dois commits | Erros próprios |
| --- | --- | --- |
| Criar arquivo ou diretório | O nome aparece na hora para todos os clientes | `ALREADY_EXISTS`, `LIMIT_EXCEEDED` no diretório cheio ou fundo demais, `NO_SPACE` |
| Escrever | Os dados aparecem na hora. O conteúdo antigo dos blocos tocados continua no dispositivo até o commit | `LIMIT_EXCEEDED` acima do maior arquivo, `NO_SPACE` |
| Truncar | Encurtar descarta o fim; estender cria um buraco | `LIMIT_EXCEEDED`, `NO_SPACE` |
| Renomear | O nome antigo some e o novo aparece na mesma operação. Um destino existente do mesmo tipo é substituído; diretório só substitui diretório vazio | `NOT_FOUND`, `IS_A_DIRECTORY`, `NOT_A_DIRECTORY`, `NOT_EMPTY`, `LIMIT_EXCEEDED` no destino cheio ou fundo demais, `INVALID_ARGUMENT` ao mover um diretório para dentro dele mesmo, `UNSUPPORTED` entre montagens |
| Remover | O nome some na hora. Diretório precisa estar vazio | `NOT_FOUND`, `NOT_EMPTY` |

Uma operação recusada por validação, direito, limite ou falta de espaço não muda nada. Um rename nunca é visto pela metade, nem por outro cliente nem depois de um crash: ou o commit que o contém foi publicado, ou o nome antigo continua lá.

Em `tmp`, `SYNC` faz o mesmo commit sobre memória e nada sobrevive ao serviço. Em `boot`, `SYNC` não faz nada.

## Falhas

| Situação | O que o cliente recebe |
| --- | --- |
| Montagem somente leitura | `READ_ONLY` em toda mudança |
| Bloco que não confere com o checksum | `CORRUPTED` na operação que o leu |
| Erro do dispositivo ao gravar os dados de um arquivo | O erro no `WRITE` ou no `TRUNCATE`. Uma escrita mantém os blocos gravados antes do erro e o tamanho que eles cobrem; um truncamento que falha não muda o arquivo. O volume continua em uso |
| Erro do dispositivo antes de o root ser publicado | `IO_ERROR` no `SYNC`. O estado durável é o do commit anterior |
| Erro do dispositivo durante a publicação do root | `UNKNOWN_OUTCOME` no `SYNC`. O commit pode ter sido publicado ou não |
| Qualquer operação depois de uma das duas | `IO_ERROR`, até o serviço ser reiniciado |
| Serviço de blocos que não responde | `IO_ERROR` em leitura, `UNKNOWN_OUTCOME` em escrita e flush |

`UNKNOWN_OUTCOME` não é para repetir às cegas. O cliente descobre o que aconteceu depois que o volume é montado de novo, lendo o que precisa.

## Reinício

O `init` é o supervisor do serviço: só ele pode pedir `ROOT`, `EVICT` e a parada. Ao reiniciar o serviço de arquivos, ele para a instância antiga, pede a cada serviço de blocos que esqueça o cliente antigo e inicia outra instância, que monta os volumes de novo com a recuperação normal.

A instância nova tem outra identidade. Sessões, handles e capabilities de namespace da instância anterior devolvem `INVALID_HANDLE` ou `PEER_CLOSED`; nenhum pedido antigo é reexecutado. O cliente entra de novo em um namespace e reabre o que precisa.

A suíte `vfs` cobre caminhos, arquivos e diretórios, handles, namespaces e direitos, a imagem de boot, clientes simultâneos e o reinício do serviço. A suíte `storage` cobre durabilidade depois de `SYNC`, volume cheio, reinício do serviço de blocos e os volumes que o sistema recusa ou monta somente leitura.
