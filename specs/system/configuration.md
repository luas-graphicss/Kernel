# Configuração do sistema

[English](configuration.en.md)

O sistema lê uma única configuração, o arquivo `system/config` da imagem de boot, antes de iniciar qualquer serviço além do armazenamento. O arquivo é texto e é tratado como dados: o leitor reconhece seções, chaves, números, textos e listas, e nada nele é avaliado como Python. O arquivo do repositório é `config/system/system.conf`, e o código está em `kernel_protocol.configuration`.

A configuração é lida inteira, validada inteira e só então aplicada. Um erro em qualquer ponto recusa o documento todo: nenhum serviço da configuração inicia, o sistema informa o motivo e termina com `kernel: status=failed`.

## Sintaxe

```
[service.network]
needs = ["entropy"]
restarts = 3
window_seconds = 60
heap_bytes = 4194304
```

| Elemento | Regra |
| --- | --- |
| Seção | `[nome]`, com letras minúsculas, dígitos, `_`, `.` e `-`, começando por letra. Cada nome aparece uma vez |
| Chave | `chave = valor`, com letras minúsculas, dígitos e `_`, começando por letra, dentro de uma seção. Cada chave aparece uma vez por seção |
| Número | Decimal sem sinal, de até 18 dígitos, sem zero à esquerda |
| Texto | Entre aspas duplas, de até 128 bytes, sem aspas e sem barra invertida |
| Lista | `["a", "b"]`, com até 16 textos |
| Booleano | `true` ou `false`. Nenhuma chave atual usa |
| Comentário | Linha que começa com `#` |

| Limite | Valor |
| --- | --- |
| Documento | 16.384 bytes e 256 linhas |
| Linha | 256 bytes, só caracteres ASCII imprimíveis |
| Seções | 32 |
| Chaves por seção | 16 |

## Seções

Uma seção ou chave desconhecida recusa o documento. Uma chave obrigatória ausente também.

### `[system]`

| Chave | Tipo | Regra |
| --- | --- | --- |
| `version` | Número | 1 |
| `name` | Texto | De 1 a 32 bytes |

### `[interface]`

Obrigatória quando existe `[service.network]`, e recusada sem ele.

| Chave | Tipo | Regra |
| --- | --- | --- |
| `address` | Texto | Endereço IPv4 de uma estação: nem a rede, nem o broadcast do prefixo |
| `prefix` | Número | De 8 a 30 |
| `gateway` | Texto, opcional | Estação da mesma sub-rede, diferente de `address` |
| `mtu` | Número | De 576 a 1500 |

### `[service.<nome>]`

Os nomes aceitos são `console`, `entropy`, `storage`, `network` e `shell`. Os três primeiros são obrigatórios.

| Chave | Tipo | Regra |
| --- | --- | --- |
| `needs` | Lista, opcional | Serviços que precisam estar prontos antes. `network` precisa declarar `entropy`; `shell` precisa declarar `console` e `storage` |
| `restarts` | Número | De 0 a 16: quantos reinícios cabem na janela |
| `window_seconds` | Número | De 1 a 3600 |
| `priority` | Número, opcional | De 0 a 3. O padrão é 2 |
| `heap_bytes` | Número, opcional | De 4096 a 4.194.304, múltiplo de 4096. O padrão é 1.048.576 |

### `[access.shell]` e `[access.application]`

Dizem o que o shell e as aplicações recebem. O que não está na lista não é concedido.

| Chave | Tipo | Regra |
| --- | --- | --- |
| `network` | Lista, opcional | Direitos de `specs/network/socket-service.md`: `connect`, `listen`, `datagram`, `echo`, `inspect`, `delegate` |
| `files` | Texto, opcional | `none`, `read` ou `read-write`. O padrão é `none` |
| `control` | Lista, opcional, só em `[access.shell]` | `observe`, `launch`, `signal`, `power`, de `control-service.md` |
| `limit` | Número, opcional, só em `[access.application]` | De 0 a 8 aplicações ao mesmo tempo. O padrão é 0 |
| `heap_bytes` | Número, opcional, só em `[access.application]` | Como nos serviços |
| `priority` | Número, opcional, só em `[access.application]` | Como nos serviços |

## Validação

Depois de ler as seções, o validador confere o conjunto:

- As dependências formam uma ordem de início. Um ciclo recusa o documento.
- Os processos dos serviços, mais o limite de aplicações, mais o próprio gerente cabem no limite de processos do perfil. O armazenamento conta três processos; os outros serviços, um.

| Motivo | Sujeito informado | Causa |
| --- | --- | --- |
| `missing-document` | `boot/system/config` | O arquivo não existe |
| `unreadable` | O nome do erro | O arquivo existe e a leitura falhou |
| `storage-unavailable` | `boot` | A imagem de boot não montou |
| `syntax` | `line-N` | Linha que não é seção, atribuição nem comentário, ou valor malformado |
| `too-large` | `document`, `lines`, `line-N` | Um limite da sintaxe foi excedido |
| `duplicate` | A seção ou a chave | Nome repetido |
| `unknown-section`, `unknown-key` | A seção, ou `seção.chave` | Nome que o formato não conhece |
| `missing-section`, `missing-key` | A seção, ou `seção.chave` | Obrigatória e ausente |
| `wrong-type` | `seção.chave` | Valor de outro tipo |
| `out-of-range` | `seção.chave` | Valor fora da faixa, heap fora de página ou item repetido em uma lista |
| `unsupported-version` | `system.version` | Versão diferente de 1 |
| `unknown-service`, `missing-service` | O serviço | Serviço fora da lista, ou obrigatório e ausente |
| `unknown-dependency`, `missing-dependency` | `serviço.dependência` | Dependência que não é um serviço declarado, ou obrigatória e ausente |
| `self-dependency`, `dependency-cycle` | O serviço | Serviço que depende de si mesmo, ou de um ciclo |
| `invalid-address` | `seção.chave` | Texto que não é um endereço IPv4 de estação |
| `gateway-off-link` | `interface.gateway` | Gateway fora da sub-rede ou igual ao endereço |
| `unknown-right` | `seção.chave` | Direito que não existe |
| `process-budget` | A quantidade pedida | Mais processos do que o perfil admite |

A recusa aparece no console em uma linha:

```
system: configuration=rejected reason=out-of-range subject=service.network.heap_bytes
```

Uma configuração aceita aparece como `system: configuration=accepted name=kernel services=5`.

## O que a configuração não faz

Ela não é relida com o sistema em execução, e não existe comando para mudar um valor a quente. Mudar a configuração é gerar outra imagem de boot e reiniciar. A imagem de boot é montada somente leitura, então nenhum processo do sistema altera o arquivo.

## Evidência

`tests/conformance/test_configuration.py` cobre a sintaxe, os limites, cada motivo de recusa, a ordem de início e a regra de que um valor nunca é avaliado. A suíte `supervision` inicia o sistema com quatro imagens de boot: sem o arquivo, com dependência circular, com um heap acima do limite e com o gateway fora da sub-rede. Em cada uma o cenário exige a linha de recusa e proíbe qualquer linha de serviço iniciado, de estado do sistema e do shell.
