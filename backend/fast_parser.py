"""
fast_parser.py
Rule-based command parser — runs in microseconds with zero AI overhead.
Handles the most common commands instantly so the app feels responsive.

The pipeline:
1. fast_parser.py tries to match the command with rules (instant)
2. If confident → return result immediately, skip Ollama entirely
3. If not sure → hand off to ai_parser.py (Ollama)

This makes ~80% of commands instant and only uses AI for
genuinely complex or ambiguous ones.
"""

import re
from pathlib import Path

# ── Directory keywords ─────────────────────────────────────────────────────────
DIRECTORY_KEYWORDS = {
    "desktop":   str(Path.home() / "Desktop"),
    "documents": str(Path.home() / "Documents"),
    "downloads": str(Path.home() / "Downloads"),
    "pictures":  str(Path.home() / "Pictures"),
    "movies":    str(Path.home() / "Movies"),
    "music":     str(Path.home() / "Music"),
    "home":      str(Path.home()),
}

# ── Category keywords ──────────────────────────────────────────────────────────
CATEGORY_KEYWORDS = {
    "screenshot":   ["screenshot", "screenshots"],
    "image":        ["image", "images", "photo", "photos", "picture", "pictures",
                     "jpg", "jpeg", "png", "gif"],
    "document":     ["document", "documents", "doc", "docs", "pdf", "pdfs",
                     "word", "pages", "text", "txt"],
    "video":        ["video", "videos", "movie", "movies", "film", "films",
                     "mp4", "mov"],
    "audio":        ["audio", "music", "song", "songs", "mp3", "podcast"],
    "code":         ["code", "script", "scripts", "py", "js", "swift"],
    "archive":      ["archive", "archives", "zip", "zips", "compressed"],
    "spreadsheet":  ["spreadsheet", "spreadsheets", "excel", "csv", "numbers"],
}

# ── Mode keywords ──────────────────────────────────────────────────────────────
MODE_KEYWORDS = {
    "date":      ["date", "dates", "month", "year", "when", "time", "old", "recent"],
    "extension": ["type", "types", "extension", "extensions", "kind", "format"],
    "category":  ["category", "categories", "kind", "organize", "sort", "tidy",
                  "clean", "clear", "group"],
}


def extract_directory(text: str) -> str:
    """Find which directory the user is talking about."""
    t = text.lower()
    for keyword, path in DIRECTORY_KEYWORDS.items():
        if keyword in t:
            return path
    return str(Path.home() / "Desktop")  # default to desktop


def extract_mode(text: str) -> str:
    """Determine how to group files."""
    t = text.lower()
    for mode, keywords in MODE_KEYWORDS.items():
        if any(k in t for k in keywords):
            if mode == "date":      return "date"
            if mode == "extension": return "extension"
    return "category"   # default


def extract_categories(text: str) -> tuple[list, list]:
    """
    Returns (include, exclude) category lists.
    'move screenshots but leave images alone' → include=['screenshot'], exclude=['image']
    """
    t = text.lower()
    include = []
    exclude = []

    # Detect exclude patterns — "leave X alone", "keep X", "don't move X", "except X"
    exclude_patterns = [
        r"leave\s+(\w+)\s+alone",
        r"keep\s+(\w+)\s+(?:where|in place)",
        r"don'?t\s+(?:move|touch)\s+(\w+)",
        r"except\s+(?:my\s+)?(\w+)",
        r"but\s+not\s+(?:my\s+)?(\w+)",
    ]

    for pattern in exclude_patterns:
        matches = re.findall(pattern, t)
        for match in matches:
            for cat, keywords in CATEGORY_KEYWORDS.items():
                if match in keywords or match.rstrip('s') in [k.rstrip('s') for k in keywords]:
                    if cat not in exclude:
                        exclude.append(cat)

    # Detect include patterns — "move X", "put X", "organize X"
    include_patterns = [
        r"(?:move|put|organize|sort|group)\s+(?:my\s+|all\s+|the\s+)?(\w+)",
        r"(?:just|only)\s+(?:my\s+|the\s+)?(\w+)",
    ]

    for pattern in include_patterns:
        matches = re.findall(pattern, t)
        for match in matches:
            for cat, keywords in CATEGORY_KEYWORDS.items():
                if match in keywords or match.rstrip('s') in [k.rstrip('s') for k in keywords]:
                    if cat not in include and cat not in exclude:
                        include.append(cat)

    return include, exclude


