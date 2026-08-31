import Foundation

/// The field a correction read its timestamp from, as named by the pipeline's
/// `source` token on a `timestamp_result` event.
///
/// The token carries what the timestamp strings cannot: whether the original's
/// digits are UTC or local wall-clock time. Every display decision that depends on
/// that — the source label under the Original cell, whether that cell's value
/// reads `UTC` — is taken from the case, never by parsing a formatted value back.
enum TimestampSource: String {
    case dateTimeOriginal = "datetimeoriginal"
    case creationDate = "creationdate"
    case mediaCreateDate = "mediacreatedate"
    case filename
    case fileBirth = "file_birth"
    case fileModified = "file_mtime"

    init?(token: String?) {
        guard let token, let source = TimestampSource(rawValue: token) else { return nil }
        self = source
    }

    var label: String {
        switch self {
        case .dateTimeOriginal: return Strings.DiffTable.sourceDateTimeOriginal
        case .creationDate: return Strings.DiffTable.sourceCreationDate
        case .mediaCreateDate: return Strings.DiffTable.sourceClockUTC
        case .filename: return Strings.DiffTable.sourceFilename
        case .fileBirth, .fileModified: return Strings.DiffTable.sourceFileTime
        }
    }

    /// Whether the source's stored digits are a UTC instant rather than local time.
    /// The QuickTime clock atoms are UTC by specification; every other source the
    /// ranking can pick either states its own zone or has none.
    var isUTC: Bool {
        self == .mediaCreateDate
    }

    /// The original timestamp as the table shows it: a UTC instant reads as `UTC`,
    /// a zoned source keeps its own ±HH:MM, and a naive one stays bare digits.
    func originalDisplay(_ stored: String) -> String {
        guard isUTC else { return stored }
        let digits = stored.hasSuffix("Z") ? String(stored.dropLast()) : stored
        return "\(digits) \(Strings.DiffTable.utcSuffix)"
    }
}
