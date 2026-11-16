# Serviços e configuração

Como ler o estado dos serviços, o que acontece quando um deles falha e como mudar a configuração do sistema. As regras completas estão em `specs/system/configuration.md` e em `specs/system/control-service.md`.

## O que roda

O gerente do sistema inicia cinco serviços, na ordem das dependências que a configuração declara:

| Serviço | Faz | Precisa de |
| --- | --- | --- |
| `console` | Entrada e saída pela porta serial | Nada |
| `entropy` | Bytes aleatórios do dispositivo | Nada |
| `storage` | Discos e arquivos | Nada |
| `network` | Interface, pilha IPv4 e sockets | `entropy` |
| `shell` | O prompt | `console` e `storage` |

`ps` mostra cada um:

```
ps: service=network state=ready restarts=0/3 starts=1
```

`restarts=0/3` são as falhas dentro da janela atual e o limite da configuração. `starts` conta quantas vezes o serviço iniciou desde o boot.

| Estado | Significado | O que fazer |
| --- | --- | --- |
| `ready` | Em execução | Nada |
| `starting` | Processo criado, ainda sem responder | Esperar até 20 segundos |
| `blocked` | Espera um serviço de que precisa | Olhar o estado do outro serviço |
| `degraded` | Falhou mais vezes do que a janela permite e ficou parado | Corrigir a causa e reiniciar o sistema |
| `stopped` | Parado em ordem, durante o desligamento | Nada |

## Quando um serviço falha

O gerente percebe a morte de um serviço em até 50 ms e escreve no console o que faz. Este trecho é do caso `restart-with-a-pending-request` da suíte `supervision`, em que o serviço `client` depende de `base` e `base` é encerrado à força:

```
system: service=base state=failed reason=killed value=0
system: service=client state=stopped clean=1
system: service=base state=restarting attempt=1 limit=2
system: service=base state=ready
system: service=client state=ready
```

Antes de reiniciar um serviço, o gerente para os que dependem dele e os inicia de novo depois. Quem usava a instância antiga recebe erro nas operações pendentes e precisa abrir de novo o que tinha: arquivos, sockets, conexões. Nada é repetido sozinho.

O limite existe para um serviço quebrado não ficar em laço. A imagem do repositório permite 2 reinícios em 60 segundos para `console`, `entropy` e `storage`, e 3 para `network` e `shell`. Esgotado o limite:

```
system: service=network state=degraded restarts=3 window-seconds=60
system: state=degraded
```

O sistema continua com o que sobrou. Sem dispositivo de rede, que é o que `kernel-tool run --without-network` produz, o boot fica assim:

```
system: devices serial=1 entropy=1 network=0 block=2
system: configuration=accepted name=kernel services=5
system: service=console state=ready
system: service=entropy state=ready
system: service=network state=failed stage=start
system: service=network state=restarting attempt=1 limit=3
system: service=network state=failed stage=start
system: service=network state=restarting attempt=2 limit=3
system: service=network state=failed stage=start
system: service=network state=restarting attempt=3 limit=3
system: service=network state=failed stage=start
system: service=network state=degraded restarts=3 window-seconds=60
system: service=shell state=ready
system: state=degraded
```

`net` e `ping` devolvem `BAD_STATE`, e arquivos, programas e desligamento funcionam. Um serviço degradado só volta com um novo boot.

O `console` e o `storage` são diferentes: o shell depende dos dois. Se um deles degrada, o shell fica `blocked` e não há prompt. O estado continua visível nas linhas `system:`, que saem pelo console de diagnóstico do kernel e não pelo serviço.

## Mudar a configuração

A configuração é o arquivo `config/system/system.conf`, copiado para `system/config` na imagem de boot. O sistema a lê uma vez, no boot, e não existe comando para mudá-la em execução.

1. Edite `config/system/system.conf`.
2. Confira antes de iniciar: `uv run pytest tests/conformance/test_configuration.py`. O primeiro teste carrega o arquivo do repositório com o mesmo validador do convidado.
3. `uv run kernel-tool build` gera a imagem de boot de novo.
4. `uv run kernel-tool run`.

Mudanças comuns:

| Para | Mude |
| --- | --- |
| Trocar o endereço | `address`, `prefix` e `gateway` em `[interface]`. O gateway precisa estar na mesma sub-rede |
| Tirar a rede | Remova `[service.network]` e `[interface]`. As duas seções saem juntas |
| Permitir mais aplicações | `limit` em `[access.application]`, até 8. Cada aplicação é um processo, e o perfil admite 16 no total |
| Dar mais memória a uma aplicação | `heap_bytes` em `[access.application]`, até 4 MiB, em múltiplos de 4096 |
| Impedir que aplicações gravem | `files = "read"` em `[access.application]` |
| Impedir que aplicações escutem portas | Tire `"listen"` de `network` em `[access.application]` |
| Tolerar mais falhas de um serviço | `restarts` e `window_seconds` em `[service.<nome>]` |

## Quando a configuração é recusada

O sistema não inicia com uma configuração inválida. Ele não aplica a parte que entendeu: informa o primeiro erro, não inicia nenhum serviço e termina.

```
system: configuration=rejected reason=gateway-off-link subject=interface.gateway
policy: reaped=init reason=exit value=1 live=0 memory-in-use=0
policy: resources=released
kernel: status=failed
```

`reason` diz a regra e `subject` diz onde: a linha, a seção, a chave ou o serviço. A tabela completa está em `specs/system/configuration.md`. As mais comuns:

| `reason` | Significa |
| --- | --- |
| `missing-document` | A imagem de boot não tem `system/config` |
| `syntax` | A linha indicada não é uma seção, uma atribuição nem um comentário |
| `unknown-key`, `unknown-section` | Nome digitado errado, ou chave na seção errada |
| `out-of-range` | Número fora da faixa da chave, ou heap que não é múltiplo de 4096 |
| `dependency-cycle` | Dois serviços que dependem um do outro |
| `missing-dependency` | `network` sem `entropy` em `needs`, ou `shell` sem `console` e `storage` |
| `gateway-off-link` | Gateway fora da sub-rede do endereço |
| `process-budget` | Serviços e aplicações somam mais processos do que o perfil admite |

Para voltar a um sistema que inicia, corrija o arquivo e gere a imagem de novo. O volume de dados não é tocado por uma recusa.

## Desligamento

`shutdown` e `shutdown restart` param os serviços na ordem inversa do início. Cada serviço tem 20 segundos para terminar o que está fazendo. A sequência e as linhas do console estão em `system-operation.md`.
