import SwiftUI

struct FileProgressCardView: View {
    let row: DiffTableRow
    let enabledSteps: [PipelineStep]
    @State private var isExpanded = false

    private var isComplete: Bool {
        row.pipelineResult != nil
    }

    private var isFailed: Bool {
        row.pipelineResult == "failed"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            stageIndicators
                .padding(.horizontal, 10)
                .padding(.bottom, 8)
            if isExpanded {
                Divider()
                detailsSection
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .strokeBorder(borderColor.opacity(0.3), lineWidth: 1)
        )
    }

    // MARK: - Header

    private var header: some View {
        Button { isExpanded.toggle() } label: {
            HStack(spacing: 6) {
                resultIcon
                    .font(.system(size: 11))
                    .frame(width: 14)

                Text(row.file)
                    .font(.system(size: 12, weight: .medium, design: .monospaced))
                    .lineLimit(1)
                    .truncationMode(.middle)

                Spacer()

                Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                    .font(.system(size: 9))
                    .foregroundStyle(.tertiary)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(borderColor.opacity(0.06))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private var resultIcon: some View {
        switch row.pipelineResult {
        case "changed":
            Image(systemName: "checkmark.circle.fill")
                .foregroundStyle(Color("NeonCyan"))
        case "unchanged":
            Image(systemName: "minus.circle.fill")
                .foregroundStyle(.secondary)
        case "failed":
            if row.timestampAction == "tz_mismatch" {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(Color("NeonYellow"))
            } else {
                Image(systemName: "xmark.circle.fill")
                    .foregroundStyle(.red)
            }
        case "would_change":
            Image(systemName: "arrow.triangle.2.circlepath.circle.fill")
                .foregroundStyle(Color("NeonCyan").opacity(0.7))
        default:
            ProgressView()
                .controlSize(.mini)
        }
    }

    private var borderColor: Color {
        switch row.pipelineResult {
        case "changed": Color("NeonCyan")
        case "failed": row.timestampAction == "tz_mismatch" ? Color("NeonYellow") : .red
        case "would_change": Color("NeonCyan")
        default: .secondary
        }
    }

    // MARK: - Stage indicators

    private var stageIndicators: some View {
        HStack(spacing: 4) {
            ForEach(enabledSteps, id: \.id) { step in
                stageChip(step)
                if step != enabledSteps.last {
                    Image(systemName: "chevron.right")
                        .font(.system(size: 7))
                        .foregroundStyle(.quaternary)
                }
            }
            Spacer()
        }
    }

    @ViewBuilder
    private func stageChip(_ step: PipelineStep) -> some View {
        let stageKey = step.stageKey
        let isStageComplete = stageKey.map { row.completedStages.contains($0) } ?? false
        let isFailedStage = isFailed && !isStageComplete && isFirstIncompleteStep(step)

        let chipContent = HStack(spacing: 3) {
            Image(systemName: step.systemImage)
                .font(.system(size: 9))
            if isStageComplete {
                Image(systemName: "checkmark")
                    .font(.system(size: 8, weight: .bold))
            } else if isFailedStage {
                Image(systemName: "xmark")
                    .font(.system(size: 8, weight: .bold))
            }
        }
        .padding(.horizontal, 5)
        .padding(.vertical, 3)
        .background(
            RoundedRectangle(cornerRadius: 4)
                .fill(
                    isStageComplete ? step.iconColor.opacity(0.1)
                        : isFailedStage ? Color.red.opacity(0.1)
                        : .clear
                )
        )
        .help(step.label)

        if isStageComplete {
            chipContent.foregroundStyle(step.iconColor)
        } else if isFailedStage {
            chipContent.foregroundStyle(.red)
        } else {
            chipContent.foregroundStyle(.tertiary)
        }
    }

    private func isFirstIncompleteStep(_ step: PipelineStep) -> Bool {
        for s in enabledSteps {
            let key = s.stageKey
            let complete = key.map { row.completedStages.contains($0) } ?? true
            if !complete {
                return s == step
            }
        }
        return false
    }

    // MARK: - Expanded details

    private var detailsSection: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let tagAction = row.tagAction {
                detailRow(Strings.Pipeline.tagLabel, value: tagAction)
            }
            if let tagsAdded = row.tagsAdded {
                detailRow(Strings.Workflow.tagsLabel, value: tagsAdded)
            }
            if let original = row.originalTime {
                detailRow(Strings.DiffTable.originalColumn, value: original)
            }
            if let corrected = row.correctedTime {
                detailRow(Strings.DiffTable.correctedColumn, value: corrected)
            }
            if let tz = row.timezone {
                detailRow(Strings.DiffTable.tzColumn, value: tz)
            }
            if let dest = row.dest {
                detailRow(Strings.DiffTable.destinationColumn, value: (dest as NSString).lastPathComponent)
                    .help(dest)
            }
        }
        .padding(10)
    }

    private func detailRow(_ label: String, value: String) -> some View {
        HStack(alignment: .top, spacing: 6) {
            Text(label)
                .font(.system(size: 10))
                .foregroundStyle(.secondary)
                .frame(width: 65, alignment: .trailing)
            Text(value)
                .font(.system(size: 10, design: .monospaced))
                .lineLimit(1)
                .truncationMode(.middle)
                .textSelection(.enabled)
        }
    }
}

// MARK: - Progress cards container

struct FileProgressCardsView: View {
    let rows: [DiffTableRow]
    let enabledSteps: [PipelineStep]
    let isRunning: Bool

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 6) {
                Image(systemName: "square.stack.fill")
                    .foregroundStyle(.secondary)
                Text(Strings.ProgressCards.title)
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

            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 6) {
                        ForEach(rows) { row in
                            FileProgressCardView(
                                row: row,
                                enabledSteps: enabledSteps
                            )
                            .id(row.id)
                        }
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                }
                .onChange(of: rows.count) { _, _ in
                    if let lastID = rows.last?.id {
                        withAnimation(.easeOut(duration: 0.2)) {
                            proxy.scrollTo(lastID, anchor: .bottom)
                        }
                    }
                }
            }
        }
        .frame(maxHeight: .infinity)
    }
}
