"""Minimal Windows stand-in so Home Assistant's test plugin can import."""
LOCK_SH = 1
LOCK_EX = 2
LOCK_NB = 4
LOCK_UN = 8
F_GETFL = 3
F_SETFL = 4
F_GETFD = 1
F_SETFD = 2
FD_CLOEXEC = 1


def flock(*args, **kwargs):
    return None


def fcntl(*args, **kwargs):
    return 0


def lockf(*args, **kwargs):
    return None
