import SwiftUI
import Quartz

struct DiffTableView: View {
    let rows: [DiffTableRow]
    let sourceDir: String

    @State private var selection: Set<DiffTableRow.ID> = []
    @State private var previewCoordinator = QuickLookCoordinator()
    @State private var measurements = RowMeasurements()

    private static let cellPadding: CGFloat = 20
    private static let iconWidth: CGFloat = 18
    private static let timelineColumnWidth: CGFloat = 120
    private static let monoFont = NSFont.monospacedSystemFont(ofSize: 11, weight: .regular)
    private static let systemFont = NSFont.systemFont(ofSize: 11)

    static func idealWidth(of cell: CellText) -> CGFloat {
        if let fixed = cell.fixedWidth { return fixed }
        let attrs: [NSAttributedString.Key: Any] = [.font: cell.font]
        let widest = cell.strings
            .filter { !$0.isEmpty }
            .map { ($0 as NSString).size(withAttributes: attrs).width }
            .max() ?? 0
        return widest == 0 ? 0 : widest + cell.extraWidth + cellPadding
    }

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

    /// The scale is a function of every row's epochs, so it is computed once per
    /// change to the rows rather than once per rendered cell.
    private var timelineScale: TimelineScale {
        measurements.timelineScale(for: rows)
    }

