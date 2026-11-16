GUEST_TESTS := tests/guest

SELFTEST_KERNEL := $(BUILD)/kernel-selftest.elf
SELFTEST_C_SOURCES := \
	$(GUEST_TESTS)/supervisor/collector_probes.c \
	$(GUEST_TESTS)/supervisor/restart_probe.c \
	$(GUEST_TESTS)/supervisor/selftest_entry.c
SELFTEST_ASSEMBLY_SOURCES := \
	$(GUEST_TESTS)/supervisor/collector_roots.S \
	$(GUEST_TESTS)/supervisor/trap_probe.S
SELFTEST_OBJECTS := \
	$(addprefix $(BUILD)/,$(SELFTEST_ASSEMBLY_SOURCES:.S=.o)) \
	$(addprefix $(BUILD)/,$(SELFTEST_C_SOURCES:.c=.o))
SELFTEST_CFLAGS := $(NATIVE_CFLAGS) -Iports/micropython/shared -I$(GUEST_TESTS)/supervisor

SELFTEST_MANIFEST := $(GUEST_TESTS)/manifest.py
SELFTEST_INPUTS := \
	$(POLICY_MANIFEST) $(POLICY_INPUTS) \
	$(shell find $(GUEST_TESTS)/runtime_selftest tests/conformance/corpus -name '*.py' | LC_ALL=C sort)
SELFTEST_FROZEN := $(RUNTIME_BUILD)/supervisor/frozen/selftest/frozen_content.o

FAULT_ELF := $(USER_BUILD)/fault.elf
FAULT_IMAGE := $(BUILD)/fault.img
FAULT_START_OBJECT := $(BUILD)/$(GUEST_TESTS)/user/fault_start.o
FAULT_HEAP_BYTES := 0x1000
FAULT_STACK_BYTES := 0x1000

$(BUILD)/$(GUEST_TESTS)/%.o: $(GUEST_TESTS)/%.c
	@mkdir -p $(dir $@)
	$(CROSS_COMPILE)gcc $(SELFTEST_CFLAGS) -MMD -MP -c -o $@ $<

$(BUILD)/$(GUEST_TESTS)/%.o: $(GUEST_TESTS)/%.S
	@mkdir -p $(dir $@)
	$(CROSS_COMPILE)gcc $(SELFTEST_CFLAGS) -MMD -MP -c -o $@ $<

$(SELFTEST_FROZEN): $(SELFTEST_MANIFEST) $(SELFTEST_INPUTS) $(SUPERVISOR_LIBRARY) $(POLICY_FROZEN)
	$(call frozen_make,supervisor,selftest,$(SELFTEST_MANIFEST),$(SELFTEST_INPUTS))

$(SELFTEST_KERNEL): $(NATIVE_OBJECTS) $(SELFTEST_OBJECTS) $(SELFTEST_FROZEN) $(KERNEL_RUNTIME) $(KERNEL_LINKER_SCRIPT)
	$(call link_kernel,$(NATIVE_OBJECTS) $(SELFTEST_OBJECTS) $(SELFTEST_FROZEN))

$(FAULT_ELF): $(USER_HEADER_OBJECT) $(FAULT_START_OBJECT) $(USER_LINKER_SCRIPT)
	@mkdir -p $(dir $@)
	$(CROSS_COMPILE)ld $(call user_link_flags,$(FAULT_HEAP_BYTES),$(FAULT_STACK_BYTES)) \
		-Map=$@.map -o $@ $(USER_HEADER_OBJECT) $(FAULT_START_OBJECT)

-include $(SELFTEST_OBJECTS:.o=.d)
