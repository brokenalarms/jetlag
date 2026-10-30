import SwiftUI

struct DiffTableView: View {
    let rows: [DiffTableRow]

    @State private var measurements = RowMeasurements()

    private static let iconWidth: CGFloat = 18
    private static let timelineColumnWidth: CGFloat = 120
    /// A camera filename can run to 40+ characters, and past this it is truncated
    /// in the middle rather than pushing every other column off the panel.
    static let fileColumnMaxWidth: CGFloat = 320
    private static let monoFont = Theme.Typography.nsFileMono
    private static let systemFont = Theme.Typography.nsFile
    private static let detailFont = Theme.Typography.nsDetail
    /// The writes subtitle lists every stale field (e.g. "Writes Keys:CreationDate,
    /// QuickTime:CreateDate, QuickTime:TrackCreateDate, …"), which can grow past
    /// any reasonable column width. Capped to fit three fields untruncated; a
    /// fourth truncates with an ellipsis. The full list stays available via .help.
    static let writesColumnMaxWidth: CGFloat = {
        let threeFields = Strings.DiffTable.wouldWrite(
            "Keys:CreationDate, QuickTime:CreateDate, QuickTime:TrackCreateDate")
        return (threeFields as NSString).size(withAttributes: [.font: detailFont]).width + CellText.padding
    }()

    static func idealWidth(of cell: CellText) -> CGFloat { cell.idealWidth }

    static func contentFitWidth(of cell: CellText) -> CGFloat { cell.contentFitWidth }

    struct TimelineScale {
        let rangeStart: Double
        let rangeEnd: Double
        let duration: Double

        init(range: (lo: Double, hi: Double)?) {
            guard let range, range.hi > range.lo else {
                rangeStart = 0; rangeEnd = 1; duration = 1; return
            }
            let pad = max((range.hi - range.lo) * 0.05, 60)
            rangeStart = range.lo - pad; rangeEnd = range.hi + pad
            duration = rangeEnd - rangeStart
        }

        func fraction(for epoch: Double) -> Double {
            (epoch - rangeStart) / duration
        }
    }

    /// The row's status: what the pipeline said it did, composed from the emitted
    /// action tokens. `dest` never contributes — a skipped file carries one too.
    func statusText(_ row: DiffTableRow) -> String {
        switch row.pipelineResult {
        case "changed":
            return row.outcome.statusLabel ?? Strings.DiffTable.changedStatus
        case "would_change":
            return row.outcome.statusLabel ?? Strings.DiffTable.wouldChangeStatus
        case "unchanged": return Strings.DiffTable.noChangeStatus
        case "failed":
            return Strings.DiffTable.failedStatus
        case nil: return row.lastCompletedStageLabel ?? ""
        default: return row.pipelineResult ?? ""
        }
    }

    func statusState(_ row: DiffTableRow) -> StatusBadgeState {
        switch row.pipelineResult {
        case "changed": .done
        case "unchanged": .unchanged
        case "failed": .failed
        case "would_change": .wouldDo
        case nil: .pending
        default: .plain
        }
    }

    /// What each of a row's cells would draw, in column order: the text, its font
    /// and any icon allowance. Building this is string work only; measuring it is
    /// what the cache avoids repeating for rows that have not changed.
    func cellTexts(_ row: DiffTableRow) -> [CellText] {
        columns(timeline: TimelineScale(range: nil)).map { $0.measure(row) }
    }

    func availableFileURLs(for ids: Set<DiffTableRow.ID>) -> [URL] {
        ResultsTable<DiffTableRow>.fileURLs(for: ids, in: rows, locating: Self.fileURL)
    }

    private static func fileURL(of row: DiffTableRow) -> URL? {
        RowFileLocation.path(for: row).map { URL(fileURLWithPath: $0) }
    }

    /// The destination file a row's own conflicting file is blocking — only rows
    /// whose organize reason is `existsDiffers` have one, and only when that file
    /// still exists on disk. Reading `dest` here is safe: the reason token itself
    /// already states a different file is at that path.
    ///
    /// A selection that mixes conflicts with ordinary rows still offers the item,
    /// acting on the conflicting subset — the alternative is a menu that silently
    /// loses a command because one extra row was selected.
    func conflictingDestinationURLs(for ids: Set<DiffTableRow.ID>) -> [URL] {
        Self.conflictingDestinationURLs(in: rows.filter { ids.contains($0.id) })
    }

