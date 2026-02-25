import SwiftUI

struct DiffTableView: View {
    let rows: [DiffTableRow]

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 6) {
                Image(systemName: "tablecells")
                    .foregroundStyle(.secondary)
                Text("Files")
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(.secondary)
                Spacer()
                if !rows.isEmpty {
                    Text("\(rows.count) files")
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)

            Table(rows) {
                TableColumn("File") { row in
                    Text(row.file)
                        .font(.system(size: 11, design: .monospaced))
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
                .width(min: 80, ideal: 140)

                TableColumn("Original") { row in
                    Text(row.originalTime ?? "—")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(row.originalTime != nil ? .primary : .tertiary)
                }
                .width(min: 130, ideal: 175)

                TableColumn("Corrected") { row in
                    Text(row.correctedTime ?? "—")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(row.correctedTime != nil ? .primary : .tertiary)
                }
                .width(min: 130, ideal: 175)

                TableColumn("TZ") { row in
                    Text(row.timezone ?? "—")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(row.timezone != nil ? .primary : .tertiary)
                }
                .width(min: 50, ideal: 60)

                TableColumn("Destination") { row in
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

                TableColumn("Status") { row in
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
            Label("Changed", systemImage: "checkmark.circle.fill")
                .font(.system(size: 11))
                .foregroundStyle(Color("NeonCyan"))
        case "unchanged":
            Label("No change", systemImage: "minus.circle.fill")
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
        case "failed":
            Label("Failed", systemImage: "xmark.circle.fill")
                .font(.system(size: 11))
                .foregroundStyle(.red)
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
