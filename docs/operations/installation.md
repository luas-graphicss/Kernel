# Instalar, atualizar e recuperar

O alvo suportado é a máquina `virt` do QEMU para RISC-V de 64 bits, com o firmware OpenSBI, descrita em `config/profiles/qemu-riscv64.toml`. Um pacote de release traz imagens para esse alvo. Ele não é uma ISO, não inicia em um PC e não foi homologado em hardware físico.

## O que há em um pacote

`kernel-tool release-check` monta o pacote em `build/qemu-riscv64/release/kernel-<versão>-qemu-riscv64/`.

| Arquivo | Conteúdo |
| --- | --- |
| `kernel.elf` | Imagem do kernel: código nativo próprio, o runtime MicroPython do supervisor e a política Python congelada |
| `init.img` | Runtime de usuário: MicroPython com os serviços, os drivers, o shell e o executor de aplicações congelados |
| `boot.img` | Volume de boot somente leitura: configuração, identidade do release, licença e os programas de `apps/` |
| `manifest.json` | Versão, perfil, SHA-256 de cada imagem, interfaces congeladas, formatos de volume lidos, o que é preciso além do pacote e a linha de comando do emulador |
| `sbom.spdx.json` | Lista de materiais em SPDX 2.3 |
| `licenses.json` e `licenses/` | Inventário de licenças e os textos do que é distribuído |
| `release-report.json` | Resultado de cada gate de release na hora em que o pacote foi montado |
| `toolchain.lock.toml` e `profile.toml` | Versões e hashes do emulador, do firmware e do compilador, e o perfil da máquina |
| `SHA256SUMS` | SHA-256 de todos os arquivos acima |
| `SHA256SUMS.sig` | Assinatura dos checksums, quando o pacote foi assinado |

O pacote não traz o QEMU nem o OpenSBI. `manifest.json` diz as versões exigidas, e `kernel-tool toolchain` baixa as duas e confere os hashes.

O binário não é só Python. `sbom.spdx.json` separa o que é código do projeto, o MicroPython 1.29.0 e os membros da `libgcc` ligados às imagens. O que cada parte pode fazer está em `docs/security/trusted-computing-base.md`.

Um pacote com `"qualified": false` no manifesto foi montado com algum gate de release em aberto. `release-report.json` diz quais. Ele serve para ensaiar a instalação e não é um release.

## Preparar o host

```sh
uv sync --frozen
uv run kernel-tool toolchain
```

Os requisitos do host estão no `README.md`. Para a rede, o host precisa conseguir criar um namespace de rede com uma interface TAP.

## Conferir o pacote

```sh
uv run kernel-tool release-verify <pacote> --allowed-signers <arquivo> --identity <signatário>
```

O comando confere a assinatura de `SHA256SUMS` e depois cada arquivo contra os checksums. Sem `--allowed-signers` ele confere só os checksums, o que detecta um arquivo corrompido e não diz de onde o pacote veio. O arquivo de signatários e a identidade vêm de quem publica o release, por um canal separado do pacote.

## Primeira instalação

```sh
uv run kernel-tool install <pacote> --target <diretório>
uv run kernel-tool run --installation <diretório>
```

`install` confere o pacote, copia-o para `<diretório>/releases/` e cria `<diretório>/data.img`, um volume vazio de 1 MiB. `--allowed-signers` e `--identity` valem aqui também. Se o diretório já tem um `data.img`, ele é mantido como está, desde que o release leia o formato dele. Um `data.img` que não é um volume interrompe a instalação e não é alterado.

`run --installation` inicia as imagens instaladas com esse volume. O uso do shell está em `system-operation.md`. No primeiro boot, `cat boot/system/release` mostra a versão instalada.

Sem o `kernel-tool`, a chave `launch` de `manifest.json` traz os argumentos do emulador. `{emulator}` é o `qemu-system-riscv64` da versão exigida e `{firmware}` é o OpenSBI. Os nomes de arquivo são relativos a um diretório com as três imagens e o `data.img`. Esse caminho não liga a rede.

## Atualizar

```sh
uv run kernel-tool update <pacote novo> --target <diretório>
```

O sistema precisa estar parado. `update` confere o pacote novo, confere que ele lê o formato do volume instalado, copia-o e passa a usá-lo. O release anterior continua em `releases/`, e o volume não é tocado. Um pacote que não lê o formato do volume é recusado, e a instalação fica como estava. A troca é a substituição de um arquivo, `installation.json`: se o comando for interrompido antes dela, a instalação continua no release anterior.

## Voltar ao release anterior

```sh
uv run kernel-tool rollback --target <diretório>
```

`rollback` confere os checksums do release anterior e que ele lê o formato em que o volume está agora. Se lê, as imagens são trocadas e o volume segue o mesmo, com tudo o que o release mais novo gravou. Se não lê, o comando recusa e nada muda. As regras de formato estão em `specs/compatibility.md`.

## Recuperar o volume

| Situação | O que o sistema faz | O que o operador faz |
| --- | --- | --- |
| Queda de energia no meio de uma gravação | Monta o último commit inteiro. O que teve `sync` confirmado está lá | Nada |
| Root mais novo danificado | Monta o root anterior, somente leitura. Gravações respondem `READ_ONLY` | Copiar os dados para fora e criar um volume novo |
| Formato desconhecido | Não monta o volume. O sistema inicia sem `data` | Usar um release que leia o formato, ou guardar o arquivo e criar um volume novo |
| Volume sem formato ou corrompido | Não monta e nunca formata por conta própria | Restaurar uma cópia ou criar um volume novo |

Com o sistema parado, `uv run kernel-tool verify-filesystem --image <diretório>/data.img` diz em qual desses casos o volume está, e `uv run kernel-tool inspect-volume <diretório>/data.img` lista os superblocks e a árvore. Para uma cópia de segurança, copie `data.img` com o sistema parado. Para um volume novo, mova o arquivo antigo e rode `uv run kernel-tool create-volume <diretório>/data.img`.

## O que foi exercitado

A suíte `release-journey` roda no QEMU a primeira inicialização, a atualização para uma imagem de boot de outra versão sobre o mesmo volume, a volta à imagem anterior com os dados das duas, o volume com o root danificado e o volume em formato desconhecido. `tests/host/test_release_installation.py` cobre `install`, `update` e `rollback`, incluindo as recusas. A execução registrada está em `docs/acceptance/qualification-and-distribution.md`.

## Limites

- A assinatura confere origem e integridade na distribuição. Não há secure boot: um host ou um firmware comprometido fica fora do que o produto garante.
- `update` e `rollback` trocam as três imagens juntas. Não há atualização de uma parte.
- O volume tem tamanho fixo, definido na criação.
- Um único hart, e nenhuma homologação fora do QEMU com TCG.
