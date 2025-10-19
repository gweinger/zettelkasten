"""Project root detection utilities."""

from pathlib import Path
from typing import Optional


def find_project_root(start_path: Optional[Path] = None) -> Optional[Path]:
    """
    Find the Zettelkasten project root by walking up the directory tree.

    Searches for directories containing markers that identify a Zettelkasten project:
    - A .zettelkasten marker file
    - A vault/ directory
    - A .env file with VAULT_PATH defined

    Args:
        start_path: Directory to start searching from (defaults to current working directory)

    Returns:
        Path to project root, or None if not found
    """
    if start_path is None:
        start_path = Path.cwd()

    current = start_path.resolve()

    # Walk up the directory tree
    while True:
        # Check for .zettelkasten marker file (explicit marker)
        if (current / ".zettelkasten").exists():
            return current

        # Check for vault/ directory (implicit marker)
        if (current / "vault").is_dir():
            return current

        # Check for .env file with VAULT_PATH (implicit marker)
        env_file = current / ".env"
        if env_file.exists():
            try:
                with open(env_file, "r") as f:
                    content = f.read()
                    if "VAULT_PATH" in content:
                        return current
            except Exception:
                pass  # Couldn't read .env, continue searching

        # Move to parent directory
        parent = current.parent
        if parent == current:
            # Reached filesystem root without finding project
            return None
        current = parent
