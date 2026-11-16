#include "kernel/devices/interrupt_controller.h"

#include "kernel/memory/page_table.h"

#define PRIORITY_BYTES 4u
#define ENABLE_BASE 0x2000u
#define ENABLE_CONTEXT_BYTES 0x80u
#define CONTEXT_BASE 0x200000u
#define CONTEXT_BYTES 0x1000u
#define CONTEXT_THRESHOLD 0u
#define CONTEXT_CLAIM 4u
#define WORD_BITS 32u
#define WORD_BYTES 4u
#define ENABLED_PRIORITY 1u
#define ACCEPT_EVERY_PRIORITY 0u

static uintptr_t registers;
static uint32_t context;
static uint32_t sources;

static volatile uint32_t *word_at(uint64_t offset)
{
    return (volatile uint32_t *)(registers + offset);
}

static uint64_t enable_offset(uint32_t supervisor_context, uint32_t source)
{
    return ENABLE_BASE + (uint64_t)supervisor_context * ENABLE_CONTEXT_BYTES +
           (uint64_t)(source / WORD_BITS) * WORD_BYTES;
}

static uint64_t context_offset(uint32_t supervisor_context)
{
    return CONTEXT_BASE + (uint64_t)supervisor_context * CONTEXT_BYTES;
}

static struct memory_range page_of(uint64_t address)
{
    return (struct memory_range){.base = address - address % PAGE_BYTES, .length = PAGE_BYTES};
}

bool interrupt_controller_pages(const struct interrupt_controller_description *description,
                                struct memory_range pages[INTERRUPT_CONTROLLER_PAGES])
{
    uint64_t base = description->registers.base;
    uint64_t last_enable = enable_offset(description->supervisor_context, description->sources);
    uint64_t claim = context_offset(description->supervisor_context) + CONTEXT_CLAIM;

    if (base % PAGE_BYTES != 0 || claim + WORD_BYTES > description->registers.length ||
        (uint64_t)(description->sources + 1u) * PRIORITY_BYTES > PAGE_BYTES ||
        page_of(last_enable).base != page_of(enable_offset(description->supervisor_context, 0)).base) {
        return false;
    }
    pages[0] = page_of(base);
    pages[1] = page_of(base + last_enable);
    pages[2] = page_of(base + claim);
    return true;
}

void interrupt_controller_attach(const struct interrupt_controller_description *description)
{
    registers = (uintptr_t)description->registers.base;
    context = description->supervisor_context;
    sources = description->sources;
    for (uint32_t source = 0; source <= sources; source += WORD_BITS) {
        *word_at(enable_offset(context, source)) = 0;
    }
    *word_at(context_offset(context) + CONTEXT_THRESHOLD) = ACCEPT_EVERY_PRIORITY;
}

void interrupt_controller_enable(uint32_t source)
{
    volatile uint32_t *enable = word_at(enable_offset(context, source));

    *word_at((uint64_t)source * PRIORITY_BYTES) = ENABLED_PRIORITY;
    *enable = *enable | (1u << (source % WORD_BITS));
}

void interrupt_controller_disable(uint32_t source)
{
    volatile uint32_t *enable = word_at(enable_offset(context, source));

    *enable = *enable & ~(1u << (source % WORD_BITS));
}

uint32_t interrupt_controller_claim(void)
{
    return *word_at(context_offset(context) + CONTEXT_CLAIM);
}

void interrupt_controller_complete(uint32_t source)
{
    *word_at(context_offset(context) + CONTEXT_CLAIM) = source;
}