def is_undo_command(text: str) -> bool:
    t = text.lower().strip()
    return t in ["undo", "undo that", "go back", "reverse that",
                 "revert", "undo last", "undo last action"]


def is_duplicates_command(text: str) -> bool:
    t = text.lower()
    return ("duplicate" in t or "dupes" in t or
            ("copies" in t and ("find" in t or "remove" in t or "clean" in t)))


def is_create_folder_command(text: str) -> tuple[bool, str]:
    """Returns (is_create, folder_name)"""
    t = text.lower()
    patterns = [
        r"create\s+(?:a\s+)?folder\s+(?:called\s+|named\s+)?[\"']?([a-z0-9 _-]+)[\"']?",
        r"make\s+(?:a\s+)?(?:new\s+)?folder\s+(?:called\s+|named\s+)?[\"']?([a-z0-9 _-]+)[\"']?",
        r"new\s+folder\s+(?:called\s+|named\s+)?[\"']?([a-z0-9 _-]+)[\"']?",
    ]
    for pattern in patterns:
        match = re.search(pattern, t)
        if match:
            return True, match.group(1).strip().title()
    return False, ""


def is_trash_command(text: str) -> bool:
    """Is this clearly a delete/trash command?"""
    t = text.lower()
    trash_words = ["delete", "remove", "trash", "get rid of",
                   "throw away", "throw out", "erase", "wipe"]
    return any(word in t for word in trash_words)


def is_rename_command(text: str) -> bool:
    """Is this clearly a rename command?"""
    t = text.lower()
    return ("rename" in t or "add to the name" in t or
            "replace in the name" in t or "add prefix" in t or
            "add suffix" in t or "start with" in t and
            ("name" in t or "rename" in t or "call" in t))


def is_organize_command(text: str) -> bool:
    """Is this clearly an organize/clean/sort command?
    Must NOT match trash commands — check is_trash_command first."""
    t = text.lower()
    # Skip if it's actually a trash command
    if is_trash_command(t):
        return False
    organize_words = ["organize", "organise", "sort", "clean", "clear",
                      "tidy", "arrange", "group", "move", "put", "fix"]
    return any(word in t for word in organize_words)


