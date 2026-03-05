#!/bin/sh
# Ensure data directories exist and are writable by appuser
for dir in /app/data/uploads /app/data/exports /app/data/images /app/data/chroma /app/data/huggingface; do
    mkdir -p "$dir"
    chown appuser:appuser "$dir"
done

# Drop privileges and run the application
exec gosu appuser "$@"
