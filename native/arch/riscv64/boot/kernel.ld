OUTPUT_ARCH(riscv)
ENTRY(_start)

PHDRS
{
    text PT_LOAD FLAGS(5);
    rodata PT_LOAD FLAGS(4);
    data PT_LOAD FLAGS(6);
}

SECTIONS
{
    . = KERNEL_BASE;
    kernel_image_start = .;

    .text : {
        KEEP(*(.text.entry))
        *(.text .text.*)
    } :text

    .rodata : ALIGN(4096) {
        *(.rodata .rodata.* .srodata .srodata.*)
    } :rodata

    .data : ALIGN(4096) {
        *(.data .data.* .sdata .sdata.*)
    } :data

    .bss (NOLOAD) : ALIGN(16) {
        kernel_bss_start = .;
        *(.bss .bss.* .sbss .sbss.* COMMON)
        . = ALIGN(16);
        kernel_bss_end = .;
    } :data

    . = ALIGN(4096);
    kernel_image_end = .;

    supervisor_stack_bottom = .;
    . += SUPERVISOR_STACK_BYTES;
    supervisor_stack_top = .;

    emergency_stack_bottom = .;
    . += EMERGENCY_STACK_BYTES;
    emergency_stack_top = .;

    supervisor_heap_start = .;
    . += SUPERVISOR_HEAP_BYTES;
    supervisor_heap_end = .;

    user_region_start = USER_REGION_BASE;
    user_region_end = USER_REGION_BASE + USER_REGION_BYTES;

    ASSERT(supervisor_heap_end <= user_region_start, "the kernel image overlaps the user region")

    /DISCARD/ : {
        *(.comment)
        *(.note .note.*)
        *(.eh_frame .eh_frame_hdr)
    }
}
