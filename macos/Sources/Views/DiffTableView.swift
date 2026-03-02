import SwiftUI

struct DiffTableView: View {
    let rows: [DiffTableRow]

    private static let cellPadding: CGFloat = 20
    private static let iconWidth: CGFloat = 18

    private static let monoFont = NSFont.monospacedSystemFont(ofSize: 11, weight: .regular)
    private static let systemFont = NSFont.systemFont(ofSize: 11)

    private static let allBadgeStrings = [
        Strings.DiffTable.wouldFixChange,
        Strings.DiffTable.fixedChange,
        Strings.DiffTable.noChangeChange,
        Strings.DiffTable.tzMismatchStatus,
        Strings.DiffTable.errorChange,
    ]

    private static let allStatusStrings = [
        Strings.DiffTable.wouldChangeStatus,
        Strings.DiffTable.wouldFixStatus,
        Strings.DiffTable.wouldMoveStatus,
        Strings.DiffTable.changedStatus,
        Strings.DiffTable.noChangeStatus,
        Strings.DiffTable.fixedStatus,
        Strings.DiffTable.movedStatus,
        Strings.DiffTable.tzMismatchStatus,
        Strings.DiffTable.failedStatus,
    ]

    private static func textWidth(_ string: String, font: NSFont) -> CGFloat {
        let attributes: [NSAttributedString.Key: Any] = [.font: font]
        return (string as NSString).size(withAttributes: attributes).width
    }

    private static func longestByCharCount(_ strings: [String]) -> String? {
        strings.max(by: { $0.count < $1.count })
    }

    private var columnWidths: [CGFloat] {
        [fileIdeal, originalIdeal, correctedIdeal, timestampIdeal, destinationIdeal, statusIdeal]
    }

    private var fileIdeal: CGFloat {
        let headerWidth = Self.textWidth(Strings.DiffTable.fileColumn, font: Self.systemFont)
        guard let widest = Self.longestByCharCount(rows.map(\.file)) else {
            return headerWidth + Self.cellPadding
        }
        let contentWidth = Self.textWidth(widest, font: Self.monoFont)
        return max(headerWidth, contentWidth) + Self.cellPadding
    }

    private var originalIdeal: CGFloat {
        let headerWidth = Self.textWidth(Strings.DiffTable.originalColumn, font: Self.systemFont)
        guard let widest = Self.longestByCharCount(rows.compactMap(\.originalTime)) else {
            return headerWidth + Self.cellPadding
        }
        let contentWidth = Self.textWidth(widest, font: Self.monoFont)
        return max(headerWidth, contentWidth) + Self.cellPadding
    }

    private var correctedIdeal: CGFloat {
        let headerWidth = Self.textWidth(Strings.DiffTable.correctedColumn, font: Self.systemFont)
        guard let widest = Self.longestByCharCount(rows.compactMap(\.correctedTime)) else {
            return headerWidth + Self.cellPadding
        }
        let contentWidth = Self.textWidth(widest, font: Self.monoFont)
        return max(headerWidth, contentWidth) + Self.cellPadding
    }

    private var timestampIdeal: CGFloat {
        let headerWidth = Self.textWidth(Strings.DiffTable.timestampColumn, font: Self.systemFont)
        let contentWidth = Self.allBadgeStrings.map {
            Self.textWidth($0, font: Self.systemFont)
        }.max() ?? 0
        return max(headerWidth, contentWidth) + Self.cellPadding
    }

    private var destinationIdeal: CGFloat {
        let headerWidth = Self.textWidth(Strings.DiffTable.destinationColumn, font: Self.systemFont)
        let components = rows.compactMap(\.dest).map { ($0 as NSString).lastPathComponent }
        guard let widest = Self.longestByCharCount(components) else {
            return headerWidth + Self.cellPadding
        }
        let contentWidth = Self.textWidth(widest, font: Self.monoFont)
        return max(headerWidth, contentWidth) + Self.cellPadding
    }

