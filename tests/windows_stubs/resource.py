"""Minimal Windows stand-in for the Unix ``resource`` module."""
RLIMIT_NOFILE = 7
RLIM_INFINITY = -1


def getrlimit(_which):
    return (1024, 1024)


def setrlimit(_which, _limits):
    return None
