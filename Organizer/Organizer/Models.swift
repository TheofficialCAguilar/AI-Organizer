//
//  Models.swift
//  Organizer
//
//  Created by Carlos Aguilar
//
//  Data structures that match the JSON responses from the Python backend.
//  Every API response gets decoded into one of these models.

import Foundation

// ── File item ─────────────────────────────────────────────────────────────────
// Matches the FileItem dict returned by /scan
struct FileItem: Codable, Identifiable {
    var id:         String { path }   // path is unique per file
    let name:       String
    let path:       String
    let type:       String
    let category:   String
    let sizeBytes:  Int
    let sizeLabel:  String
    let modified:   String
    let isFolder:   Bool

    enum CodingKeys: String, CodingKey {
        case name, path, type, category, modified
        case sizeBytes  = "size_bytes"
        case sizeLabel  = "size_label"
        case isFolder   = "is_folder"
    }
}

// ── Scan result ───────────────────────────────────────────────────────────────
// Matches the response from GET /scan
struct ScanResult: Codable {
    let path:       String
    let totalItems: Int
    let totalSize:  String
    let categories: [String: Int]
    let items:      [FileItem]

    enum CodingKeys: String, CodingKey {
        case path, categories, items
        case totalItems = "total_items"
        case totalSize  = "total_size"
    }
}

// ── File operation ────────────────────────────────────────────────────────────
// Represents a single move operation in the preview list
struct FileOperation: Codable, Identifiable {
    var id:       String { from }
    let file:     String
    let from:     String
    let to:       String
    let folder:   String
    let category: String
    let size:     String

    // "from" is a reserved word in Swift — explicit CodingKeys ensures
    // it encodes/decodes as "from" in JSON, not something mangled.
    enum CodingKeys: String, CodingKey {
        case file, to, folder, category, size
        case from = "from"
    }
}

// ── AI intent ─────────────────────────────────────────────────────────────────
// What the AI understood from the user's command
struct Intent: Codable {
    let action:        String
    let directory:     String
    let mode:          String
    let exclude:       [String]
    let include:       [String]
    let confidence:    String
    let explanation:   String
    let customFolders: [String: [String]]?

    enum CodingKeys: String, CodingKey {
        case action, directory, mode, exclude,
             include, confidence, explanation
        case customFolders = "custom_folders"
    }
}

// ── Validation result ─────────────────────────────────────────────────────────
struct ValidationResult: Codable {
    let valid:    Bool
    let warnings: [String]
    let errors:   [String]
    let checked:  Int
}

// ── Command response ──────────────────────────────────────────────────────────
// Full response from POST /command
// This is what SwiftUI shows as the preview before the user confirms
struct CommandResponse: Codable {
    let intent:      Intent
    let action:      String
    let directory:   String
    let operations:  [FileOperation]
    let folders:     [String: Int]
    let totalFiles:  Int
    let summary:     String
    let validation:  ValidationResult
    let explanation: String
    let files:       [FileItem]?     // search results (search/duplicates)
    let zipName:     String?         // archive name for zip actions

    enum CodingKeys: String, CodingKey {
        case intent, action, directory, operations,
             folders, summary, validation, explanation, files
        case totalFiles = "total_files"
        case zipName    = "zipName"
    }
}

// ── Execute result ────────────────────────────────────────────────────────────
// Response from POST /execute
struct ExecuteResult: Codable {
    let sessionId:      String
    let moved:          Int
    let skipped:        Int
    let errors:         [String]
    let foldersCreated: [String]
    let summary:        String

    enum CodingKeys: String, CodingKey {
        case moved, skipped, errors, summary
        case sessionId      = "session_id"
        case foldersCreated = "folders_created"
    }
}

// ── Undo result ───────────────────────────────────────────────────────────────
// Response from POST /undo
struct UndoResult: Codable {
    let sessionId: String?
    let command:   String?
    let reversed:  Int
    let skipped:   Int
    let errors:    [String]
    let message:   String?

    enum CodingKeys: String, CodingKey {
        case command, reversed, skipped, errors, message
        case sessionId = "session_id"
    }
}

// ── Health check ──────────────────────────────────────────────────────────────
// Response from GET /health
struct HealthStatus: Codable {
    let server:  String
    let ollama:  String
    let model:   String
    let version: String

    var isHealthy: Bool {
        server == "running" && ollama == "connected"
    }

    var statusMessage: String {
        if server != "running" {
            return "Server not running"
        }
        if ollama != "connected" {
            return "Ollama not running — start it with: brew services start ollama"
        }
        return "Ready"
    }
}

// ── History item ──────────────────────────────────────────────────────────────
// One entry in the undo history list
struct HistoryItem: Codable, Identifiable {
    var id:        String { sessionId }
    let sessionId: String
    let timestamp: String
    let command:   String
    let files:     Int

    enum CodingKeys: String, CodingKey {
        case timestamp, command, files
        case sessionId = "id"
    }
}

// ── App state ─────────────────────────────────────────────────────────────────
// The different states the main UI can be in
// Used to drive what ContentView shows
enum AppState {
    case idle           // waiting for input
    case thinking       // AI is parsing the command
    case preview        // showing the operation preview
    case executing      // moving files
    case done           // finished — showing result
    case error(String)  // something went wrong
}

// ── Common directories ────────────────────────────────────────────────────────
// Matches GET /directories response
struct CommonDirectories: Codable {
    let desktop:   String
    let documents: String
    let downloads: String
    let home:      String
}
