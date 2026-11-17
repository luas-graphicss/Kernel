# Buffers

[English](buffers.en.md)

Um buffer é uma faixa de memória física que o supervisor entrega a processos por capability. É a forma de trocar dados maiores que o payload de uma mensagem sem compartilhar objetos Python entre runtimes.

## Criação

`buffer_create(bytes)` reserva a memória, zerada, e devolve um handle com `READ`, `WRITE`, `MAP` e `DELEGATE`. O tamanho é arredondado para uma potência de dois de páginas de 4096 bytes e conta na cota de memória de quem criou.

| Condição | Erro |
| --- | --- |
| Tamanho zero | `INVALID_ARGUMENT` |
| Mais de 4 MiB | `LIMIT_EXCEEDED` |
| Cota de memória do processo esgotada | `LIMIT_EXCEEDED` |
| Sem frames acima da reserva do supervisor | `OUT_OF_MEMORY` |

## Mapeamento

`buffer_map(handle, direitos, descrição)` mapeia o buffer no processo que chama. `direitos` é `READ` ou `READ | WRITE`; qualquer outro valor devolve `INVALID_ARGUMENT`. A capability precisa ter `MAP` e os direitos pedidos. O supervisor escolhe o endereço e grava uma descrição de 16 bytes: endereço e comprimento, 8 bytes cada.

`buffer_unmap(endereço)` desfaz o mapeamento que começa naquele endereço. Um endereço que não é um mapeamento devolve `INVALID_ARGUMENT`.

## Ownership

Quem cria o buffer é o dono. Outro processo só o alcança por uma capability derivada, com os direitos que o dono escolheu. Um leitor com `READ | MAP` enxerga as mesmas páginas e não consegue mapeá-las para escrita.

Um mapeamento não sobrevive à última capability que o permite:

- Revogar a capability desfaz os mapeamentos feitos com as derivadas, inclusive em outro processo.
- Fechar uma capability mais fraca não desfaz um mapeamento que outra capability do mesmo processo ainda permite.
- Quando o dono morre, o buffer é destruído e ninguém mais consegue mapeá-lo: `buffer_map` devolve `PEER_CLOSED`.

Um buffer cedido a um pedido de dispositivo fica fixado até o pedido ser concluído ou o dispositivo confirmar um reset. Se o dono morre nesse intervalo, o buffer é destruído para os processos como em qualquer outro caso, mas os frames só voltam ao alocador quando o buffer é solto. Com o dispositivo em quarentena eles não voltam. As regras estão em `devices.md`.

Depois que o mapeamento some, um acesso à página é uma falha de página que encerra o processo, e uma syscall que apontava para ela devolve `BAD_ADDRESS`. Isso vale também para uma resposta de IPC que chegaria em um mapeamento removido durante a chamada.

A suíte `memory` cobre criação, limites, leitura e escrita por processos diferentes e remoção do mapeamento durante uma chamada bloqueada. A suíte `capabilities` cobre a relação entre mapeamento e capability.
