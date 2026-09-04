"""
undo_log.py
Logs every file operation before it happens so it can be reversed.
This is the safety net — nothing gets moved without being logged first.

The log is stored as a JSON file:
~/.organizer_undo_log.json

Each entry looks like:
{
    "id":         "abc123",
    "timestamp":  "2024-03-15 10:30:00",
    "command":    "organize my desktop by category",
    "operations": [
        {
            "action": "move",
            "from":   "/Users/sandal/Desktop/resume.pdf",
            "to":     "/Users/sandal/Desktop/Documents/resume.pdf",
            "done":   true
        },
        ...
    ]
}

FUTURE: add a max log size — keep only the last 20 sessions
to prevent the log file growing too large over time.
"""

import json
import uuid
from pathlib import Path
from datetime import datetime

# Log file lives in home directory — hidden, out of the way
LOG_PATH = Path.home() / ".organizer_undo_log.json"


#Load log 
def load_log() -> list:
    """
    Loads the full undo log from disk.
    Returns empty list if no log exists yet.
    """
    if not LOG_PATH.exists():
        return []
    try:
        with open(LOG_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        # Log is corrupted or unreadable — start fresh
        # FUTURE: back up corrupted log before clearing it
        return []


#Save log 
def save_log(log: list) -> None:
    """Writes the full log back to disk."""
    with open(LOG_PATH, "w") as f:
        json.dump(log, f, indent=2)


#Create session 
def create_session(command: str, operations: list) -> str:
    """
    Creates a new log session before executing operations.
    Call this BEFORE moving any files.

    Args:
        command:    The original user command e.g. 'organize desktop by category'
        operations: List of planned operations from categorizer.py

    Returns:
        session_id: A unique ID for this session (used to undo it later)
    """
    session_id = str(uuid.uuid4())[:8]   # short 8-char ID is enough

    session = {
        "id":         session_id,
        "timestamp":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "command":    command,
        "operations": [
            {
                "action": "move",
                "from":   op["from"],
                "to":     op["to"],
                "done":   False,   # marked True as each file is moved
            }
            for op in operations
        ]
    }

    log = load_log()
    log.append(session)

    # FUTURE: trim log to last 20 sessions here
    # if len(log) > 20:
    #     log = log[-20:]

    save_log(log)
    return session_id


#Mark operation done 
def mark_done(session_id: str, from_path: str) -> None:
    """
    Marks a single operation as completed after the file is moved.
    This way if the app crashes mid-operation we know which files
    were moved and which weren't.
    """
    log = load_log()

    for session in log:
        if session["id"] == session_id:
            for op in session["operations"]:
                if op["from"] == from_path:
                    op["done"] = True
                    break
            break

    save_log(log)


#Get last session 
def get_last_session() -> dict | None:
    """
    Returns the most recent session from the log.
    Used to know what to undo when the user hits Undo.
    """
    log = load_log()
    if not log:
        return None
    return log[-1]


#Undo last session 
def undo_last_session() -> dict:
    """
    Reverses every completed operation in the last session.
    Moves files back to where they came from and removes empty folders.

    Returns:
    {
        "session_id":  "abc123",
        "command":     "organize desktop by category",
        "reversed":    14,
        "skipped":     0,
        "errors":      [],
    }
    """
    log = load_log()

    if not log:
        return {"error": "Nothing to undo — no operations in log"}

    session  = log[-1]
    reversed_count = 0
    skipped  = 0
    errors   = []
    folders_created = set()

    # Reverse operations in reverse order
    # (so if A→B→C, we do C→B then B→A)
    for op in reversed(session["operations"]):
        if not op["done"]:
            skipped += 1
            continue

        src = Path(op["to"])    # where the file is now
        dst = Path(op["from"])  # where it came from

        if not src.exists():
            skipped += 1
            continue

        try:
            # Make sure the original folder still exists
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)
            op["done"] = False   # mark as undone
            reversed_count += 1
            folders_created.add(str(src.parent))
        except Exception as e:
            errors.append(f"Could not reverse {src.name}: {e}")

    # Clean up empty folders that were created during the operation
    for folder_path in folders_created:
        folder = Path(folder_path)
        try:
            if folder.exists() and not any(folder.iterdir()):
                folder.rmdir()
        except Exception:
            pass   # if we can't remove it that's fine — not critical

    # Remove the session from the log after undoing
    log.pop()
    save_log(log)

    return {
        "session_id": session["id"],
        "command":    session["command"],
        "reversed":   reversed_count,
        "skipped":    skipped,
        "errors":     errors,
    }


#Get log history
def get_history() -> list:
    """
    Returns a summary of all past sessions for display in the UI.
    FUTURE: SwiftUI Settings view will show this as an undo history list.
    """
    log = load_log()
    history = []

    for session in reversed(log):   # newest first
        done_count = sum(1 for op in session["operations"] if op["done"])
        history.append({
            "id":        session["id"],
            "timestamp": session["timestamp"],
            "command":   session["command"],
            "files":     done_count,
        })

    return history


#Clear log 
def clear_log() -> None:
    """
    Wipes the entire log. Called from Settings → 'Clear undo history'.
    FUTURE: expose this as a Settings option in SwiftUI.
    """
    save_log([])


#test 
if __name__ == "__main__":
    print("Testing undo log...\n")

    # Simulate creating a session
    fake_operations = [
        {"from": "/Users/sandal/Desktop/test1.png",
         "to":   "/Users/sandal/Desktop/Screenshots/test1.png"},
        {"from": "/Users/sandal/Desktop/test2.pdf",
         "to":   "/Users/sandal/Desktop/Documents/test2.pdf"},
    ]

    session_id = create_session("organize desktop by category", fake_operations)
    print(f"Created session: {session_id}")

    # Simulate marking one as done
    mark_done(session_id, "/Users/sandal/Desktop/test1.png")
    print("Marked test1.png as done")

    # Check history
    history = get_history()
    print(f"\nHistory ({len(history)} sessions):")
    for h in history:
        print(f"  [{h['id']}] {h['timestamp']} — {h['command']} ({h['files']} files moved)")

    # Check last session
    last = get_last_session()
    print(f"\nLast session: {last['id']} — {last['command']}")
    done = [op for op in last["operations"] if op["done"]]
    print(f"Operations done: {len(done)}/{len(last['operations'])}")

    # Clean up test session from log
    log = load_log()
    log = [s for s in log if s["id"] != session_id]
    save_log(log)
    print("\nTest session cleaned up from log.")
    print("\nUndo log working correctly.")