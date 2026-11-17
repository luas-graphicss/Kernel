# Operar o sistema

[English](system-operation.en.md)

Como iniciar o sistema no QEMU, usar o shell, rodar programas do volume e desligar. Os trechos de console desta página são a saída da suíte `system-journey`.

## Iniciar

```sh
uv run kernel-tool build
uv run kernel-tool run
```

`run` inicia o QEMU com a porta serial ligada ao terminal e passa `init=kernel_services.manager.main` ao kernel. Ele anexa:

- a imagem de boot `build/qemu-riscv64/boot.img`, somente leitura;
- o volume de dados `build/qemu-riscv64/system/data.img`, de 1 MiB, criado vazio na primeira execução e mantido nas seguintes;
- a fonte de entropia;
- a interface de rede, ligada a uma estação de teste isolada no host. Sem permissão para criar a rede isolada, `run` avisa `booting without a network` e segue sem ela. `--without-network` pede isso de propósito. Os detalhes estão em `network-operation.md`.

O boot termina no prompt:

```
system: manager=started runtime=micropython privilege=user
system: devices serial=1 entropy=1 network=1 block=2
system: configuration=accepted name=kernel services=5
system: service=console state=ready
system: service=entropy state=ready
network: interface=10.0.2.15/24 mtu=1500
system: service=network state=ready
system: service=shell state=ready
system: state=running
shell: ready
kernel>
```

`system: state=degraded` no lugar de `running` significa que algum serviço não iniciou. O shell continua disponível quando o console e o armazenamento estão prontos; `services-and-configuration.md` explica o que fazer.

`run` termina quando o sistema desliga, com status 0. `--deadline SEGUNDOS` encerra a sessão depois desse tempo, com status 1. Ctrl-C mata o emulador sem parada ordenada: o que não passou por `sync` pode se perder.

Quando a entrada padrão não é um terminal, `run` retém o que chega por ela e só repassa ao console depois de `shell: ready`. Um comando enviado por pipe ou redirecionado de um arquivo chega inteiro:

```sh
printf 'ls boot\nshutdown\n' | uv run kernel-tool run --without-network
```

No terminal a entrada vai direto ao emulador. Digite depois do prompt: um byte enviado antes de o firmware preparar a porta serial se perde.

## O shell

Uma linha é um comando e seus argumentos, separados por espaço. Aspas duplas juntam palavras em um argumento. Não há pipes, redirecionamento, variáveis, curingas nem histórico, e nenhum comando é um atalho para um programa do host.

| Limite | Valor |
| --- | --- |
| Linha | 255 bytes |
| Palavras | 16 |
| Linhas completas à espera do shell | 4 |
| Bytes recebidos à espera do console | 256 |

O que passa de 255 bytes não entra na linha e toca a campainha. Uma linha que estourou não é executada: no Enter o shell responde `shell: command=none status=failed error=MESSAGE_TOO_LARGE`. Ctrl-U apaga a linha e permite recomeçar.

O console guarda até quatro linhas completas enquanto o shell executa um comando. Cada linha além disso é descartada, e o console avisa com `console: dropped-lines=N`, em que N é o total descartado desde que o serviço de console iniciou. Um script deve esperar a linha de status de um comando antes de enviar o próximo. Uma rajada com mais de 256 bytes ainda não lidos perde o excesso antes de chegar ao console, sem aviso.

TAB vale como espaço. Uma sequência de escape, como a das setas e das teclas de função, é descartada inteira.

Todo comando termina com uma linha de status, e é ela que um script deve conferir:

```
shell: command=mkdir status=ok
shell: command=cat status=failed error=NOT_FOUND
```

