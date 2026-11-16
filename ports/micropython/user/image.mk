USER_PORT := ports/micropython/user
USER_BUILD := $(BUILD)/user
USER_LINKER_SCRIPT := $(USER_PORT)/user.ld
USER_HEADER_OBJECT := $(BUILD)/$(USER_PORT)/image_header.o
USER_START_OBJECT := $(BUILD)/$(USER_PORT)/start.o

INIT_ELF := $(USER_BUILD)/init.elf
INIT_IMAGE := $(BUILD)/init.img

user_link_flags = \
	-m elf64lriscv -nostdlib --no-relax --gc-sections --build-id=none \
	-T $(USER_LINKER_SCRIPT) \
	--defsym=USER_REGION_BASE=$(USER_REGION_BASE) \
	--defsym=USER_REGION_BYTES=$(USER_REGION_BYTES) \
	--defsym=USER_HEAP_BYTES=$(1) \
	--defsym=USER_STACK_BYTES=$(2)

$(BUILD)/$(USER_PORT)/%.o: $(USER_PORT)/%.S
	@mkdir -p $(dir $@)
	$(CROSS_COMPILE)gcc $(NATIVE_CFLAGS) -c -o $@ $<

$(INIT_ELF): $(USER_HEADER_OBJECT) $(USER_START_OBJECT) $(INIT_FROZEN) $(USER_LIBRARY) $(LIBC_OBJECT) $(USER_LINKER_SCRIPT)
	@mkdir -p $(dir $@)
	$(CROSS_COMPILE)ld $(call user_link_flags,$(USER_HEAP_BYTES),$(USER_STACK_BYTES)) \
		-Map=$@.map -o $@ $(USER_HEADER_OBJECT) $(USER_START_OBJECT) $(INIT_FROZEN) \
		$(USER_LIBRARY) $(LIBC_OBJECT) $(LIBGCC)

$(BUILD)/%.img: $(USER_BUILD)/%.elf
	$(CROSS_COMPILE)objcopy -O binary $< $@
