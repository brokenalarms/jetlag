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

                TableColumn(Strings.DiffTable.tzColumn) { row in
                    Text(row.timezone ?? "—")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(row.timezone != nil ? .primary : .tertiary)
                }
                .width(min: 50, ideal: 60)

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
                .width(min: 60, ideal: 80)
            }
        }
        .frame(maxHeight: .infinity)
    }

    @ViewBuilder
    private func statusBadge(_ row: DiffTableRow) -> some View {
        switch row.pipelineResult {
        case "changed":
            Label(Strings.DiffTable.changedStatus, systemImage: "checkmark.circle.fill")
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
            Label(Strings.DiffTable.wouldChangeStatus, systemImage: "arrow.triangle.2.circlepath.circle.fill")
                .font(.system(size: 11))
                .foregroundStyle(Color("NeonCyan").opacity(0.7))
        case nil:
            ProgressView()
                .controlSize(.small)
        default:
            Text(row.pipelineResult ?? "")
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
        }
    }
}
