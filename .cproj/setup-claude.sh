#!/bin/bash
# Auto-generated script to setup Node.js for Claude CLI
# Run: source .cproj/setup-claude.sh

echo "🚀 Setting up Node.js environment for Claude CLI..."

# Source nvm
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

# Use LTS Node
nvm use --lts

echo "✅ Node.js LTS activated. You can now run 'claude' command."
echo "💡 Tip: Run 'source .cproj/setup-claude.sh' whenever you open a new terminal in this directory"
