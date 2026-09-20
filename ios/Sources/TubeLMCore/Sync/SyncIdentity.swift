import Foundation

public enum SyncIdentity: Sendable {
    /// Exact port of desktop/templates/reader.html:normalizeVideoUrl
    /// YouTube host -> v param else pathname.slice(1); otherwise origin + pathname;
    /// catch -> trimmed raw; empty -> ''
    public static func normalizeVideoUrl(_ urlString: String?) -> String {
        guard let raw = urlString?.trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty else {
            return ""
        }
        guard let components = URLComponents(string: raw), let host = components.host?.lowercased() else {
            return raw
        }
        if host.contains("youtube.com") || host.contains("youtu.be") {
            if let vItem = components.queryItems?.first(where: { $0.name == "v" })?.value,
               !vItem.isEmpty {
                return vItem
            }
            let path = components.path
            if path.count > 1 {
                return String(path.dropFirst())
            }
        }
        if let scheme = components.scheme {
            let portStr = components.port.map { ":\($0)" } ?? ""
            return "\(scheme)://\(components.host ?? "")\(portStr)\(components.path)"
        }
        return raw
    }

    public static func aliases(id: String, videoId: String? = nil, url: String? = nil) -> Set<String> {
        var keys = Set<String>()
        let cleanId = id.trimmingCharacters(in: .whitespacesAndNewlines)
        if !cleanId.isEmpty { keys.insert(cleanId) }
        if let vid = videoId?.trimmingCharacters(in: .whitespacesAndNewlines), !vid.isEmpty {
            keys.insert(vid)
        }
        if let u = url?.trimmingCharacters(in: .whitespacesAndNewlines), !u.isEmpty {
            keys.insert(u)
            let norm = normalizeVideoUrl(u)
            if !norm.isEmpty { keys.insert(norm) }
        }
        return keys
    }

    public static func isItemRead(aliases: Set<String>, in readIDs: Set<String>) -> Bool {
        !aliases.isDisjoint(with: readIDs)
    }
}
