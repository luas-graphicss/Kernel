REQUIRED_VARIABLES := \
	BUILD CROSS_COMPILE MICROPYTHON_DIR KERNEL_ROOT MPY_CROSS \
	TARGET_FLAGS ASSEMBLER_FLAGS PATH_MAPS
$(foreach name,$(REQUIRED_VARIABLES),$(if $($(name)),,$(error $(name) is not set; build from the repository Makefile)))

include $(MICROPYTHON_DIR)/py/mkenv.mk
include $(TOP)/py/py.mk

PORT_ROOT := ..
RUNTIME_LIBRARY := $(BUILD)/libruntime.a

SHARED_SOURCES := \
	shared/diagnostics/failures.c \
	shared/imports/external.c \
	shared/lifecycle/runtime.c \
	shared/memory/collector.c \
	shared/memory/heap.c
UPSTREAM_SOURCES := shared/runtime/gchelper_native.c
UPSTREAM_ASSEMBLY := shared/runtime/gchelper_rv64i.s
PORT_SOURCES := $(SHARED_SOURCES) $(PROFILE_SOURCES)

INC := -I. -I$(PORT_ROOT)/shared -I$(TOP) -I$(BUILD) -I$(KERNEL_ROOT)/native/include
CFLAGS += \
	$(INC) -std=gnu99 -Os -g $(TARGET_FLAGS) $(PATH_MAPS) \
	-Wall -Wextra -Wno-unused-parameter -Wpointer-arith -Werror \
	-DMICROPY_MODULE_FROZEN_MPY=1 -DMICROPY_QSTR_EXTRA_POOL=mp_qstr_frozen_const_pool
AFLAGS += $(ASSEMBLER_FLAGS)

SRC_QSTR += $(PORT_SOURCES)
OBJ := \
	$(PY_CORE_O) \
	$(addprefix $(BUILD)/,$(PORT_SOURCES:.c=.o)) \
	$(addprefix $(BUILD)/,$(PROFILE_ASSEMBLY:.S=.o)) \
	$(addprefix $(BUILD)/,$(UPSTREAM_SOURCES:.c=.o)) \
	$(addprefix $(BUILD)/,$(UPSTREAM_ASSEMBLY:.s=.o))

.PHONY: runtime frozen
runtime: $(RUNTIME_LIBRARY)

$(RUNTIME_LIBRARY): $(OBJ)
	$(ECHO) "AR $@"
	$(Q)$(RM) -f $@
	$(Q)$(AR) rcsD $@ $^

ifneq ($(FROZEN_SET),)
FROZEN_BUILD := $(BUILD)/frozen/$(FROZEN_SET)
FROZEN_SOURCE := $(FROZEN_BUILD)/frozen_content.c
FROZEN_OBJECT := $(FROZEN_BUILD)/frozen_content.o

frozen: $(FROZEN_OBJECT)

$(FROZEN_SOURCE): $(FROZEN_SET_MANIFEST) $(FROZEN_SET_INPUTS) $(HEADER_BUILD)/qstrdefs.generated.h $(MPY_CROSS)
	$(ECHO) "FREEZE $(FROZEN_SET)"
	$(Q)$(MKDIR) -p $(FROZEN_BUILD)/genhdr
	$(Q)$(CP) $(HEADER_BUILD)/qstrdefs.preprocessed.h $(FROZEN_BUILD)/genhdr/qstrdefs.preprocessed.h
	$(Q)$(RM) -f $@
	$(Q)MICROPY_MPYCROSS=$(MPY_CROSS) $(MAKE_MANIFEST) -o $@ \
		-v "MPY_DIR=$(TOP)" -v "PORT_DIR=$(CURDIR)" -v "KERNEL_ROOT=$(KERNEL_ROOT)" \
		-b "$(FROZEN_BUILD)" -f"$(MPY_CROSS_FLAGS)" $(FROZEN_SET_MANIFEST)

$(FROZEN_OBJECT): $(FROZEN_SOURCE)
	$(ECHO) "CC $<"
	$(Q)$(CC) $(CFLAGS) -c -o $@ $<
endif

include $(TOP)/py/mkrules.mk

vpath %.c $(PORT_ROOT)
