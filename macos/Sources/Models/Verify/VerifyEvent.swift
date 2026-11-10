import Foundation

/// JSONL events verify-card.sh writes on stdout, declared in
/// scripts/lib/verify-card-schema.yaml.
enum VerifyEvent: Decodable, Equatable {
    case location(VerifyLocationStatus)
    case file(VerifyFileDetails)
    case result(file: String, location: String, outcome: VerifyOutcome)
    case summary(VerifySummary)

    private enum CodingKeys: String, CodingKey {
        case event, file, kind, size, location, verdict, basis, copies, hash
        case dataBytes = "data_bytes"
        case recordedHashesDisagree = "recorded_hashes_disagree"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        switch try c.decode(String.self, forKey: .event) {
        case "verify_location":
            self = .location(try VerifyLocationStatus(from: decoder))
        case "verify_file":
            self = .file(try VerifyFileDetails(from: decoder))
        case "verify_result":
            self = .result(
                file: try c.decode(String.self, forKey: .file),
                location: try c.decode(String.self, forKey: .location),
                outcome: VerifyOutcome(
                    verdict: try c.decode(VerifyVerdict.self, forKey: .verdict),
                    basis: try c.decodeIfPresent(String.self, forKey: .basis),
                    copies: try c.decode([String].self, forKey: .copies),
                    hash: try c.decodeIfPresent(String.self, forKey: .hash)))
        case "verify_summary":
            self = .summary(try VerifySummary(from: decoder))
        case let other:
            throw DecodingError.dataCorruptedError(
                forKey: .event, in: c, debugDescription: "Unknown verify-card event \(other)")
        }
    }

    /// The event a machine-readable line carries, or nil for any other line.
    static func decode(_ line: String) -> VerifyEvent? {
        guard let data = line.data(using: .utf8) else { return nil }
        return try? JSONDecoder().decode(VerifyEvent.self, from: data)
    }
}

/// A checked card file, and for one not on every location what helps judge it.
struct VerifyFileDetails: Decodable, Equatable {
    let file: String
    let kind: String
    let size: Int
    let dataBytes: Int?
    let recordedHashesDisagree: Bool
    let durationSeconds: Double?
    /// false: ffprobe finds no duration, a broken recording. nil: not probed.
    let opens: Bool?
    let neighboursBackedUp: Bool?

    private enum CodingKeys: String, CodingKey {
        case file, kind, size, opens
        case dataBytes = "data_bytes"
        case recordedHashesDisagree = "recorded_hashes_disagree"
        case durationSeconds = "duration_seconds"
        case neighboursBackedUp = "neighbours_backed_up"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        file = try c.decode(String.self, forKey: .file)
        kind = try c.decode(String.self, forKey: .kind)
        size = try c.decode(Int.self, forKey: .size)
        dataBytes = try c.decodeIfPresent(Int.self, forKey: .dataBytes)
        recordedHashesDisagree = try c.decodeIfPresent(Bool.self, forKey: .recordedHashesDisagree) ?? false
        durationSeconds = try c.decodeIfPresent(Double.self, forKey: .durationSeconds)
        opens = try c.decodeIfPresent(Bool.self, forKey: .opens)
        neighboursBackedUp = try c.decodeIfPresent(Bool.self, forKey: .neighboursBackedUp)
    }
}

struct VerifyLocationStatus: Decodable, Equatable {
    let location: String
    let root: String
    let remote: Bool
    let network: Bool
    let reachable: Bool
    let files: Int?
}

/// A `verify_result` verdict. Every token the schema declares is a case, so a
/// label switch with no default fails to compile when one is missing.
enum VerifyVerdict: String, Decodable, CaseIterable {
    case matched, missing, duplicate
    case dataDiffers = "data_differs"
    case sizeDiffers = "size_differs"
    case unverifiable, unreachable
    case hashMismatch = "hash_mismatch"

    var label: String {
        switch self {
        case .matched: Strings.Verify.verdictMatched
        case .missing: Strings.Verify.verdictMissing
        case .duplicate: Strings.Verify.verdictDuplicate
        case .dataDiffers: Strings.Verify.verdictDataDiffers
        case .sizeDiffers: Strings.Verify.verdictSizeDiffers
        case .unverifiable: Strings.Verify.verdictUnverifiable
        case .unreachable: Strings.Verify.verdictUnreachable
        case .hashMismatch: Strings.Verify.verdictHashMismatch
        }
    }

    var passes: Bool { self == .matched }
}

struct VerifyOutcome: Equatable {
    let verdict: VerifyVerdict
    let basis: String?
    let copies: [String]
    let hash: String?
}

struct VerifySummary: Decodable, Equatable {
    let checked: Int
    let onEveryLocation: Int
    let needAttention: Int
    let notChecked: Int
    let notCheckedKinds: [String]
    let hashesChecked: Int?
    let hashCacheWritten: Int?

    private enum CodingKeys: String, CodingKey {
        case checked
        case onEveryLocation = "on_every_location"
        case needAttention = "need_attention"
        case notChecked = "not_checked"
        case notCheckedKinds = "not_checked_kinds"
        case hashesChecked = "hashes_checked"
        case hashCacheWritten = "hash_cache_written"
    }
}
