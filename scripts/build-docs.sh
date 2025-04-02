#!/bin/bash

# Function to kill all background processes
cleanup() {
	echo "Terminating all background processes..."
	kill $pid_core $pid_frontend $pid_codegen $pid_storage $pid_audit $pid_ui
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
PROJECT=audit sphinx-autobuild --port=56679 -a --watch packages/ap-audit/ docs _docs-build/audit &
pid_audit=$!
PROJECT=ui sphinx-autobuild --port=56680 -a --watch packages/ap-ui/ docs _docs-build/ui &
pid_ui=$!
PROJECT=pdf sphinx-autobuild --port=56681 -a --watch packages/ap-pdf/ docs _docs-build/pdf &
pid_pdf=$!
PROJECT=server-choices sphinx-autobuild --port=56682 -a --watch packages/ap-server-choices/ docs _docs-build/server-choices &
pid_server_choices=$!
PROJECT=ordered-model sphinx-autobuild --port=56683 -a --watch packages/ap-ordered-model/ docs _docs-build/ordered-model &
pid_ordered_model=$!
sphinx-autobuild --port=56675 --open-browser -a --watch packages/ap-core/ docs _docs-build/core &
pid_core=$!

# Wait for all background processes to finish
wait $pid_core $pid_frontend $pid_codegen $pid_storage $pid_audit $pid_ui $pid_pdf $pid_server_choices $pid_ordered_model
