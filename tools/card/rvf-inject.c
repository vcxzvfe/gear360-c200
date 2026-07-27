/*
 * rvf-inject.c  --  minimal ARM32 ptrace function-call injector.
 *
 * Purpose: from a root shell on the SM-C200, make the *running* di-camera-app
 * process call one of its own in-process functions with controlled integer
 * arguments, so that Remote View Finder starts (TCP 7679 binds) without a phone.
 *
 * It performs NO writes to any block device. It attaches to a live process,
 * runs one function call, restores the original register state, and detaches.
 *
 * Why this exists: the liveview command path runs entirely inside di-camera-app
 * (it links libdi-network-bt-app.so.0). The command normally arrives over
 * SAP/RFCOMM from the phone. There is no D-Bus/SysV/socket path a shell can use
 * to inject it, and there is no gdb/gdbserver/frida on the device. So we call the
 * proven entry point directly, in-process, via ptrace.
 *
 * Build (on the host, static, ARMv7):
 *   arm-linux-gnueabi-gcc -static -O2 -march=armv7-a -o rvf-inject rvf-inject.c
 * (hardfloat toolchain works too; -static makes the float ABI irrelevant.)
 *
 * Usage:
 *   rvf-inject <pid> <arm|thumb> <func_hex> <r0> <r1> <r2> <r3>
 * Args r0..r3 are parsed with strtoul base 0 (accept 0x.. or decimal).
 * Prints "OK r0=0x..." on a clean return, or an error and nonzero exit.
 *
 * Two call forms used by rvf-start.sh (both use command id 20 = EXE_LIVEVIEW):
 *   1) btSendEventToUI(8,0,20,0)  -- thumb, func = <libbase>+0x8de0
 *   2) handle_bt_app_receive_command(0x005027f4,0,20,0x005027f4) -- arm, func=0x241b08
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <signal.h>
#include <unistd.h>
#include <sys/ptrace.h>
#include <sys/types.h>
#include <sys/wait.h>

/* 18-word ARM register block as returned by PTRACE_GETREGS on ARM Linux. */
struct arm_regs { unsigned long uregs[18]; };
#define R_R0   0
#define R_SP   13
#define R_LR   14
#define R_PC   15
#define R_CPSR 16
#define CPSR_T 0x20u          /* Thumb execution-state bit */

/* Fallback request numbers, so this builds under any Linux libc (glibc, musl)
 * whose <sys/ptrace.h> spells these differently. Standard Linux values. */
#ifndef PTRACE_ATTACH
#define PTRACE_ATTACH 16
#endif
#ifndef PTRACE_DETACH
#define PTRACE_DETACH 17
#endif
#ifndef PTRACE_CONT
#define PTRACE_CONT 7
#endif
#ifndef PTRACE_GETREGS
#define PTRACE_GETREGS 12
#endif
#ifndef PTRACE_SETREGS
#define PTRACE_SETREGS 13
#endif

int main(int argc, char **argv)
{
    if (argc != 8) {
        fprintf(stderr,
            "usage: %s <pid> <arm|thumb> <func_hex> <r0> <r1> <r2> <r3>\n",
            argv[0]);
        return 2;
    }

    pid_t pid = (pid_t)strtol(argv[1], NULL, 0);
    int thumb = (strcmp(argv[2], "thumb") == 0);
    unsigned long func = strtoul(argv[3], NULL, 0);
    unsigned long a0 = strtoul(argv[4], NULL, 0);
    unsigned long a1 = strtoul(argv[5], NULL, 0);
    unsigned long a2 = strtoul(argv[6], NULL, 0);
    unsigned long a3 = strtoul(argv[7], NULL, 0);

    if (ptrace(PTRACE_ATTACH, pid, 0, 0) < 0) {
        fprintf(stderr, "PTRACE_ATTACH(%d) failed: %s\n", pid, strerror(errno));
        /* EPERM here usually means SMACK/yama blocked us -- see rvf-start.sh. */
        return 3;
    }

    int status;
    if (waitpid(pid, &status, 0) < 0) {
        fprintf(stderr, "waitpid(attach) failed: %s\n", strerror(errno));
        ptrace(PTRACE_DETACH, pid, 0, 0);
        return 3;
    }

    struct arm_regs saved, regs;
    if (ptrace(PTRACE_GETREGS, pid, 0, &saved) < 0) {
        fprintf(stderr, "GETREGS failed: %s\n", strerror(errno));
        ptrace(PTRACE_DETACH, pid, 0, 0);
        return 4;
    }

    regs = saved;
    regs.uregs[R_R0 + 0] = a0;
    regs.uregs[R_R0 + 1] = a1;
    regs.uregs[R_R0 + 2] = a2;
    regs.uregs[R_R0 + 3] = a3;
    regs.uregs[R_SP] &= ~7UL;          /* keep the stack 8-byte aligned      */
    regs.uregs[R_LR] = 0;              /* return to 0 -> faults -> we catch it */
    if (thumb) {
        regs.uregs[R_PC]   = func & ~1UL;
        regs.uregs[R_CPSR] |= CPSR_T;
    } else {
        regs.uregs[R_PC]   = func;
        regs.uregs[R_CPSR] &= ~CPSR_T;
    }

    if (ptrace(PTRACE_SETREGS, pid, 0, &regs) < 0) {
        fprintf(stderr, "SETREGS failed: %s\n", strerror(errno));
        ptrace(PTRACE_SETREGS, pid, 0, &saved);
        ptrace(PTRACE_DETACH, pid, 0, 0);
        return 4;
    }

    /* Run until the injected call returns to lr=0 (SIGSEGV) or we give up.
     * Tolerate a few unrelated signal-stops by re-delivering them. One
     * PTRACE_CONT + one waitpid per iteration; `pending` carries the signal
     * to re-deliver (0 = none). */
    unsigned long ret = 0;
    int ok = 0;
    long pending = 0;
    for (int i = 0; i < 64; i++) {
        if (ptrace(PTRACE_CONT, pid, 0, (void *)pending) < 0) {
            fprintf(stderr, "CONT failed: %s\n", strerror(errno));
            break;
        }
        pending = 0;
        if (waitpid(pid, &status, 0) < 0) {
            fprintf(stderr, "waitpid(run) failed: %s\n", strerror(errno));
            break;
        }
        if (WIFEXITED(status) || WIFSIGNALED(status)) {
            fprintf(stderr, "tracee died during call (status=0x%x)\n", status);
            return 5;                  /* nothing left to restore */
        }
        if (!WIFSTOPPED(status)) continue;

        int sig = WSTOPSIG(status);
        struct arm_regs cur;
        if (ptrace(PTRACE_GETREGS, pid, 0, &cur) < 0) break;

        /* Completion: control returned to the lr=0 trampoline. On ARM that is
         * a prefetch abort (SIGSEGV) or SIGILL with pc at ~0. */
        if ((sig == SIGSEGV || sig == SIGILL) && (cur.uregs[R_PC] & ~1UL) == 0) {
            ret = cur.uregs[R_R0];
            ok = 1;
            break;
        }
        /* Unrelated stop: re-deliver this signal on the next continue. */
        pending = sig;
    }

    /* Restore the process to exactly how we found it, then let it run. */
    ptrace(PTRACE_SETREGS, pid, 0, &saved);
    ptrace(PTRACE_DETACH, pid, 0, 0);

    if (!ok) {
        fprintf(stderr, "call did not complete cleanly\n");
        return 6;
    }
    printf("OK r0=0x%lx\n", ret);
    return 0;
}