| Comando | O que faz | Saída |
| --- | --- | --- |
| `help` | Lista os comandos | Uma linha `help:` por comando |
| `run <caminho> [argumentos]` | Inicia o programa do volume como aplicação | `run: application=N program=<caminho>` |
| `ps` | Lista o estado do sistema, os serviços e as aplicações | `ps: system=`, `ps: service=`, `ps: application=` |
| `kill <aplicação>` | Encerra uma aplicação | `kill: application=N` |
| `wait <aplicação> [segundos]` | Espera a aplicação terminar. Sem tempo, espera sem limite | `wait: application=N reason=<motivo> value=<valor>` |
| `mem` | Mostra frames de memória e objetos do kernel | Duas linhas `mem:` |
| `ls [caminho]` | Lista um diretório. Sem caminho, lista as montagens | `ls: name= kind= size=` por entrada e `ls: entries=N` |
| `cat <caminho>` | Imprime um arquivo de até 65.536 bytes | O conteúdo e `cat: bytes=N` |
| `mkdir <caminho>` | Cria um diretório | Só o status |
| `write <caminho> <texto>` | Substitui o arquivo por uma linha com o texto | `write: bytes=N` |
| `rm <caminho>` | Remove um arquivo ou um diretório vazio | Só o status |
| `sync` | Torna duráveis os volumes com escrita | `sync: mount=<nome> durable=1` por volume e `sync: volumes=N` |
| `net [counters\|neighbors]` | Mostra a interface, os contadores ou os vizinhos | Linhas `net:` |
| `ping <endereço> [quantidade]` | Envia echo requests. O padrão é 3 e o máximo é 16 | `ping: from=`, e `ping: sent=N received=M` |
| `shutdown [restart]` | Para o sistema em ordem e desliga, ou reinicia | `shutdown: action=` |

Um nome que não está na tabela devolve `status=failed error=UNSUPPORTED`.

## Arquivos

Os caminhos começam pelo nome de uma montagem e não têm barra inicial.

| Montagem | Conteúdo | Escrita | Sobrevive ao desligamento |
| --- | --- | --- | --- |
| `boot` | A imagem de boot: `system/config`, `system/release`, `system/license` e os programas de `apps/` | Não | Sim, é a mesma imagem |
| `data` | O volume persistente | Sim | Sim, a partir do `sync` |
| `tmp` | Arquivos em memória | Sim | Não |

```
kernel> mkdir data/journey
shell: command=mkdir status=ok
kernel> write data/journey/note written before the restart
write: bytes=27
shell: command=write status=ok
kernel> cat data/journey/note
written before the restart
cat: bytes=27
shell: command=cat status=ok
kernel> sync
sync: mount=data durable=1
sync: mount=tmp durable=1
sync: volumes=2
shell: command=sync status=ok
```

Um arquivo gravado só está garantido no disco depois de `sync` responder ou depois de uma parada ordenada. `rm boot/system/release` devolve `READ_ONLY`.

Um `write` recusado, por exemplo com `NO_SPACE`, remove o arquivo que tinha acabado de criar. Um arquivo que já existia continua listado, vazio: o comando o esvazia antes de gravar.

## Programas

`run` inicia um arquivo Python do volume em um processo próprio e devolve o prompt na hora. A aplicação recebe um número, que os outros comandos usam.

```
kernel> run boot/apps/wordcount.py data/journey/note
system: application=1 state=running program=boot/apps/wordcount.py
run: application=1 program=boot/apps/wordcount.py
shell: command=run status=ok
kernel> wait 1 10
wordcount: path=data/journey/note lines=1 words=4 bytes=27
system: application=1 state=exited reason=exit value=0
wait: application=1 reason=exit value=0
shell: command=wait status=ok
```

A saída de uma aplicação vai direto para o console de diagnóstico, sem passar pelo shell. Uma aplicação que escreve enquanto o shell também escreve pode aparecer no meio de uma linha dele; `wait` evita isso, porque o shell só volta a escrever quando a aplicação termina.

