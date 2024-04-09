#!/bin/bash

if [[ -f /home/runner/.netrc ]] ; then
    # I added this as, in github actions, I would get:
    # [NetrcParseError]: ~/.netrc access too permissive: access permissions must restrict access to only the owner (/home/runner/.netrc, line 3)
    # This appeared to come from the `pdm publish` step, but unclear exactly why. This fixes it.
    echo "Found /home/runner/.netrc, updating permissions"
    chmod og-rw /home/runner/.netrc
else
    echo "No .netrc found"
fi
pdm run scripts/publish.py