def parse(command: str) -> dict | None:
    """
    Try to parse a command instantly without AI.

    Returns:
        A complete intent dict (same format as ai_parser.py returns) if confident
        None if the command is too complex and should go to Ollama
    """
    text = command.strip()

    # ── Undo ──────────────────────────────────────────────────────────────────
    if is_undo_command(text):
        return {
            "action":        "undo",
            "directory":     "desktop",
            "mode":          "category",
            "exclude":       [],
            "include":       [],
            "custom_folders": {},
            "confidence":    "high",
            "explanation":   "Reverse the last file organization",
            "fast_parsed":   True,
        }

    # ── Folder summary ────────────────────────────────────────────────────────
    t = text.lower()
    if (("what" in t and ("on my" in t or "in my" in t or "taking up" in t)) or
            "breakdown" in t or "how much space" in t or "overview" in t):
        dir_name = "desktop"
        for key in DIRECTORY_KEYWORDS:
            if key in t:
                dir_name = key
                break
        return {
            "action": "summary", "directory": dir_name,
            "mode": "category", "exclude": [], "include": [],
            "custom_folders": {}, "params": {},
            "confidence": "high", "fast_parsed": True,
            "explanation": f"Show a breakdown of your {dir_name.title()}",
        }

    # ── Large files ───────────────────────────────────────────────────────────
    if ("large" in t or "biggest" in t or "largest" in t or
            "taking up space" in t or ("bigger than" in t) or
            ("over" in t and "mb" in t)):
        import re
        dir_name = "desktop"
        for key in DIRECTORY_KEYWORDS:
            if key in t:
                dir_name = key
                break
        min_mb = 1.0
        m = re.search(r"(\d+)\s*mb", t)
        if m:
            min_mb = float(m.group(1))
        return {
            "action": "large_files", "directory": dir_name,
            "mode": "category", "exclude": [], "include": [],
            "custom_folders": {}, "params": {"min_mb": min_mb},
            "confidence": "high", "fast_parsed": True,
            "explanation": f"Find files over {min_mb:.0f}MB on your {dir_name.title()}",
        }

    # ── Old files ─────────────────────────────────────────────────────────────
    if (("old" in t and ("files" in t or "haven" in t or "untouched" in t or
                         "desktop" in t or "download" in t or "document" in t)) or
            "older than" in t or "haven't touched" in t or
            "untouched" in t or "last year" in t or "6 months" in t):
        import re
        dir_name = "desktop"
        for key in DIRECTORY_KEYWORDS:
            if key in t:
                dir_name = key
                break
        days = 365
        if "6 month" in t or "180" in t:
            days = 180
        elif "3 month" in t or "90" in t:
            days = 90
        m = re.search(r"(\d+)\s*days?", t)
        if m:
            days = int(m.group(1))
        return {
            "action": "old_files", "directory": dir_name,
            "mode": "category", "exclude": [], "include": [],
            "custom_folders": {}, "params": {"days": days},
            "confidence": "high", "fast_parsed": True,
            "explanation": f"Find files untouched for over {days} days",
        }

    # ── Recent files ──────────────────────────────────────────────────────────
    if ("this week" in t or "today" in t or "recently" in t or
            "last week" in t or "this month" in t or "recently added" in t):
        import re
        dir_name = "downloads"
        for key in DIRECTORY_KEYWORDS:
            if key in t:
                dir_name = key
                break
        days = 7
        if "today" in t:
            days = 1
        elif "this month" in t or "last month" in t:
            days = 30
        m = re.search(r"(\d+)\s*days?", t)
        if m:
            days = int(m.group(1))
        return {
            "action": "recent_files", "directory": dir_name,
            "mode": "category", "exclude": [], "include": [],
            "custom_folders": {}, "params": {"days": days},
            "confidence": "high", "fast_parsed": True,
            "explanation": f"Show files from the last {days} day(s)",
        }

    # ── Duplicates ────────────────────────────────────────────────────────────
    if is_duplicates_command(text):
        dir_name = "desktop"
        for key in DIRECTORY_KEYWORDS:
            if key in text.lower():
                dir_name = key
                break
        return {
            "action":         "duplicates",
            "directory":      dir_name,
            "mode":           "category",
            "exclude":        [],
            "include":        [],
            "custom_folders": {},
            "params":         {},
            "confidence":     "high",
            "explanation":    "Find duplicate files and flag extra copies for Trash",
            "fast_parsed":    True,
        }

    # ── Create folder ─────────────────────────────────────────────────────────
    is_create, folder_name = is_create_folder_command(text)
    if is_create and folder_name:
        directory = extract_directory(text)
        return {
            "action":        "create_folder",
            "directory":     directory,
            "mode":          "custom",
            "exclude":       [],
            "include":       [],
            "custom_folders": {folder_name: []},
            "confidence":    "high",
            "explanation":   f"Create a folder called '{folder_name}'",
            "fast_parsed":   True,
        }

    # ── Organize ──────────────────────────────────────────────────────────────
    if is_organize_command(text):
        directory = extract_directory(text)
        mode      = extract_mode(text)
        include, exclude = extract_categories(text)

        # Simple commands: fast parse gives instant preview
        # but still gets verified by AI in the background
        if len(include) + len(exclude) <= 2:
            dir_name = "desktop"
            for key in DIRECTORY_KEYWORDS:
                if key in text.lower():
                    dir_name = key
                    break

            return {
                "action":         "organize",
                "directory":      dir_name,
                "mode":           mode,
                "exclude":        exclude,
                "include":        include,
                "custom_folders": {},
                "confidence":     "high",
                "explanation":    _build_explanation(dir_name, mode, include, exclude),
                "fast_parsed":    True,
                # flag tells main.py to still run AI in background
                # for quality check on complex variations
                "needs_ai_verify": len(include) + len(exclude) > 0,
            }

    # Complex command — needs full AI parsing
    return None


def _build_explanation(directory: str, mode: str, include: list, exclude: list) -> str:
    dir_label = directory.title()
    if include:
        cats = " and ".join(c.replace("_", " ") + "s" for c in include)
        return f"Move {cats} from {dir_label} into folders"
    if mode == "date":
        return f"Group {dir_label} files into folders by month"
    if mode == "extension":
        return f"Group {dir_label} files into folders by file type"
    excl = ""
    if exclude:
        excl = ", leaving " + " and ".join(c + "s" for c in exclude) + " untouched"
    return f"Organize {dir_label} files into folders by category{excl}"