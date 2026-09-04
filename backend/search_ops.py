"""
search_ops.py
Read-only search and duplicate detection.

- search_files():   "find all PDFs from June" → filtered file list
- find_duplicates(): detects true duplicates via size + MD5 content hash,
                     keeps the newest copy, flags the rest for Trash
"""

import hashlib
from pathlib import Path
from file_scanner import scan_directory, format_size


def search_files(directory: str,
                 name_contains: str | None = None,
                 categories: list | None = None,
                 extensions: list | None = None,
                 modified_after: str | None = None,
                 modified_before: str | None = None,
                 min_size_mb: float | None = None) -> dict:
    """Filter a directory's files by name, category, extension, date, size."""
    scan = scan_directory(directory)
    if "error" in scan:
        return scan

    results = [i for i in scan["items"] if not i["is_folder"]]

    if name_contains:
        q = name_contains.lower()
        results = [i for i in results if q in i["name"].lower()]

    if categories:
        results = [i for i in results if i["category"] in categories]

    if extensions:
        exts = [e.lower().lstrip(".") for e in extensions]
        results = [i for i in results if i["type"] in exts]

    if modified_after:
        results = [i for i in results if i["modified"] >= modified_after]

    if modified_before:
        results = [i for i in results if i["modified"] <= modified_before]

    if min_size_mb:
        results = [i for i in results
                   if i["size_bytes"] >= min_size_mb * 1024 * 1024]

    return {
        "directory": scan["path"],
        "count":     len(results),
        "items":     results,
    }


