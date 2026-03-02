import SwiftUI

struct DiffTableView: View {
    let rows: [DiffTableRow]

    private static let cellPadding: CGFloat = 20
    private static let iconWidth: CGFloat = 18
    private static let monoFont = NSFont.monospacedSystemFont(ofSize: 11, weight: .regular)
    private static let systemFont = NSFont.systemFont(ofSize: 11)

    private static func idealWidth(
        for strings: [String],
        font: NSFont,
        extraWidth: CGFloat = 0
    ) -> CGFloat {
        guard let longest = strings.max(by: { $0.count < $1.count }) else {
            return 0
        }
        let attrs: [NSAttributedString.Key: Any] = [.font: font]
        let textWidth = (longest as NSString).size(withAttributes: attrs).width
        return textWidth + extraWidth + cellPadding
    }

    private func statusText(_ row: DiffTableRow) -> String {
        switch row.pipelineResult {
        case "changed": return changedLabel(row)
        case "unchanged": return Strings.DiffTable.noChangeStatus
        case "failed":
            return row.timestampAction == "tz_mismatch"
                ? Strings.DiffTable.tzMismatchStatus
                : Strings.DiffTable.failedStatus
        case "would_change": return wouldChangeLabel(row)
        case nil: return row.lastCompletedStageLabel ?? ""
        default: return row.pipelineResult ?? ""
        }
    }

    private var columnWidths: [CGFloat] {
        [
            Self.idealWidth(for: rows.map(\.file), font: Self.monoFont),
            Self.idealWidth(for: rows.compactMap(\.originalTime), font: Self.monoFont),
            Self.idealWidth(for: rows.compactMap(\.correctedTime), font: Self.monoFont),
            Self.idealWidth(for: rows.map { changeBadgeText($0) }, font: Self.systemFont),
            Self.idealWidth(
                for: rows.compactMap(\.dest).map { ($0 as NSString).lastPathComponent },
                font: Self.monoFont),
            Self.idealWidth(
                for: rows.map { statusText($0) },
                font: Self.systemFont,
                extraWidth: Self.iconWidth),
        ]
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
                .width(min: 80)

                TableColumn(Strings.DiffTable.originalColumn) { row in
                    Text(row.originalTime ?? "—")
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
                    changeBadge(row)
                }
                .width(min: 70)

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
                .width(min: 80)

                TableColumn(Strings.DiffTable.statusColumn) { row in
                    statusBadge(row)
                }
                .width(min: 80)
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

// MARK: - NSTableView introspection

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
            for (i, width) in columnWidths.enumerated()
                where i < tableView.tableColumns.count {
                tableView.tableColumns[i].width = width
            }

            if !coordinator.gestureInstalled, let headerView = tableView.headerView {
                let gesture = NSClickGestureRecognizer(
                    target: coordinator,
                    action: #selector(Coordinator.headerDoubleClicked(_:)))
                gesture.numberOfClicksRequired = 2
                headerView.addGestureRecognizer(gesture)
                coordinator.gestureInstalled = true
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
