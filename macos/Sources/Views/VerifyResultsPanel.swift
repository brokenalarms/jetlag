import SwiftUI

/// The Verify tab's results side: the shared `ResultsPanel` — header, table, and the
/// command-output log behind the terminal toggle — holding a table of card files.
struct VerifyResultsPanel: View {
    @Bindable var state: AppState

    private var session: VerifySession { state.verifySession }
    private var rows: [VerifyRow] { session.report.visibleRows(showMatched: session.showMatched) }

    var body: some View {
        ResultsPanel(phase: phase,
                     showsLog: $state.verifySession.showsLog,
                     logLines: session.log,
                     logHolder: state.verifyLogHolder,
                     onClearLog: { state.clearVerifyLog() }) {
            VerifyTableView(rows: rows,
                            locations: session.report.locations.map(\.location),
                            source: session.source)
        }
    }

    private var summaryLine: String? {
        session.report.summary.map {
            Strings.Verify.summary(checked: $0.checked, onEvery: $0.onEveryLocation,
                                   attention: $0.needAttention, notChecked: $0.notChecked,
                                   kinds: $0.notCheckedKinds)
        }
    }

    private var phase: ResultsPhase {
        if session.isRunning && session.report.rows.isEmpty {
            return .startingUp(label: Strings.Verify.checkingLabel,
                               status: session.log.last { !$0.strippedText.isEmpty }?.strippedText)
        }
        if !rows.isEmpty {
            // The summary line is always shown once a check has run, so a short table
            // reads as the files that need attention, not as all there is.
            return .content(ResultsHeader(icon: "checkmark.shield", title: Strings.Verify.resultsTitle,
                                          count: summaryLine))
        }
        if let summaryLine {
            return .message(title: Strings.Verify.allClear, detail: summaryLine)
        }
        return .idle(label: Strings.Verify.idleLabel)
    }
}

/// Card files and their verdict on each location, in the shared `ResultsTable`: the
/// file, one status column per location the check ran against, and the details that
/// help judge a file not on every location.
struct VerifyTableView: View {
    let rows: [VerifyRow]
    let locations: [String]
    let source: String

    @State private var measurements = ColumnMeasurements()

    private static let iconWidth: CGFloat = 18
    private static let monoFont = Theme.Typography.nsFileMono
    private static let systemFont = Theme.Typography.nsFile
    private static let detailFont = Theme.Typography.nsDetail
    /// `ResultsTable` draws at most ten columns: the file, the details, and up to
    /// eight locations.
    static let maxLocationColumns = 8

    var body: some View {
        ResultsTable(rows: rows,
                     columns: columns,
                     measurements: measurements,
                     fileURL: { row in
                         URL(fileURLWithPath: (source as NSString).appendingPathComponent(row.file))
                     })
    }

    private var columns: [ResultsColumn<VerifyRow>] {
        var columns = [
            ResultsColumn<VerifyRow>(Strings.Verify.fileColumn, minWidth: 80,
                          measure: { row in
                              CellText([(row.file, Self.monoFont)], maxWidth: DiffTableView.fileColumnMaxWidth)
                          }, cell: { row in
                              Text(row.file)
                                  .font(Theme.Typography.fileMono)
                                  .lineLimit(1)
                                  .truncationMode(.middle)
                          }),
        ]
        for location in locations.prefix(Self.maxLocationColumns) {
            columns.append(ResultsColumn<VerifyRow>(location, minWidth: 80,
                measure: { row in
                    CellText([(Self.label(row.outcomes[location]), Self.systemFont),
                              (Self.subtitle(row.outcomes[location]) ?? "", Self.detailFont)],
                             extraWidth: Self.iconWidth)
                }, cell: { row in
                    Self.locationCell(row.outcomes[location])
                }))
        }
        columns.append(ResultsColumn<VerifyRow>(Strings.Verify.detailsColumn, minWidth: 80,
            measure: { row in
                CellText([(Strings.Verify.clipDetails(row.details), Self.systemFont),
                          (row.details.recordedHashesDisagree ? Strings.Verify.recordedHashesDisagree : "",
                           Self.detailFont)])
            }, cell: { row in
                VStack(alignment: .leading, spacing: Theme.Space.hairline) {
                    Text(Strings.Verify.clipDetails(row.details))
                        .font(Theme.Typography.file)
                        .foregroundStyle(row.details.opens == false ? Theme.Status.failure : Theme.Text.secondaryColor)
                        .lineLimit(1)
                    if row.details.recordedHashesDisagree {
                        Text(Strings.Verify.recordedHashesDisagree)
                            .font(Theme.Typography.detail)
                            .foregroundStyle(Theme.Status.warning)
                            .lineLimit(1)
                    }
                }
            }))
        return columns
    }

    private static func label(_ outcome: VerifyOutcome?) -> String {
        outcome?.verdict.label ?? "—"
    }

    /// The hash result under a matched verdict, or how many copies a duplicate found.
    private static func subtitle(_ outcome: VerifyOutcome?) -> String? {
        guard let outcome else { return nil }
        if outcome.verdict == .duplicate { return Strings.Verify.copiesFound(outcome.copies.count) }
        switch outcome.hash {
        case "match": return Strings.Verify.hashMatch
        case "not_hashable": return Strings.Verify.hashNotHashable
        default: return nil
        }
    }

    static func badgeState(_ verdict: VerifyVerdict) -> StatusBadgeState {
        switch verdict {
        case .matched: .done
        case .unverifiable: .custom(icon: "questionmark.circle.fill", tint: Theme.Status.warning)
        case .unreachable: .unchanged
        case .missing, .duplicate, .dataDiffers, .sizeDiffers, .hashMismatch: .failed
        }
    }

    @ViewBuilder
    private static func locationCell(_ outcome: VerifyOutcome?) -> some View {
        if let outcome {
            VStack(alignment: .leading, spacing: Theme.Space.hairline) {
                StatusBadge(state: badgeState(outcome.verdict), label: outcome.verdict.label)
                if let subtitle = subtitle(outcome) {
                    Text(subtitle)
                        .font(Theme.Typography.detail)
                        .foregroundStyle(Theme.Text.tertiary)
                        .lineLimit(1)
                }
            }
            .help(outcome.copies.joined(separator: "\n"))
        } else {
            Text("—").foregroundStyle(Theme.Text.tertiary)
        }
    }
}
