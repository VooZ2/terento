// Read-only initialization check for the exact bundled library on the build host.
#include <dlfcn.h>
#include <stdio.h>

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    void *library = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (!library) { fputs("Cannot load bundled libusb\n", stderr); return 1; }
    int (*initialize)(void **) = (int (*)(void **))dlsym(library, "libusb_init");
    void (*finish)(void *) = (void (*)(void *))dlsym(library, "libusb_exit");
    if (!initialize || !finish) return 1;
    // No device is opened or claimed; no transfer, reset or file operation.
    for (int attempt = 0; attempt < 3; ++attempt) {
        void *context = NULL;
        if (initialize(&context) != 0 || !context) return 1;
        finish(context);
    }
    dlclose(library);
    puts("Bundled libusb initialization/exit: PASS");
    return 0;
}
