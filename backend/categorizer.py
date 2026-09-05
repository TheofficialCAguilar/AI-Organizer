"""
categorizer.py
Takes raw scan results from file_scanner.py and groups files
into smart folder suggestions.

This is what turns a list of files into an actionable plan:
"Put these 41 screenshots in Screenshots/"
"Put these 2 images in Images/"

Works independently of the AI — pure logic based on file categories.
The AI layer (ai_parser.py) will call this after understanding
what the user wants to do.
"""

from pathlib import Path
from datetime import datetime
from file_scanner import scan_directory, get_common_directories

# Default folder names per category 
# These are the folder names we suggest when organizing.
# FUTURE: let users customize these names in Settings
CATEGORY_FOLDERS = {
    "screenshot":    "Screenshots",
    "image":         "Images",
    "document":      "Documents",
    "spreadsheet":   "Spreadsheets",
    "presentation":  "Presentations",
    "video":         "Videos",
    "audio":         "Audio",
    "code":          "Code",
    "archive":       "Archives",
    "application":   "Applications",
    "font":          "Fonts",
    "other":         "Other",
    "folder":        None,   # folders stay where they are by default
}


#Group by category
def group_by_category(scan_result: dict) -> dict:
    """
    Groups files from a scan into categories.
    Returns a dict of category → list of file items.

    Example output:
    {
        "screenshot": [ {file1}, {file2}, ... ],
        "image":      [ {file3} ],
        "other":      [ {file4} ],
    }
    """
    groups = {}

    for item in scan_result.get("items", []):
        # Skip folders — we don't move folders by default
        if item["is_folder"]:
            continue

        cat = item["category"]
        if cat not in groups:
            groups[cat] = []
        groups[cat].append(item)

    return groups


#Group by date
def group_by_date(scan_result: dict) -> dict:
    """
    Groups files by the month/year they were last modified.
    Useful for commands like 'organize my downloads by date'.

    Example output:
    {
        "2024-03": [ {file1}, {file2} ],
        "2024-04": [ {file3} ],
    }
    """
    groups = {}

    for item in scan_result.get("items", []):
        if item["is_folder"]:
            continue

        # Modified date is "YYYY-MM-DD" — grab just "YYYY-MM"
        month_key = item["modified"][:7]
        if month_key not in groups:
            groups[month_key] = []
        groups[month_key].append(item)

    return groups


#Group by extension
def group_by_extension(scan_result: dict) -> dict:
    """
    Groups files by exact extension.
    Useful for commands like 'organize by file type'.

    Example output:
    {
        "pdf":  [ {file1}, {file2} ],
        "png":  [ {file3}, {file4} ],
        "docx": [ {file5} ],
    }
    """
    groups = {}

    for item in scan_result.get("items", []):
        if item["is_folder"]:
            continue

        ext = item["type"] or "no_extension"
        if ext not in groups:
            groups[ext] = []
        groups[ext].append(item)

    return groups


#Build operation plan 
def build_plan(groups: dict, destination_dir: str,
               group_type: str = "category") -> list:
    """
    Turns grouped files into a list of move operations.
    This is the 'preview' the user sees before confirming.

    Args:
        groups:          Output from group_by_* functions
        destination_dir: Where the organized folders will be created
        group_type:      'category', 'date', or 'extension'

    Returns list of operation dicts:
    [
        {
            "file":        "Screenshot 2024-03-15.png",
            "from":        "/Users/sandal/Desktop/Screenshot 2024-03-15.png",
            "to":          "/Users/sandal/Desktop/Screenshots/Screenshot 2024-03-15.png",
            "folder":      "Screenshots",
            "category":    "screenshot",
        },
        ...
    ]
    """
    operations = []
    dest = Path(destination_dir)

    for group_key, items in groups.items():
        # Determine the folder name for this group
        if group_type == "category":
            folder_name = CATEGORY_FOLDERS.get(group_key)
            if folder_name is None:
                continue   # skip folders
        elif group_type == "date":
            # Format "2024-03" → "2024-March"
            try:
                dt = datetime.strptime(group_key, "%Y-%m")
                folder_name = dt.strftime("%Y-%B")
            except ValueError:
                folder_name = group_key
        elif group_type == "extension":
            folder_name = group_key.upper() + " Files"
        else:
            folder_name = group_key

        for item in items:
            target_folder = dest / folder_name
            target_path   = target_folder / item["name"]

            operations.append({
                "file":     item["name"],
                "from":     item["path"],
                "to":       str(target_path),
                "folder":   folder_name,
                "category": item["category"],
                "size":     item["size_label"],
            })

    return operations


#Suggest plan from directory
def suggest_plan(directory: str, mode: str = "category") -> dict:
    """
    Main entry point — scans a directory and returns a complete
    organization plan ready to show the user as a preview.

    Args:
        directory: Path to scan and organize
        mode:      'category' | 'date' | 'extension'

    Returns:
    {
        "directory":     "/Users/sandal/Desktop",
        "mode":          "category",
        "total_files":   44,
        "folders":       { "Screenshots": 41, "Images": 2, "Other": 1 },
        "operations":    [ ...move operations... ],
        "summary":       "Will create 3 folders and move 44 files"
    }
    """
    scan   = scan_directory(directory)

    if "error" in scan:
        return scan

    # Group files based on mode
    if mode == "category":
        groups = group_by_category(scan)
    elif mode == "date":
        groups = group_by_date(scan)
    elif mode == "extension":
        groups = group_by_extension(scan)
    else:
        groups = group_by_category(scan)

    operations  = build_plan(groups, directory, group_type=mode)

    # Count how many files go into each folder
    folder_counts = {}
    for op in operations:
        folder_counts[op["folder"]] = folder_counts.get(op["folder"], 0) + 1

    total_files   = len(operations)
    total_folders = len(folder_counts)
    summary = f"Will create {total_folders} folder{'s' if total_folders != 1 else ''} and move {total_files} file{'s' if total_files != 1 else ''}"

    return {
        "directory":  directory,
        "mode":       mode,
        "total_files": total_files,
        "folders":    folder_counts,
        "operations": operations,
        "summary":    summary,
    }


# test
if __name__ == "__main__":
    import json

    dirs = get_common_directories()

    print("=== Category mode ===")
    plan = suggest_plan(dirs["desktop"], mode="category")

    if "error" in plan:
        print(f"Error: {plan['error']}")
    else:
        print(f"Directory: {plan['directory']}")
        print(f"Summary:   {plan['summary']}")
        print(f"Folders:   {json.dumps(plan['folders'], indent=2)}")
        print(f"\nFirst 5 operations:")
        for op in plan["operations"][:5]:
            print(f"  {op['file']}")
            print(f"    → {op['folder']}/")

    print("\n=== Date mode ===")
    plan_date = suggest_plan(dirs["desktop"], mode="date")
    if "error" not in plan_date:
        print(f"Summary: {plan_date['summary']}")
        print(f"Folders: {list(plan_date['folders'].keys())}")

    print("\n=== Extension mode ===")
    plan_ext = suggest_plan(dirs["desktop"], mode="extension")
    if "error" not in plan_ext:
        print(f"Summary: {plan_ext['summary']}")
        print(f"Folders: {list(plan_ext['folders'].keys())}")