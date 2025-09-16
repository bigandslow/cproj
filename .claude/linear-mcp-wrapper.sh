#!/bin/bash
# Wrapper script for Linear MCP server that retrieves API key from 1Password

# Look for 1Password reference file in multiple locations
# First check workspace-specific, then user home
REFERENCE_FILE=""
if [ -f ".cproj/.linear-1password-ref" ]; then
    REFERENCE_FILE=".cproj/.linear-1password-ref"
elif [ -f "$HOME/.cproj/.linear-1password-ref" ]; then
    REFERENCE_FILE="$HOME/.cproj/.linear-1password-ref"
fi

if [ -z "$REFERENCE_FILE" ] || [ ! -f "$REFERENCE_FILE" ]; then
    echo "Error: No 1Password reference configured. Run 'cproj linear setup --from-1password' first." >&2
    exit 1
fi

# Read the 1Password reference
REFERENCE=$(cat "$REFERENCE_FILE")

# Retrieve the API key from 1Password
API_KEY=$(op read "$REFERENCE" 2>/dev/null)

if [ -z "$API_KEY" ]; then
    echo "Error: Failed to retrieve API key from 1Password. Make sure you're authenticated with 'op signin'." >&2
    exit 1
fi

# Run the Linear MCP server with the API key
LINEAR_API_KEY="$API_KEY" exec npx @linear/mcp-server "$@"