    private var statusIdeal: CGFloat {
        let headerWidth = Self.textWidth(Strings.DiffTable.statusColumn, font: Self.systemFont)
        let contentWidth = Self.allStatusStrings.map {
            Self.textWidth($0, font: Self.systemFont)
        }.max() ?? 0
        return max(headerWidth, contentWidth) + Self.iconWidth + Self.cellPadding
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

            Table(rows) {
                TableColumn(Strings.DiffTable.fileColumn) { row in
                    Text(row.file)
                        .font(.system(size: 11, design: .monospaced))
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
                .width(min: 80, ideal: fileIdeal)

                TableColumn(Strings.DiffTable.originalColumn) { row in
                    Text(row.originalTime ?? "—")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(row.originalTime != nil ? .primary : .tertiary)
                }
                .width(min: 130, ideal: originalIdeal)

                TableColumn(Strings.DiffTable.correctedColumn) { row in
                    Text(row.correctedTime ?? "—")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(row.correctedTime != nil ? .primary : .tertiary)
                }
                .width(min: 130, ideal: correctedIdeal)

                TableColumn(Strings.DiffTable.timestampColumn) { row in
                    changeBadge(row)
                }
                .width(min: 70, ideal: timestampIdeal)

                TableColumn(Strings.DiffTable.destinationColumn) { row in
                    if let dest = row.dest {
                        Text((dest as NSString).lastPathComponent)
                            .font(.system(size: 11, design: .monospaced))
                            .lineLimit(1)
                            .truncationMode(.middle)
                            .help(dest)
                    } else {
                        Text("—")
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundStyle(.tertiary)
                    }
                }
                .width(min: 80, ideal: destinationIdeal)

                TableColumn(Strings.DiffTable.statusColumn) { row in
                    statusBadge(row)
                }
                .width(min: 80, ideal: statusIdeal)
            }
            .background {
                ColumnAutoSizer(columnWidths: columnWidths)
                    .frame(width: 0, height: 0)
            }
        }
        .frame(maxHeight: .infinity)
    }

    private func wouldChangeLabel(_ row: DiffTableRow) -> String {
        if row.timestampAction == "would_fix" && row.dest != nil {
            return Strings.DiffTable.wouldFixAndMoveStatus
        }
        if row.timestampAction == "would_fix" { return Strings.DiffTable.wouldFixStatus }
        if row.dest != nil { return Strings.DiffTable.wouldMoveStatus }
        return Strings.DiffTable.wouldChangeStatus
    }

    private func changedLabel(_ row: DiffTableRow) -> String {
        if row.timestampAction == "fixed" && row.dest != nil {
            return Strings.DiffTable.fixedAndMovedStatus
        }
        if row.timestampAction == "fixed" { return Strings.DiffTable.fixedStatus }
        if row.dest != nil { return Strings.DiffTable.movedStatus }
        return Strings.DiffTable.changedStatus
    }

    private func changeBadgeText(_ row: DiffTableRow) -> String {
        switch row.timestampAction {
        case "would_fix", "fixed":
            if row.correctionMode == "time", let offset = row.timeOffsetDisplay {
                return offset
            }
            return row.timestampAction == "would_fix"
                ? Strings.DiffTable.wouldFixChange : Strings.DiffTable.fixedChange
        case "no_change": return Strings.DiffTable.noChangeChange
        case "error": return row.timestampError ?? Strings.DiffTable.errorChange
        default: return "—"
        }
    }

    @ViewBuilder
    private func changeBadge(_ row: DiffTableRow) -> some View {
        let text = changeBadgeText(row)
        switch row.timestampAction {
        case "would_fix":
            Text(text)
                .font(.system(size: 11))
                .foregroundStyle(Color("NeonCyan").opacity(0.7))
        case "fixed":
            Text(text)
                .font(.system(size: 11))
                .foregroundStyle(Color("NeonCyan"))
        case "no_change":
            Text(text)
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
        case "error":
            Text(text)
                .font(.system(size: 11))
                .foregroundStyle(.red)
                .help(row.timestampError ?? "")
        default:
            Text("—")
                .font(.system(size: 11))
                .foregroundStyle(.tertiary)
        }
    }

