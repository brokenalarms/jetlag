import SwiftUI

struct LogOutputView: View {
    let lines: [LogLine]
    var onClear: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 6) {
                Image(systemName: "terminal")
                    .foregroundStyle(.secondary)
                Text(Strings.LogOutput.title)
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(.secondary)
                Spacer()
                if !lines.isEmpty {
                    Text(Strings.LogOutput.lineCount(lines.count))
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                }
                Button {
                    let text = lines.map(\.text).joined(separator: "\n")
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(text, forType: .string)
                } label: {
                    Label(
                        Strings.LogOutput.copyAllButton,
                        systemImage: "doc.on.doc"
                    )
                }
                .buttonStyle(.borderless)
                .font(.caption)
                .disabled(lines.isEmpty)

                Button(Strings.LogOutput.clearButton) { onClear() }
                    .buttonStyle(.borderless)
                    .font(.caption)
                    .disabled(lines.isEmpty)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)

            LogTextView(lines: lines)
                .background(Color(nsColor: .textBackgroundColor).opacity(0.5))
        }
        .frame(maxHeight: .infinity)
    }
}

// MARK: - NSTextView wrapper for better performance and text selection

struct LogTextView: NSViewRepresentable {
    let lines: [LogLine]

    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = NSTextView.scrollableTextView()
        let textView = scrollView.documentView as! NSTextView

        textView.isEditable = false
        textView.isSelectable = true
        textView.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        textView.textColor = .labelColor
        textView.backgroundColor = .clear
        textView.textContainerInset = NSSize(width: 10, height: 6)
        textView.autoresizingMask = [.width]

        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let textView = scrollView.documentView as? NSTextView else {
            return
        }

        let newText = lines.map(\.text).joined(separator: "\n")

        // Only update if text has changed
        if textView.string != newText {
            let wasAtBottom = isScrolledToBottom(scrollView)

            textView.string = newText

            // Auto-scroll to bottom if we were already at the bottom
            if wasAtBottom {
                textView.scrollToEndOfDocument(nil)
            }
        }
    }

    private func isScrolledToBottom(_ scrollView: NSScrollView) -> Bool {
        guard let textView = scrollView.documentView as? NSTextView else {
            return false
        }
        let visibleRect = scrollView.contentView.documentVisibleRect
        let contentHeight = textView.bounds.height
        return visibleRect.maxY >= contentHeight - 10  // 10pt threshold
    }
}
