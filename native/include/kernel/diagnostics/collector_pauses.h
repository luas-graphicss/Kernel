#ifndef KERNEL_DIAGNOSTICS_COLLECTOR_PAUSES_H
#define KERNEL_DIAGNOSTICS_COLLECTOR_PAUSES_H

#include "kernel/diagnostics/pause_statistics.h"

void collector_pause_begins(void);
void collector_pause_ends(void);
struct pause_summary collector_pauses_summary(void);

#endif