    /// The row's status: what the pipeline said it did, composed from the emitted
    /// action tokens. `dest` never contributes — a skipped file carries one too.
    private func statusText(_ row: DiffTableRow) -> String {
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

    /// One width per table column, in the order the columns are declared: a
    /// mismatch here resizes the wrong column. Measured incrementally: a row's cells
    /// are measured when they first appear and again only when their text changes
    /// (a live row fills in as its events arrive), and the widths are folded into a
    /// running maximum instead of every row being re-measured per update.
    private var columnWidths: [CGFloat] {
        measurements.columnWidths(for: rows, texts: cellTexts)
    }

    /// What each of a row's cells would draw, in column order: the text, its font
    /// and any icon allowance. Building this is string work only; measuring it is
    /// what the cache avoids repeating for rows that have not changed.
    private func cellTexts(_ row: DiffTableRow) -> [CellText] {
        [
            CellText(row.file, font: Self.monoFont),
            CellText(nil, font: Self.monoFont, fixedWidth: Self.timelineColumnWidth),
            CellText(row.originalTimeDisplay, font: Self.monoFont),
            CellText(row.correctedTime, font: Self.monoFont),
            CellText([changeBadgeText(row), row.timestampSource?.label ?? ""], font: Self.systemFont),
            CellText(
                [row.dest.map { ($0 as NSString).lastPathComponent } ?? "",
                 row.skipReason?.explanation ?? ""],
                font: row.skipReason == nil ? Self.monoFont : Self.systemFont,
                extraWidth: row.hasDestinationConflict ? Self.iconWidth : 0),
            CellText([statusText(row), staleFieldsText(row) ?? ""], font: Self.systemFont, extraWidth: Self.iconWidth),
        ]
    }

    /// The rows selected by the given ids, resolved to the file URLs Show in
    /// Finder / Quick Look can act on — a row whose file no longer exists at
    /// its known path (moved, archived) is left out rather than disabled
    /// one-by-one, so a mixed selection still acts on the files that remain.
    private func availableFileURLs(for ids: Set<DiffTableRow.ID>) -> [URL] {
        rows
            .filter { ids.contains($0.id) }
            .filter { RowFileLocation.exists(for: $0, sourceDir: sourceDir) }
            .compactMap { RowFileLocation.path(for: $0, sourceDir: sourceDir) }
            .map { URL(fileURLWithPath: $0) }
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 6) {
                Image(systemName: "tablecells")
                    .foregroundStyle(.secondary)
                Text(Strings.DiffTable.title)
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(.secondary)
                Spacer()
                if !rows.isEmpty {
                    Text(Strings.DiffTable.fileCount(rows.count))
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)

            Table(rows, selection: $selection) {
                TableColumn(Strings.DiffTable.fileColumn) { row in
                    Text(row.file)
                        .font(.system(size: 11, design: .monospaced))
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
                .width(min: 80)

                TableColumn(Strings.DiffTable.timelineColumn) { row in
                    timelineCell(row, scale: timelineScale)
                }
                .width(min: 50, ideal: 80)

                TableColumn(Strings.DiffTable.originalColumn) { row in
                    Text(row.originalTimeDisplay ?? "—")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(row.originalTime != nil ? .primary : .tertiary)
                }
                .width(min: 130)

                TableColumn(Strings.DiffTable.correctedColumn) { row in
                    Text(row.correctedTime ?? "—")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(row.correctedTime != nil ? .primary : .tertiary)
                }
                .width(min: 130)

                TableColumn(Strings.DiffTable.timestampColumn) { row in
                    timestampCell(row)
                }
                .width(min: 70)

                TableColumn(Strings.DiffTable.destinationColumn) { row in
                    destinationCell(row)
                }
                .width(min: 80)

                TableColumn(Strings.DiffTable.statusColumn) { row in
                    VStack(alignment: .leading, spacing: 1) {
                        statusBadge(row)
                        if let fields = staleFieldsText(row) {
                            Text(Strings.DiffTable.wouldWrite(fields))
                                .font(.system(size: 9))
                                .foregroundStyle(.tertiary)
                                .lineLimit(1)
                        }
                    }
                    .help(rowExplanation(row))
                }
                .width(min: 80)
            }
            .contextMenu(forSelectionType: DiffTableRow.ID.self) { ids in
                let urls = availableFileURLs(for: ids)
                Button(Strings.DiffTable.showInFinder) {
                    NSWorkspace.shared.activateFileViewerSelecting(urls)
                }
                .disabled(urls.isEmpty)

                Button(Strings.DiffTable.quickLook) {
                    previewCoordinator.show(urls)
                }
                .disabled(urls.isEmpty)
            }
            .onKeyPress(.space) {
                let urls = availableFileURLs(for: selection)
                guard !urls.isEmpty else { return .ignored }
                previewCoordinator.show(urls)
                return .handled
            }
            .background {
                ColumnAutoSizer(columnWidths: columnWidths)
                    .frame(width: 0, height: 0)
            }
        }
        .frame(maxHeight: .infinity)
    }

    @ViewBuilder
    private func timelineCell(_ row: DiffTableRow, scale: TimelineScale) -> some View {
        GeometryReader { geo in
            let markSize: CGFloat = 6
            let usable = geo.size.width - markSize
            ZStack(alignment: .leading) {
                Rectangle()
                    .fill(Color.primary.opacity(0.06))
                    .frame(height: 1)
                    .frame(maxWidth: .infinity)

                if let oEpoch = row.originalEpoch, let cEpoch = row.correctedEpoch,
                   oEpoch != cEpoch {
                    let oX = CGFloat(scale.fraction(for: oEpoch)) * usable
                    let cX = CGFloat(scale.fraction(for: cEpoch)) * usable
                    Rectangle()
                        .fill(Color("NeonCyan").opacity(0.15))
                        .frame(width: abs(cX - oX), height: 2)
                        .offset(x: min(oX, cX) + markSize / 2)
                }

                if let epoch = row.originalEpoch {
                    RoundedRectangle(cornerRadius: 0.5)
                        .fill(Color.primary.opacity(0.25))
                        .frame(width: 2, height: 10)
                        .offset(x: CGFloat(scale.fraction(for: epoch)) * usable + (markSize - 2) / 2)
                }

                if let epoch = row.correctedEpoch {
                    Circle()
                        .fill(Color("NeonCyan"))
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
        case .noChange: return Strings.DiffTable.noChangeChange
        case .error: return row.timestampError ?? Strings.DiffTable.errorChange
        case nil: return "—"
        }
    }

    /// The fields a correction would write, for the rows that would write any.
    private func staleFieldsText(_ row: DiffTableRow) -> String? {
        row.staleFields.isEmpty ? nil : row.staleFields.joined(separator: ", ")
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
        VStack(alignment: .leading, spacing: 1) {
            HStack(spacing: 3) {
                if row.hasDestinationConflict {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.system(size: 9))
                        .foregroundStyle(.orange)
                }
                if let dest = row.dest {
                    Text((dest as NSString).lastPathComponent)
                        .font(.system(size: 11, design: .monospaced))
                        .lineLimit(1)
                        .truncationMode(.middle)
                } else {
                    Text("—")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(.tertiary)
                }
            }
            if let reason = row.skipReason {
                Text(reason.explanation)
                    .font(.system(size: 9))
                    .foregroundStyle(.tertiary)
                    .lineLimit(1)
            }
        }
        .help(rowExplanation(row))
    }

    @ViewBuilder
    private func timestampCell(_ row: DiffTableRow) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            changeBadge(row)
            if let label = row.timestampSource?.label {
                Text(label)
                    .font(.system(size: 9))
                    .foregroundStyle(.tertiary)
                    .lineLimit(1)
            }
        }
        .help(rowExplanation(row))
    }

