# Gerente do sistema e serviço de controle

O gerente, `kernel_services.manager.main`, é o primeiro processo de usuário quando o boot recebe `init=kernel_services.manager.main`, que é o que `kernel-tool run` passa. Ele roda em U-mode, com prioridade 1, e é o único processo que recebe a capability do sistema. Ele lê a configuração, inicia e supervisiona os serviços, atende o shell por um endpoint de controle, inicia as aplicações e conduz a parada. A configuração está em `configuration.md` e as aplicações em `applications.md`.

O `init` anterior, `kernel_services.init.main`, continua sendo o padrão sem o argumento. Ele inicia os serviços de dispositivo, confere cada um e encerra, e é o que o cenário `boot` da suíte `bootstrap` executa.

## Início

O gerente escreve o que faz no console, em linhas `system:`.

1. `system: manager=started runtime=micropython privilege=user`.
2. Lê o inventário de dispositivos e reivindica cada um: `system: devices serial=1 entropy=1 network=1 block=2`.
3. Inicia o armazenamento, que são um serviço de blocos por disco e o serviço de arquivos, para ler `boot/system/config`.
4. Valida a configuração. Recusada, o gerente para o armazenamento e termina com falha. Aceita: `system: configuration=accepted name=kernel services=5`.
5. Inicia os serviços na ordem das dependências. Cada um aparece como `system: service=<nome> state=ready`.
6. Informa `system: state=running`, ou `system: state=degraded` se algum serviço não ficou pronto.

Um serviço está pronto quando o processo dele se registra, em até 20 segundos. O gerente concede a cada serviço só o que a função dele pede:

| Serviço | Processos | Recebe |
| --- | --- | --- |
| `console` | 1 | A porta serial |
| `entropy` | 1 | O dispositivo de entropia |
| `storage` | 3 | Cada serviço de blocos, um disco; o serviço de arquivos, os endpoints dos serviços de blocos |
| `network` | 1 | O dispositivo de rede, o endpoint do serviço de entropia e os dados da interface |
| `shell` | 1 | O endpoint de controle, com `SEND` |

Nenhum serviço recebe a capability do sistema.

## Estados

| Valor | Estado de um serviço | Significado |
| --- | --- | --- |
| 0 | `stopped` | Não iniciado, ou parado em ordem |
| 1 | `starting` | Processo criado, ainda sem registro |
| 2 | `ready` | Registrado e em execução |
| 3 | `degraded` | Esgotou os reinícios da janela e fica parado |
| 4 | `blocked` | Espera um serviço de que precisa |

| Valor | Estado do sistema | Significado |
| --- | --- | --- |
| 0 | `starting` | Antes de a configuração ser aplicada |
| 1 | `running` | Todos os serviços configurados estão `ready` |
| 2 | `degraded` | Algum serviço não está `ready` |
| 3 | `stopping` | Uma parada foi pedida |

## Supervisão

A cada volta, de no máximo 50 ms, o gerente confere se o processo de cada serviço pronto ainda existe.

Quando um serviço morre, o gerente informa `system: service=<nome> state=failed`, com o motivo e o valor do término, e para os serviços que dependem dele, direta ou indiretamente, na ordem inversa do início. Depois reinicia o serviço, se a política permite, e inicia de novo os dependentes.

A política é a da configuração: `restarts` falhas dentro de `window_seconds`. Falhas mais antigas que a janela deixam de contar. Dentro do limite aparece `system: service=<nome> state=restarting attempt=N limit=M`. Esgotado o limite, o serviço fica `degraded`, com `system: service=<nome> state=degraded restarts=N window-seconds=W`, e não é mais reiniciado naquela janela. Não existe laço de reinício sem limite.

Um serviço que depende de outro que não está pronto fica `blocked`, com `system: service=<nome> state=blocked waiting-for=<outro>`. Os demais serviços continuam: sem dispositivo de rede o serviço `network` degrada, e o armazenamento, o console e o shell seguem em uso.

Uma instância nova recebe exatamente as concessões da anterior. Os clientes da instância antiga recebem `PEER_CLOSED` nas chamadas pendentes e `INVALID_HANDLE` ao usar um handle antigo; nenhuma operação é repetida por eles. O shell descarta os handles antigos e pede o endpoint de novo ao controle.

## Serviço de controle

O gerente cria o endpoint de controle e o concede só ao shell. A autorização não vem da posse do endpoint: o gerente mantém a lista dos processos que admitiu, com os direitos de `[access.shell]`, e confere a identidade que o supervisor grava em cada mensagem. Um processo fora da lista recebe `ACCESS_DENIED` em qualquer operação.

| Direito | Operações |
| --- | --- |
| `observe` | `STATUS`, `APPLICATIONS`, `WAIT`, `MEMORY` |
| `launch` | `LAUNCH` |
| `signal` | `SIGNAL` |
| `power` | `POWER` |

