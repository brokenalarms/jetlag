import SwiftUI

struct CameraValue: View {
    let make: String?
    let model: String?

    var body: some View {
        if let camera = FileCamera(make: make, model: model) {
            Text(camera.name)
        } else {
            Text(Strings.Common.noCameraRecorded)
                .foregroundStyle(Theme.Text.secondary)
        }
    }
}
