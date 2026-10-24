#! /bin/bash
export VIDNOTE_SCRIPT="${VIDNOTE_SCRIPT:-${APPDIR}/annotate.sh}"
export LD_LIBRARY_PATH="${APPDIR}/extra-libs${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
export PYTHONPATH="${APPDIR}${PYTHONPATH:+:${PYTHONPATH}}"
exec {{ python-executable }} -s -m vidnote "$@"