    @ViewBuilder
    private func changeBadge(_ row: DiffTableRow) -> some View {
        let text = changeBadgeText(row)
        switch row.outcome.correction {
        case .wouldFix:
            HStack(spacing: 4) {
                if row.requiresForceTimezone {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.system(size: 10))
                        .foregroundStyle(.orange)
                        .help(Strings.DiffTable.requiresForceTimezoneHelp)
                }
                Text(text)
                    .font(.system(size: 11))
                    .foregroundStyle(Color("NeonCyan").opacity(0.7))
            }
        case .fixed:
            Text(text)
                .font(.system(size: 11))
                .foregroundStyle(Color("NeonCyan"))
        case .noChange:
            Text(text)
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
        case .error:
            Text(text)
                .font(.system(size: 11))
                .foregroundStyle(.red)
                .help(row.timestampError ?? "")
        case nil:
            Text("—")
                .font(.system(size: 11))
                .foregroundStyle(.tertiary)
        }
    }

    @ViewBuilder
    private func statusBadge(_ row: DiffTableRow) -> some View {
        switch row.pipelineResult {
        case "changed":
            Label(statusText(row), systemImage: "checkmark.circle.fill")
                .font(.system(size: 11))
                .foregroundStyle(Color("NeonCyan"))
        case "unchanged":
            Label(Strings.DiffTable.noChangeStatus, systemImage: "minus.circle.fill")
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
        case "failed":
            Label(Strings.DiffTable.failedStatus, systemImage: "xmark.circle.fill")
                .font(.system(size: 11))
                .foregroundStyle(.red)
        case "would_change":
            Label(statusText(row), systemImage: "arrow.triangle.2.circlepath.circle.fill")
                .font(.system(size: 11))
                .foregroundStyle(Color("NeonCyan").opacity(0.7))
        case nil:
            HStack(spacing: 2) {
                ProgressView()
                    .controlSize(.small)
                if let stage = row.lastCompletedStageLabel {
                    Text(stage)
                        .font(.system(size: 10))
                        .foregroundStyle(.secondary)
                }
            }
        default:
            Text(row.pipelineResult ?? "")
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
        }
    }
}

// MARK: - Quick Look

/// Feeds the shared Quick Look panel the file(s) a context-menu or Space-key
/// action picked. No custom previewer: a format with no Quick Look generator
/// simply shows the panel's generic icon.
final class QuickLookCoordinator: NSObject, QLPreviewPanelDataSource {
    private var items: [URL] = []

    func show(_ urls: [URL]) {
        guard !urls.isEmpty, let panel = QLPreviewPanel.shared() else { return }
        items = urls
        panel.dataSource = self
        panel.reloadData()
        panel.makeKeyAndOrderFront(nil)
    }

    func numberOfPreviewItems(in panel: QLPreviewPanel!) -> Int {
        items.count
    }

