import Foundation

enum MetadataError: Error, LocalizedError {
    case processNotRunning
    case invalidRequest(String)
    case unknownOperation(String)

    var errorDescription: String? {
        switch self {
        case .processNotRunning: "ExifTool process is not running"
        case .invalidRequest(let detail): "Invalid request: \(detail)"
        case .unknownOperation(let op): "Unknown operation: \(op)"
        }
    }
}

struct ReadRequest: Decodable {
    let file: String
    let tags: [String]
    let fast: Bool?
}

struct WriteRequest: Decodable {
    let file: String
    let tags: [String: String]
}

struct Request: Decodable {
    let op: String
    let file: String
    let tags: AnyCodableTags?
    let fast: Bool?

    enum CodingKeys: String, CodingKey {
        case op, file, tags, fast
    }
}

enum AnyCodableTags: Decodable {
    case array([String])
    case dict([String: String])

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let arr = try? container.decode([String].self) {
            self = .array(arr)
        } else if let dict = try? container.decode([String: String].self) {
            self = .dict(dict)
        } else {
            throw DecodingError.typeMismatch(
                AnyCodableTags.self,
                .init(codingPath: decoder.codingPath, debugDescription: "Expected array or dict for tags")
            )
        }
    }
}

struct ErrorResponse: Encodable {
    let error: String
}

struct ReadResponse: Encodable {
    let tags: [String: String]

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(tags)
    }
}

struct WriteResponse: Encodable {
    let updated: Bool
    let files_changed: Int
}
