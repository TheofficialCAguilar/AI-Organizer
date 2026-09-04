"""
file_scanner.py
Scans a directory and returns structured information about every file.
This is the foundation — every other module reads from what this produces.

Returns a list of FileItem dicts:
{
    "name":       "resume.pdf",
    "path":       "/Users/sandal/Desktop/resume.pdf",
    "type":       "pdf",
    "category":   "document",
    "size_bytes": 204800,
    "size_label": "200 KB",
    "modified":   "2024-03-15",
    "is_folder":  False
}
"""

import os
from pathlib import Path
from datetime import datetime

# Category map
# Maps file extensions to human-readable categories.
# ADD new extensions here if users report files not being recognized.
EXTENSION_CATEGORIES = {
    # Documents
    "pdf":   "document", "doc":  "document", "docx": "document",
    "txt":   "document", "rtf":  "document", "pages":"document",
    "odt":   "document", "md":   "document",

    # Spreadsheets
    "xls":   "spreadsheet", "xlsx": "spreadsheet", "csv": "spreadsheet",
    "numbers": "spreadsheet",

    # Presentations
    "ppt":   "presentation", "pptx": "presentation", "key": "presentation",

    # Images
    "jpg":   "image", "jpeg": "image", "png":  "image",
    "gif":   "image", "bmp":  "image", "tiff": "image",
    "webp":  "image", "heic": "image", "svg":  "image", "raw": "image",

    # Screenshots (common macOS naming)
    # FUTURE: detect screenshot naming pattern "Screenshot YYYY-MM-DD"
    # and auto-categorize even without extension match

    # Videos
    "mp4":   "video", "mov":  "video", "avi":  "video",
    "mkv":   "video", "wmv":  "video", "m4v":  "video",

    # Audio
    "mp3":   "audio", "wav":  "audio", "aac":  "audio",
    "flac":  "audio", "m4a":  "audio", "ogg":  "audio",

    # Code
    "py":    "code",  "js":   "code",  "ts":   "code",
    "jsx":   "code",  "tsx":  "code",  "swift":"code",
    "cpp":   "code",  "c":    "code",  "h":    "code",
    "java":  "code",  "html": "code",  "css":  "code",
    "json":  "code",  "xml":  "code",  "yaml": "code",
    "yml":   "code",  "sh":   "code",  "rb":   "code",

    # Archives
    "zip":   "archive", "tar": "archive", "gz":  "archive",
    "rar":   "archive", "7z":  "archive", "dmg": "archive",
    "pkg":   "archive",

    # Applications
    "app":   "application", "exe": "application",

    # Fonts
    "ttf":   "font", "otf": "font", "woff": "font",
}

#Size formatter
def format_size(size_bytes: int) -> str:
    """Converts raw bytes into a readable label like '1.2 MB'."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / (1024 ** 2):.1f} MB"
    else:
        return f"{size_bytes / (1024 ** 3):.1f} GB"


#Screenshot detector 
def is_screenshot(name: str) -> bool:
    """
    Detects macOS screenshot naming convention.
    macOS names screenshots like: 'Screenshot 2024-03-15 at 10.30.00 AM.png'
    """
    return name.lower().startswith("screenshot") and name.endswith(".png")


#Single file scanner 
def scan_item(path: Path) -> dict:
    """
    Scans a single file or folder and returns a FileItem dict.
    Called by scan_directory for every item it finds.
    """
    try:
        stat        = path.stat()
        size_bytes  = stat.st_size if path.is_file() else 0
        modified    = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")
        extension   = path.suffix.lstrip(".").lower() if path.is_file() else ""
        is_folder   = path.is_dir()

        # Determine category
        if is_folder:
            category = "folder"
        elif is_screenshot(path.name):
            # Screenshots get their own category even though they're .png
            category = "screenshot"
        else:
            category = EXTENSION_CATEGORIES.get(extension, "other")

        return {
            "name":       path.name,
            "path":       str(path),
            "type":       extension if extension else "folder",
            "category":   category,
            "size_bytes": size_bytes,
            "size_label": format_size(size_bytes),
            "modified":   modified,
            "is_folder":  is_folder,
        }

    except PermissionError:
        # Skip files we don't have access to — don't crash
        return None
    except Exception as e:
        print(f"Warning: could not scan {path}: {e}")
        return None


#Directory scanner
def scan_directory(directory: str) -> dict:
    """
    Scans an entire directory and returns a summary with all file items.

    Args:
        directory: Full path to scan e.g. '/Users/sandal/Desktop'

    Returns:
        {
            "path":        "/Users/sandal/Desktop",
            "total_items": 23,
            "total_size":  "1.2 GB",
            "categories":  { "document": 5, "image": 8, ... },
            "items":       [ ...FileItem dicts... ]
        }
    """
    target = Path(directory).expanduser()

    if not target.exists():
        return {"error": f"Directory not found: {directory}"}

    if not target.is_dir():
        return {"error": f"Not a directory: {directory}"}

    items       = []
    total_bytes = 0
    categories  = {}

    for child in sorted(target.iterdir()):
        # Skip hidden files (start with .) like .DS_Store
        if child.name.startswith("."):
            continue

        item = scan_item(child)
        if item is None:
            continue

        items.append(item)
        total_bytes += item["size_bytes"]

        # Tally category counts
        cat = item["category"]
        categories[cat] = categories.get(cat, 0) + 1

    return {
        "path":        str(target),
        "total_items": len(items),
        "total_size":  format_size(total_bytes),
        "categories":  categories,
        "items":       items,
    }


# Common Mac directories 
def get_common_directories() -> dict:
    """
    Returns the paths to common Mac directories.
    SwiftUI will call this so it always knows where Desktop etc. are.

    FUTURE: add custom directories from user settings
    """
    home = Path.home()
    return {
        "desktop":   str(home / "Desktop"),
        "documents": str(home / "Documents"),
        "downloads": str(home / "Downloads"),
        "home":      str(home),
    }


#test 
# Run this file directly to test: python3 file_scanner.py
if __name__ == "__main__":
    import json

    dirs = get_common_directories()
    print("Common directories:")
    for name, path in dirs.items():
        print(f"  {name}: {path}")

    print("\nScanning Desktop...")
    result = scan_directory(dirs["desktop"])

    if "error" in result:
        print(f"Error: {result['error']}")
    else:
        print(f"Found {result['total_items']} items ({result['total_size']})")
        print(f"Categories: {result['categories']}")
        print("\nFirst 5 items:")
        for item in result["items"][:5]:
            print(f"  {item['name']} — {item['category']} ({item['size_label']})")