| Número | Operação | Pedido | Resposta |
| --- | --- | --- | --- |
| 16 | `STATUS` | Vazio | Estado do sistema e de cada serviço |
| 17 | `ENDPOINT` | Nome de um serviço, de 1 a 32 bytes: `console`, `storage` ou `network` | Vazia, com a capability do endpoint do serviço, com `SEND` e `DELEGATE` |
| 18 | `ACCESS` | Nome de um serviço: `storage` ou `network` | Vazia, com a capability de acesso: um namespace de arquivos no modo configurado, ou um acesso de rede com os direitos configurados |
| 19 | `LAUNCH` | A linha de comando, de 1 a 63 bytes | Identidade da aplicação, em 4 bytes |
| 20 | `APPLICATIONS` | Vazio | Uma entrada por aplicação conhecida |
| 21 | `SIGNAL` | Identidade, em 4 | Vazia. A aplicação é encerrada |
| 22 | `WAIT` | Identidade, em 4, e espera em nanossegundos, em 8 | Motivo do término, em 1, e valor, em 4 |
| 23 | `MEMORY` | Vazio | Os contadores de `system_counters`, em 8 bytes cada |
| 24 | `POWER` | Ação, em 1 byte: 0 desliga, 1 reinicia | Vazia. A parada começa em seguida |

`STATUS` devolve o estado do sistema, em 1 byte, a quantidade de serviços, em 1, e para cada serviço: estado, falhas dentro da janela, limite de reinícios, quantas vezes iniciou e o tamanho do nome, em 1 byte cada, seguidos do nome.

`APPLICATIONS` devolve, por aplicação: identidade, em 4 bytes, estado, em 1, motivo, em 1, valor, em 4, tamanho do comando, em 2, e o comando. O estado é 1 para `running` e 2 para `exited`. O motivo e o valor são os de `process_wait`, em `specs/abi/processes.md`.

| Operação | Condição | Erro |
| --- | --- | --- |
| Qualquer | Processo que o gerente não admitiu, ou sem o direito da operação | `ACCESS_DENIED` |
| Qualquer | Pedido com uma capability, ou corpo fora do formato | `INVALID_ARGUMENT` |
| `ENDPOINT`, `ACCESS` | A política de acesso não concede o serviço | `ACCESS_DENIED` |
| `ENDPOINT`, `ACCESS` | Serviço que não está pronto | `BAD_STATE` |
| `ENDPOINT` | Nome que não é de um serviço | `NOT_FOUND` |
| `LAUNCH` | Parada em andamento | `BAD_STATE` |
| `LAUNCH` | Limite de aplicações em execução atingido | `LIMIT_EXCEEDED` |
| `LAUNCH` | Comando vazio, acima de 63 bytes, iniciado por espaço ou com byte fora do ASCII imprimível | `INVALID_ARGUMENT` |
| `SIGNAL`, `WAIT` | Identidade desconhecida | `NOT_FOUND` |
| `SIGNAL` | Aplicação que já terminou | `BAD_STATE` |
| `WAIT` | A espera acabou, ou espera zero com a aplicação em execução | `TIMED_OUT` |
| `WAIT` | Oito esperas já pendentes | `LIMIT_EXCEEDED` |
| `WAIT` | A parada começou | `CANCELLED` |
| `POWER` | Ação desconhecida | `INVALID_ARGUMENT` |
| `POWER` | Parada já pedida | `BAD_STATE` |

O gerente guarda as oito aplicações terminadas mais recentes, além das que estão em execução. Uma identidade mais antiga devolve `NOT_FOUND`.

## Parada ordenada

`POWER` é o único caminho para desligar ou reiniciar por pedido. A sequência é a mesma nos dois casos:

1. `system: shutdown=started action=shutdown` ou `action=restart`. A partir daqui `LAUNCH` devolve `BAD_STATE`.
2. As aplicações em execução são encerradas, e cada uma aparece como `system: application=N state=exited reason=killed value=0`. As esperas pendentes recebem `CANCELLED`. `system: shutdown=applications stopped=N`.
3. Os serviços recebem `STOP` na ordem inversa do início: `shell`, `network`, `storage`, `entropy`, `console`. O serviço de rede encerra as sessões e aborta as conexões. O serviço de arquivos sincroniza os volumes antes de responder. Cada um tem 20 segundos; quem não responde é encerrado com `process_kill` e aparece com `clean=0`.
4. O gerente chama `system_power` com a ação e informa `system: shutdown=complete clean=1`, ou `clean=0` se algum serviço não parou em ordem.
5. O gerente termina. O supervisor confere que nenhum recurso ficou para trás, escreve `kernel: power=restart` quando a ação é reiniciar, escreve `kernel: status=ok` e pede ao firmware o desligamento ou o reboot a frio.

`system_power`, em `specs/abi/syscalls.md`, só registra a ação. Ela é executada no fim do passo 5, e só quando o sistema terminou com sucesso: um boot que falha desliga, mesmo com reinício pedido.

## Evidência

`tests/conformance/test_service_supervision.py` cobre a ordem de início e de parada, o orçamento de reinícios, a janela, o estado degradado e o reinício dos dependentes. `tests/conformance/test_control_protocol.py` cobre os formatos desta página.

No QEMU, a suíte `supervision` tem os casos `dependency-order`, `readiness-and-degraded-state`, `restart-with-a-pending-request`, `restart-budget` e `restart-window`, e o cenário `network-absent`, que inicia o sistema sem dispositivo de rede e exige o serviço `network` degradado depois de três tentativas, com o shell e o armazenamento em uso. A suíte `applications` cobre `LAUNCH`, `SIGNAL`, `WAIT` e os limites. A suíte `system-journey` cobre a parada com uma aplicação em execução, o reinício e o segundo boot com os dados gravados no primeiro.
