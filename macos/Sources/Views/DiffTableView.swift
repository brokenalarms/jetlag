import SwiftUI

struct DiffTableView: View {
    let rows: [DiffTableRow]

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
                .width(min: 80, ideal: 140)

                TableColumn(Strings.DiffTable.originalColumn) { row in
                    Text(row.originalTime ?? "—")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(row.originalTime != nil ? .primary : .tertiary)
                }
                .width(min: 130, ideal: 175)

                TableColumn(Strings.DiffTable.correctedColumn) { row in
                    Text(row.correctedTime ?? "—")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(row.correctedTime != nil ? .primary : .tertiary)
                }
                .width(min: 130, ideal: 175)

                TableColumn(Strings.DiffTable.timestampColumn) { row in
                    changeBadge(row)
                }
                .width(min: 70, ideal: 90)

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
                .width(min: 80, ideal: 120)

                TableColumn(Strings.DiffTable.statusColumn) { row in
                    statusBadge(row)
                }
                .width(min: 80, ideal: 100)
            }
        }
        .frame(maxHeight: .infinity)
    }

    private func wouldChangeLabel(_ row: DiffTableRow) -> String {
        if row.timestampAction == "would_fix" { return Strings.DiffTable.wouldFixStatus }
        if row.dest != nil { return Strings.DiffTable.wouldMoveStatus }
        return Strings.DiffTable.wouldChangeStatus
    }

    private func changedLabel(_ row: DiffTableRow) -> String {
        if row.timestampAction == "fixed" { return Strings.DiffTable.fixedStatus }
        if row.dest != nil { return Strings.DiffTable.movedStatus }
        return Strings.DiffTable.changedStatus
    }

    @ViewBuilder
    private func changeBadge(_ row: DiffTableRow) -> some View {
        switch row.timestampAction {
        case "would_fix":
            Text(Strings.DiffTable.wouldFixChange)
                .font(.system(size: 11))
                .foregroundStyle(Color("NeonCyan").opacity(0.7))
        case "fixed":
            Text(Strings.DiffTable.fixedChange)
                .font(.system(size: 11))
                .foregroundStyle(Color("NeonCyan"))
        case "no_change":
            Text(Strings.DiffTable.noChangeChange)
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
        case "tz_mismatch":
            Text(Strings.DiffTable.tzMismatchStatus)
                .font(.system(size: 11))
                .foregroundStyle(Color("NeonYellow"))
        case "error":
            Text(Strings.DiffTable.errorChange)
                .font(.system(size: 11))
                .foregroundStyle(.red)
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
