import SwiftUI

struct LogOutputView: View {
    let lines: [LogLine]
    var onClear: () -> Void

    private var visibleLines: [LogLine] {
        lines.filter { !$0.isMachineReadable }
    }

    var body: some View {
        VStack(spacing: 0) {
            Divider()

            HStack(spacing: 6) {
                Image(systemName: "terminal")
                    .foregroundStyle(.secondary)
                Text("Output")
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(.secondary)
                Spacer()
                if !visibleLines.isEmpty {
                    Text("\(visibleLines.count) lines")
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                }
                Button("Clear") { onClear() }
                    .buttonStyle(.borderless)
                    .font(.caption)
                    .disabled(lines.isEmpty)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(.bar)

            Divider()

            ScrollViewReader { proxy in
                ScrollView(.vertical) {
                    LazyVStack(alignment: .leading, spacing: 0) {
                        ForEach(visibleLines) { line in
                            Text(line.text)
                                .font(.system(size: 11, design: .monospaced))
                                .foregroundStyle(colorFor(line))
                                .padding(.vertical, 1)
                                .padding(.horizontal, 10)
                                .textSelection(.enabled)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .id(line.id)
                        }
                    }
                    .padding(.vertical, 6)
                }
                .onChange(of: lines.count) {
                    if let last = visibleLines.last {
                        proxy.scrollTo(last.id, anchor: .bottom)
                    }
                }
            }
            .background(Color(nsColor: .textBackgroundColor).opacity(0.5))
        }
        .frame(maxHeight: .infinity)
    }

    private func colorFor(_ line: LogLine) -> Color {
        if line.isMachineReadable { return .blue }
        switch line.stream {
        case .stdout: return .primary
        case .stderr: return .secondary
        }
    }
}
