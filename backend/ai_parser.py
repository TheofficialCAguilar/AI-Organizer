"""
ai_parser.py
Sends the user's natural language command to Ollama (Llama 3)
and gets back a structured intent that the rest of the app can act on.

The AI's only job is to understand what the user wants.
It never sees file contents — only file names and the command.
All actual file decisions are made by categorizer.py and file_operations.py.

Example input:
  command: "clean my desktop, put screenshots in their own folder
            and documents together, leave my images alone"
  context: { "desktop": { "screenshot": 41, "image": 2, "other": 1 } }

Example output:
{
    "action":     "organize",
    "directory":  "desktop",
    "mode":       "category",
    "exclude":    ["image"],
    "include":    ["screenshot", "document"],
    "custom_folders": {},
    "confidence": "high",
    "explanation": "Move screenshots to Screenshots/ and documents
                    to Documents/, leave images untouched"
}
"""

import json
import ollama

# ── Model config ──────────────────────────────────────────────────────────────
# Change this to switch models without touching any other code.
# llama3.2 (3B) — 4x smaller than llama3 8B, ~2GB RAM vs ~6GB.
# Fast on Apple Silicon and plenty capable for structured JSON parsing.
# FUTURE: make this configurable in Settings so users can pick
#         a larger model if their Mac has more RAM.
MODEL = "llama3.2"

