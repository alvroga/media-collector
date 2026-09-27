import Foundation

// Wire types for the engine protocol (docs/agent_docs/app-protocol.md, protocol version 1).
// The decoder uses .convertFromSnakeCase, so `non_file_skipped` is `nonFileSkipped`, etc.

struct SequenceInfo: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let originals: Int
}

struct UnmappedPrefix: Codable, Hashable, Identifiable {
    let prefix: String
    let files: Int
    var id: String { prefix }
}

struct ProjectSummary: Codable {
    let path: String
    let format: String
    let sequences: [SequenceInfo]
    let files: Int
    let originals: Int
    let proxies: Int
    let unused: Int
    let cache: Int
    let nonFileSkipped: Int
    let warnings: [String]
    let canRelink: Bool  // false: readable but not relinkable (the option is disabled)
    let unmappedPrefixes: [UnmappedPrefix]
}

struct MissingFile: Codable, Hashable, Identifiable {
    let path: String
    let reason: String  // "unmapped" | "not_found"
    var id: String { path }
}

struct MissingSummary: Codable {
    let count: Int
    let items: [MissingFile]
}

struct PlanExample: Codable, Hashable {
    let source: String
    let destRel: String
}

struct PlanSummary: Codable {
    let files: Int
    let originals: Int
    let proxies: Int
    let bytes: Int64
    let missing: MissingSummary
    let unmappedPrefixes: [UnmappedPrefix]
    let cacheSkipped: Int
    let renamedOnCollision: Int
    let unusable: Int?  // references with no usable file name, left out of the plan
    let examples: [PlanExample]
}

/// What the user chose; `engineDictionary` is the protocol's options object.
/// The folder structure is always kept (product decision); only the number of leading levels to
/// skip is configurable. Flattening exists only as a developer-CLI option.
struct CopyOptions: Equatable {
    var includeUnused = false
    var includeProxies = false
    var sequenceIDs: [String]? = nil  // nil = every sequence
    var skipLevels = 0                // "skip the first N folder levels"

    var engineDictionary: [String: Any] {
        [
            "include_unused": includeUnused,
            "include_proxies": includeProxies,
            "keep_from_level": skipLevels,
            "sequences": sequenceIDs ?? NSNull(),
        ]
    }
}

// MARK: run

struct RunProgress: Decodable, Equatable {
    let fileIndex: Int
    let fileCount: Int
    let name: String
    let phase: String  // copying | verifying | checking | done
    let fileBytesDone: Int64
    let fileBytesTotal: Int64
    let bytesDone: Int64
    let bytesTotal: Int64
    var fraction: Double { bytesTotal > 0 ? min(1, Double(bytesDone) / Double(bytesTotal)) : 0 }
}

struct RunProblem: Codable, Hashable, Identifiable {
    let status: String  // conflict | missing | failed | cancelled
    let path: String
    let detail: String
    var id: String { status + path }
}

struct RelinkSummary: Codable {
    let relinked: Int?
    let mediaObjects: Int?
    let leftUnchanged: Int?
    let missingAfter: [String]?
    let notes: [String]?
    let skipped: String?  // why relinking was not done
    let error: String?
}

struct ProjectCopy: Codable {
    let status: String  // copied | skipped_identical | conflict | failed
    let path: String
    let detail: String
}

struct RunReport: Codable {
    let ok: Bool
    let cancelled: Bool
    /// Status names as sent by the engine ("copied", "skipped_identical", ...); the snake-case decoding
    /// strategy renames struct fields but not dictionary keys.
    let counts: [String: Int]
    let bytes: Int64
    let problems: [RunProblem]
    let projectCopy: ProjectCopy?
    let relinkedProject: String?
    let relink: RelinkSummary?

    var copied: Int { counts["copied"] ?? 0 }
    var skippedIdentical: Int { counts["skipped_identical"] ?? 0 }
}
