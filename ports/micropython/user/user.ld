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
    . = USER_REGION_BASE;
    user_image_start = .;

    .text : {
        KEEP(*(.image_header))
        *(.text.start)
        *(.text .text.*)
    } :text

    .rodata : ALIGN(8) {
        *(.rodata .rodata.* .srodata .srodata.*)
    } :rodata

    .data : ALIGN(8) {
        *(.data .data.* .sdata .sdata.*)
    } :data

    user_file_end = .;

    .bss (NOLOAD) : ALIGN(16) {
        *(.bss .bss.* .sbss .sbss.* COMMON)
    } :data

    . = ALIGN(16);
    user_heap_start = .;
    . += USER_HEAP_BYTES;
    user_heap_end = .;

    user_stack_bottom = .;
    . += USER_STACK_BYTES;
    user_stack_top = .;
    user_memory_end = .;

    user_file_bytes = user_file_end - user_image_start;
    user_memory_bytes = user_memory_end - user_image_start;
    user_heap_bytes = USER_HEAP_BYTES;
    user_stack_bytes = USER_STACK_BYTES;

    ASSERT(user_memory_end <= USER_REGION_BASE + USER_REGION_BYTES,
           "the user image does not fit the user region")

    /DISCARD/ : {
        *(.comment)
        *(.note .note.*)
        *(.eh_frame .eh_frame_hdr)
    }
}