    private static func conflictingDestinationURLs(in rows: [DiffTableRow]) -> [URL] {
        rows
            .filter { $0.hasDestinationConflict }
            .compactMap { $0.dest }
            .filter { FileManager.default.fileExists(atPath: $0) }
            .map { URL(fileURLWithPath: $0) }
    }

    /// One column per entry, in the order the table draws them; the cell and the text
    /// it is measured from sit side by side so the two cannot drift apart.
    private func columns(timeline: TimelineScale) -> [ResultsColumn<DiffTableRow>] {
        [
            ResultsColumn(Strings.DiffTable.fileColumn, minWidth: 80,
                          measure: { row in
                              CellText([(row.file, Self.monoFont)],
                                       extraWidth: row.fileCamera != nil ? Self.iconWidth : 0,
                                       maxWidth: Self.fileColumnMaxWidth)
                          }, cell: fileCell),

            ResultsColumn(Strings.DiffTable.timelineColumn, minWidth: 50, idealWidth: 80,
                          measure: { _ in CellText(fixedWidth: Self.timelineColumnWidth) },
                          cell: { timelineCell($0, scale: timeline) }),

            ResultsColumn(Strings.DiffTable.originalColumn, minWidth: 130,
                          measure: { row in
                              CellText([(row.originalTimeDisplay ?? "", Self.monoFont),
                                        (row.timestampSource?.label ?? "", Self.detailFont)])
                          }, cell: originalCell),

            ResultsColumn(Strings.DiffTable.correctedColumn, minWidth: 130,
                          measure: { row in CellText([(row.correctedTime ?? "", Self.monoFont)]) },
                          cell: { row in
                              Text(row.correctedTime ?? "—")
                                  .font(Theme.Typography.fileMono)
                                  .foregroundStyle(row.correctedTime != nil ? Theme.Text.primary : Theme.Text.tertiary)
                          }),

            ResultsColumn(Strings.DiffTable.timestampColumn, minWidth: 70,
                          measure: { row in
                              CellText([(changeBadgeText(row), Self.systemFont),
                                        (staleFieldsText(row).map(Strings.DiffTable.wouldWrite) ?? "", Self.detailFont)],
                                       extraWidth: row.requiresForceTimezone ? Self.iconWidth : 0,
                                       maxWidth: Self.writesColumnMaxWidth)
                          }, cell: timestampCell),

            ResultsColumn(Strings.DiffTable.destinationColumn, minWidth: 80,
                          measure: { row in
                              CellText([(row.dest.map { ($0 as NSString).lastPathComponent } ?? "", Self.monoFont),
                                        (row.skipReason?.explanation ?? "", Self.detailFont)],
                                       extraWidth: row.hasDestinationConflict ? Self.iconWidth : 0)
                          }, cell: destinationCell),

            ResultsColumn(Strings.DiffTable.statusColumn, minWidth: 80,
                          measure: { row in
                              CellText([(statusText(row), Self.systemFont),
                                        (staleFieldsText(row).map(Strings.DiffTable.wouldWrite) ?? "", Self.detailFont)],
                                       extraWidth: Self.iconWidth,
                                       maxWidth: Self.writesColumnMaxWidth)
                          }, cell: statusCell),
        ]
    }

    var body: some View {
        ResultsTable(rows: rows,
                     columns: columns(timeline: measurements.timelineScale(for: rows)),
                     measurements: measurements,
                     fileURL: Self.fileURL,
                     extraMenuItems: { selected in
                         let urls = Self.conflictingDestinationURLs(in: selected)
                         return urls.isEmpty
                             ? [] : [ResultsMenuItem(title: Strings.DiffTable.showExistingAtDestination, urls: urls)]
                     })
    }

    private func fileCell(_ row: DiffTableRow) -> some View {
        HStack(spacing: Theme.Space.xs) {
            if let camera = row.fileCamera {
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(Theme.Typography.detail)
                    .foregroundStyle(Theme.Status.warning)
                    .help(Strings.DiffTable.cameraMismatchHelp(camera.name))
            }
            Text(row.file)
                .font(Theme.Typography.fileMono)
                .lineLimit(1)
                .truncationMode(.middle)
        }
    }

    private func originalCell(_ row: DiffTableRow) -> some View {
        VStack(alignment: .leading, spacing: Theme.Space.hairline) {
            Text(row.originalTimeDisplay ?? "—")
                .font(Theme.Typography.fileMono)
                .foregroundStyle(row.originalTime != nil ? Theme.Text.primary : Theme.Text.tertiary)
            if let label = row.timestampSource?.label {
                Text(label)
                    .font(Theme.Typography.detail)
                    .foregroundStyle(Theme.Text.tertiary)
                    .lineLimit(1)
            }
        }
        .help(rowExplanation(row))
    }

