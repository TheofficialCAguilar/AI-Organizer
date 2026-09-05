"""
main.py
FastAPI server — connects all modules together.

Endpoints:
  GET  /health         — check server + ollama
  GET  /directories    — common Mac paths
  GET  /scan           — scan a directory
  POST /command        — parse command → preview
  POST /execute        — run confirmed operations
  POST /trash          — move files to Trash
  POST /zip            — compress files to .zip
  POST /undo           — reverse last operation
  GET  /history        — undo history
  POST /create-folder  — create a new folder
  GET  /              — API info

Start: uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Any
from pathlib import Path
import ollama as ollama_client

from file_scanner    import scan_directory, get_common_directories
from categorizer     import suggest_plan
from file_operations import (
    validate_operations, execute_operations,
    create_folder, undo_last, trash_files, zip_files,
)
from ai_parser       import parse_command, resolve_directory
from fast_parser     import parse as fast_parse
from undo_log        import get_history as get_undo_history, get_last_session
from search_ops      import (search_files, find_duplicates,
                             find_large_files, find_old_files,
                             find_recent_files, folder_summary)

# ── App setup ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title="AI Organizer",
    description="macOS file organizer powered by local AI — Carlos Aguilar",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request models ────────────────────────────────────────────────────────────
class CommandRequest(BaseModel):
    command:   str
    directory: Optional[str] = None

class ExecuteRequest(BaseModel):
    operations: list
    command:    str

class CreateFolderRequest(BaseModel):
    parent_dir:  str
    folder_name: str


# ── Helpers ───────────────────────────────────────────────────────────────────
def ops_as_dicts(operations: list) -> list[dict]:
    """
    Normalise operations — they arrive as either plain dicts (from our
    command handlers) or as Pydantic models (when Swift POSTs to /execute
    or /trash).  Always return plain dicts so every downstream function
    can use op["from"] / op["file"] without worrying about the type.
    """
    out = []
    for op in operations:
        if isinstance(op, dict):
            out.append(op)
        else:
            # Pydantic model — convert to dict
            out.append({
                "file":     getattr(op, "file",     ""),
                "from":     getattr(op, "from_",    ""),
                "to":       getattr(op, "to",       ""),
                "folder":   getattr(op, "folder",   ""),
                "category": getattr(op, "category", ""),
                "size":     getattr(op, "size",     ""),
            })
    return out


def read_only_response(intent, action, directory, items, summary, explanation=""):
    """Shared response shape for read-only results (search, large, old, recent, summary)."""
    return {
        "intent":      intent,
        "action":      action,
        "directory":   directory,
        "operations":  [],
        "folders":     {},
        "total_files": len(items),
        "summary":     summary,
        "validation":  {"valid": True, "warnings": [], "errors": [], "checked": 0},
        "explanation": explanation or summary,
        "files":       items[:20],
    }


# ── Startup — warm up model ───────────────────────────────────────────────────
@app.on_event("startup")
async def warm_up_model():
    import threading
    def load():
        try:
            import ollama as ol
            print("Warming up llama3.2…")
            ol.chat(
                model="llama3.2",
                messages=[{"role": "user", "content": "hi"}],
                options={"num_predict": 1},
                keep_alive="10m",
            )
            print("Model ready.")
        except Exception as e:
            print(f"Warm-up skipped: {e}")
    threading.Thread(target=load, daemon=True).start()


# ── GET /health ───────────────────────────────────────────────────────────────
@app.get("/health")
def health_check():
    ollama_status = "connected"
    try:
        models = ollama_client.list()
        if not models.models:
            ollama_status = "no models installed"
    except Exception as e:
        ollama_status = f"not running: {e}"
    return {
        "server":  "running",
        "ollama":  ollama_status,
        "model":   "llama3.2",
        "version": "1.0.0",
    }


# ── GET /directories ──────────────────────────────────────────────────────────
@app.get("/directories")
def directories():
    return get_common_directories()


# ── GET /scan ─────────────────────────────────────────────────────────────────
@app.get("/scan")
def scan(directory: str = "desktop"):
    dirs     = get_common_directories()
    dir_path = dirs.get(directory.lower(), directory)
    result   = scan_directory(dir_path)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ── POST /command ─────────────────────────────────────────────────────────────
@app.post("/command")
def command(req: CommandRequest):
    # 1 — fast parser (instant, no AI)
    intent = fast_parse(req.command)

    # 2 — fall back to Ollama when needed
    if intent is None or intent.get("needs_ai_verify") or intent.get("confidence") != "high":
        context = None
        if req.directory:
            s = scan_directory(req.directory)
            if "error" not in s:
                context = {"directory": req.directory,
                           "total_items": s["total_items"],
                           "categories": s["categories"]}
        ai = parse_command(req.command, context)
        if ai.get("action") == "error":
            if intent is None:
                raise HTTPException(status_code=503,
                    detail="Could not connect to Ollama. Make sure it is running.")
        else:
            intent = ai

    action    = intent.get("action", "unknown")
    directory = req.directory or resolve_directory(intent)

    # ── Undo ──────────────────────────────────────────────────────────────────
    if action == "undo":
        return {"intent": intent, "action": "undo",
                "preview": None, "operations": [],
                "folders": {}, "total_files": 0,
                "summary": "Reversing last operation…",
                "validation": {"valid": True, "warnings": [], "errors": [], "checked": 0},
                "explanation": "Reverse the last operation"}

    # ── Unknown ───────────────────────────────────────────────────────────────
    if action == "unknown":
        msg = intent.get("explanation") or "I can organise, search, rename, zip and trash files — try one of those!"
        return {"intent": intent, "action": "unknown", "directory": "",
                "operations": [], "folders": {}, "total_files": 0,
                "summary": msg, "validation": {"valid": False, "warnings": [],
                "errors": [], "checked": 0}, "explanation": msg}

    # ── Large files ───────────────────────────────────────────────────────────
    if action == "large_files":
        p      = intent.get("params") or {}
        min_mb = float(p.get("min_mb", 10))          # default 10MB — more useful
        r      = find_large_files(directory, min_mb=min_mb)
        if "error" in r:
            raise HTTPException(status_code=404, detail=r["error"])
        summary = (f"Found {r['count']} file(s) over {min_mb:.0f}MB"
                   + (f" — {r['total_size']} total" if r["count"] else ""))
        return read_only_response(intent, "search", directory,
                                  r["items"], summary, intent.get("explanation",""))

    # ── Old files ─────────────────────────────────────────────────────────────
    if action == "old_files":
        p    = intent.get("params") or {}
        days = int(p.get("days", 365))
        r    = find_old_files(directory, older_than_days=days)
        if "error" in r:
            raise HTTPException(status_code=404, detail=r["error"])
        label   = "a year" if days >= 365 else f"{days} days"
        summary = (f"Found {r['count']} file(s) untouched for over {label}"
                   + (f" — {r['total_size']} total" if r["count"] else ""))
        return read_only_response(intent, "search", directory,
                                  r["items"], summary, intent.get("explanation",""))

    # ── Recent files ──────────────────────────────────────────────────────────
    if action == "recent_files":
        p    = intent.get("params") or {}
        days = int(p.get("days", 7))
        r    = find_recent_files(directory, days=days)
        if "error" in r:
            raise HTTPException(status_code=404, detail=r["error"])
        summary = f"Found {r['count']} file(s) from the last {days} day(s)"
        return read_only_response(intent, "search", directory,
                                  r["items"], summary, intent.get("explanation",""))

    # ── Folder summary ────────────────────────────────────────────────────────
    if action == "summary":
        r = folder_summary(directory)
        if "error" in r:
            raise HTTPException(status_code=404, detail=r["error"])
        top  = ", ".join(f"{c['count']} {c['category']}s"
                         for c in r["categories"][:3])
        summary = (f"{r['total_files']} files · {r['total_size']}"
                   + (f" · mostly {top}" if top else ""))
        return {
            **read_only_response(intent, "summary", directory,
                                 r["largest"], summary, intent.get("explanation","")),
            "folders":    {c["category"]: c["count"] for c in r["categories"]},
            "folderData": r,
        }

    # ── Search ────────────────────────────────────────────────────────────────
    if action == "search":
        p = intent.get("params") or {}
        r = search_files(
            directory,
            name_contains = p.get("name_contains"),
            categories    = intent.get("include") or None,
            extensions    = p.get("extensions"),
        )
        if "error" in r:
            raise HTTPException(status_code=404, detail=r["error"])
        summary = f"Found {r['count']} file(s)"
        return read_only_response(intent, "search", directory,
                                  r["items"][:50], summary, intent.get("explanation",""))

    # ── Duplicates ────────────────────────────────────────────────────────────
    if action == "duplicates":
        r = find_duplicates(directory)
        if "error" in r:
            raise HTTPException(status_code=404, detail=r["error"])
        if r["duplicate_count"] == 0:
            return read_only_response(intent, "search", directory, [],
                                      "No duplicates found — you're already tidy!",
                                      "No duplicates found")
        trash_dir  = str(Path.home() / ".Trash")
        operations = [
            {"file": d["name"], "from": d["path"],
             "to": str(Path(trash_dir) / d["name"]),
             "folder": "Trash", "category": d["category"],
             "size": d["size_label"]}
            for g in r["groups"] for d in g["duplicates"]
        ]
        explanation = (f"Found {r['duplicate_count']} duplicate(s) wasting "
                       f"{r['wasted_space']}. Newest copy kept — extras go to Trash.")
        return {
            "intent":      intent,
            "action":      "trash",
            "directory":   directory,
            "operations":  operations,
            "folders":     {"Trash": len(operations)},
            "total_files": len(operations),
            "summary":     explanation,
            "validation":  validate_operations(
                [{"from": op["from"], "to": op["to"]} for op in operations]),
            "explanation": explanation,
        }

    # ── Rename ────────────────────────────────────────────────────────────────
    if action == "rename":
        scan_result = scan_directory(directory)
        if "error" in scan_result:
            raise HTTPException(status_code=404, detail=scan_result["error"])

        items   = [i for i in scan_result["items"] if not i["is_folder"]]
        include = intent.get("include", [])
        exclude = intent.get("exclude", [])
        if include:
            items = [i for i in items if i["category"] in include]
        if exclude:
            items = [i for i in items if i["category"] not in exclude]

        p       = intent.get("params") or {}
        find    = p.get("find",    "")
        replace = p.get("replace", "")
        prefix  = p.get("prefix",  "")
        suffix  = p.get("suffix",  "")

        operations = []
        for i in items:
            fpath    = Path(i["path"])
            stem     = fpath.stem
            new_stem = stem

            if find:
                new_stem = new_stem.replace(find, replace)
            if prefix and not new_stem.startswith(prefix):
                new_stem = prefix + new_stem
            if suffix and not new_stem.endswith(suffix):
                new_stem = new_stem + suffix
            if new_stem == stem:
                continue

            new_path = fpath.parent / (new_stem + fpath.suffix)
            operations.append({
                "file":     i["name"],
                "from":     i["path"],
                "to":       str(new_path),
                "folder":   "Renamed",
                "category": i["category"],
                "size":     i["size_label"],
            })

        if not operations:
            return read_only_response(intent, "search", directory, [],
                                      "No files matched the rename pattern.",
                                      "Nothing to rename")

        # Skip validate_operations for renames — destination doesn't
        # exist yet (it's the same folder with a new name) so the
        # safety check would always pass anyway; we just need to confirm
        # the source exists.
        missing = [op for op in operations if not Path(op["from"]).exists()]
        validation = {
            "valid":    len(missing) == 0,
            "warnings": [f"'{Path(op['from']).name}' not found" for op in missing],
            "errors":   [],
            "checked":  len(operations),
        }

        return {
            "intent":      intent,
            "action":      "rename",
            "directory":   directory,
            "operations":  operations,
            "folders":     {"Renamed": len(operations)},
            "total_files": len(operations),
            "summary":     f"Will rename {len(operations)} file(s)",
            "validation":  validation,
            "explanation": intent.get("explanation", f"Rename {len(operations)} file(s)"),
        }

    # ── Zip ───────────────────────────────────────────────────────────────────
    if action == "zip":
        scan_result = scan_directory(directory)
        if "error" in scan_result:
            raise HTTPException(status_code=404, detail=scan_result["error"])

        items   = [i for i in scan_result["items"] if not i["is_folder"]]
        include = intent.get("include", [])
        exclude = intent.get("exclude", [])
        if include:
            items = [i for i in items if i["category"] in include]
        if exclude:
            items = [i for i in items if i["category"] not in exclude]

        p        = intent.get("params") or {}
        zip_name = p.get("zip_name") or "Archive"
        if not zip_name.lower().endswith(".zip"):
            zip_name += ".zip"

        operations = [
            {"file": i["name"], "from": i["path"],
             "to": str(Path(directory) / zip_name),
             "folder": zip_name, "category": i["category"],
             "size": i["size_label"]}
            for i in items
        ]

        return {
            "intent":      intent,
            "action":      "zip",
            "directory":   directory,
            "operations":  operations,
            "folders":     {zip_name: len(operations)},
            "total_files": len(operations),
            "summary":     f"Will zip {len(operations)} file(s) into {zip_name}",
            "validation":  {"valid": len(operations) > 0, "warnings": [],
                            "errors": [], "checked": len(operations)},
            "explanation": intent.get("explanation",
                           f"Compress {len(operations)} files into {zip_name}"),
            "zipName":     zip_name,
        }

    # ── Create folder ─────────────────────────────────────────────────────────
    if action == "create_folder":
        custom = intent.get("custom_folders", {})
        folder_name = list(custom.keys())[0] if custom else "New Folder"
        result = create_folder(directory, folder_name)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return read_only_response(intent, "search", directory, [],
                                  f"Created folder '{folder_name}'",
                                  f"Created folder '{folder_name}'")

    # ── Trash ─────────────────────────────────────────────────────────────────
    if action == "trash":
        scan_result = scan_directory(directory)
        if "error" in scan_result:
            raise HTTPException(status_code=404, detail=scan_result["error"])

        items   = [i for i in scan_result["items"] if not i["is_folder"]]
        include = intent.get("include", [])
        exclude = intent.get("exclude", [])
        if include:
            items = [i for i in items if i["category"] in include]
        if exclude:
            items = [i for i in items if i["category"] not in exclude]

        trash_dir  = str(Path.home() / ".Trash")
        operations = [
            {"file": i["name"], "from": i["path"],
             "to": str(Path(trash_dir) / i["name"]),
             "folder": "Trash", "category": i["category"],
             "size": i["size_label"]}
            for i in items
        ]

        return {
            "intent":      intent,
            "action":      "trash",
            "directory":   directory,
            "operations":  operations,
            "folders":     {"Trash": len(operations)},
            "total_files": len(operations),
            "summary":     f"Will move {len(operations)} file(s) to Trash",
            "validation":  validate_operations(
                [{"from": op["from"], "to": op["to"]} for op in operations]),
            "explanation": intent.get("explanation",
                           f"Move {len(operations)} files to Trash"),
        }

    # ── Organize (default) ────────────────────────────────────────────────────
    mode = intent.get("mode", "category")
    plan = suggest_plan(directory, mode=mode)
    if "error" in plan:
        raise HTTPException(status_code=500, detail=plan["error"])

    operations = plan["operations"]
    include    = intent.get("include", [])
    exclude    = intent.get("exclude", [])
    custom     = intent.get("custom_folders", {})

    if include:
        operations = [op for op in operations if op["category"] in include]
    if exclude:
        operations = [op for op in operations if op["category"] not in exclude]

    # Apply custom folder names
    if custom:
        for folder_name, categories in custom.items():
            for op in operations:
                if not categories or op["category"] in categories or op["type"] in categories:
                    op["to"]     = str(Path(directory) / folder_name / Path(op["from"]).name)
                    op["folder"] = folder_name

    folder_counts = {}
    for op in operations:
        folder_counts[op["folder"]] = folder_counts.get(op["folder"], 0) + 1

    validation = validate_operations(operations)

    return {
        "intent":      intent,
        "action":      "organize",
        "directory":   directory,
        "operations":  operations,
        "folders":     folder_counts,
        "total_files": len(operations),
        "summary":     plan["summary"],
        "validation":  validation,
        "explanation": intent.get("explanation", ""),
    }


# ── POST /execute ─────────────────────────────────────────────────────────────
@app.post("/execute")
def execute(req: ExecuteRequest):
    if not req.operations:
        return {"session_id": "", "moved": 0, "skipped": 0,
                "errors": [], "folders_created": [], "summary": "Nothing to execute"}
    ops    = ops_as_dicts(req.operations)
    result = execute_operations(ops, req.command)
    return result


# ── POST /trash ───────────────────────────────────────────────────────────────
@app.post("/trash")
def trash_endpoint(req: ExecuteRequest):
    if not req.operations:
        return {"session_id": "", "moved": 0, "skipped": 0,
                "errors": [], "folders_created": [], "summary": "Nothing to trash"}
    ops    = ops_as_dicts(req.operations)
    result = trash_files(ops, req.command)
    return {
        "session_id":      "",
        "moved":           result["trashed"],
        "skipped":         result["skipped"],
        "errors":          result["errors"],
        "folders_created": ["Trash"],
        "summary":         result["summary"],
    }


# ── POST /zip ─────────────────────────────────────────────────────────────────
@app.post("/zip")
def zip_endpoint(req: ExecuteRequest):
    if not req.operations:
        return {"session_id": "", "moved": 0, "skipped": 0,
                "errors": [], "folders_created": [], "summary": "Nothing to zip"}
    ops      = ops_as_dicts(req.operations)
    first_to = ops[0].get("to", "") if ops else ""
    archive  = Path(first_to)
    zip_name = archive.name or "Archive.zip"
    dirpath  = str(archive.parent) if str(archive.parent) != "." else str(Path.home() / "Desktop")
    result   = zip_files(ops, zip_name, dirpath)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {
        "session_id":      "",
        "moved":           result["zipped"],
        "skipped":         result["skipped"],
        "errors":          result["errors"],
        "folders_created": [Path(result["archive"]).name],
        "summary":         result["summary"],
    }


# ── POST /undo ────────────────────────────────────────────────────────────────
@app.post("/undo")
def undo():
    last = get_last_session()
    if not last:
        return {"session_id": None, "command": None, "reversed": 0,
                "skipped": 0, "errors": [], "message": "Nothing to undo"}
    return undo_last()


# ── GET /history ──────────────────────────────────────────────────────────────
@app.get("/history")
def history():
    return {"history": get_undo_history()}


# ── POST /create-folder ───────────────────────────────────────────────────────
@app.post("/create-folder")
def make_folder(req: CreateFolderRequest):
    result = create_folder(req.parent_dir, req.folder_name)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ── GET / ─────────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "name":    "AI Organizer API",
        "version": "1.0.0",
        "author":  "Carlos Aguilar",
        "endpoints": [
            "GET  /health", "GET  /directories",
            "GET  /scan",   "POST /command",
            "POST /execute","POST /trash",
            "POST /zip",    "POST /undo",
            "GET  /history","POST /create-folder",
        ]
    }