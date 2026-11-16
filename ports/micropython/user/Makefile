PROFILE_SOURCES := \
	bindings/buffers.c \
	bindings/calls.c \
	bindings/messages.c \
	bindings/module.c \
	main.c \
	platform.c \
	startup.c \
	$(EXTENSION_SOURCES)
PROFILE_ASSEMBLY := process_calls.S $(EXTENSION_ASSEMBLY)

ifneq ($(EXTENSION_ROOT),)
CFLAGS += -I$(EXTENSION_ROOT)
vpath %.c $(EXTENSION_ROOT)
vpath %.S $(EXTENSION_ROOT)
endif

include ../port.mk