    private func statusCell(_ row: DiffTableRow) -> some View {
        VStack(alignment: .leading, spacing: Theme.Space.hairline) {
            StatusBadge(state: statusState(row), label: statusText(row))
            if let fields = staleFieldsText(row) {
                Text(Strings.DiffTable.wouldWrite(fields))
                    .font(Theme.Typography.detail)
                    .foregroundStyle(Theme.Text.tertiary)
                    .lineLimit(1)
            }
        }
        .help(rowExplanation(row))
    }

    @ViewBuilder
    private func timelineCell(_ row: DiffTableRow, scale: TimelineScale) -> some View {
        GeometryReader { geo in
            let markSize: CGFloat = 6
            let usable = geo.size.width - markSize
            ZStack(alignment: .leading) {
                Rectangle()
                    .fill(Theme.Text.primaryColor.opacity(Theme.Tint.stripe))
                    .frame(height: 1)
                    .frame(maxWidth: .infinity)

                if let oEpoch = row.originalEpoch, let cEpoch = row.correctedEpoch,
                   oEpoch != cEpoch {
                    let oX = CGFloat(scale.fraction(for: oEpoch)) * usable
                    let cX = CGFloat(scale.fraction(for: cEpoch)) * usable
                    Rectangle()
                        .fill(Theme.Accent.highlight.opacity(Theme.Tint.timelineSpan))
                        .frame(width: abs(cX - oX), height: 2)
                        .offset(x: min(oX, cX) + markSize / 2)
                }

                if let epoch = row.originalEpoch {
                    RoundedRectangle(cornerRadius: Theme.Radius.tick)
                        .fill(Theme.Text.primaryColor.opacity(Theme.Tint.tick))
                        .frame(width: 2, height: 10)
                        .offset(x: CGFloat(scale.fraction(for: epoch)) * usable + (markSize - 2) / 2)
                }

                if let epoch = row.correctedEpoch {
                    Circle()
                        .fill(Theme.Accent.highlight)
                        .frame(width: markSize, height: markSize)
                        .offset(x: CGFloat(scale.fraction(for: epoch)) * usable)
                }
            }
            .frame(maxHeight: .infinity)
        }
    }

    /// The switch has no default: a token added to `RowOutcome.Correction` without a
    /// badge text stops compiling, and one added to the schema alone fails
    /// `PipelineSchemaContractTests.testEveryTimestampActionTokenIsAKnownCorrection`.
    func changeBadgeText(_ row: DiffTableRow) -> String {
        switch row.outcome.correction {
        case .wouldFix, .fixed:
            if row.correctionMode == "time", let offset = row.timeOffsetDisplay {
                return offset
            }
            return row.outcome.correction == .wouldFix
                ? Strings.DiffTable.wouldFixChange : Strings.DiffTable.fixedChange
        case .wouldAdd: return Strings.DiffTable.wouldAddChange
        case .added: return Strings.DiffTable.addedChange
        case .noChange: return Strings.DiffTable.noChangeChange
        case .error: return row.timestampError ?? Strings.DiffTable.errorChange
        case nil: return "—"
        }
    }

    /// The metadata fields and file system times a correction would write, for the rows that would write any.
    private func staleFieldsText(_ row: DiffTableRow) -> String? {
        let written = row.staleFields + row.staleFileTimes
        return written.isEmpty ? nil : written.joined(separator: ", ")
    }

    /// Why a row says what it says: which field the correction read, which fields
    /// it would write, and — for a file the organize step left alone — the reason
    /// it gave. A row whose original and corrected times are the same string has
    /// nothing else to go on.
    private func rowExplanation(_ row: DiffTableRow) -> String {
        var parts: [String] = []
        if let label = row.timestampSource?.label {
            parts.append(Strings.DiffTable.sourceHelp(label))
        }
        if let fields = staleFieldsText(row) {
            parts.append(Strings.DiffTable.wouldWrite(fields))
        }
        if let reason = row.skipReason {
            parts.append(reason.explanation)
        }
        if let dest = row.dest {
            parts.append(dest)
        }
        return parts.joined(separator: "\n")
    }

