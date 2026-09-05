# Organizer — AI File Organizer for macOS

A macOS menu bar app that organizes your files using natural 
language commands. Powered by a local AI model (Ollama/Llama 3.2) 
— your files never leave your computer.

## What it can do?
- Organize desktop by category, date, or file type
- Move specific file types to custom folders
- Trash files safely (always recoverable from Finder)
- Find duplicate files by content
- Search files by name, type, or size
- Batch rename files
- Zip/compress files
- Find large files, old files, recent files
- Full folder summary — size breakdown, largest files

## Tech Stack
- macOS App: Swift, SwiftUI (menu bar app)
- Backend: Python, FastAPI
- AI: Ollama with Llama 3.2 (runs 100% locally)
- File ops: Python pathlib, shutil

### Requirements
- macOS 13+
- Python 3.11+
- Xcode 15+
- Homebrew

### Backend setup
(Open terminal
brew install ollama
ollama pull llama3.2
brew services start ollama

pip3 install fastapi uvicorn ollama

cd backend
uvicorn main:app --reload --port 8000

### Open the app
Open `Organizer/Organizer.xcodeproj` in Xcode and press Run.

## Status
Active development — UI design pass in progress.

## Author
Carlos Aguilar · [GitHub](https://github.com/TheofficialCAguilar)

© 2026 Carlos Aguilar · All Rights Reserved
EOF
