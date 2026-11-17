# ADR 0001: Plataforma de referência

[English](0001-reference-platform.en.md)

Estado: aceita.

## Contexto

O kernel precisa de um alvo único e reproduzível antes de qualquer subsistema. Um alvo com modelo de privilégio explícito e dispositivos estáveis permite provar boot, traps e runtime sem depender de uma placa específica.

## Decisão

O alvo da versão 1.0 é RISC-V de 64 bits, little-endian, perfil RV64GC, na máquina `virt` do QEMU com um hart.

| Dimensão | Valor fixado |
| --- | --- |
| Emulador | QEMU 9.2.4, pacote xPack `9.2.4-1`, acelerador TCG |
| Máquina | `virt,aia=none,acpi=off`, com `virtio-mmio.force-legacy=false` |
| CPU | `rv64,h=off,v=off`, um hart |
| Firmware | OpenSBI 1.5.1 em M-mode, o `fw_dynamic` distribuído no pacote do QEMU |
| Privilégios | Kernel em S-mode, processos em U-mode |
| Memória | 256 MiB a partir do endereço descrito no DTB |
| Console | UART NS16550 descoberta no DTB; SBI DBCN antes de o DTB ser validado |

Versões, URLs e hashes ficam em `toolchain.lock.toml`. O perfil executável fica em `config/profiles/qemu-riscv64.toml`.

Endereços de dispositivos e de memória vêm do DTB validado. O único endereço fixo no código é o de linkagem do kernel, `0x80200000`, que é o ponto de entrada que o OpenSBI usa nesta máquina.

O código nativo do supervisor é compilado para `rv64imac_zicsr_zifencei` com ABI `lp64` e roda com `sstatus.FS` desligado. As únicas instruções de ponto flutuante do kernel ficam na entrada e na saída de U-mode, em Assembly, e salvam e restauram `f0` a `f31` e `fcsr` do processo.

## Consequências

Aprovação no QEMU não homologa hardware físico. SMP, extensões vetoriais e de virtualização ficam fora: `h=off` e `v=off` impedem que uma aplicação dependa delas por acidente.

Sv39 com páginas de 4 KiB comporta o orçamento do perfil: a suíte `processes` mantém 16 processos vivos ao mesmo tempo, cada um com o próprio espaço de endereçamento, e a reserva de frames do supervisor continua livre.

Com este firmware, o motivo passado a `sbi_system_reset` não chega ao código de saída do QEMU, porque o desligamento passa pelo `syscon-poweroff`. O estado final do boot é a linha `kernel: status=` na serial, avaliada junto com o código de saída do emulador.

## Hipóteses a confirmar

- O runtime de usuário passa para a ABI `lp64d`. A troca de contexto já salva os registradores FP e `fcsr`, e um processo pode executar instruções de ponto flutuante, mas os dois perfis do runtime continuam compilados sem elas.
- PLIC e VirtIO-MMIO estão fixados no perfil, mas nenhum driver os usa ainda.
