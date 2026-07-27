/*
 * rvftrig.so  --  LD_PRELOAD trigger for RVF on the SM-C200.
 *
 * ptrace call-injection was proven unworkable here: hijacking di-camera-app's
 * main thread (stopped inside the ecore/glib main loop's blocking syscall)
 * corrupts that syscall and crashes the app -- even for a harmless getpid().
 * See 11-injection-bench-log.md.
 *
 * This takes the opposite approach: the app loads us via LD_PRELOAD at a normal
 * service start, so our code runs INSIDE the fully-initialised process on our
 * OWN clean thread -- the same context the Bluetooth receive thread uses when a
 * phone sends "execute liveview". Our constructor spawns a thread; the thread
 * waits for init, then calls the app's own btSendEventToUI(8,0,20,0), which is
 * byte-for-byte the phone's execute-liveview call (command 20 = EXE_LIVEVIEW).
 * btSendEventToUI hands off to the event manager, whose delivery to the main
 * loop is thread-safe by design -- so calling it from a non-main thread is the
 * intended, safe path, unlike the ptrace hijack.
 *
 * It writes only to the SD card (/mnt/mmc/rvf-out/50-preload.txt). No block
 * device write. It falls back to the fixed-address handler if dlsym fails.
 *
 * Build (glibc 2.13 target so it loads into di-camera-app cleanly):
 *   zig cc -target arm-linux-gnueabihf.2.13 -shared -fPIC \
 *       -o build/rvftrig.so rvftrig.c -ldl -lpthread
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#define LOGPATH "/mnt/mmc/rvf-out/50-preload.txt"

/* di-camera-app is ET_EXEC, so these are fixed. Fallback if dlsym fails. */
#define HANDLER_ADDR   0x241b08u          /* handle_bt_app_receive_command (ARM) */
#define BT_SINGLETON   0x005027f4u        /* CUINETFuncBluetooth this / payload   */
#define CMD_LIVEVIEW   20                 /* EXE_LIVEVIEW                          */

typedef void (*bt_send_fn)(int, int, int, int);
typedef void (*handler_fn)(unsigned, int, int, void *);

static void logln(const char *msg)
{
    FILE *f = fopen(LOGPATH, "a");
    if (f) {
        fputs(msg, f);
        fputc('\n', f);
        fclose(f);
    }
    sync();
}

static void *trigger_thread(void *arg)
{
    (void)arg;
    logln("preload: thread started; waiting 12s for app init");
    sleep(12);

    bt_send_fn send = (bt_send_fn)dlsym(RTLD_DEFAULT, "btSendEventToUI");
    char buf[80];
    snprintf(buf, sizeof buf, "preload: dlsym btSendEventToUI = %p", (void *)send);
    logln(buf);

    if (send) {
        logln("preload: calling btSendEventToUI(8,0,20,0) from our thread");
        send(8, 0, CMD_LIVEVIEW, 0);
        logln("preload: btSendEventToUI returned; app survived the call");
    } else {
        logln("preload: dlsym failed; calling fixed handler @0x241b08");
        handler_fn h = (handler_fn)HANDLER_ADDR;
        h(BT_SINGLETON, 0, CMD_LIVEVIEW, (void *)(unsigned long)BT_SINGLETON);
        logln("preload: fixed handler returned; app survived the call");
    }

    /* Give RVF a few seconds to bind 7679, then check for it ourselves by
     * reading /proc/net/tcp. Port 7679 = 0x1DFF; a listening socket shows
     * state 0A. This puts the answer straight into the card log. */
    sleep(5);
    FILE *tcp = fopen("/proc/net/tcp", "r");
    int found = 0;
    if (tcp) {
        char line[512];
        while (fgets(line, sizeof line, tcp)) {
            /* local_address is the 2nd field as HEXIP:HEXPORT; 7679 = :1DFF */
            if (strstr(line, ":1DFF ") || strstr(line, ":1DFF\t")) { found = 1; break; }
        }
        fclose(tcp);
    }
    logln(found ? "preload: *** 7679 IS LISTENING -- RVF STARTED, NO PHONE ***"
                : "preload: 7679 not listening yet (trigger ran, app alive)");
    logln("preload: done");
    return 0;
}

__attribute__((constructor))
static void rvftrig_init(void)
{
    /* Self-clean FIRST. The service is set Restart=always so a kill will
     * reload us, but that also means if we ever crashed the app it would
     * re-preload us on every restart -> a loop. Deleting our .so and the
     * drop-in here makes a subsequent restart start the app WITHOUT us, so at
     * most one trigger ever happens. We are already mapped into memory, so
     * unlinking the file does not affect this running instance. */
    unlink("/opt/usr/rvftrig.so");
    unlink("/run/systemd/system/di-camera-app.service.d/rvf-preload.conf");

    logln("preload: constructor entered -- app started with LD_PRELOAD; self-cleaned");
    pthread_t t;
    if (pthread_create(&t, 0, trigger_thread, 0) != 0)
        logln("preload: pthread_create FAILED");
}
