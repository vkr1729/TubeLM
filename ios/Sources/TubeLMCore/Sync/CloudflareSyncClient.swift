import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

public struct SyncPayload: Codable, Sendable {
    public let readIds: [String]
    public let top20Read: [String]
    public let itemStates: [String: Double]
    public let bookmarks: [FeedItem]
    public let bookmarkStates: [String: Double]

    enum CodingKeys: String, CodingKey {
        case readIds = "read_ids"
        case top20Read = "top20_read"
        case itemStates = "item_states"
        case bookmarks
        case bookmarkStates = "bookmark_states"
    }

    public init(
        readIds: [String],
        top20Read: [String],
        itemStates: [String: Double],
        bookmarks: [FeedItem] = [],
        bookmarkStates: [String: Double] = [:]
    ) {
        self.readIds = readIds
        self.top20Read = top20Read
        self.itemStates = itemStates
        self.bookmarks = bookmarks
        self.bookmarkStates = bookmarkStates
    }
}

public struct SyncResponse: Codable, Sendable {
    public let ok: Bool?
    public let readIds: [String]
    public let top20Read: [String]
    public let itemStates: [String: Double]
    public let bookmarks: [FeedItem]
    public let bookmarkStates: [String: Double]
    public let updatedAt: String?
    public let message: String?

    enum CodingKeys: String, CodingKey {
        case ok
        case readIds = "read_ids"
        case top20Read = "top20_read"
        case itemStates = "item_states"
        case bookmarks
        case bookmarkStates = "bookmark_states"
        case updatedAt = "updated_at"
        case message
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.ok = try c.decodeIfPresent(Bool.self, forKey: .ok)
        self.readIds = try c.decodeIfPresent([String].self, forKey: .readIds) ?? []
        self.top20Read = try c.decodeIfPresent([String].self, forKey: .top20Read) ?? []
        self.itemStates = try c.decodeIfPresent([String: Double].self, forKey: .itemStates) ?? [:]
        self.bookmarks = try c.decodeIfPresent([FeedItem].self, forKey: .bookmarks) ?? []
        self.bookmarkStates = try c.decodeIfPresent([String: Double].self, forKey: .bookmarkStates) ?? [:]
        self.updatedAt = try c.decodeIfPresent(String.self, forKey: .updatedAt)
        self.message = try c.decodeIfPresent(String.self, forKey: .message)
    }

    public init(
        readIds: [String] = [],
        top20Read: [String] = [],
        itemStates: [String: Double] = [:],
        bookmarks: [FeedItem] = [],
        bookmarkStates: [String: Double] = [:]
    ) {
        self.ok = nil
        self.readIds = readIds
        self.top20Read = top20Read
        self.itemStates = itemStates
        self.bookmarks = bookmarks
        self.bookmarkStates = bookmarkStates
        self.updatedAt = nil
        self.message = nil
    }
}

public enum SyncError: Error, Sendable {
    case unauthorized
    case rateLimited
    case payloadTooLarge
    case server(status: Int)
    case decoding(Error)
}

public actor CloudflareSyncClient {
    private let baseURL: URL
    private let syncKey: String
    private let session: URLSession

    public init(
        baseURL: URL = URL(string: "https://tubelm-sync.kedarvreddy.workers.dev")!,
        syncKey: String = "",
        session: URLSession = .shared
    ) {
        self.baseURL = baseURL
        self.syncKey = syncKey
        self.session = session
    }

    public var isConfigured: Bool { !syncKey.isEmpty }

    private func authorizedRequest(method: String) -> URLRequest {
        var request = URLRequest(url: baseURL)
        request.httpMethod = method
        request.timeoutInterval = 15
        request.addValue("Bearer \(syncKey)", forHTTPHeaderField: "Authorization")
        request.addValue(syncKey, forHTTPHeaderField: "X-Sync-Key")
        return request
    }

    private func perform(_ request: URLRequest) async throws -> Data {
        #if canImport(FoundationNetworking)
        let (data, response) = try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<(Data, URLResponse), Error>) in
            let task = self.session.dataTask(with: request) { data, response, error in
                if let error = error { continuation.resume(throwing: error); return }
                guard let data = data, let response = response else {
                    continuation.resume(throwing: URLError(.badServerResponse)); return
                }
                continuation.resume(returning: (data, response))
            }
            task.resume()
        }
        #else
        let (data, response) = try await session.data(for: request)
        #endif

        if let http = response as? HTTPURLResponse, http.statusCode >= 400 {
            switch http.statusCode {
            case 401: throw SyncError.unauthorized
            case 429: throw SyncError.rateLimited
            case 413: throw SyncError.payloadTooLarge
            default: throw SyncError.server(status: http.statusCode)
            }
        }
        return data
    }

    private func decodeResponse(_ data: Data) throws -> SyncResponse {
        do {
            return try JSONDecoder().decode(SyncResponse.self, from: data)
        } catch {
            throw SyncError.decoding(error)
        }
    }

    public func fetchRemoteState() async throws -> SyncResponse? {
        guard isConfigured else { return nil }
        let data = try await perform(authorizedRequest(method: "GET"))
        return try decodeResponse(data)
    }

    public func pushLocalMutations(
        readIds: [String],
        top20Read: [String],
        itemStates: [String: Double],
        bookmarks: [FeedItem] = [],
        bookmarkStates: [String: Double] = [:]
    ) async throws -> SyncResponse? {
        guard isConfigured else { return nil }
        var request = authorizedRequest(method: "POST")
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")
        let cleanIds = Array(readIds.map {
            $0.trimmingCharacters(in: .whitespacesAndNewlines)
        }.filter { !$0.isEmpty && $0.count <= 256 }.prefix(5000))
        let cleanTop20 = Array(top20Read.map {
            $0.trimmingCharacters(in: .whitespacesAndNewlines)
        }.filter { !$0.isEmpty && $0.count <= 256 }.prefix(5000))
        var cleanStates: [String: Double] = [:]
        for (key, ts) in itemStates {
            let id = key.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !id.isEmpty, id.count <= 256, ts.isFinite else { continue }
            cleanStates[id] = ts
        }
        var cleanBookmarkStates: [String: Double] = [:]
        for (key, ts) in bookmarkStates {
            let id = key.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !id.isEmpty, id.count <= 256, ts.isFinite else { continue }
            cleanBookmarkStates[id] = ts
        }
        let cappedBookmarks = Array(bookmarks.prefix(200))
        request.httpBody = try JSONEncoder().encode(
            SyncPayload(
                readIds: cleanIds,
                top20Read: cleanTop20,
                itemStates: cleanStates,
                bookmarks: cappedBookmarks,
                bookmarkStates: cleanBookmarkStates
            )
        )
        let data = try await perform(request)
        return try decodeResponse(data)
    }
}
