import Foundation

struct LogLine: Identifiable {
    let id = UUID()
    let text: String
    let stream: Stream
    /// Text without the ANSI colour codes the scripts write for terminal use.
    /// Computed once here: the log view renders every line exactly once, and a
    /// transcript of thousands of lines must never be re-stripped per update.
    let strippedText: String

    enum Stream {
        case stdout, stderr
    }

    init(text: String, stream: Stream) {
        self.text = text
        self.stream = stream
        self.strippedText = text
            .replacingOccurrences(of: "\u{1B}\\[[0-9;]*m", with: "", options: .regularExpression)
            .trimmingCharacters(in: .whitespaces)
    }

    var isMachineReadable: Bool {
        text.hasPrefix("{")
    }
}