    @ViewBuilder
    private func statusBadge(_ row: DiffTableRow) -> some View {
        switch row.pipelineResult {
        case "changed":
            Label(changedLabel(row), systemImage: "checkmark.circle.fill")
                .font(.system(size: 11))
                .foregroundStyle(Color("NeonCyan"))
        case "unchanged":
            Label(Strings.DiffTable.noChangeStatus, systemImage: "minus.circle.fill")
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
        case "failed":
            if row.timestampAction == "tz_mismatch" {
                Label(Strings.DiffTable.tzMismatchStatus, systemImage: "exclamationmark.triangle.fill")
                    .font(.system(size: 11))
                    .foregroundStyle(Color("NeonYellow"))
            } else {
                Label(Strings.DiffTable.failedStatus, systemImage: "xmark.circle.fill")
                    .font(.system(size: 11))
                    .foregroundStyle(.red)
            }
        case "would_change":
            Label(wouldChangeLabel(row), systemImage: "arrow.triangle.2.circlepath.circle.fill")
                .font(.system(size: 11))
                .foregroundStyle(Color("NeonCyan").opacity(0.7))
        case nil:
            HStack(spacing: 4) {
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

// MARK: - NSTableView introspection

private struct ColumnAutoSizer: NSViewRepresentable {
    let columnWidths: [CGFloat]

    final class Coordinator: NSObject {
        weak var tableView: NSTableView?
        var columnWidths: [CGFloat] = []
        weak var gesture: NSClickGestureRecognizer?

        @objc func headerDoubleClicked(_ gesture: NSClickGestureRecognizer) {
            guard let headerView = gesture.view as? NSTableHeaderView,
                  let tableView else { return }

            let location = gesture.location(in: headerView)
            var x: CGFloat = 0
            for i in 0..<tableView.numberOfColumns {
                x += tableView.tableColumns[i].width + tableView.intercellSpacing.width
                if abs(location.x - x) < 5, i < columnWidths.count {
                    tableView.tableColumns[i].width = columnWidths[i]
                    return
                }
            }
        }
    }

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeNSView(context: Context) -> TableFinderView {
        let view = TableFinderView()
        view.onTableFound = { tableView in
            context.coordinator.tableView = tableView
            applyWidths(context.coordinator)
            installDoubleClick(context.coordinator)
        }
        return view
    }

    func updateNSView(_ nsView: TableFinderView, context: Context) {
        context.coordinator.columnWidths = columnWidths
        if context.coordinator.tableView == nil {
            nsView.retryFindTable()
        }
        applyWidths(context.coordinator)
    }

    private func applyWidths(_ coordinator: Coordinator) {
        guard let tableView = coordinator.tableView else { return }
        for (i, width) in columnWidths.enumerated()
            where i < tableView.tableColumns.count {
            tableView.tableColumns[i].width = width
        }
    }

    private func installDoubleClick(_ coordinator: Coordinator) {
        guard let headerView = coordinator.tableView?.headerView,
              coordinator.gesture == nil else { return }

        let gesture = NSClickGestureRecognizer(
            target: coordinator,
            action: #selector(Coordinator.headerDoubleClicked(_:)))
        gesture.numberOfClicksRequired = 2
        headerView.addGestureRecognizer(gesture)
        coordinator.gesture = gesture
    }
}

private final class TableFinderView: NSView {
    var onTableFound: ((NSTableView) -> Void)?

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        guard window != nil else { return }
        retryFindTable()
    }

    func retryFindTable() {
        guard let tableView = findTableView() else { return }
        onTableFound?(tableView)
    }

    private func findTableView() -> NSTableView? {
        var current: NSView? = superview
        while let view = current {
            if let found = searchSubviews(of: view) {
                return found
            }
            current = view.superview
        }
        return nil
    }

    private func searchSubviews(of view: NSView) -> NSTableView? {
        if let scrollView = view as? NSScrollView,
           let tableView = scrollView.documentView as? NSTableView {
            return tableView
        }
        for subview in view.subviews {
            if let found = searchSubviews(of: subview) {
                return found
            }
        }
        return nil
    }
}