    func previewPanel(_ panel: QLPreviewPanel!, previewItemAt index: Int) -> QLPreviewItem! {
        items[index] as NSURL
    }
}

// MARK: - NSTableView introspection

/// Assigning a column width invalidates the table's layout, and `updateNSView` fires
/// once per row appended during a streaming run. Writing a width that has not changed
/// would therefore keep the window's update-constraints pass alive for as long as rows
/// keep arriving, which AppKit eventually aborts as a constraint loop.
enum TableColumnSizing {
    /// Assigns each width only where it differs from what the column already resolves
    /// to. The comparison uses the width clamped to the column's own min/max, since
    /// that — not the requested value — is what the column will end up reporting.
    @discardableResult
    static func applyWidths(_ widths: [CGFloat], to tableView: NSTableView) -> [Int] {
        var resized: [Int] = []
        for (index, width) in widths.enumerated() where index < tableView.tableColumns.count {
            let column = tableView.tableColumns[index]
            let target = min(max(width, column.minWidth), column.maxWidth)
            guard column.width != target else { continue }
            column.width = target
            resized.append(index)
        }
        return resized
    }

    /// The table can be wider than the panel, so it needs a horizontal scroller.
    /// Which style that scroller takes is the user's system preference, not the
    /// app's: forcing the legacy style would override "Show scroll bars" for this one
    /// view. Each flag is compared before assignment because this runs on every
    /// update, and an unconditional write would re-invalidate the scroll view's
    /// layout every pass (jetlag-m9a).
    static func configureHorizontalScroller(for scrollView: NSScrollView) {
        if !scrollView.hasHorizontalScroller {
            scrollView.hasHorizontalScroller = true
        }
        if !scrollView.autohidesScrollers {
            scrollView.autohidesScrollers = true
        }
    }

    /// Overlay scrollers stay hidden until a scroll gesture, so a table that has just
    /// grown past its panel gives no sign that columns lie off to the right. AppKit's
    /// cue for exactly this is `flashScrollers()`, which reveals them briefly — what
    /// Finder does when a view's content changes. Called only when a width actually
    /// changed and the document now overflows, so idle updates never flash.
    static func revealOverflow(in scrollView: NSScrollView, afterResizing resized: [Int]) {
        guard !resized.isEmpty, let document = scrollView.documentView,
              document.frame.width > scrollView.contentView.bounds.width else { return }
        scrollView.flashScrollers()
    }
}


private struct ColumnAutoSizer: NSViewRepresentable {
    let columnWidths: [CGFloat]

    final class Coordinator: NSObject {
        weak var tableView: NSTableView?
        var columnWidths: [CGFloat] = []
        var gestureInstalled = false

        @objc func headerDoubleClicked(_ gesture: NSClickGestureRecognizer) {
            guard let headerView = gesture.view as? NSTableHeaderView,
                  let tableView else { return }

            let location = gesture.location(in: headerView)
            for i in 0..<tableView.numberOfColumns {
                let rightEdge = tableView.rect(ofColumn: i).maxX
                if abs(location.x - rightEdge) < 5, i < columnWidths.count {
                    tableView.tableColumns[i].width = columnWidths[i]
                    return
                }
            }
        }
    }

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeNSView(context: Context) -> NSView {
        NSView(frame: .zero)
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        let coordinator = context.coordinator
        coordinator.columnWidths = columnWidths

        if coordinator.tableView == nil || coordinator.tableView?.window == nil {
            coordinator.tableView = findTableView(from: nsView)
        }

        if let tableView = coordinator.tableView {
            let resized = TableColumnSizing.applyWidths(columnWidths, to: tableView)
            tableView.enclosingScrollView?.detachSizeFromContent()

            if !coordinator.gestureInstalled, let headerView = tableView.headerView {
                let gesture = NSClickGestureRecognizer(
                    target: coordinator,
                    action: #selector(Coordinator.headerDoubleClicked(_:)))
                gesture.numberOfClicksRequired = 2
                headerView.addGestureRecognizer(gesture)
                coordinator.gestureInstalled = true
            }

            if let scrollView = tableView.enclosingScrollView {
                TableColumnSizing.configureHorizontalScroller(for: scrollView)
                TableColumnSizing.revealOverflow(in: scrollView, afterResizing: resized)
            }
        }
    }

    private func findTableView(from view: NSView) -> NSTableView? {
        guard let contentView = view.window?.contentView else { return nil }
        return searchForTableView(in: contentView)
    }

    private func searchForTableView(in view: NSView) -> NSTableView? {
        if let tableView = view as? NSTableView {
            return tableView
        }
        for subview in view.subviews {
            if let found = searchForTableView(in: subview) {
                return found
            }
        }
        return nil
    }
}


// MARK: - Incremental measurement

/// The text a table cell would draw, with what its measurement depends on.
struct CellText: Equatable {
    let strings: [String]
    let font: NSFont
    let extraWidth: CGFloat
    let fixedWidth: CGFloat?

