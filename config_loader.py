import json
import os
from pathlib import Path

def load_config(config_path="config.json"):
    """Load configuration from JSON file"""
    try:
        # Try to find config file in the same directory as the script
        script_dir = Path(__file__).parent
        config_file = script_dir / config_path
        
        if not config_file.exists():
            # Try current working directory
            config_file = Path.cwd() / config_path
        
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            raise FileNotFoundError(f"Configuration file '{config_path}' not found")
    except Exception as e:
        print(f"Error loading configuration: {e}")
        raise

def get_olt_devices(config=None):
    """Get OLT devices from config"""
    if config is None:
        config = load_config()
    return config.get("olt_devices", {})

def get_credentials(config=None):
    """Get credentials from config"""
    if config is None:
        config = load_config()
    creds = config.get("credentials", {})
    return creds.get("username", ""), creds.get("password", "")

def get_file_paths(config=None):
    """Get file paths from config"""
    if config is None:
        config = load_config()
    return config.get("file_paths", {})

def get_settings(config=None):
    """Get settings from config"""
    if config is None:
        config = load_config()
    return config.get("settings", {})