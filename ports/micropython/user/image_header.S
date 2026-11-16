#include "kernel/abi/user_image.h"

    .section .image_header, "a", @progbits
    .word USER_IMAGE_MAGIC
    .word USER_IMAGE_VERSION
    .dword user_image_start
    .dword user_file_bytes
    .dword user_memory_bytes
    .dword _start
    .dword user_heap_bytes
    .dword user_stack_bytes