    /// The destination a row would use, and — when the file was not moved there —
    /// the reason the pipeline gave, so the path is never read as a move. A row
    /// blocked by a different file at that path is flagged: those are the rows
    /// an apply would leave behind unless the user chooses to overwrite.
    @ViewBuilder
    private func destinationCell(_ row: DiffTableRow) -> some View {
        VStack(alignment: .leading, spacing: Theme.Space.hairline) {
            HStack(spacing: Theme.Space.xs) {
                if row.hasDestinationConflict {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(Theme.Typography.detail)
                        .foregroundStyle(Theme.Status.warning)
                }
                if let dest = row.dest {
                    Text((dest as NSString).lastPathComponent)
                        .font(Theme.Typography.fileMono)
                        .lineLimit(1)
                        .truncationMode(.middle)
                } else {
                    Text("—")
                        .font(Theme.Typography.fileMono)
                        .foregroundStyle(Theme.Text.tertiary)
                }
            }
            if let reason = row.skipReason {
                Text(reason.explanation)
                    .font(Theme.Typography.detail)
                    .foregroundStyle(Theme.Text.tertiary)
                    .lineLimit(1)
            }
        }
        .help(rowExplanation(row))
    }

    @ViewBuilder
    private func timestampCell(_ row: DiffTableRow) -> some View {
        VStack(alignment: .leading, spacing: Theme.Space.hairline) {
            changeBadge(row)
            if let fields = staleFieldsText(row) {
                Text(Strings.DiffTable.wouldWrite(fields))
                    .font(Theme.Typography.detail)
                    .foregroundStyle(Theme.Text.tertiary)
                    .lineLimit(1)
            }
        }
        .help(rowExplanation(row))
    }

    @ViewBuilder
    private func changeBadge(_ row: DiffTableRow) -> some View {
        let text = changeBadgeText(row)
        switch row.outcome.correction {
        case .wouldFix, .wouldAdd:
            HStack(spacing: Theme.Space.sm) {
                if row.requiresForceTimezone {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(Theme.Typography.detailIcon)
                        .foregroundStyle(Theme.Status.warning)
                        .help(Strings.DiffTable.requiresForceTimezoneHelp)
                }
                Text(text)
                    .font(Theme.Typography.file)
                    .foregroundStyle(Theme.Accent.highlight.opacity(Theme.Tint.dimmedHighlight))
            }
        case .fixed, .added:
            Text(text)
                .font(Theme.Typography.file)
                .foregroundStyle(Theme.Accent.highlight)
        case .noChange:
            Text(text)
                .font(Theme.Typography.file)
                .foregroundStyle(Theme.Text.secondary)
        case .error:
            Text(text)
                .font(Theme.Typography.file)
                .foregroundStyle(Theme.Status.failure)
                .help(row.timestampError ?? "")
        case nil:
            Text("—")
                .font(Theme.Typography.file)
                .foregroundStyle(Theme.Text.tertiary)
        }
    }
}

/// The column-width cache plus what only the pipeline's table needs: the timeline's
/// range, the extent of every row's epochs, folded as rows arrive.
final class RowMeasurements: ColumnMeasurements {
    private var epochRange: (lo: Double, hi: Double)?
    private var foldedEpochs: [DiffTableRow.ID: (Double?, Double?)] = [:]

    func timelineScale(for rows: [DiffTableRow]) -> DiffTableView.TimelineScale {
        if foldedEpochs.count > rows.count {
            // Rows were removed (a cleared table): rebuild the range from what remains.
            let remaining = Set(rows.map(\.id))
            foldedEpochs = foldedEpochs.filter { remaining.contains($0.key) }
            epochRange = nil
            for (_, epochs) in foldedEpochs {
                for epoch in [epochs.0, epochs.1].compactMap({ $0 }) { fold(epoch) }
            }
        }
        for row in rows where foldedEpochs[row.id]?.0 != row.originalEpoch || foldedEpochs[row.id]?.1 != row.correctedEpoch {
            fold(epochsOf: row)
        }
        return DiffTableView.TimelineScale(range: epochRange)
    }

    private func fold(epochsOf row: DiffTableRow) {
        foldedEpochs[row.id] = (row.originalEpoch, row.correctedEpoch)
        for epoch in [row.originalEpoch, row.correctedEpoch].compactMap({ $0 }) { fold(epoch) }
    }

    private func fold(_ epoch: Double) {
        if let range = epochRange {
            epochRange = (min(range.lo, epoch), max(range.hi, epoch))
        } else {
            epochRange = (epoch, epoch)
        }
    }
}
