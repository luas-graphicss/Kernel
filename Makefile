REQUIRED_VARIABLES := \
	BUILD CROSS_COMPILE MICROPYTHON_DIR KERNEL_BASE SUPERVISOR_STACK_BYTES \
	EMERGENCY_STACK_BYTES SUPERVISOR_HEAP_BYTES USER_REGION_BASE USER_REGION_BYTES \
	PROFILE_MEMORY_BYTES
$(foreach name,$(REQUIRED_VARIABLES),$(if $($(name)),,$(error $(name) is not set; build with kernel-tool)))

include native/native.mk

KERNEL := $(BUILD)/kernel.elf
LIBC_OBJECT := $(BUILD)/micropython/shared/libc/string0.o
LIBC_CFLAGS := \
	-std=gnu99 -Os -g $(NATIVE_ARCH_FLAGS) $(NATIVE_FREESTANDING_FLAGS) $(NATIVE_PATH_MAPS) \
	-fno-tree-loop-distribute-patterns -Wall -Werror
LINK_FLAGS := \
	-m elf64lriscv -nostdlib --no-relax --gc-sections --build-id=none \
	-T native/arch/riscv64/boot/kernel.ld \
	--defsym=KERNEL_BASE=$(KERNEL_BASE) \
	--defsym=SUPERVISOR_STACK_BYTES=$(SUPERVISOR_STACK_BYTES) \
	--defsym=EMERGENCY_STACK_BYTES=$(EMERGENCY_STACK_BYTES) \
	--defsym=SUPERVISOR_HEAP_BYTES=$(SUPERVISOR_HEAP_BYTES) \
	--defsym=USER_REGION_BASE=$(USER_REGION_BASE) \
	--defsym=USER_REGION_BYTES=$(USER_REGION_BYTES)

.DEFAULT_GOAL := all
.PHONY: all analyze
all: $(KERNEL)

analyze: $(NATIVE_ANALYSIS)

$(LIBC_OBJECT): $(MICROPYTHON_DIR)/shared/libc/string0.c
	@mkdir -p $(dir $@)
	$(CROSS_COMPILE)gcc $(LIBC_CFLAGS) -c -o $@ $<

$(KERNEL): $(NATIVE_OBJECTS) $(LIBC_OBJECT) native/arch/riscv64/boot/kernel.ld
	$(CROSS_COMPILE)ld $(LINK_FLAGS) -Map=$@.map -o $@ $(NATIVE_OBJECTS) $(LIBC_OBJECT)