# ── System prompt ─────────────────────────────────────────────────────────────
# This tells Llama exactly how to respond.
# Keeping it strict (JSON only) makes parsing reliable.
SYSTEM_PROMPT = """You are an AI file organizer assistant for macOS.
Your job is to understand what the user wants to do with their files
and return a structured JSON response.

You must ALWAYS respond with valid JSON only — no explanation, no markdown,
no extra text. Just the raw JSON object.

The JSON must follow this exact structure:
{
    "action":         "organize" | "trash" | "search" | "duplicates" | "rename" | "zip" | "create_folder" | "undo" | "unknown",
    "directory":      "desktop" | "documents" | "downloads" | "home" | "<custom path>",
    "mode":           "category" | "date" | "extension" | "custom",
    "exclude":        [],
    "include":        [],
    "custom_folders": {},
    "params":         {},
    "confidence":     "high" | "medium" | "low",
    "explanation":    "one sentence describing what will happen"
}

Field rules:
- action:         what the user wants to do.
                  "trash" when user says delete/remove/trash
                  "search" when user wants to FIND files (find, search, show me, where are)
                  "duplicates" when user wants duplicate/copy detection
                  "rename" when user wants to rename files
                  "zip" when user wants to compress/archive files
- directory:      which folder to work on (default: desktop)
- mode:           how to group files (default: category)
- exclude:        list of categories to leave untouched e.g. ["image", "video"]
- include:        if set, ONLY process these categories
- custom_folders: for custom groupings e.g. {"Work": ["pdf", "docx"]}
- params:         extra details per action:
                  search → {"name_contains": "tax", "extensions": ["pdf"]}
                  rename → {"find": "Screenshot", "replace": "SS",
                            "prefix": "vacation_", "suffix": "_2026"}
                  zip    → {"zip_name": "Old Screenshots"}
- confidence:     how confident you are you understood the command
- explanation:    plain English summary of what will happen

Categories you understand: screenshot, image, document, spreadsheet,
presentation, video, audio, code, archive, application, font, other

Example commands and responses:

Command: "organize my desktop"
Response: {"action":"organize","directory":"desktop","mode":"category","exclude":[],"include":[],"custom_folders":{},"confidence":"high","explanation":"Group all desktop files into folders by type"}

Command: "clean up downloads by date"
Response: {"action":"organize","directory":"downloads","mode":"date","exclude":[],"include":[],"custom_folders":{},"confidence":"high","explanation":"Group downloads into folders by month and year"}

Command: "move screenshots to their own folder but leave everything else"
Response: {"action":"organize","directory":"desktop","mode":"category","exclude":[],"include":["screenshot"],"custom_folders":{},"confidence":"high","explanation":"Move screenshots to Screenshots folder, leave all other files untouched"}

Command: "delete all the files on my desktop"
Response: {"action":"trash","directory":"desktop","mode":"category","exclude":[],"include":[],"custom_folders":{},"confidence":"high","explanation":"Move all desktop files to Trash"}

Command: "delete all screenshots on my desktop"
Response: {"action":"trash","directory":"desktop","mode":"category","exclude":[],"include":["screenshot"],"custom_folders":{},"confidence":"high","explanation":"Move all screenshots to Trash"}

Command: "clear my desktop"
Response: {"action":"organize","directory":"desktop","mode":"category","exclude":[],"include":[],"custom_folders":{},"confidence":"high","explanation":"Organize all desktop files into folders by type"}

Command: "trash my old downloads"
Response: {"action":"trash","directory":"downloads","mode":"category","exclude":[],"include":[],"custom_folders":{},"params":{},"confidence":"high","explanation":"Move all downloads to Trash"}

Command: "find all pdfs on my desktop"
Response: {"action":"search","directory":"desktop","mode":"category","exclude":[],"include":[],"custom_folders":{},"params":{"extensions":["pdf"]},"confidence":"high","explanation":"Find all PDF files on the Desktop"}

Command: "where are my files with tax in the name"
Response: {"action":"search","directory":"desktop","mode":"category","exclude":[],"include":[],"custom_folders":{},"params":{"name_contains":"tax"},"confidence":"high","explanation":"Find files containing 'tax' in the name"}

Command: "find duplicate files on my desktop"
Response: {"action":"duplicates","directory":"desktop","mode":"category","exclude":[],"include":[],"custom_folders":{},"params":{},"confidence":"high","explanation":"Find duplicate files and flag extra copies for Trash"}

Command: "rename all screenshots to start with vacation"
Response: {"action":"rename","directory":"desktop","mode":"category","exclude":[],"include":["screenshot"],"custom_folders":{},"params":{"prefix":"vacation_"},"confidence":"high","explanation":"Add 'vacation_' to the start of every screenshot name"}

Command: "replace Screenshot with SS in all my screenshot names"
Response: {"action":"rename","directory":"desktop","mode":"category","exclude":[],"include":["screenshot"],"custom_folders":{},"params":{"find":"Screenshot","replace":"SS"},"confidence":"high","explanation":"Rename screenshots replacing 'Screenshot' with 'SS'"}

Command: "zip up all my screenshots into an archive called old shots"
Response: {"action":"zip","directory":"desktop","mode":"category","exclude":[],"include":["screenshot"],"custom_folders":{},"params":{"zip_name":"old shots"},"confidence":"high","explanation":"Compress all screenshots into old shots.zip"}
"""


# ── Parse command ─────────────────────────────────────────────────────────────
def parse_command(command: str, context: dict = None) -> dict:
    """
    Sends a natural language command to Ollama and returns structured intent.

    Args:
        command: The user's raw text input
        context: Optional dict with current directory state
                 e.g. { "categories": {"screenshot": 41, "image": 2} }

    Returns:
        Parsed intent dict or error dict
    """
    # Build the user message — include context if available
    if context:
        user_message = f"""Command: "{command}"

Current state:
{json.dumps(context, indent=2)}

Return JSON only."""
    else:
        user_message = f'Command: "{command}"\n\nReturn JSON only.'

    try:
        response = ollama.chat(
            model=MODEL,
            messages=[
                {"role": "system",  "content": SYSTEM_PROMPT},
                {"role": "user",    "content": user_message},
            ],
            options={
                "temperature": 0.1,   # low = more consistent, less creative
                "num_predict": 300,   # max tokens — intents are short
            },
            keep_alive="5m",  # unload model from RAM after 5 min idle —
                              # keeps repeat commands fast without hogging
                              # memory all day
        )

        raw = response["message"]["content"].strip()

        # Strip markdown code fences if model adds them anyway
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw   = "\n".join(
                line for line in lines
                if not line.startswith("```")
            ).strip()

        intent = json.loads(raw)

        # Validate required fields are present
        required = ["action", "directory", "mode", "confidence"]
        for field in required:
            if field not in intent:
                intent[field] = "unknown" if field != "confidence" else "low"

        # Ensure lists exist
        intent.setdefault("exclude",        [])
        intent.setdefault("include",        [])
        intent.setdefault("custom_folders", {})
        intent.setdefault("params",         {})
        intent.setdefault("explanation",    "No explanation provided")

        return intent

    except json.JSONDecodeError as e:
        # FUTURE: retry once with a stricter prompt before failing
        return {
            "action":      "unknown",
            "error":       f"Could not parse AI response: {e}",
            "raw":         raw if "raw" in dir() else "",
            "confidence":  "low",
            "explanation": "I couldn't understand that command. Try rephrasing."
        }
    except Exception as e:
        return {
            "action":      "error",
            "error":       str(e),
            "confidence":  "low",
            "explanation": "Could not connect to Ollama. Make sure it is running."
        }


