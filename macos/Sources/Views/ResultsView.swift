import SwiftUI

struct ResultsView: View {
    let accumulator: ProcessedFileAccumulator
    let isRunning: Bool

    var body: some View {
        VStack(spacing: 0) {
            Divider()
            summaryBar
            fileList
        }
        .frame(maxHeight: .infinity)
    }

    // MARK: - Summary bar

    private var summaryBar: some View {
        HStack(spacing: 16) {
            Image(systemName: "chart.bar.xaxis")
                .foregroundStyle(.secondary)
            Text("Results")
                .font(.subheadline.weight(.medium))
                .foregroundStyle(.secondary)

            Spacer()

            if !accumulator.files.isEmpty || isRunning {
                HStack(spacing: 12) {
                    summaryPill(
                        count: accumulator.summary.total,
                        label: "processed",
                        color: .secondary
                    )
                    if accumulator.summary.changed > 0 {
                        summaryPill(
                            count: accumulator.summary.changed,
                            label: "changed",
                            color: Color("NeonYellow")
                        )
                    }
                    if accumulator.summary.unchanged > 0 {
                        summaryPill(
                            count: accumulator.summary.unchanged,
                            label: "ok",
                            color: .green.opacity(0.7)
                        )
                    }
                    if accumulator.summary.failed > 0 {
                        summaryPill(
                            count: accumulator.summary.failed,
                            label: "failed",
                            color: .red
                        )
                    }
                }
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
    }

    private func summaryPill(count: Int, label: String, color: Color) -> some View {
        HStack(spacing: 4) {
            Text("\(count)")
                .font(.system(size: 12, weight: .bold, design: .monospaced))
                .foregroundStyle(color)
            Text(label)
                .font(.system(size: 10))
                .foregroundStyle(.secondary)
        }
    }

    // MARK: - File list

    private var fileList: some View {
        ScrollViewReader { proxy in
            ScrollView(.vertical) {
                if accumulator.files.isEmpty && !isRunning {
                    emptyState
                } else {
                    LazyVStack(spacing: 4) {
                        ForEach(accumulator.files) { file in
                            FileResultCard(file: file)
                                .id(file.id)
                        }

                        if isRunning {
                            HStack(spacing: 8) {
                                ProgressView()
                                    .controlSize(.small)
                                Text("Processing...")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 8)
                        }
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 6)
                }
            }
            .onChange(of: accumulator.files.count) {
                if let last = accumulator.files.last {
                    proxy.scrollTo(last.id, anchor: .bottom)
                }
            }
        }
        .background(Color(nsColor: .textBackgroundColor).opacity(0.5))
    }

    private var emptyState: some View {
        VStack(spacing: 8) {
            Spacer()
            Image(systemName: "tray")
                .font(.system(size: 28))
                .foregroundStyle(.quaternary)
            Text("Run the pipeline to see results")
                .font(.caption)
                .foregroundStyle(.tertiary)
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(.vertical, 40)
    }
}
