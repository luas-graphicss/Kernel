# Diferenças entre CPython e o runtime do convidado

[English](runtime-differences.en.md)

O código de `src/` e o corpus de `tests/conformance/corpus/` rodam em dois interpretadores: CPython 3.13 no host, que serve de referência, e MicroPython 1.29.0 no convidado. Este documento lista as diferenças aceitas entre os dois e a regra que o código compartilhado segue para não depender delas.

## O que não pode diferir

O resultado dos contratos compartilhados. O cenário `runtime-selftest` executa no convidado as 10.000 transições do corpus, com a mesma seed, e o `kernel-tool` compara cada linha de resultado com a que o CPython produz ao executar `python -m corpus`. Qualquer diferença reprova o cenário. Nenhuma diferença de resultado está aceita.

## Diferenças aceitas

| Tema | No convidado | Regra para o código compartilhado |
| --- | --- | --- |
| Ponto flutuante | Desligado (`MICROPY_FLOAT_IMPL_NONE`) | Só inteiros, com divisão `//` |
| Inteiros | Precisão arbitrária com MPZ, como no CPython | Sem restrição. O autoteste cobre aritmética, shifts e conversão para texto e para bytes além de 64 bits |
| Biblioteca padrão | Mínima. O autoteste usa `builtins`, `sys` e `gc` | `src/` importa só módulos do projeto e os módulos nativos: `_supervisor` nas políticas e `_process` na biblioteca cliente. Nada de `typing`, `dataclasses`, `enum`, `struct` ou `asyncio` |
| Anotações de tipo | Descartadas pelo `mpy-cross`, nunca avaliadas | As anotações usam tipos embutidos e classes do projeto. Sem `typing`, não há `Protocol`, `TypeVar` nem genéricos próprios |
| Código externo | Sem carga de `.mpy`, e `sys.path` contém só `.frozen`: nenhum módulo é importado de um arquivo. `compile`, `open` e `input` não existem. O perfil `supervisor` não tem compilador. O perfil `user` tem, com `exec` e `eval`, e é com ele que o runner executa o arquivo de uma aplicação | Todo módulo do convidado entra congelado no build. Um programa de aplicação é um arquivo só e importa apenas módulos congelados |
| f-strings | Suportadas no perfil `user`, pelo compilador do processo. Os módulos congelados são compilados no build pelo `mpy-cross` | Sem restrição |
| Formatação com `%` | `str` não tem o operador `%`: `'F%05d' % 7` levanta `TypeError`. `'{:05d}'.format(7)` e `f'{7:05d}'` devolvem `00007` | Formatar com f-strings ou com `str.format` |
| Exceções | Os mesmos tipos embutidos nos casos cobertos pelo autoteste; mensagens e traceback têm outro formato | Comparar o tipo e os campos próprios, como o código de `KernelError`. Nunca o texto da mensagem |
| Recursão profunda | `RuntimeError`, pela checagem de stack. Não existe `RecursionError` | Capturar `RuntimeError` quando o limite importar |
| Coleta de memória | Mark and sweep, sem contagem de referências; finalizadores desligados | Não depender de `__del__` nem do momento em que a memória é liberada |
| Saída | `print` escreve no console serial. No perfil `user` ele usa a chamada `debug write`, que aceita até 256 bytes por vez | Linhas curtas de diagnóstico |
| `sys` | `sys.platform` vale `kernel`; `sys.argv` e `sys.exit` não existem | A entrada é o `main()` do módulo e o valor devolvido define o status |

## Como uma diferença nova entra aqui

Um módulo de `src/` só é aceito quando o `mpy-cross` fixado o compila e o cenário que o exercita passa no QEMU. A aprovação do `mypy` e dos testes em CPython não basta. Se um comportamento divergir, a correção é reescrever o código no subconjunto comum. Uma diferença só entra nesta tabela quando não muda o resultado de nenhum contrato compartilhado.

Os casos puros do autoteste também rodam em CPython, em `tests/conformance/test_guest_programs.py`, para que a mesma verificação exista nos dois interpretadores. O supervisor Python, a biblioteca cliente e os serviços rodam em CPython contra dublês dos módulos nativos, em `tests/conformance/doubles/`.
