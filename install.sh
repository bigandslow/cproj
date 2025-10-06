#!/bin/bash
#
# Installation script for cproj - Standalone Python CLI tool
# This script creates an isolated installation that won't conflict with other Python apps
#

set -e

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="${CPROJ_INSTALL_DIR:-$HOME/.local/share/cproj}"
BIN_DIR="${CPROJ_BIN_DIR:-$HOME/.local/bin}"
PYTHON_VERSION="${CPROJ_PYTHON:-python3}"

echo -e "${BLUE}🚀 Installing cproj - Multi-project CLI with git worktree + uv${NC}"
echo

# Check if Python 3.8+ is available
echo -e "${BLUE}Checking Python version...${NC}"
if ! command -v "$PYTHON_VERSION" >/dev/null 2>&1; then
    echo -e "${RED}❌ Python 3 not found. Please install Python 3.8 or later.${NC}"
    exit 1
fi

PYTHON_VER=$($PYTHON_VERSION -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_VER_MAJOR=$($PYTHON_VERSION -c "import sys; print(sys.version_info.major)")
PYTHON_VER_MINOR=$($PYTHON_VERSION -c "import sys; print(sys.version_info.minor)")

if [ "$PYTHON_VER_MAJOR" -lt 3 ] || [ "$PYTHON_VER_MAJOR" -eq 3 -a "$PYTHON_VER_MINOR" -lt 8 ]; then
    echo -e "${RED}❌ Python 3.8+ required, found Python $PYTHON_VER${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Found Python $PYTHON_VER${NC}"

# Create installation directory
echo -e "${BLUE}Creating installation directory...${NC}"
mkdir -p "$INSTALL_DIR"
mkdir -p "$BIN_DIR"

# Create virtual environment for isolated installation
echo -e "${BLUE}Creating isolated Python environment...${NC}"
$PYTHON_VERSION -m venv "$INSTALL_DIR/venv"

# Activate virtual environment
source "$INSTALL_DIR/venv/bin/activate"

# Install dependencies
echo -e "${BLUE}Installing dependencies...${NC}"
pip install --quiet PyYAML

# Copy cproj.py to installation directory
echo -e "${BLUE}Installing cproj...${NC}"
cp "$SCRIPT_DIR/cproj.py" "$INSTALL_DIR/"

# Copy .claude directory if it exists
if [ -d "$SCRIPT_DIR/.claude" ]; then
    echo -e "${BLUE}Copying .claude template directory...${NC}"
    cp -r "$SCRIPT_DIR/.claude" "$INSTALL_DIR/"
fi

# Create wrapper script
echo -e "${BLUE}Creating executable wrapper...${NC}"
cat > "$BIN_DIR/cproj" << EOF
#!/bin/bash
#
# cproj wrapper script - executes cproj in isolated environment
#
export CPROJ_INSTALL_DIR="$INSTALL_DIR"
exec "$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/cproj.py" "\$@"
EOF

chmod +x "$BIN_DIR/cproj"

echo -e "${GREEN}✅ cproj installed successfully!${NC}"
echo
echo -e "${YELLOW}Installation details:${NC}"
echo "  - Install directory: $INSTALL_DIR"
echo "  - Executable: $BIN_DIR/cproj"
echo "  - Python environment: $INSTALL_DIR/venv"
echo

# Check if BIN_DIR is in PATH
if echo "$PATH" | grep -q "$BIN_DIR"; then
    echo -e "${GREEN}✅ $BIN_DIR is already in your PATH${NC}"
else
    echo -e "${YELLOW}⚠️  Add $BIN_DIR to your PATH:${NC}"
    echo
    echo "  For bash/zsh, add to ~/.bashrc or ~/.zshrc:"
    echo "    export PATH=\"$BIN_DIR:\$PATH\""
    echo
    echo "  Then restart your shell or run:"
    echo "    source ~/.bashrc  # or ~/.zshrc"
    echo
fi

# Show next steps
echo -e "${BLUE}🎉 Ready to use cproj!${NC}"
echo
echo "Try these commands:"
echo "  cproj init              # Interactive setup"
echo "  cproj --help            # Show all commands"
echo "  cproj config            # View current configuration"
echo

# Check for recommended tools
echo -e "${BLUE}Checking recommended tools...${NC}"
missing_tools=()

if ! command -v git >/dev/null 2>&1; then
    missing_tools+=("git")
fi

if ! command -v gh >/dev/null 2>&1; then
    missing_tools+=("gh (GitHub CLI)")
fi

if ! command -v uv >/dev/null 2>&1; then
    echo -e "${YELLOW}💡 uv not found - will use venv as fallback${NC}"
    echo "   Install uv for faster Python environments: curl -LsSf https://astral.sh/uv/install.sh | sh"
fi

if ! command -v op >/dev/null 2>&1; then
    echo -e "${YELLOW}💡 1Password CLI not found - secret management will be limited${NC}"
    echo "   Install from: https://developer.1password.com/docs/cli/get-started/"
fi

if [ ${#missing_tools[@]} -gt 0 ]; then
    echo -e "${YELLOW}⚠️  Missing recommended tools:${NC}"
    printf '   %s\n' "${missing_tools[@]}"
    echo
fi

echo -e "${GREEN}Installation complete! 🎉${NC}"