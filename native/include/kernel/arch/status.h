#ifndef KERNEL_ARCH_STATUS_H
#define KERNEL_ARCH_STATUS_H

#define SSTATUS_SIE (1 << 1)
#define SSTATUS_SPIE (1 << 5)
#define SSTATUS_SPP (1 << 8)
#define SSTATUS_FS (3 << 13)
#define SSTATUS_FS_CLEAN (2 << 13)
#define SSTATUS_SUM (1 << 18)
#define SSTATUS_MXR (1 << 19)

#define INTERRUPT_SUPERVISOR_TIMER (1 << 5)

#define SATP_MODE_SV39 8
#define SATP_MODE_SHIFT 60
#define SATP_FRAME_SHIFT 12

#endif
