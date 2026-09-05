//
//  APIService.swift
//  Organizer
//
//  Created by Carlos Aguilar
//
//  Handles all HTTP communication with the Python FastAPI backend.
//  All requests go to localhost:8000 — the backend must be running.

import Foundation

// Explicit IPv4 — "localhost" can resolve to IPv6 (::1) which uvicorn
// doesn't listen on, causing intermittent "connection refused" errors.
private let BASE_URL = "http://127.0.0.1:8000"

// ── API errors ────────────────────────────────────────────────────────────────
enum APIError: Error, LocalizedError {
    case serverUnreachable
    case decodingFailed(String)
    case serverError(String)
    case ollamaNotRunning

    var errorDescription: String? {
        switch self {
        case .serverUnreachable:
            return "Cannot reach the Organizer server. Make sure uvicorn is running on port 8000."
        case .decodingFailed(let msg):
            return "Response error: \(msg)"
        case .serverError(let msg):
            return "Server error: \(msg)"
        case .ollamaNotRunning:
            return "Ollama is not running. Start it with: brew services start ollama"
        }
    }
}

// ── API Service ───────────────────────────────────────────────────────────────
class APIService: ObservableObject {
    static let shared = APIService()
    private init() {}

    // ── URL Session ───────────────────────────────────────────────────────────
    // waitsForConnectivity intentionally NOT set — it causes localhost
    // requests to hang indefinitely in sandboxed MenuBarExtra apps.
    private let session: URLSession = {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest  = 90    // 90s — Ollama cold starts are slow
        config.timeoutIntervalForResource = 180   // 3min total per resource
        config.requestCachePolicy         = .reloadIgnoringLocalCacheData
        return URLSession(configuration: config)
    }()

    // ── Generic GET ───────────────────────────────────────────────────────────
    private func get<T: Decodable>(_ path: String) async throws -> T {
        guard let url = URL(string: BASE_URL + path) else {
            throw APIError.serverUnreachable
        }
        var request = URLRequest(url: url)
        request.timeoutInterval = 90

        do {
            let (data, response) = try await session.data(for: request)
            try handleHTTPResponse(response, data: data)
            return try decode(T.self, from: data)
        } catch let e as APIError { throw e }
          catch { throw APIError.serverUnreachable }
    }

    // ── Generic POST ──────────────────────────────────────────────────────────
    private func post<T: Decodable, B: Encodable>(
        _ path: String,
        body: B
    ) async throws -> T {
        guard let url = URL(string: BASE_URL + path) else {
            throw APIError.serverUnreachable
        }
        var request        = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let encoded        = try JSONEncoder().encode(body)
        request.httpBody   = encoded
        request.timeoutInterval = 90

        // Debug — print what we're sending so 500s are diagnosable
        if let bodyStr = String(data: encoded, encoding: .utf8) {
            print("POST \(path) body: \(bodyStr.prefix(500))")
        }

        do {
            let (data, response) = try await session.data(for: request)
            if let respStr = String(data: data, encoding: .utf8) {
                print("POST \(path) response: \(respStr.prefix(300))")
            }
            try handleHTTPResponse(response, data: data)
            return try decode(T.self, from: data)
        } catch let e as APIError { throw e }
          catch { throw APIError.serverUnreachable }
    }

    // ── POST empty body ───────────────────────────────────────────────────────
    private func postEmpty<T: Decodable>(_ path: String) async throws -> T {
        guard let url = URL(string: BASE_URL + path) else {
            throw APIError.serverUnreachable
        }
        var request        = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody   = "{}".data(using: .utf8)
        request.timeoutInterval = 90

        do {
            let (data, response) = try await session.data(for: request)
            try handleHTTPResponse(response, data: data)
            return try decode(T.self, from: data)
        } catch let e as APIError { throw e }
          catch { throw APIError.serverUnreachable }
    }

    // ── Response handler ──────────────────────────────────────────────────────
    private func handleHTTPResponse(_ response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse else { return }
        if http.statusCode == 503 { throw APIError.ollamaNotRunning }
        if http.statusCode >= 400 {
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let detail = json["detail"] as? String {
                throw APIError.serverError(detail)
            }
            throw APIError.serverError("HTTP \(http.statusCode)")
        }
    }

    // ── Decoder ───────────────────────────────────────────────────────────────
    private func decode<T: Decodable>(_ type: T.Type, from data: Data) throws -> T {
        do {
            return try JSONDecoder().decode(type, from: data)
        } catch {
            throw APIError.decodingFailed(error.localizedDescription)
        }
    }


    // ── Public endpoints ──────────────────────────────────────────────────────

    func checkHealth() async throws -> HealthStatus {
        try await get("/health")
    }

    func getDirectories() async throws -> CommonDirectories {
        try await get("/directories")
    }

    func scan(directory: String = "desktop") async throws -> ScanResult {
        let encoded = directory.addingPercentEncoding(
            withAllowedCharacters: .urlQueryAllowed
        ) ?? directory
        return try await get("/scan?directory=\(encoded)")
    }

    func sendCommand(
        command: String,
        directory: String? = nil
    ) async throws -> CommandResponse {
        struct Body: Encodable {
            let command:   String
            let directory: String?
        }
        return try await post(
            "/command",
            body: Body(command: command, directory: directory)
        )
    }

    func zip(
        operations: [FileOperation],
        command: String
    ) async throws -> ExecuteResult {
        struct Body: Encodable {
            let operations: [FileOperation]
            let command:    String
        }
        return try await post(
            "/zip",
            body: Body(operations: operations, command: command)
        )
    }

    func trash(
        operations: [FileOperation],
        command: String
    ) async throws -> ExecuteResult {
        struct Body: Encodable {
            let operations: [FileOperation]
            let command:    String
        }
        return try await post(
            "/trash",
            body: Body(operations: operations, command: command)
        )
    }

    func execute(
        operations: [FileOperation],
        command: String
    ) async throws -> ExecuteResult {
        struct Body: Encodable {
            let operations: [FileOperation]
            let command:    String
        }
        return try await post(
            "/execute",
            body: Body(operations: operations, command: command)
        )
    }

    func undo() async throws -> UndoResult {
        try await postEmpty("/undo")
    }

    func getHistory() async throws -> [HistoryItem] {
        struct HistoryResponse: Decodable { let history: [HistoryItem] }
        let r: HistoryResponse = try await get("/history")
        return r.history
    }

    func createFolder(
        parentDir: String,
        folderName: String
    ) async throws -> [String: String] {
        struct Body: Encodable {
            let parentDir:  String
            let folderName: String
            enum CodingKeys: String, CodingKey {
                case parentDir  = "parent_dir"
                case folderName = "folder_name"
            }
        }
        return try await post(
            "/create-folder",
            body: Body(parentDir: parentDir, folderName: folderName)
        )
    }
}
