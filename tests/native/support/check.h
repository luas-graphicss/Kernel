#ifndef TESTS_NATIVE_SUPPORT_CHECK_H
#define TESTS_NATIVE_SUPPORT_CHECK_H

#include <stdio.h>

extern int check_failures;

#define CHECK(condition)                                                                    \
    do {                                                                                    \
        if (!(condition)) {                                                                 \
            check_failures++;                                                               \
            fprintf(stderr, "%s:%d: check failed: %s\n", __FILE__, __LINE__, #condition);  \
        }                                                                                   \
    } while (0)

int check_finish(const char *suite);

#endif
