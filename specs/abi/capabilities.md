# Capabilities

Toda autoridade de um processo é uma capability na sua tabela: um objeto do supervisor, um conjunto de direitos e o vínculo com a capability de que foi derivada. O processo a nomeia por um handle, no formato de `handles.md`. As decisões estão no ADR 0005.

## Direitos

| Bit | Nome | Permite |
| --- | --- | --- |
| `0x01` | `RIGHT_SEND` | Enviar a um endpoint; responder com uma capability de resposta |
| `0x02` | `RIGHT_RECEIVE` | Receber de um endpoint |
| `0x04` | `RIGHT_READ` | Mapear um buffer para leitura; esperar um processo; ler os contadores do sistema |
| `0x08` | `RIGHT_WRITE` | Mapear um buffer para escrita |
| `0x10` | `RIGHT_MAP` | Mapear um buffer |
| `0x20` | `RIGHT_DELEGATE` | Derivar, transferir ou conceder a capability |
| `0x40` | `RIGHT_ADMIN` | Criar processos com a capability do sistema; encerrar ou interromper um processo |

## Objetos

| Tipo | Valor | Como nasce | Direitos iniciais |
| --- | --- | --- | --- |
| Sistema | 1 | Entregue ao `init` como primeiro handle | `ADMIN`, `READ`, `DELEGATE` |
| Processo | 2 | `process_spawn`, na tabela de quem criou | `READ`, `ADMIN`, `DELEGATE` |
| Endpoint | 3 | `endpoint_create` | `SEND`, `RECEIVE`, `DELEGATE` |
| Buffer | 4 | `buffer_create` | `READ`, `WRITE`, `MAP`, `DELEGATE` |
| Resposta | 5 | Entregue ao servidor junto com uma chamada | `SEND`, uso único |

Um processo começa só com o que o criador concedeu no pedido de criação. Não há nomes globais, caminhos nem identificadores de processo que valham como autorização.

## Operações

| Chamada | Regra |
| --- | --- |
| `capability_derive(handle, direitos)` | Cria na mesma tabela uma capability derivada. Exige `DELEGATE` na origem, e os direitos pedidos precisam estar contidos nos da origem; caso contrário, `ACCESS_DENIED`. Direitos vazios ou com bit desconhecido devolvem `INVALID_ARGUMENT`. A derivada fica um nível mais funda que a origem |
| `capability_inspect(handle)` | Devolve o tipo nos bits 0 a 7, os direitos nos bits 8 a 15 e a profundidade a partir do bit 16 |
| `capability_revoke(handle)` | Invalida todas as capabilities derivadas da indicada, em qualquer processo, e devolve quantas eram. A capability indicada e as irmãs dela continuam válidas |
| `capability_close(handle)` | Remove a capability da tabela. As derivadas continuam válidas e passam a depender da capability de que a removida derivava |

Um handle fechado ou revogado não volta a valer, mesmo quando o slot é reutilizado: o slot recebe outra geração.

## Transferência

Uma capability muda de processo de duas formas. Nas duas o supervisor instala uma capability derivada na tabela do destino:

- No pedido de `process_spawn`, como concessão. O filho a encontra na lista de handles do bloco de início, na ordem do pedido.
- Em `ipc_send`, `ipc_call` ou `ipc_reply`, como capability transferida. O handle novo chega nos metadados da mensagem, nunca no payload.

Transferir exige `DELEGATE`. O direito `RECEIVE` não é derivado, concedido nem transferido: só o processo que criou o endpoint recebe dele. Uma capability de resposta não é transferida.

Escrever o inteiro de um handle em um payload não transfere nada. O número só tem significado na tabela do processo que o recebeu do supervisor.

## Vida do objeto

O objeto existe enquanto alguma capability o referencia. Quando o dono de um endpoint morre, ou fecha a capability com `RECEIVE`, o endpoint fecha: as mensagens pendentes são descartadas, quem envia recebe `PEER_CLOSED` e quem esperava resposta é acordado com o mesmo erro. Quando um processo termina, todas as capabilities da sua tabela são fechadas.

## Limites

| Limite | Valor | Ao atingir |
| --- | --- | --- |
| Capabilities por processo | 128 | `LIMIT_EXCEEDED`, sem efeito parcial |
| Profundidade de derivação | 16 | `LIMIT_EXCEEDED` |
| Concessões em um pedido de criação | 8 | `INVALID_ARGUMENT` |

Os valores estão em `native/include/kernel/abi/rights.h` e em `kernel_protocol.identity.rights`. A suíte `capabilities` do `kernel-tool test` cobre handles antigos e forjados, delegação atenuada, revogação com descendentes, cota, ausência de autoridade ambiente e mapeamentos que seguem a capability.
