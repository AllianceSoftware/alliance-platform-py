#!/bin/bash

# Function to kill all background processes
cleanup() {
    echo "Terminating all background processes..."
    kill $pid1 $pid2 $pid3
}

# Trap SIGINT (Ctrl+C) and SIGTERM (termination signal) to call the cleanup function
trap cleanup SIGINT SIGTERM

# Start your processes in the background and capture their PIDs
PROJECT=frontend sphinx-autobuild --port=56676 --open-browser -a --watch packages/ap-frontend/ docs _docs-build/frontend&
pid2=$!
PROJECT=codegen sphinx-autobuild --port=56677 --open-browser -a --watch packages/ap-codegen/ docs _docs-build/codegen&
pid3=$!
sphinx-autobuild --port=56675 --open-browser -a --watch packages/ap-core/ docs _docs-build/core& 
pid1=$!

# Wait for all background processes to finish
wait $pid1 $pid2 $pid3
