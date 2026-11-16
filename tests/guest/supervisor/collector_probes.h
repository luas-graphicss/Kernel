#ifndef GUEST_SUPERVISOR_COLLECTOR_PROBES_H
#define GUEST_SUPERVISOR_COLLECTOR_PROBES_H

#include <stdbool.h>

#define COLLECTOR_PROBE_PASSED 0
#define COLLECTOR_PROBE_ROOT_COLLECTED 1
#define COLLECTOR_PROBE_DECOY_RETAINED 2

#ifndef __ASSEMBLER__

int collector_probe_register_s0(void);
int collector_probe_register_s1(void);
int collector_probe_register_s2(void);
int collector_probe_register_s3(void);
int collector_probe_register_s4(void);
int collector_probe_register_s5(void);
int collector_probe_register_s6(void);
int collector_probe_register_s7(void);
int collector_probe_register_s8(void);
int collector_probe_register_s9(void);
int collector_probe_register_s10(void);
int collector_probe_register_s11(void);
int collector_probe_stack_slot(void);

bool collector_probes_run(void);

#endif

#endif
