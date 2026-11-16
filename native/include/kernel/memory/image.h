#ifndef KERNEL_MEMORY_IMAGE_H
#define KERNEL_MEMORY_IMAGE_H

extern const char kernel_image_start[];
extern const char kernel_image_end[];
extern const char supervisor_stack_bottom[];
extern const char supervisor_stack_top[];
extern const char emergency_stack_bottom[];
extern const char emergency_stack_top[];
extern const char supervisor_heap_start[];
extern const char supervisor_heap_end[];
extern const char user_region_start[];
extern const char user_region_end[];

#endif
