#!/bin/bash


if [[ $# -lt 1 ]] ; then
    echo "usage: $0 [program-name]"
    exit 1
fi

"$@"

exit_code=$?

if [[ ${exit_code} -eq 0 ]] ; then
    echo "exiting with 0"
    exit 0
else
    if xdpyinfo >/dev/null ; then
    # the xserver is down
        echo "exiting with 1"
        exit ${exit_code}
    else
        # it was a genuine crash
        echo "exiting with 0"
        exit 0
    fi
fi
