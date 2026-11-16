#include "check.h"

int check_failures;

int check_finish(const char *suite)
{
    printf("%s: %s\n", suite, check_failures == 0 ? "passed" : "failed");
    return check_failures == 0 ? 0 : 1;
}
