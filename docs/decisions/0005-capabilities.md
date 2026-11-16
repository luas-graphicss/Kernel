# ADR 0005: Capabilities e identidade geracional

Estado: aceita.

## Contexto

Autoridade ambiente, em que um processo pode tudo o que o usuário dele pode, impede delegação mínima e torna difícil auditar o que um serviço alcança. O kernel também precisa de identificadores que não voltem a valer depois que o objeto morreu.

## Decisão

Toda autoridade é uma capability: objeto, geração, direitos e vínculo de delegação. Direitos nomeiam operações concretas, como enviar, receber, ler, escrever, mapear, delegar e administrar.

Um processo referencia uma capability por um handle de 64 bits, local à sua própria tabela:

| Bits | Campo |
| --- | --- |
| 0 a 23 | Índice do slot |
| 24 a 55 | Geração, a partir de 1 |
| 56 a 63 | Reservados, sempre zero |

O valor zero nunca é um handle válido. Liberar um slot aumenta a geração; quando o contador chega ao máximo, o slot é aposentado em vez de reutilizado. Um handle antigo não volta a resolver.

Regras de autoridade:

- O supervisor valida a capability em toda operação, mesmo quando o chamador usa a biblioteca cliente oficial.
- Delegar só reduz direitos. A profundidade máxima de delegação é 16.
- Copiar o inteiro de um handle para outro processo não transfere nada. A transferência é uma operação nativa que instala a capability na tabela do destinatário.
- A identidade do remetente vem de metadados preenchidos pelo supervisor, nunca de um campo do payload.
- Cada processo tem no máximo 128 capabilities. O `init` concede só o que o manifesto do serviço declara.

A codificação e o modelo da tabela estão em `src/kernel_protocol/identity/`, o formato em `specs/abi/handles.md` e as operações em `specs/abi/capabilities.md`. A tabela que o supervisor aplica é nativa, em `native/supervisor/capabilities/` e `native/supervisor/objects/`.

## Consequências

Um serviço não atua como procurador: ele autoriza a operação sobre o recurso com a capability que o cliente apresentou.

Toda syscall que recebe um handle o resolve na tabela de quem chama e confere o tipo do objeto e os direitos. O direito de receber de um endpoint não é derivado nem transferido: só quem criou o endpoint recebe dele.

## Hipóteses a confirmar

- O custo de revogar cabe em uma syscall. A revogação marca os descendentes e depois varre o registro de capabilities para remover os marcados; esse custo ainda não foi medido.
- 24 bits de índice e 32 de geração bastam para a vida útil esperada de um slot.
