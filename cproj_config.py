#!/usr/bin/env python3
"""
Configuration management for cproj
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from cproj_security import SecurityError, safe_file_read, safe_file_write


class Config:
    """Configuration management for cproj"""

    def __init__(self, config_path: Optional[Path] = None) -> None:
        """Initialize configuration with optional custom path"""
        if config_path:
            self.config_path = config_path
        else:
            self.config_path = Path.home() / ".config" / "cproj" / "config.json"

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self._data: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load configuration from file"""
        if self.config_path.exists():
            try:
                content = safe_file_read(self.config_path)
                self._data = json.loads(content)
            except (json.JSONDecodeError, SecurityError) as e:
                print(f"Warning: Could not load config: {e}")
                self._data = {}
        else:
            self._data = {}

    def save(self) -> None:
        """Save configuration to file"""
        try:
            content = json.dumps(self._data, indent=2)
            safe_file_write(self.config_path, content)
        except SecurityError as e:
            raise Exception(f"Could not save config: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set configuration value"""
        self._data[key] = value

    def delete(self, key: str) -> None:
        """Delete configuration key"""
        if key in self._data:
            del self._data[key]

    def get_all(self) -> Dict[str, Any]:
        """Get all configuration data"""
        return self._data.copy()

    def clear(self) -> None:
        """Clear all configuration"""
        self._data = {}