#include "kernel/devices/interrupts.h"

#include <stddef.h>

#include "kernel/abi/devices.h"
#include "kernel/arch/interrupts.h"
#include "kernel/devices/interrupt_controller.h"

#define NO_SOURCE 0u
#define CLAIMS_PER_DISPATCH 16u

struct binding {
    uint32_t source;
    interrupt_handler handler;
    void *context;
};

static struct binding bindings[DEVICE_SLOTS];
static uint32_t bound;
static uint64_t handled;
static bool attached;

static const struct binding *binding_of(uint32_t source)
{
    for (uint32_t index = 0; index < bound; index++) {
        if (bindings[index].source == source) {
            return &bindings[index];
        }
    }
    return NULL;
}

void interrupts_attach(const struct interrupt_controller_description *controller)
{
    interrupt_controller_attach(controller);
    bound = 0;
    handled = 0;
    attached = true;
    cpu_external_interrupts_enable();
}

bool interrupts_bind(uint32_t source, interrupt_handler handler, void *context)
{
    if (!attached || bound == DEVICE_SLOTS || binding_of(source) != NULL) {
        return false;
    }
    bindings[bound] = (struct binding){.source = source, .handler = handler, .context = context};
    bound++;
    interrupt_controller_enable(source);
    return true;
}

void interrupts_dispatch(void)
{
    if (!attached) {
        return;
    }
    for (uint32_t claim = 0; claim < CLAIMS_PER_DISPATCH; claim++) {
        uint32_t source = interrupt_controller_claim();
        const struct binding *binding;

        if (source == NO_SOURCE) {
            return;
        }
        binding = binding_of(source);
        if (binding != NULL) {
            binding->handler(binding->context);
        } else {
            interrupt_controller_disable(source);
        }
        interrupt_controller_complete(source);
        handled++;
    }
}

uint64_t interrupts_handled(void)
{
    return handled;
}
