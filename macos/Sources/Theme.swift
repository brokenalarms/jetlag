import AppKit
import SwiftUI

enum Theme {
    enum Accent {
        static let ingest = Color("NeonCyan")
        static let tag = Color("NeonPink")
        static let fixTimestamps = Color("NeonYellow")
        static let organize = Color.accentColor
        static let gyroflow = Color("NeonPurple")
        static let archiveSource = Color("NeonCyan")
        static let highlight = Color("NeonCyan")
    }

    enum Text {
        static let primary = HierarchicalShapeStyle.primary
        static let secondary = HierarchicalShapeStyle.secondary
        static let tertiary = HierarchicalShapeStyle.tertiary
        static let primaryColor = Color.primary
        static let secondaryColor = Color.secondary
        static let log = NSColor.labelColor
    }

    enum Status {
        static let success = Color.green
        static let warning = Color.orange
        static let failure = Color.red
    }

    enum Surface {
        static let bar = Material.bar
        static let background = BackgroundStyle.background
        static let clear = Color.clear
        static let separator = SeparatorShapeStyle.separator
        static let log = Color(nsColor: .textBackgroundColor).opacity(Tint.logBackground)
        static let logTextView = NSColor.clear
        static let shadow = Color.black.opacity(Tint.shadow)
    }

    enum Tint {
        static let rule = 0.12
        static let shadow = 0.08
        static let stripe = 0.06
        static let tick = 0.25
        static let headerAlwaysOn = 0.03
        static let header = 0.05
        static let borderAlwaysOn = 0.12
        static let border = 0.2
        static let borderInactive = 0.15
        static let chip = 0.15
        static let chipSeparator = 0.3
        static let selectedSegment = 0.12
        static let timelineSpan = 0.15
        static let dimmedHighlight = 0.7
        static let logBackground = 0.5
    }

    enum Radius {
        static let card = 8.0
        static let field = 6.0
        static let chip = 4.0
        static let tick = 0.5
    }

    enum Space {
        static let hairline = 1.0
        static let xxs = 2.0
        static let xs = 3.0
        static let sm = 4.0
        static let md = 6.0
        static let lg = 8.0
        static let xl = 10.0
        static let xxl = 12.0
        static let xxxl = 16.0
        static let section = 20.0
        static let page = 24.0
    }

    enum Size {
        static let form: CGFloat = 600
        static let helpPopover = 240.0
        static let headerIcon = 16.0
        static let optionLabel = 52.0
        static let numberField = 90.0
        static let shortNumberField = 70.0
        static let profileList = 200.0
        static let profileLabel = 110.0
        static let listIcon = 14.0
        static let iconButton = 24.0
        static let typePicker = 160.0
        static let zoomMethodPicker = 200.0
        static let gyroflowNumberField = 80.0
    }

    enum Stroke {
        static let hairline = 1.0
    }

    enum Shadow {
        static let radius = 2.0
        static let offsetY = 1.0
    }

    enum Typography {
        static let body = Font.body
        static let bodyMono = Font.system(.body, design: .monospaced)
        static let subheadline = Font.subheadline
        static let subheadlineMedium = Font.subheadline.weight(.medium)
        static let title = Font.title2.bold()
        static let largeTitle = Font.largeTitle
        static let caption = Font.caption
        static let captionMono = Font.system(.caption, design: .monospaced)
        static let hero = Font.system(size: 28)
        static let step = Font.system(size: 12)
        static let stepMedium = Font.system(size: 12, weight: .medium)
        static let file = Font.system(size: 11)
        static let fileMono = Font.system(size: 11, design: .monospaced)
        static let detailIcon = Font.system(size: 10)
        static let detail = Font.system(size: 9)
        static let chip = Font.system(size: 10, weight: .medium)
        static let chipIcon = Font.system(size: 9)
        static let chipSeparator = Font.system(size: 7, weight: .bold)
        static let badge = Font.system(size: 10, weight: .medium)

        static let nsFileMono = NSFont.monospacedSystemFont(ofSize: 11, weight: .regular)
        static let nsFile = NSFont.systemFont(ofSize: 11)
        static let nsDetail = NSFont.systemFont(ofSize: 9)
        static let nsLog = nsFileMono
    }
}
