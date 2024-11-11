#!/bin/bash

# Function to kill all background processes
cleanup() {
	echo "Terminating all background processes..."
	kill $pid_core $pid_frontend $pid_codegen $pid_storage
}

# Trap SIGINT (Ctrl+C) and SIGTERM (termination signal) to call the cleanup function
trap cleanup SIGINT SIGTERM

# Start your processes in the background and capture their PIDs
PROJECT=frontend sphinx-autobuild --port=56676 -a --watch packages/ap-frontend/ docs _docs-build/frontend &
pid_frontend=$!
PROJECT=codegen sphinx-autobuild --port=56677 -a --watch packages/ap-codegen/ docs _docs-build/codegen &
pid_codegen=$!
PROJECT=storage sphinx-autobuild --port=56678 -a --watch packages/ap-storage/ docs _docs-build/storage &
pid_storage=$!
sphinx-autobuild --port=56675 --open-browser -a --watch packages/ap-core/ docs _docs-build/core &
pid_core=$!

# Wait for all background processes to finish
wait $pid_core $pid_frontend $pid_codegen $pid_storage
