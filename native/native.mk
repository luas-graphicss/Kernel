NATIVE_ARCH_FLAGS := -march=rv64imac_zicsr_zifencei -mabi=lp64 -mcmodel=medany -mno-relax
NATIVE_PATH_MAPS := \
	-ffile-prefix-map=$(CURDIR)=. \
	-ffile-prefix-map=$(MICROPYTHON_DIR)=micropython \
	-ffile-prefix-map=$(BUILD)=build
NATIVE_FREESTANDING_FLAGS := \
	-ffreestanding -fno-common -fno-pie -fno-stack-protector \
	-ffunction-sections -fdata-sections
NATIVE_HEADER_FLAGS := -nostdinc -isystem $(shell $(CROSS_COMPILE)gcc -print-file-name=include) -Inative/include
NATIVE_WARNING_FLAGS := \
	-Wall -Wextra -Wpedantic -Wconversion -Wshadow -Wundef \
	-Wstrict-prototypes -Wmissing-prototypes -Werror
NATIVE_PROFILE_FLAGS := -DPROFILE_MEMORY_BYTES=$(PROFILE_MEMORY_BYTES)ull
NATIVE_CFLAGS := \
	-std=c17 -O2 -g $(NATIVE_ARCH_FLAGS) $(NATIVE_FREESTANDING_FLAGS) \
	$(NATIVE_HEADER_FLAGS) $(NATIVE_PATH_MAPS) $(NATIVE_WARNING_FLAGS) $(NATIVE_PROFILE_FLAGS)

NATIVE_C_SOURCES := \
	native/arch/riscv64/sbi/sbi.c \
	native/arch/riscv64/traps/trap.c \
	native/supervisor/devices/device_tree/boot_description.c \
	native/supervisor/devices/device_tree/container.c \
	native/supervisor/devices/device_tree/tokens.c \
	native/supervisor/devices/uart_ns16550.c \
	native/supervisor/diagnostics/console.c \
	native/supervisor/diagnostics/halt.c \
	native/supervisor/main.c \
	native/supervisor/memory/layout.c \
	native/supervisor/memory/range.c \
	native/supervisor/startup/environment.c

NATIVE_ASSEMBLY_SOURCES := \
	native/arch/riscv64/boot/entry.S \
	native/arch/riscv64/sbi/sbi_call.S \
	native/arch/riscv64/traps/trap_vector.S

NATIVE_OBJECTS := \
	$(addprefix $(BUILD)/,$(NATIVE_ASSEMBLY_SOURCES:.S=.o)) \
	$(addprefix $(BUILD)/,$(NATIVE_C_SOURCES:.c=.o))
NATIVE_ANALYSIS := $(addprefix $(BUILD)/analysis/,$(NATIVE_C_SOURCES:.c=.checked))

$(BUILD)/native/%.o: native/%.c
	@mkdir -p $(dir $@)
	$(CROSS_COMPILE)gcc $(NATIVE_CFLAGS) -MMD -MP -c -o $@ $<

$(BUILD)/native/%.o: native/%.S
	@mkdir -p $(dir $@)
	$(CROSS_COMPILE)gcc $(NATIVE_CFLAGS) -MMD -MP -c -o $@ $<

$(BUILD)/analysis/native/%.checked: native/%.c
	@mkdir -p $(dir $@)
	$(CROSS_COMPILE)gcc $(NATIVE_CFLAGS) -fanalyzer -c -o /dev/null $<
	@touch $@

-include $(NATIVE_OBJECTS:.o=.d)
