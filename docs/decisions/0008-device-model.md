# ADR 0008: Dispositivos e DMA mediado

Estado: aceita.

## Contexto

O perfil de referência não tem IOMMU. Quem escreve um endereço físico em uma fila de dispositivo faz o dispositivo ler ou gravar essa memória, seja de quem for. Um driver em U-mode com os registradores e a fila mapeados teria, na prática, o privilégio do supervisor.

Ao mesmo tempo o projeto quer os drivers em Python, fora da TCB, com o comportamento do dispositivo onde ele pode ser lido e testado.

## Decisão

O transporte é nativo e o driver é Python.

O supervisor descobre os dispositivos no DTB, mapeia os registradores só para si, negocia com o dispositivo e é dono da fila. O driver recebe uma capability do dispositivo e pede transferências nomeando buffers por handle, offset e comprimento. O supervisor confere a capability de cada buffer, fixa a memória, escreve os descritores e avisa o dispositivo. O driver nunca informa nem recebe um endereço físico, e a fila não é mapeada em nenhum processo.

Na volta, o supervisor confere o que o dispositivo diz: uma conclusão precisa nomear um pedido em andamento e não pode declarar mais bytes do que o pedido permitia. O supervisor guarda a cadeia de cada pedido em memória própria e nunca relê a tabela de descritores. Um dispositivo que viola o protocolo é parado, com a memória ainda fixada.

O que fica em cada lado:

| Nativo | Python, em U-mode |
| --- | --- |
| Descoberta no DTB e posse por capability | Quais dispositivos o sistema usa e quem recebe cada um |
| Negociação do VirtIO, endereços da fila, descritores, barreiras e notificação | Features próprias do dispositivo, formato de cada pedido |
| Validação da fila de conclusões | Deadline de cada pedido, reset depois do deadline, classificação do erro |
| Fixação de buffers, reset e quarentena | Protocolo oferecido aos clientes |
| Transmissão e recepção de bytes da UART; console de emergência | Disciplina de linha e comportamento do console |
| Controlador de interrupções e tratadores | Nada: Python não executa em interrupção |

Regras que saem daí:

- Só VirtIO-MMIO versão 2 com `VIRTIO_F_VERSION_1`. Um dispositivo legado não é registrado.
- O driver negocia só os bits de feature do tipo de dispositivo, de 0 a 23. As features do transporte são escolha do supervisor, e hoje ele só aceita `VIRTIO_F_VERSION_1`.
- Uma fila por dispositivo, com 16 descritores, quatro pedidos em andamento e quatro segmentos por pedido. Os números são pequenos de propósito: todo o estado da fila cabe em tabelas fixas do supervisor.
- Um dispositivo tem um dono por vez. O `init` reivindica cada um com a capability do sistema e concede ao serviço que o manifesto indica.
- Um reset que o dispositivo não confirma leva à quarentena: os frames fixados não voltam ao alocador e o dispositivo não é reaberto até o próximo boot.
- O processo que perde a capability do dispositivo, inclusive por morrer, provoca o mesmo reset. A memória de um driver morto não volta a ser usada enquanto o dispositivo puder alcançá-la.
- Interrupções externas são atendidas por código nativo, só quando um processo executa em U-mode ou quando o supervisor espera sem processo pronto.

A interface está em `specs/abi/devices.md`, o transporte em `native/supervisor/devices/` e os drivers em `src/kernel_drivers/`.

## Consequências

Cada transferência custa duas syscalls e a cópia dos metadados do pedido. Com quatro pedidos em andamento por dispositivo, a vazão é limitada; nenhuma medida mostrou ainda que isso importa.

Um driver com defeito estraga os dados do próprio dispositivo e nega serviço aos clientes dele. Ele não alcança memória fora dos buffers que tem.

A proteção vale para os dispositivos do perfil: `virtio-blk`, `virtio-rng` e a UART do QEMU. Um dispositivo físico que acesse memória por conta própria está fora do modelo de ameaças.

## Hipóteses a confirmar

- Uma fila bastou até a rede chegar. O `virtio-net` usa duas, e desde o ADR 0009 o supervisor programa até duas filas por dispositivo, com o limite de quatro pedidos valendo para cada uma.
- O limite de leituras à espera da confirmação do reset serve fora do QEMU. Ele é uma contagem, não um tempo.
- Quatro pedidos em andamento não limitam o serviço de arquivos, que hoje faz um pedido por vez.
