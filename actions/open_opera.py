import subprocess
import sys
import os

def open_opera(parameters: dict) -> str:
    """
    Opens the Opera browser on the user's computer.

    Args:
        parameters (dict): A dictionary of parameters. For this tool,
                           it expects 'action': 'execute'.

    Returns:
        str: A string indicating the result of the operation.
    """
    platform = sys.platform

    try:
        if platform == "win32":
            # Attempt to open Opera using the 'start' command, which is robust on Windows.
            # It relies on the system's ability to find and launch the application.
            # Using shell=True for 'start' command.
            subprocess.Popen(['start', 'opera'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return "Opera browser successfully opened on Windows."
        elif platform == "darwin":  # macOS
            # Use 'open -a Opera' to launch the application.
            subprocess.Popen(['open', '-a', 'Opera'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return "Opera browser successfully opened on macOS."
        elif platform.startswith("linux"):  # Linux
            # Attempt to launch the 'opera' executable.
            subprocess.Popen(['opera'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return "Opera browser successfully opened on Linux."
        else:
            return f"Error: Unsupported operating system: {platform}"
    except FileNotFoundError as e:
        # This error is more likely on Linux/macOS if the command 'opera' or 'open' isn't found.
        # On Windows with shell=True, FileNotFoundError for 'start' itself is rare.
        return f"Error: Command to open Opera not found on {platform}. Please ensure Opera is installed and accessible in your system's PATH or application directory. Details: {e}"
    except Exception as e:
        # Catch any other unexpected errors during the process execution.
        return f"An unexpected error occurred while trying to open Opera on {platform}: {e}"

TOOL_DEF = {
    "name": "open_opera",
    "description": "Opens the Opera browser on the user's computer.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Must be 'execute' to open the Opera browser."
            }
        },
        "required": ["action"]
    }
}