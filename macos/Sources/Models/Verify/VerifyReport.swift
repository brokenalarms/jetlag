import Foundation

/// One checked card file and its verdict on each location.
struct VerifyRow: Identifiable, Equatable {
    let details: VerifyFileDetails
    var outcomes: [String: VerifyOutcome] = [:]

    var id: String { details.file }
    var file: String { details.file }

    /// On every location the run checked: the only rows hidden while "Show matched"
    /// is off, and the only files safe to wipe.
    var isMatchedEverywhere: Bool {
        !outcomes.isEmpty && outcomes.values.allSatisfy { $0.verdict.passes }
    }
}

/// verify-card's events folded into what the Verify screen shows.
struct VerifyReport: Equatable {
    var locations: [VerifyLocationStatus] = []
    var rows: [VerifyRow] = []
    var summary: VerifySummary?

    mutating func apply(_ event: VerifyEvent) {
        switch event {
        case .location(let status):
            locations.append(status)
        case .file(let details):
            rows.append(VerifyRow(details: details))
        case let .result(file, location, outcome):
            if let index = rows.lastIndex(where: { $0.file == file }) {
                rows[index].outcomes[location] = outcome
            }
        case .summary(let summary):
            self.summary = summary
        }
    }

    func visibleRows(showMatched: Bool) -> [VerifyRow] {
        showMatched ? rows : rows.filter { !$0.isMatchedEverywhere }
    }
}