# ── Resolve directory path ────────────────────────────────────────────────────
def resolve_directory(intent: dict) -> str:
    """
    Converts the directory name from the intent into a full path.
    Handles 'desktop', 'documents', 'downloads', 'home',
    and custom paths.

    FUTURE: support arbitrary Finder folders — e.g.:
      - 'organize sandal folder' → /Users/sandal/
      - 'clean up my Projects folder' → /Users/sandal/Projects/
      - 'sort everything in Downloads/Work' → nested paths
      - 'organize this folder' → use currently open Finder window path
    When SwiftUI is built, it will pass the active Finder window path
    as context so 'this folder' always resolves correctly.
    """
    from pathlib import Path

    home = Path.home()

    # Known shorthand names → full paths
    dir_map = {
        "desktop":   str(home / "Desktop"),
        "documents": str(home / "Documents"),
        "downloads": str(home / "Downloads"),
        "home":      str(home),
        "pictures":  str(home / "Pictures"),
        "movies":    str(home / "Movies"),
        "music":     str(home / "Music"),
        "projects":  str(home / "Projects"),
    }

    directory = intent.get("directory", "desktop").lower().strip()

    # Check known shorthands first
    if directory in dir_map:
        return dir_map[directory]

    # If it looks like a full path already, use it directly
    if directory.startswith("/") or directory.startswith("~"):
        resolved = str(Path(directory).expanduser())
        return resolved

    # Otherwise assume it's a folder name inside home
    # e.g. "sandal" → /Users/sandal/sandal
    # e.g. "Work" → /Users/sandal/Work
    # FUTURE: fuzzy match against actual folder names in home directory
    return str(home / directory)


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Testing ai_parser.py — make sure Ollama is running first")
    print(f"Using model: {MODEL}\n")

    test_commands = [
        "organize my desktop",
        "clean up my downloads by date",
        "move all screenshots to their own folder but leave my images alone",
        "create a folder called Work on my desktop",
        "undo",
        "put all pdfs and word docs in a Work folder and images in a Photos folder",
    ]

    for cmd in test_commands:
        print(f"Command: \"{cmd}\"")
        intent = parse_command(cmd)

        if "error" in intent and intent.get("action") == "error":
            print(f"  ERROR: {intent['error']}")
        else:
            print(f"  Action:      {intent.get('action')}")
            print(f"  Directory:   {intent.get('directory')}")
            print(f"  Mode:        {intent.get('mode')}")
            print(f"  Confidence:  {intent.get('confidence')}")
            if intent.get("exclude"):
                print(f"  Exclude:     {intent.get('exclude')}")
            if intent.get("include"):
                print(f"  Include:     {intent.get('include')}")
            if intent.get("custom_folders"):
                print(f"  Custom:      {intent.get('custom_folders')}")
            print(f"  Explanation: {intent.get('explanation')}")
            resolved = resolve_directory(intent)
            print(f"  Resolved to: {resolved}")
        print()