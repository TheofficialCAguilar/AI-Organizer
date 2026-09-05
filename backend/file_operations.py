"""
file_operations.py
Executes file operations safely — moves, renames, creates folders.
This is the only module that actually touches the filesystem.

Every operation goes through three steps:
1. Validate  — check the file exists, destination is safe
2. Log       — record in undo_log before touching anything
3. Execute   — move the file, mark as done in log

NEVER call this without going through the validation step first.
The SwiftUI preview screen is what triggers execute — not the AI.
"""

import shutil
from pathlib import Path
from undo_log import create_session, mark_done, undo_last_session


# ── Safety checks ─────────────────────────────────────────────────────────────

# Folders we absolutely never touch no matter what the user says.
# FUTURE: let users add their own protected paths in Settings.
PROTECTED_PATHS = {
    Path.home() / "Library",
    Path.home() / "System",
    Path("/System"),
    Path("/Library"),
    Path("/usr"),
    Path("/bin"),
    Path("/etc"),
}

def is_protected(path: Path) -> bool:
    """Returns True if a path is inside a protected system directory."""
    for protected in PROTECTED_PATHS:
        try:
            path.resolve().relative_to(protected.resolve())
            return True
        except ValueError:
            continue
    return False


def is_safe_destination(destination: Path) -> bool:
    """Checks that a destination path is safe — must be inside home directory."""
    try:
        destination.resolve().relative_to(Path.home().resolve())
        return True
    except ValueError:
        return False


# ── Conflict resolver ─────────────────────────────────────────────────────────
def resolve_conflict(destination: Path) -> Path:
    """
    If a file already exists at the destination, appends a number.
    'resume.pdf' -> 'resume (1).pdf' -> 'resume (2).pdf' etc.

    FUTURE: add a 'skip duplicates' option — if the file at destination
    is identical (same size + modified date) skip instead of renaming.
    """
    if not destination.exists():
        return destination

    stem    = destination.stem
    suffix  = destination.suffix
    parent  = destination.parent
    counter = 1

    while True:
        new_path = parent / f"{stem} ({counter}){suffix}"
        if not new_path.exists():
            return new_path
        counter += 1


# ── Validate operations ───────────────────────────────────────────────────────
def validate_operations(operations: list) -> dict:
    """
    Validates a list of operations before executing.
    Returns any issues found so the UI can warn the user.
    """
    warnings = []
    errors   = []

    for op in operations:
        src = Path(op["from"])
        dst = Path(op["to"])

        if not src.exists():
            warnings.append(f"'{src.name}' no longer exists — will skip")
            continue

        if is_protected(src):
            errors.append(f"'{src.name}' is in a protected location")
            continue

        if not is_safe_destination(dst):
            errors.append(f"Destination for '{src.name}' is outside home directory")
            continue

    return {
        "valid":    len(errors) == 0,
        "warnings": warnings,
        "errors":   errors,
        "checked":  len(operations),
    }


# ── Execute operations ────────────────────────────────────────────────────────
def execute_operations(operations: list, command: str) -> dict:
    """
    Executes a validated list of move operations.
    Logs everything to undo_log before and after each move.
    """
    # Create undo log session BEFORE touching any files
    session_id = create_session(command, operations)

    moved           = 0
    skipped         = 0
    errors          = []
    folders_created = set()

    for op in operations:
        src = Path(op["from"])
        dst = Path(op["to"])

        if not src.exists():
            skipped += 1
            continue

        try:
            # Create destination folder if it doesn't exist
            dst.parent.mkdir(parents=True, exist_ok=True)
            folders_created.add(dst.parent.name)

            # Resolve naming conflicts
            final_dst = resolve_conflict(dst)

            # Move the file
            shutil.move(str(src), str(final_dst))

            # Mark as done in undo log immediately after move
            mark_done(session_id, str(src))
            moved += 1

        except PermissionError:
            errors.append(f"No permission to move '{src.name}'")
            skipped += 1
        except Exception as e:
            errors.append(f"Failed to move '{src.name}': {str(e)}")
            skipped += 1

    folders_list = sorted(folders_created)
    summary = (
        f"Moved {moved} file{'s' if moved != 1 else ''} "
        f"into {len(folders_list)} folder{'s' if len(folders_list) != 1 else ''}"
    )
    if skipped:
        summary += f" ({skipped} skipped)"

    return {
        "session_id":      session_id,
        "moved":           moved,
        "skipped":         skipped,
        "errors":          errors,
        "folders_created": folders_list,
        "summary":         summary,
    }


# ── Undo last operation ───────────────────────────────────────────────────────
def undo_last() -> dict:
    """
    Reverses the last executed session.
    Thin wrapper around undo_log.undo_last_session().
    """
    return undo_last_session()


