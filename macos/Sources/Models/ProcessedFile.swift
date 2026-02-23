import Foundation

/// A single file's processing results, accumulated from @@key=value machine-readable output.
struct ProcessedFile: Identifiable {
    let id = UUID()
    let filename: String
    var originalTime: String?
    var correctedTime: String?
    var timezone: String?
    var shift: String?
    var destination: String?
    var organizeAction: String?
    var status: Status = .processing

    enum Status: String {
        case processing, changed, unchanged, failed
    }

    /// Parse a Date from an EXIF-style timestamp string like "2025:10:07 08:07:22+08:00"
    var correctedDate: Date? {
        guard let raw = correctedTime else { return nil }
        return Self.parseExifTimestamp(raw)
    }

    var originalDate: Date? {
        guard let raw = originalTime else { return nil }
        return Self.parseExifTimestamp(raw)
    }

    var statusLabel: String {
        switch status {
        case .processing: return "Processing"
        case .changed: return "Changed"
        case .unchanged: return "OK"
        case .failed: return "Failed"
        }
    }

    var statusIcon: String {
        switch status {
        case .processing: return "arrow.triangle.2.circlepath"
        case .changed: return "checkmark.circle.fill"
        case .unchanged: return "checkmark.circle"
        case .failed: return "xmark.circle.fill"
        }
    }

    /// Parses EXIF timestamps: "2025:10:07 08:07:22+08:00" or "2025:10:07 08:07:22"
    private static func parseExifTimestamp(_ raw: String) -> Date? {
        // Try with timezone offset first (e.g. "2025:10:07 08:07:22+08:00")
        let fmtWithTZ = DateFormatter()
        fmtWithTZ.dateFormat = "yyyy:MM:dd HH:mm:ssxxx"
        if let d = fmtWithTZ.date(from: raw) { return d }

        // Try without colon in offset (e.g. "2025:10:07 08:07:22+0800")
        let fmtWithTZNoColon = DateFormatter()
        fmtWithTZNoColon.dateFormat = "yyyy:MM:dd HH:mm:ssxx"
        if let d = fmtWithTZNoColon.date(from: raw) { return d }

        // Try without timezone
        let fmtNoTZ = DateFormatter()
        fmtNoTZ.dateFormat = "yyyy:MM:dd HH:mm:ss"
        return fmtNoTZ.date(from: raw)
    }
}

/// Accumulates @@key=value lines into ProcessedFile objects.
///
/// Protocol: @@file=X starts a new file block. Subsequent @@key=value lines
/// update the current file until the next @@file= or end of stream.
@Observable
final class ProcessedFileAccumulator {
    var files: [ProcessedFile] = []

    var summary: Summary {
        let total = files.count
        let changed = files.filter { $0.status == .changed }.count
        let unchanged = files.filter { $0.status == .unchanged }.count
        let failed = files.filter { $0.status == .failed }.count
        return Summary(total: total, changed: changed, unchanged: unchanged, failed: failed)
    }

    struct Summary {
        let total: Int
        let changed: Int
        let unchanged: Int
        let failed: Int
    }

    func reset() {
        files = []
    }

    /// Feed a single log line. If it's a @@key=value line, parse and accumulate.
    func ingest(_ line: LogLine) {
        guard line.isMachineReadable else { return }
        let text = line.text

        guard let eqIndex = text.firstIndex(of: "=") else { return }
        let keyStart = text.index(text.startIndex, offsetBy: 2) // skip @@
        let key = String(text[keyStart..<eqIndex])
        let value = String(text[text.index(after: eqIndex)...])

        switch key {
        case "file":
            // Start a new file block
            files.append(ProcessedFile(filename: value))
        case "original_time":
            updateCurrent { $0.originalTime = value }
        case "corrected_time":
            updateCurrent { $0.correctedTime = value }
        case "timezone":
            updateCurrent { $0.timezone = value }
        case "shift":
            updateCurrent { $0.shift = value }
        case "status":
            updateCurrent { $0.status = ProcessedFile.Status(rawValue: value) ?? .processing }
        case "dest":
            updateCurrent { $0.destination = value }
        case "action":
            updateCurrent { $0.organizeAction = value }
        default:
            break
        }
    }

    private func updateCurrent(_ update: (inout ProcessedFile) -> Void) {
        guard !files.isEmpty else { return }
        update(&files[files.count - 1])
    }
}
