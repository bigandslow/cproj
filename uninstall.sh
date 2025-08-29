#!/bin/bash
#
# Uninstall script for cproj
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
INSTALL_DIR="${CPROJ_INSTALL_DIR:-$HOME/.local/share/cproj}"
BIN_DIR="${CPROJ_BIN_DIR:-$HOME/.local/bin}"
CONFIG_DIR="$HOME/.config/cproj"

echo -e "${BLUE}🗑️  Uninstalling cproj${NC}"
echo

# Check what exists
if [ ! -d "$INSTALL_DIR" ] && [ ! -f "$BIN_DIR/cproj" ]; then
    echo -e "${YELLOW}cproj doesn't appear to be installed${NC}"
    exit 0
fi

# Show what will be removed
echo -e "${YELLOW}The following will be removed:${NC}"
[ -d "$INSTALL_DIR" ] && echo "  - Installation directory: $INSTALL_DIR"
[ -f "$BIN_DIR/cproj" ] && echo "  - Executable: $BIN_DIR/cproj"
[ -d "$CONFIG_DIR" ] && echo "  - Configuration: $CONFIG_DIR"
echo

# Confirm deletion
read -p "Continue? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled"
    exit 1
fi

# Remove files
echo -e "${BLUE}Removing files...${NC}"

if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
    echo -e "${GREEN}✅ Removed installation directory${NC}"
fi

if [ -f "$BIN_DIR/cproj" ]; then
    rm -f "$BIN_DIR/cproj"
    echo -e "${GREEN}✅ Removed executable${NC}"
fi

# Ask about config
if [ -d "$CONFIG_DIR" ]; then
    echo
    read -p "Remove configuration directory $CONFIG_DIR? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$CONFIG_DIR"
        echo -e "${GREEN}✅ Removed configuration${NC}"
    else
        echo -e "${YELLOW}Configuration kept at $CONFIG_DIR${NC}"
    fi
fi

echo
echo -e "${GREEN}cproj uninstalled successfully! 👋${NC}"