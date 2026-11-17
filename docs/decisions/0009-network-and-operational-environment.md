# ADR 0009: Rede e ambiente operacional em espaço de usuário

[English](0009-network-and-operational-environment.en.md)

Estado: aceita.

## Contexto

Faltavam ao sistema a rede e o que um operador usa: um shell, programas carregados do disco, uma configuração e alguém que mantenha os serviços de pé. Tudo isso lida com entrada não confiável: pacotes de qualquer peer, texto digitado, arquivos de programa, um arquivo de configuração.

O ADR 0002 já diz que protocolos, drivers e aplicações ficam em Python. O que precisava de decisão era onde cada peça roda, quem tem autoridade sobre o quê e o que muda no código nativo.

## Decisão

A pilha de rede é um processo de usuário só. `kernel_services.network.main` contém o driver do `virtio-net`, Ethernet, ARP, IPv4, ICMP, UDP, TCP e os sockets. O driver não é um processo à parte: cada quadro custaria uma troca de mensagens a mais, e o driver sozinho não serve a ninguém além da pilha. A capability do dispositivo fica nesse processo e não é entregue a mais ninguém.

Um socket se alcança por capability. O serviço emite acessos, que são endpoints dele com um conjunto de direitos, e só cria sessão para quem prova ter um. Acessos são restringidos e revogados pelo próprio serviço, porque os direitos de rede, como conectar, escutar e inspecionar, não cabem nos direitos genéricos de uma capability de endpoint.

Toda memória de rede é contada. Cada conexão tem buffers fixos, o serviço tem um orçamento único de bytes, e filas, tabelas e montagens têm tamanho máximo. Um pacote que não cabe é descartado e contado; nunca aumenta um limite.

O supervisor passa a programar até duas filas por dispositivo VirtIO, e o pedido de `device_submit` nomeia a fila. É a única mudança no transporte: o `virtio-net` recebe por uma fila e transmite por outra.

O sistema é mantido por um gerente em U-mode, `kernel_services.manager.main`, que substitui o `init` de conferência quando o boot pede. Ele é o único processo com a capability do sistema. Lê a configuração, inicia os serviços na ordem das dependências, reinicia quem morre dentro de um orçamento por janela e conduz a parada.

A configuração é um documento de dados, com seções, chaves, números, textos e listas. Ela não é Python. Um arquivo de configuração executável rodaria com a autoridade do gerente, e validar um documento inteiro antes de aplicar qualquer parte dele exige que ele seja só dados.

O controle do sistema autoriza pela identidade de quem chama, que o supervisor grava em cada mensagem, e não pela posse do endpoint. O gerente sabe quais processos admitiu e com que direitos. Uma aplicação que obtivesse o endpoint de controle continuaria sem ser atendida.

Uma aplicação é um arquivo de código-fonte Python, lido do volume e executado em um processo novo. Para isso o perfil `user` do runtime passa a ter o compilador do MicroPython, o que muda o ADR 0003 nesse ponto. O perfil `supervisor` continua sem compilador. Imports continuam restritos aos módulos congelados: um programa é um arquivo só.

Desligar e reiniciar passam por uma syscall nova, `system_power`, que exige `ADMIN` na capability do sistema e só registra a ação. O supervisor a executa quando o último processo termina, depois de conferir os recursos, como em qualquer término.

As interfaces estão em `specs/network/`, `specs/system/` e `specs/abi/`.

## Consequências

Um defeito na pilha de rede derruba um processo, e o gerente o reinicia. As conexões abertas se perdem e os clientes precisam entrar de novo; nada é repetido por eles. O armazenamento e o shell não dependem da rede e seguem em uso.

A pilha roda igual em CPython, porque não tem dependência do kernel além do driver. Os testes de conformidade exercitam as máquinas de estado com dois lados e um fio simulado, com relógio controlado, e é ali que perda, reordenação, janela zero e wraparound de sequência são cobertos com precisão. O QEMU cobre a integração com um peer real.

O compilador entra em todo processo de usuário, inclusive nos serviços, que não o usam. Isso aumenta a imagem de usuário e a superfície de cada processo, mas não a TCB: o compilador roda em U-mode, sobre código que o próprio processo escolheu carregar.

O gerente concentra autoridade. Ele é pequeno, não interpreta entrada de rede nem programas, e trata a configuração só depois de validada.

A vazão da rede é limitada por quatro pedidos por fila e por uma cópia de cada quadro entre o buffer do driver e a pilha. Nenhuma medição mostrou ainda que isso importa para o perfil.

## Hipóteses a confirmar

- Buffers de 16 KiB por conexão e 1 MiB no serviço bastam para as cargas do perfil. As transferências medidas vão até 128 KiB por conexão.
- O controle de congestionamento se comporta bem com perda acima de 3% e com atrasos longos. Só perda, duplicação e reordenação moderadas foram exercitadas contra um peer real.
- Uma interface e uma rota padrão bastam. Não há encaminhamento nem mais de uma interface.
- O custo de compilar um programa ao carregar cabe no uso interativo. Os programas medidos têm até 44 linhas.
