/* libdevice-node device_set_property helper for the SM-C200 watchdog.
 *   di-camera-app: Reset=set(4,26,0)  ShutdownAfterWatchdog(i)=set(4,25,i)
 *                  Enable(i)=set(4,23,i)  Disable=set(4,23,0)
 * Usage:
 *   devprop <type> <prop> <val>       one-shot
 *   devprop hold <seconds>            loop: keep watchdog kicked + no-reboot */
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
static int (*dsp)(int,int,int);
int main(int argc, char** argv){
    void* h = dlopen("libdevice-node.so.0.1", RTLD_NOW|RTLD_GLOBAL);
    if(!h){ printf("dlopen: %s\n", dlerror()); return 1; }
    dsp = (int(*)(int,int,int))dlsym(h, "device_set_property");
    if(!dsp){ printf("dlsym: %s\n", dlerror()); return 2; }
    if(argc>1 && argv[1][0]=='h'){           /* hold mode */
        int secs = argc>2 ? atoi(argv[2]) : 40;
        int i;
        for(i=0;i<secs*4;i++){
            dsp(4,25,0);                      /* do NOT reboot after watchdog */
            dsp(4,26,0);                      /* kick */
            usleep(250000);                   /* 4x/sec */
        }
        printf("hold done (%ds)\n", secs);
        return 0;
    }
    int t=argc>1?atoi(argv[1]):4, p=argc>2?atoi(argv[2]):23, v=argc>3?atoi(argv[3]):0;
    printf("device_set_property(%d,%d,%d) = %d\n", t, p, v, dsp(t,p,v));
    return 0;
}
