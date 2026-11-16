RUNTIME_PORT := ports/micropython
RUNTIME_BUILD := $(BUILD)/runtime
MPY_CROSS := $(BUILD)/mpy-cross/mpy-cross
MPY_CROSS_FLAGS := -msmall-int-bits=63
LIBGCC := $(shell $(CROSS_COMPILE)gcc $(NATIVE_ARCH_FLAGS) -print-libgcc-file-name)

LIBC_OBJECT := $(RUNTIME_BUILD)/libc/string0.o
LIBC_CFLAGS := \
	-std=gnu99 -Os -g $(NATIVE_ARCH_FLAGS) $(NATIVE_FREESTANDING_FLAGS) $(NATIVE_PATH_MAPS) \
	-fno-tree-loop-distribute-patterns -Wall -Werror

SUPERVISOR_LIBRARY := $(RUNTIME_BUILD)/supervisor/libruntime.a
USER_LIBRARY := $(RUNTIME_BUILD)/user/libruntime.a

POLICY_MANIFEST := $(RUNTIME_PORT)/supervisor/manifest.py
POLICY_INPUTS := $(shell find src/kernel_core src/kernel_protocol -name '*.py' | LC_ALL=C sort)
POLICY_FROZEN := $(RUNTIME_BUILD)/supervisor/frozen/policy/frozen_content.o

CLIENT_INPUTS := $(shell find src/kernel_client src/kernel_protocol -name '*.py' | LC_ALL=C sort)
INIT_MANIFEST := $(RUNTIME_PORT)/user/manifest.py
INIT_INPUTS := $(CLIENT_INPUTS) $(shell find src/kernel_services -name '*.py' | LC_ALL=C sort)
INIT_FROZEN := $(RUNTIME_BUILD)/user/frozen/init/frozen_content.o

runtime_make = +$(MAKE) --no-print-directory -C $(RUNTIME_PORT)/$(2) $(1) \
	BUILD=$(RUNTIME_BUILD)/$(3) KERNEL_ROOT=$(CURDIR) \
	MPY_CROSS=$(MPY_CROSS) MPY_CROSS_FLAGS=$(MPY_CROSS_FLAGS) \
	TARGET_FLAGS="$(NATIVE_ARCH_FLAGS) $(NATIVE_FREESTANDING_FLAGS)" \
	ASSEMBLER_FLAGS="$(NATIVE_ISA_FLAGS)" PATH_MAPS="$(NATIVE_PATH_MAPS)"

frozen_make = $(call runtime_make,frozen,$(1),$(2)) FROZEN_SET=$(3) \
	FROZEN_SET_MANIFEST=$(abspath $(4)) FROZEN_SET_INPUTS="$(abspath $(5))"

.PHONY: FORCE
FORCE:

$(MPY_CROSS):
	+$(MAKE) --no-print-directory -C $(MICROPYTHON_DIR)/mpy-cross \
		BUILD=$(patsubst %/,%,$(dir $@)) CROSS_COMPILE=

$(LIBC_OBJECT): $(MICROPYTHON_DIR)/shared/libc/string0.c
	@mkdir -p $(dir $@)
	$(CROSS_COMPILE)gcc $(LIBC_CFLAGS) -c -o $@ $<

$(SUPERVISOR_LIBRARY): FORCE | $(MPY_CROSS)
	$(call runtime_make,runtime,supervisor,supervisor)

$(USER_LIBRARY): FORCE | $(MPY_CROSS)
	$(call runtime_make,runtime,user,user)

$(POLICY_FROZEN): $(POLICY_MANIFEST) $(POLICY_INPUTS) $(SUPERVISOR_LIBRARY)
	$(call frozen_make,supervisor,supervisor,policy,$(POLICY_MANIFEST),$(POLICY_INPUTS))

$(INIT_FROZEN): $(INIT_MANIFEST) $(INIT_INPUTS) $(USER_LIBRARY)
	$(call frozen_make,user,user,init,$(INIT_MANIFEST),$(INIT_INPUTS))
