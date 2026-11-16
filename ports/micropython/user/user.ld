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
    user_text_content_end = .;

    . = ALIGN(4096);
    user_text_end = .;

    .rodata : {
        *(.rodata .rodata.* .srodata .srodata.*)
    } :rodata
    user_rodata_content_end = .;

    . = ALIGN(4096);
    user_rodata_end = .;

    .data : {
        *(.data .data.* .sdata .sdata.*)
    } :data
    user_data_content_end = .;

    .bss (NOLOAD) : ALIGN(16) {
        *(.bss .bss.* .sbss .sbss.* COMMON)
    } :data

    . = ALIGN(4096);
    user_data_end = .;

    user_file_end = SIZEOF(.data) > 0 ? user_data_content_end :
                    SIZEOF(.rodata) > 0 ? user_rodata_content_end : user_text_content_end;
    user_file_bytes = user_file_end - user_image_start;
    user_text_bytes = user_text_end - user_image_start;
    user_rodata_bytes = user_rodata_end - user_text_end;
    user_data_bytes = user_data_end - user_rodata_end;
    user_heap_bytes = USER_HEAP_BYTES;
    user_stack_bytes = USER_STACK_BYTES;

    ASSERT(user_data_end + USER_HEAP_BYTES + 4096 + USER_STACK_BYTES
           <= USER_REGION_BASE + USER_REGION_BYTES,
           "the user image does not fit the user region")

    /DISCARD/ : {
        *(.comment)
        *(.note .note.*)
        *(.eh_frame .eh_frame_hdr)
    }
}