def _hash_file(path: str, chunk: int = 65536) -> str:
    """MD5 of file contents — used only for duplicate comparison."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def find_duplicates(directory: str) -> dict:
    """
    Finds true duplicate files (identical content, not just same name).

    Strategy:
    1. Group by exact size (cheap prefilter)
    2. Hash contents within each size group (only where needed)
    3. In each duplicate group, keep the NEWEST file, flag the rest

    Returns:
    {
        "directory":       "...",
        "groups":          [ {keep, duplicates[], size}, ... ],
        "duplicate_count": 7,
        "wasted_space":    "34.2 MB"
    }
    """
    scan = scan_directory(directory)
    if "error" in scan:
        return scan

    by_size: dict[int, list] = {}
    for item in scan["items"]:
        if item["is_folder"] or item["size_bytes"] == 0:
            continue
        by_size.setdefault(item["size_bytes"], []).append(item)

    groups = []
    for size, items in by_size.items():
        if len(items) < 2:
            continue
        by_hash: dict[str, list] = {}
        for item in items:
            try:
                digest = _hash_file(item["path"])
            except Exception:
                continue   # unreadable file — skip, never crash
            by_hash.setdefault(digest, []).append(item)

        for digest, dupes in by_hash.items():
            if len(dupes) >= 2:
                # newest first — keep it, trash the rest
                dupes_sorted = sorted(dupes, key=lambda x: x["modified"],
                                      reverse=True)
                groups.append({
                    "keep":       dupes_sorted[0],
                    "duplicates": dupes_sorted[1:],
                    "size":       dupes_sorted[0]["size_label"],
                })

    duplicate_count = sum(len(g["duplicates"]) for g in groups)
    wasted_bytes    = sum(d["size_bytes"]
                          for g in groups for d in g["duplicates"])

    return {
        "directory":       scan["path"],
        "groups":          groups,
        "duplicate_count": duplicate_count,
        "wasted_space":    format_size(wasted_bytes),
    }


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from file_scanner import get_common_directories
    import json

    dirs = get_common_directories()

    print("=== Search test — all PNGs on Desktop ===")
    result = search_files(dirs["desktop"], extensions=["png"])
    print(f"Found: {result['count']} files")
    for item in result["items"][:3]:
        print(f"  {item['name']} ({item['size_label']})")
    if result["count"] > 3:
        print(f"  ... and {result['count'] - 3} more")

    print("\n=== Search test — name contains 'screenshot' ===")
    result2 = search_files(dirs["desktop"], name_contains="screenshot")
    print(f"Found: {result2['count']} files")

    print("\n=== Duplicate finder ===")
    dupes = find_duplicates(dirs["desktop"])
    if "error" in dupes:
        print(f"Error: {dupes['error']}")
    else:
        print(f"Duplicate groups found: {len(dupes['groups'])}")
        print(f"Total duplicates:       {dupes['duplicate_count']}")
        print(f"Wasted space:           {dupes['wasted_space']}")
        if dupes["groups"]:
            g = dupes["groups"][0]
            print(f"\nExample group:")
            print(f"  Keep:   {g['keep']['name']}")
            for d in g["duplicates"]:
                print(f"  Trash:  {d['name']}")


# ── Size finder ───────────────────────────────────────────────────────────────
def find_largest_files(directory: str,
                       min_size_mb: float = 10.0,
                       limit: int = 20) -> dict:
    """
    Finds the largest files in a directory, sorted by size descending.
    Default threshold: files over 10MB.

    Usage:
        "find my largest files on my desktop"
        "find files bigger than 100mb in downloads"
        "what's taking up the most space?"
    """
    scan = scan_directory(directory)
    if "error" in scan:
        return scan

    files = [i for i in scan["items"]
             if not i["is_folder"] and i["size_bytes"] >= min_size_mb * 1024 * 1024]
    files.sort(key=lambda x: x["size_bytes"], reverse=True)
    files = files[:limit]

    total_bytes = sum(f["size_bytes"] for f in files)

    return {
        "directory":   scan["path"],
        "count":       len(files),
        "total_size":  format_size(total_bytes),
        "threshold":   f"{min_size_mb}MB",
        "items":       files,
    }


# ── Date range finder ─────────────────────────────────────────────────────────
def find_files_by_date(directory: str,
                       days_ago: int | None = None,
                       before_days_ago: int | None = None) -> dict:
    """
    Finds files modified within a date range.

    Args:
        days_ago:        files modified within the last N days
        before_days_ago: files older than N days

    Usage:
        "show me files I downloaded this week"   → days_ago=7
        "what did I add to my desktop today"     → days_ago=1
        "find files from last month"             → days_ago=30
    """
    from datetime import datetime, timedelta

    scan = scan_directory(directory)
    if "error" in scan:
        return scan

    now   = datetime.now()
    files = [i for i in scan["items"] if not i["is_folder"]]

    if days_ago is not None:
        cutoff = (now - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        files  = [i for i in files if i["modified"] >= cutoff]

    if before_days_ago is not None:
        cutoff = (now - timedelta(days=before_days_ago)).strftime("%Y-%m-%d")
        files  = [i for i in files if i["modified"] <= cutoff]

    files.sort(key=lambda x: x["modified"], reverse=True)

    return {
        "directory": scan["path"],
        "count":     len(files),
        "items":     files,
    }


# ── Old files finder ──────────────────────────────────────────────────────────
def find_old_files(directory: str,
                   older_than_days: int = 365) -> dict:
    """
    Finds files that haven't been modified in a long time.
    Great for spring cleaning — surfaces files that are just sitting there.

    Usage:
        "find files I haven't touched in over a year"
        "what on my desktop is older than 6 months"
        "find old files in my downloads"
    """
    result = find_files_by_date(directory, before_days_ago=older_than_days)
    result["older_than_days"] = older_than_days
    result["threshold"]       = f"Not modified in {older_than_days}+ days"
    return result


# ── Folder summary (disk usage breakdown) ─────────────────────────────────────
def folder_summary(directory: str) -> dict:
    """
    Returns a breakdown of what's in a directory — category counts,
    sizes, and the top space consumers. Like a conversational 'du -sh'.

    Usage:
        "what's on my desktop"
        "give me a breakdown of my downloads folder"
        "what's taking up space in downloads"
    """
    scan = scan_directory(directory)
    if "error" in scan:
        return scan

    files   = [i for i in scan["items"] if not i["is_folder"]]
    folders = [i for i in scan["items"] if i["is_folder"]]

    # Size by category
    by_category: dict[str, dict] = {}
    for f in files:
        cat = f["category"]
        if cat not in by_category:
            by_category[cat] = {"count": 0, "size_bytes": 0}
        by_category[cat]["count"]      += 1
        by_category[cat]["size_bytes"] += f["size_bytes"]

    # Format sizes
    category_breakdown = {
        cat: {
            "count": v["count"],
            "size":  format_size(v["size_bytes"]),
            "size_bytes": v["size_bytes"],
        }
        for cat, v in sorted(
            by_category.items(),
            key=lambda x: x[1]["size_bytes"],
            reverse=True
        )
    }

    # Top 5 largest individual files
    top_files = sorted(files, key=lambda x: x["size_bytes"], reverse=True)[:5]

    return {
        "directory":          scan["path"],
        "total_items":        scan["total_items"],
        "total_size":         scan["total_size"],
        "file_count":         len(files),
        "folder_count":       len(folders),
        "category_breakdown": category_breakdown,
        "top_files":          top_files,
    }


# ── Size finder ───────────────────────────────────────────────────────────────
def find_large_files(directory: str, min_mb: float = 50.0,
                     limit: int = 20) -> dict:
    """
    Finds the largest files in a directory, sorted biggest first.
    Default threshold: 50MB.

    Commands:
      "find my largest files on my desktop"
      "what files are bigger than 100mb in downloads"
      "what's taking up the most space"
    """
    scan = scan_directory(directory)
    if "error" in scan:
        return scan

    min_bytes = min_mb * 1024 * 1024
    items = [i for i in scan["items"]
             if not i["is_folder"] and i["size_bytes"] >= min_bytes]
    items.sort(key=lambda x: x["size_bytes"], reverse=True)
    items = items[:limit]

    total_bytes = sum(i["size_bytes"] for i in items)

    return {
        "directory":   scan["path"],
        "count":       len(items),
        "total_size":  format_size(total_bytes),
        "threshold_mb": min_mb,
        "items":       items,
    }


# ── Old files finder ──────────────────────────────────────────────────────────
def find_old_files(directory: str, older_than_days: int = 365) -> dict:
    """
    Finds files that haven't been modified in N days.
    Great for spring cleaning — surfaces files users forgot exist.

    Commands:
      "find files I haven't touched in over a year"
      "what on my desktop is older than 6 months"
      "show me old files in downloads"
    """
    from datetime import datetime, timedelta

    scan = scan_directory(directory)
    if "error" in scan:
        return scan

    cutoff = (datetime.now() - timedelta(days=older_than_days)).strftime("%Y-%m-%d")
    items  = [i for i in scan["items"]
              if not i["is_folder"] and i["modified"] <= cutoff]
    items.sort(key=lambda x: x["modified"])   # oldest first

    total_bytes = sum(i["size_bytes"] for i in items)

    return {
        "directory":        scan["path"],
        "count":            len(items),
        "total_size":       format_size(total_bytes),
        "older_than_days":  older_than_days,
        "cutoff_date":      cutoff,
        "items":            items,
    }


# ── Date range filter ─────────────────────────────────────────────────────────
def find_recent_files(directory: str, days: int = 7) -> dict:
    """
    Finds files modified within the last N days.

    Commands:
      "show me files I downloaded this week"
      "what did I add to my desktop today"
      "find files from last month"
    """
    from datetime import datetime, timedelta

    scan = scan_directory(directory)
    if "error" in scan:
        return scan

    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    items  = [i for i in scan["items"]
              if not i["is_folder"] and i["modified"] >= cutoff]
    items.sort(key=lambda x: x["modified"], reverse=True)   # newest first

    total_bytes = sum(i["size_bytes"] for i in items)

    return {
        "directory":  scan["path"],
        "count":      len(items),
        "total_size": format_size(total_bytes),
        "since_date": cutoff,
        "days":       days,
        "items":      items,
    }


# ── Folder summary ────────────────────────────────────────────────────────────
def folder_summary(directory: str) -> dict:
    """
    Returns a full breakdown of a folder — category counts, sizes,
    largest files, oldest files. Answers "what's on my desktop?" or
    "what's taking up space in downloads?".

    Commands:
      "what's on my desktop"
      "give me a breakdown of my downloads"
      "what's taking up space in documents"
    """
    scan = scan_directory(directory)
    if "error" in scan:
        return scan

    files   = [i for i in scan["items"] if not i["is_folder"]]
    folders = [i for i in scan["items"] if i["is_folder"]]

    # Size per category
    by_cat: dict[str, dict] = {}
    for item in files:
        cat = item["category"]
        if cat not in by_cat:
            by_cat[cat] = {"count": 0, "bytes": 0}
        by_cat[cat]["count"]  += 1
        by_cat[cat]["bytes"]  += item["size_bytes"]

    categories = [
        {
            "category": cat,
            "count":    data["count"],
            "size":     format_size(data["bytes"]),
            "bytes":    data["bytes"],
        }
        for cat, data in sorted(by_cat.items(),
                                 key=lambda x: x[1]["bytes"],
                                 reverse=True)
    ]

    # Top 5 largest files
    largest = sorted(files, key=lambda x: x["size_bytes"], reverse=True)[:5]

    # 5 oldest files
    oldest  = sorted(files, key=lambda x: x["modified"])[:5]

    total_bytes = sum(i["size_bytes"] for i in files)

    return {
        "directory":    scan["path"],
        "total_items":  scan["total_items"],
        "total_files":  len(files),
        "total_folders": len(folders),
        "total_size":   format_size(total_bytes),
        "categories":   categories,
        "largest":      largest,
        "oldest":       oldest,
    }