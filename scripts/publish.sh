#!/bin/bash

if [[ -f /home/runner/.netrc ]] ; then
    echo "Found /home/runner/.netrc, updating permissions"
    chmod og-rw /home/runner/.netrc
else
    echo "No .netrc found"
fi
pdm run scripts/publish.py
