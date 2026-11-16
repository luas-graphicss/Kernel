# Operar a rede

Como a interface de rede é configurada, o que existe do outro lado do cabo no QEMU, como conferir a conectividade pelo shell e como ler as falhas. O que a pilha suporta está em `specs/network/protocols.md`.

## A interface

O sistema tem uma interface, com endereço estático lido de `[interface]` na configuração. A imagem do repositório usa:

| Campo | Valor |
| --- | --- |
| Endereço | `10.0.2.15/24` |
| Gateway | `10.0.2.2` |
| MTU | 1500 |
| Endereço de hardware | `52:54:00:12:34:56`, definido pelo `kernel-tool` no QEMU |

Não há DHCP nem DNS. Todo destino é um endereço IPv4 escrito em decimal, como `10.0.2.2`. Para mudar o endereço, edite `config/system/system.conf`, gere a imagem de novo e reinicie; `services-and-configuration.md` mostra o caminho.

## O outro lado

`kernel-tool run` e as suítes ligam a interface a uma estação de teste que roda no host. A estação cria um namespace de rede só dela, com uma interface TAP no endereço `10.0.2.2`, e atende com a pilha TCP/IP do Linux. O namespace não tem rota para o host nem para a internet: o convidado alcança `10.0.2.2` e nada mais.

| Porta em `10.0.2.2` | Serviço |
| --- | --- |
| 7, TCP e UDP | Devolve o que recebe |
| 9, TCP | Lê tudo e informa o hash ao `kernel-tool` |
| 13, TCP | Aceita a conexão e não envia nada |
| 14, TCP | Lê devagar, 1 KiB a cada 20 ms |
| 17, TCP | Envia um texto de 240 linhas e fecha |
| 19, TCP | Envia o fluxo de teste pedido nos 8 primeiros bytes: semente e tamanho |
| 81, TCP | Fechada: recusa a conexão |

A estação precisa criar o namespace. Ela consegue quando o `kernel-tool` roda como root, quando o host permite user namespaces sem privilégio com acesso a `/dev/net/tun`, ou quando `sudo -n` funciona sem senha. Sem nenhum dos três, `run` segue sem rede e as suítes de rede terminam com status 3.

## Conferir pelo shell

```
kernel> net
net: address=10.0.2.15/24 gateway=10.0.2.2 mtu=1500 link=up hardware=52:54:00:12:34:56
net: sockets=0 connections=0 buffered-bytes=0 device-resets=0
shell: command=net status=ok
kernel> ping 10.0.2.2 2
ping: from=10.0.2.2 bytes=32 time-us=4540
ping: from=10.0.2.2 bytes=32 time-us=2022
ping: sent=2 received=2
shell: command=ping status=ok
kernel> net neighbors
net: neighbor=10.0.2.2 hardware=ba:91:17:70:ac:7b
net: neighbors=1
shell: command=net status=ok
```

`ping` espera cada resposta por 2 segundos e falha só quando nenhuma chega. `net counters` lista os contadores diferentes de zero; os nomes estão em `specs/network/protocols.md`.

Uma resposta de `ping` prova pouco: ela mostra que ARP, IPv4 e ICMP funcionam. Para conferir TCP, traga dados por uma conexão:

```
kernel> run boot/apps/fetch.py 10.0.2.2 17 data/journey/greeting
system: application=2 state=running program=boot/apps/fetch.py
run: application=2 program=boot/apps/fetch.py
shell: command=run status=ok
kernel> wait 2 20
fetch: path=data/journey/greeting bytes=6240
system: application=2 state=exited reason=exit value=0
wait: application=2 reason=exit value=0
shell: command=wait status=ok
```

## Ler uma falha

| O que aparece | Causa | O que fazer |
| --- | --- | --- |
| `net` devolve `BAD_STATE` | O serviço de rede não está pronto | `ps`. Se o serviço está `degraded`, falta o dispositivo ou ele falhou mais vezes do que a janela permite |
| `link=down` em `net`, `network: link=down` no console | O dispositivo informou enlace caído | Esperar `network: link=up`. Os envios devolvem `UNREACHABLE` enquanto isso, e as conexões abertas retransmitem quando o enlace volta |
| `ping` com `error=UNREACHABLE` | Destino fora da sub-rede sem gateway, ou vizinho que não respondeu a três pedidos ARP | `net neighbors`; conferir endereço, prefixo e gateway |
| `ping` com `error=TIMED_OUT` | O vizinho existe e não respondeu ao echo | Conferir o outro lado. `net counters` mostra `icmp-rate-limited` se o limite local foi atingido |
| Aplicação com `CONNECTION_REFUSED` | Ninguém escuta na porta de destino | Conferir a porta |
| Aplicação com `CONNECTION_RESET` | O peer abortou a conexão | Conferir o peer |
| Aplicação com `TIMED_OUT` em uma conexão aberta | O peer parou de confirmar por oito retransmissões | `net counters`: `tcp-segments-retransmitted` cresce quando há perda |
| `network: device=recovered resets=N` | O dispositivo falhou e o driver o reiniciou | Nada. `device-resets` em `net` mostra quantas vezes aconteceu |
| `system: service=network state=restarting` | O processo do serviço morreu e foi reiniciado | As aplicações recebem `INVALID_HANDLE` nos sockets antigos e precisam entrar de novo no serviço. Nenhuma conexão atravessa o reinício |
| Contadores `*-malformed` ou `*-bad-checksum` crescendo | Tráfego inválido chegando | Capturar o tráfego, como abaixo. Pacotes inválidos são descartados e não ocupam memória |

Um problema de rede não derruba o resto: com o serviço `network` degradado, o shell, os arquivos e as aplicações sem rede continuam.

## Capturas

A estação grava tudo o que passa pelo cabo, nos dois sentidos, em formato pcap.

| Origem | Arquivo |
| --- | --- |
| `kernel-tool run` | `build/qemu-riscv64/system/network/traffic.pcap` |
| Suítes | `build/qemu-riscv64/reports/captures/<cenário>.pcap`, com o hash e a quantidade de quadros no relatório da suíte |

Cada quadro fica cortado em 96 bytes, o que guarda os cabeçalhos e descarta quase todo o payload. As capturas contêm só os endereços de teste desta página e dados gerados pelos testes; nenhum tráfego do host passa pela estação.

```sh
tcpdump -n -r build/qemu-riscv64/reports/captures/interop-impaired-link.pcap | head
```

## Limites que o operador sente

| Limite | Valor | Efeito ao atingir |
| --- | --- | --- |
| Sockets por processo | 16 | Abrir outro devolve `LIMIT_EXCEEDED` |
| Sockets no serviço | 64 | O mesmo, para qualquer processo |
| Memória de buffers | 1 MiB | Escritas aceitam menos bytes e esperam; datagramas novos são descartados |
| Conexões esperando em um socket em escuta | 8 | Pedidos novos são descartados e o peer tenta de novo |

Os demais estão em `specs/network/protocols.md`.
