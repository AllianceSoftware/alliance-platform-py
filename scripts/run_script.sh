#!/bin/bash

# This is a wrapper that handles env specific setup before running a script. Specifically,
# when running in github actions, we need to ensure that the .netrc file is not world readable.

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <script-name>"
    exit 1
fi

if [[ -f /home/runner/.netrc ]] ; then
    # I added this as, in github actions, I would get:
    # [NetrcParseError]: ~/.netrc access too permissive: access permissions must restrict access to only the owner (/home/runner/.netrc, line 3)
    # This appeared to come from the publish step, but unclear exactly why. This fixes it.
    echo "Found /home/runner/.netrc, updating permissions"
    chmod og-rw /home/runner/.netrc
else
    echo "No .netrc found"
fi

uv run python $1
