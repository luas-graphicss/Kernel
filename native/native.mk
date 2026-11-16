NATIVE_ISA_FLAGS := -march=rv64imac_zicsr_zifencei -mabi=lp64
NATIVE_ARCH_FLAGS := $(NATIVE_ISA_FLAGS) -mcmodel=medany -mno-relax
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
NATIVE_PROFILE_FLAGS := \
	-DPROFILE_MEMORY_BYTES=$(PROFILE_MEMORY_BYTES)ull \
	-DPROFILE_PROCESSES=$(PROFILE_PROCESSES)ull \
	-DPROFILE_PROCESS_HEAP_BYTES=$(PROFILE_PROCESS_HEAP_BYTES)ull \
	-DPROFILE_CAPABILITIES_PER_PROCESS=$(PROFILE_CAPABILITIES_PER_PROCESS)ull \
	-DPROFILE_IPC_PENDING_BYTES_PER_PROCESS=$(PROFILE_IPC_PENDING_BYTES_PER_PROCESS)ull \
	-DPROFILE_IPC_PENDING_BYTES_GLOBAL=$(PROFILE_IPC_PENDING_BYTES_GLOBAL)ull
NATIVE_CFLAGS := \
	-std=c17 -O2 -g $(NATIVE_ARCH_FLAGS) $(NATIVE_FREESTANDING_FLAGS) \
	$(NATIVE_HEADER_FLAGS) $(NATIVE_PATH_MAPS) $(NATIVE_WARNING_FLAGS) $(NATIVE_PROFILE_FLAGS)

NATIVE_C_SOURCES := \
	native/arch/riscv64/sbi/sbi.c \
	native/arch/riscv64/traps/trap.c \
	native/supervisor/capabilities/capability_space.c \
	native/supervisor/devices/device_tree/boot_description.c \
	native/supervisor/devices/device_tree/container.c \
	native/supervisor/devices/device_tree/device_inventory.c \
	native/supervisor/devices/device_tree/properties.c \
	native/supervisor/devices/device_tree/tokens.c \
	native/supervisor/devices/interrupts/dispatch.c \
	native/supervisor/devices/interrupts/plic.c \
	native/supervisor/devices/registry/device_registry.c \
	native/supervisor/devices/serial/serial_port.c \
	native/supervisor/devices/uart_ns16550.c \
	native/supervisor/devices/virtio/device.c \
	native/supervisor/devices/virtio/mmio.c \
	native/supervisor/devices/virtio/negotiation.c \
	native/supervisor/devices/virtio/queue.c \
	native/supervisor/diagnostics/console.c \
	native/supervisor/diagnostics/counters.c \
	native/supervisor/diagnostics/halt.c \
	native/supervisor/events/event_queue.c \
	native/supervisor/ipc/call.c \
	native/supervisor/ipc/endpoint.c \
	native/supervisor/ipc/message.c \
	native/supervisor/main.c \
	native/supervisor/memory/address_space.c \
	native/supervisor/memory/buffer.c \
	native/supervisor/memory/frame_pool.c \
	native/supervisor/memory/kernel_space.c \
	native/supervisor/memory/layout.c \
	native/supervisor/memory/page_table.c \
	native/supervisor/memory/physical_memory.c \
	native/supervisor/memory/range.c \
	native/supervisor/objects/kernel_objects.c \
	native/supervisor/objects/object_table.c \
	native/supervisor/objects/slot_table.c \
	native/supervisor/processes/lifecycle.c \
	native/supervisor/processes/process_table.c \
	native/supervisor/processes/program.c \
	native/supervisor/processes/run.c \
	native/supervisor/processes/spawn.c \
	native/supervisor/processes/spawn_request.c \
	native/supervisor/processes/supervision.c \
	native/supervisor/processes/syscall.c \
	native/supervisor/processes/syscall_capability.c \
	native/supervisor/processes/syscall_device.c \
	native/supervisor/processes/syscall_ipc.c \
	native/supervisor/processes/syscall_memory.c \
	native/supervisor/processes/syscall_process.c \
	native/supervisor/processes/user_image.c \
	native/supervisor/processes/wait.c \
	native/supervisor/startup/environment.c \
	native/supervisor/startup/profile.c \
	native/supervisor/timers/clock.c \
	native/supervisor/timers/timer.c

NATIVE_ASSEMBLY_SOURCES := \
	native/arch/riscv64/boot/entry.S \
	native/arch/riscv64/context/user_context.S \
	native/arch/riscv64/interrupts/external.S \
	native/arch/riscv64/mmu/mmu.S \
	native/arch/riscv64/sbi/sbi_call.S \
	native/arch/riscv64/timer/timer.S \
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
