# Política de compatibilidade

Cinco interfaces do sistema estão congeladas na versão 1.0. Esta página diz o que cada uma cobre, o que pode mudar sem quebrar quem já usa e o que precisa acontecer quando algo muda.

## Interfaces congeladas

| Interface | O que cobre | Versão gravada nos dados | Especificação |
| --- | --- | --- | --- |
| `abi` | Números de syscall, códigos de erro, direitos, handles, status de processo, layout de dispositivos, cabeçalho de mensagem e pedido de criação de processo | `VERSION = 1` no cabeçalho da mensagem e `REQUEST_VERSION = 1` no pedido de criação | `specs/abi/` |
| `service-protocol` | Operações e payloads dos serviços de console, entropia, bloco, arquivos, rede, controle, lançamento e energia | A do cabeçalho de mensagem | `specs/abi/device-services.md`, `specs/filesystem/file-service.md`, `specs/network/socket-service.md`, `specs/system/control-service.md` |
| `image-manifest` | Imagem de boot e cabeçalho da imagem de usuário | `FORMAT_VERSION = 1` e `ABI_VERSION = 1` na imagem de boot; `VERSION = 2` no cabeçalho da imagem de usuário | `specs/filesystem/boot-image.md`, `specs/abi/user-image.md` |
| `configuration` | Sintaxe, campos, limites e erros da configuração do sistema | `version = 1` na seção `[system]` | `specs/system/configuration.md` |
| `persistent-format` | Superblocks, índices, diretórios e nomes do volume | `FORMAT_VERSION = 1` no superblock | `specs/filesystem/volume-format.md` |

`specs/frozen-interfaces.toml` lista os arquivos que definem cada interface e o SHA-256 do conjunto. `kernel-tool verify-interfaces` recalcula os digests e reprova quando um deles mudou. A verificação roda no CI, em `kernel-tool verify --all` e em `kernel-tool release-check`.

O digest é um alarme, não uma prova de compatibilidade. Ele dispara também com uma mudança que não altera o comportamento, como um nome de constante. Quem mexe em um arquivo congelado decide, por esta página, de que tipo é a mudança.

## Mudança compatível

Vale dentro da série 1.x e sobe a versão menor da interface:

- syscall, operação de serviço, código de erro ou contador novos, com número que nunca foi usado;
- campo novo de configuração com valor padrão que mantém o comportamento anterior;
- bit de flag novo em um campo que hoje exige zero, quando o lado que não o conhece o recusa com um erro definido.

Um componente 1.x responde `UNSUPPORTED` ao que não conhece. Ele não ignora e não reinterpreta.

## Mudança incompatível

Sobe a versão maior da interface e a versão gravada nos dados:

- remover ou renumerar syscall, operação, erro, direito ou contador;
- mudar tamanho, ordem ou significado de um campo;
- mudar o layout do volume, da imagem de boot ou do cabeçalho da imagem de usuário;
- passar a aceitar uma entrada que antes era recusada por segurança.

Uma mudança incompatível pede um ADR, a atualização da especificação e dos testes de conformidade na mesma mudança, e uma versão maior do sistema.

## Volume de dados

- Um release lê e grava só os formatos que declara em `volume_formats`, no `manifest.json` do pacote.
- Um volume em formato desconhecido não é montado. O sistema inicia sem ele, e nada é escrito no disco: cenário `unknown-format-is-not-mounted` da suíte `release-journey` e `unknown-format-version` da suíte `storage`.
- Atualizar troca as imagens e nunca toca no volume. `kernel-tool update` recusa um pacote que não lê o formato do volume instalado.
- Voltar a um release anterior só é possível quando ele lê o formato em que o volume está. `kernel-tool rollback` confere isso antes de trocar as imagens.
- Um formato novo chega com um release que lê os dois. A conversão de um volume existente é um passo separado, que exige uma cópia do volume e um pedido explícito do operador. Na série 1.x não existe conversão.

## Como mudar uma interface congelada

1. Classificar a mudança por esta página.
2. Atualizar a especificação, a versão da interface em `specs/frozen-interfaces.toml` e, quando for o caso, a versão gravada nos dados.
3. Atualizar os testes de conformidade e os cenários que exercitam a interface.
4. Rodar `uv run kernel-tool verify-interfaces --freeze` e incluir o arquivo regravado na mesma mudança.
5. Para mudança incompatível, registrar o ADR.

## O que não está congelado

As linhas que o sistema escreve no console são diagnóstico. O `kernel-tool` da mesma versão é o leitor suportado, e o texto pode mudar entre versões menores. Os comandos do shell podem ganhar opções. O conteúdo dos relatórios em `build/` não é interface.