A imagem de boot traz três programas: `boot/apps/wordcount.py <caminho>`, `boot/apps/sysinfo.py` e `boot/apps/fetch.py <endereço> <porta> <caminho>`, que grava em um arquivo o que uma conexão TCP entrega. Para rodar um programa seu, coloque o arquivo na imagem de boot, por `config/boot/manifest.toml`, e gere a imagem de novo. O formato do programa e o que ele pode usar estão em `specs/system/applications.md`.

| Situação | O que aparece |
| --- | --- |
| A aplicação terminou bem | `reason=exit value=0` |
| O programa levantou exceção, tem erro de sintaxe ou não existe | O diagnóstico e `reason=exit value=1` |
| `wait` com prazo e a aplicação ainda roda | `status=failed error=TIMED_OUT`. A aplicação continua |
| `kill` | `wait: application=N reason=killed value=0` |
| Mais aplicações em execução do que o limite da configuração, que é 4 | `run` devolve `LIMIT_EXCEEDED` |
| Número desconhecido | `NOT_FOUND`. O sistema guarda as oito aplicações terminadas mais recentes |

`ps` mostra as aplicações junto com os serviços:

```
kernel> ps
ps: system=running
ps: service=console state=ready restarts=0/2 starts=1
ps: service=entropy state=ready restarts=0/2 starts=1
ps: service=storage state=ready restarts=0/2 starts=1
ps: service=network state=ready restarts=0/3 starts=1
ps: service=shell state=ready restarts=0/3 starts=1
ps: application=1 state=exited reason=exit value=0 command="boot/apps/wordcount.py data/journey/note"
shell: command=ps status=ok
```

## Desligar e reiniciar

```
kernel> shutdown restart
system: shutdown=started action=restart
system: application=5 state=exited reason=killed value=0
system: shutdown=applications stopped=1
system: service=shell state=stopped clean=1
system: service=network state=stopped clean=1
system: service=storage state=stopped clean=1
system: service=entropy state=stopped clean=1
system: service=console state=stopped clean=1
system: shutdown=complete clean=1
kernel: power=restart
kernel: status=ok
```

`shutdown` encerra as aplicações, para os serviços na ordem inversa do início e sincroniza os volumes antes de desligar. Não é preciso rodar `sync` antes. Com `restart`, `kernel-tool run` inicia o sistema de novo com o mesmo volume de dados; sem ele, `run` termina.

As linhas do próprio shell para esse comando, `shutdown: action=` e o status, nem sempre aparecem. O shell é o primeiro serviço a parar, e a parada pode alcançá-lo antes de ele escrever. As linhas `system: shutdown=` do gerente aparecem sempre.

`clean=0` em um serviço ou na última linha significa que algum serviço não respondeu à parada em 20 segundos e foi encerrado à força. Confira os dados depois do próximo boot.

## Erros comuns

| Código | Causa provável | O que fazer |
| --- | --- | --- |
| `UNSUPPORTED` | Comando que não existe | `help` |
| `INVALID_ARGUMENT` | Argumento ausente, número fora da faixa, aspas sem fechar ou mais de 16 palavras | Conferir a sintaxe na tabela |
| `MESSAGE_TOO_LARGE` | Linha com mais de 255 bytes | Encurtar a linha. Ctrl-U apaga a que está em edição |
| `NOT_FOUND` | Caminho ou aplicação que não existe | `ls`, `ps` |
| `READ_ONLY` | Escrita em `boot`, ou em um volume montado somente leitura | Usar `data` ou `tmp` |
| `NO_SPACE` | Volume de dados cheio | Remover arquivos e rodar `sync` |
| `TIMED_OUT` | A espera acabou | Repetir, ou `kill` |
| `LIMIT_EXCEEDED` | Limite de aplicações ou de sockets atingido | Esperar uma aplicação terminar |
| `BAD_STATE` | O serviço que atende o comando não está pronto | `ps`, e depois `services-and-configuration.md` |
| `ACCESS_DENIED` | A configuração não concede a operação ao shell | Rever `[access.shell]` |