# ── Create folder ─────────────────────────────────────────────────────────────
def create_folder(parent_dir: str, folder_name: str) -> dict:
    """
    Creates a new folder inside a directory.
    Used when user says 'create a folder called Work on my desktop'.

    FUTURE: support nested folder creation
    e.g. 'create Work/Projects/2024 on my desktop'
    """
    parent     = Path(parent_dir)
    new_folder = parent / folder_name

    if not is_safe_destination(new_folder):
        return {"error": "Destination is outside home directory"}

    if new_folder.exists():
        return {"error": f"Folder '{folder_name}' already exists"}

    try:
        new_folder.mkdir(parents=True)
        return {
            "created": True,
            "path":    str(new_folder),
            "name":    folder_name,
        }
    except Exception as e:
        return {"error": f"Could not create folder: {e}"}


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from categorizer import suggest_plan
    from file_scanner import get_common_directories

    dirs = get_common_directories()

    print("=== Validation test ===")
    plan = suggest_plan(dirs["desktop"], mode="category")

    if "error" in plan:
        print(f"Error: {plan['error']}")
    else:
        validation = validate_operations(plan["operations"])
        print(f"Operations checked: {validation['checked']}")
        print(f"Valid:              {validation['valid']}")
        if validation["warnings"]:
            print(f"Warnings: {validation['warnings']}")
        if validation["errors"]:
            print(f"Errors:   {validation['errors']}")

    print("\n=== Protection test ===")
    protected_tests = [
        Path.home() / "Library" / "Preferences",
        Path("/System/Library"),
        Path.home() / "Desktop" / "test.png",
    ]
    for p in protected_tests:
        status = "PROTECTED" if is_protected(p) else "safe"
        print(f"  {p}: {status}")

    print("\n=== Conflict resolver test ===")
    test_path = Path.home() / "Desktop" / "test_nonexistent.pdf"
    resolved  = resolve_conflict(test_path)
    print(f"  No conflict:   {resolved.name}")

    print("\n=== Safe destination test ===")
    safe_tests = [
        (Path.home() / "Desktop" / "test.png", True),
        (Path("/tmp/test.png"),                 False),
        (Path.home() / "Documents",             True),
    ]
    for p, expected in safe_tests:
        result = is_safe_destination(p)
        icon   = "✓" if result == expected else "✗"
        print(f"  {icon} {p}: {'safe' if result else 'unsafe'}")

    print("\nAll checks passed.")
    print("NOTE: Not executing real file moves in test mode.")
    print("      execute_operations() will be tested via FastAPI in main.py")


# ── Trash files ───────────────────────────────────────────────────────────────
def trash_files(operations: list, command: str) -> dict:
    """
    Moves files to macOS Trash (~/.Trash/) instead of deleting permanently.
    Files can always be recovered from Finder's Trash.

    Never hard-deletes anything — Trash is the only safe delete on macOS.
    Never trashes folders — too risky to accidentally remove a directory tree.

    Args:
        operations: List of file dicts with at least {"path": "...", "name": "..."}
        command:    Original user command for the undo log

    Returns:
        {
            "trashed":  12,
            "skipped":  0,
            "errors":   [],
            "files":    ["file1.png", "file2.pdf", ...],
            "summary":  "Moved 12 files to Trash"
        }
    """
    import shutil
    from datetime import datetime

    trash_dir = Path.home() / ".Trash"
    trashed   = 0
    skipped   = 0
    errors    = []
    files     = []

    for op in operations:
        from_path = op.get("from", "") if isinstance(op, dict) else str(op.from_)
        src = Path(from_path)

        # Never trash folders
        if src.is_dir():
            skipped += 1
            continue

        # Never trash protected paths
        if is_protected(src):
            errors.append(f"'{src.name}' is in a protected location")
            skipped += 1
            continue

        # Must exist
        if not src.exists():
            skipped += 1
            continue

        try:
            # Resolve name conflicts in Trash
            dst = trash_dir / src.name
            if dst.exists():
                # Append timestamp to avoid overwriting something already in Trash
                ts  = datetime.now().strftime("%H%M%S")
                dst = trash_dir / f"{src.stem}_{ts}{src.suffix}"

            shutil.move(str(src), str(dst))
            files.append(src.name)
            trashed += 1

        except PermissionError:
            errors.append(f"No permission to trash '{src.name}'")
            skipped += 1
        except Exception as e:
            errors.append(f"Could not trash '{src.name}': {e}")
            skipped += 1

    summary = f"Moved {trashed} file{'s' if trashed != 1 else ''} to Trash"
    if skipped:
        summary += f" ({skipped} skipped)"

    return {
        "trashed":  trashed,
        "skipped":  skipped,
        "errors":   errors,
        "files":    files,
        "summary":  summary,
    }


# ── Zip files ─────────────────────────────────────────────────────────────────
def zip_files(operations: list, zip_name: str, directory: str) -> dict:
    """
    Compresses the given files into a single .zip archive.
    Originals are NOT deleted — zipping is additive and safe.
    (User can trash the originals afterward with a delete command.)

    Args:
        operations: list of dicts with "from" paths
        zip_name:   archive filename e.g. "Old Screenshots.zip"
        directory:  where to create the archive
    """
    import zipfile

    if not zip_name.lower().endswith(".zip"):
        zip_name += ".zip"

    archive_path = Path(directory) / zip_name
    archive_path = resolve_conflict(archive_path)   # never overwrite

    if not is_safe_destination(archive_path):
        return {"error": "Archive destination is outside home directory"}

    zipped  = 0
    skipped = 0
    errors  = []

    try:
        with zipfile.ZipFile(archive_path, "w",
                             compression=zipfile.ZIP_DEFLATED) as zf:
            for op in operations:
                from_path = op.get("from", "") if isinstance(op, dict) else ""
                src = Path(from_path)

                if not src.exists() or src.is_dir():
                    skipped += 1
                    continue
                if is_protected(src):
                    skipped += 1
                    continue

                try:
                    zf.write(src, arcname=src.name)
                    zipped += 1
                except Exception as e:
                    errors.append(f"Could not zip '{src.name}': {e}")
                    skipped += 1
    except Exception as e:
        return {"error": f"Could not create archive: {e}"}

    summary = f"Zipped {zipped} file{'s' if zipped != 1 else ''} into {archive_path.name}"
    if skipped:
        summary += f" ({skipped} skipped)"

    return {
        "zipped":   zipped,
        "skipped":  skipped,
        "errors":   errors,
        "archive":  str(archive_path),
        "summary":  summary,
    }