    init(_ string: String?, font: NSFont, extraWidth: CGFloat = 0, fixedWidth: CGFloat? = nil) {
        self.init([string ?? ""], font: font, extraWidth: extraWidth, fixedWidth: fixedWidth)
    }

    init(_ strings: [String], font: NSFont, extraWidth: CGFloat = 0, fixedWidth: CGFloat? = nil) {
        self.strings = strings
        self.font = font
        self.extraWidth = extraWidth
        self.fixedWidth = fixedWidth
    }
}

/// Per-run caches of the quantities that depend on every row. Text measurement is
/// the expensive part, so each row's cells are measured when the row first appears
/// and again only when their text changes — a run's live row fills in as its events
/// arrive and is then replaced by the finalised row at the same index — and the
/// column widths are the running maxima. Comparing a row's cell text to what was
/// measured is string work only. Without this each update re-measured every row,
/// and the app fell behind the pipeline on a few hundred files.
final class RowMeasurements {
    private struct Measured {
        let texts: [CellText]
        let widths: [CGFloat]
    }

    private var measured: [DiffTableRow.ID: Measured] = [:]
    private var widths: [CGFloat] = []
    private var epochRange: (lo: Double, hi: Double)?
    private var foldedEpochs: [DiffTableRow.ID: (Double?, Double?)] = [:]
    /// How many rows have had their text measured, for tests that pin the cache.
    private(set) var measurementCount = 0

    func columnWidths(for rows: [DiffTableRow], texts: (DiffTableRow) -> [CellText]) -> [CGFloat] {
        var seen = Set<DiffTableRow.ID>()
        for row in rows {
            seen.insert(row.id)
            let cells = texts(row)
            if let cached = measured[row.id], cached.texts == cells {
                continue
            }
            let cellWidths = cells.map(DiffTableView.idealWidth(of:))
            measurementCount += 1
            measured[row.id] = Measured(texts: cells, widths: cellWidths)
            if widths.count < cellWidths.count {
                widths.append(contentsOf: repeatElement(0, count: cellWidths.count - widths.count))
            }
            for (index, width) in cellWidths.enumerated() where width > widths[index] {
                widths[index] = width
            }
            fold(epochsOf: row)
        }
        if seen.count < measured.count {
            // Rows were removed (a cleared table): drop what is no longer shown and
            // rebuild the maxima from what remains.
            measured = measured.filter { seen.contains($0.key) }
            foldedEpochs = foldedEpochs.filter { seen.contains($0.key) }
            widths = measured.values.reduce(into: [CGFloat]()) { acc, entry in
                if acc.count < entry.widths.count {
                    acc.append(contentsOf: repeatElement(0, count: entry.widths.count - acc.count))
                }
                for (index, width) in entry.widths.enumerated() where width > acc[index] {
                    acc[index] = width
                }
            }
            epochRange = nil
            for (_, epochs) in foldedEpochs {
                for epoch in [epochs.0, epochs.1].compactMap({ $0 }) { fold(epoch) }
            }
        }
        return widths
    }

    func timelineScale(for rows: [DiffTableRow]) -> DiffTableView.TimelineScale {
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
