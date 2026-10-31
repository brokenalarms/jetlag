import SwiftUI

/// The three gyroflow settings as rows of an enclosing `OptionGroup`. Editing any of them
/// on a profile with no settings yet creates them.
struct GyroflowSettingsRows: View {
    @Binding var settings: StabilizationSettings?

    var body: some View {
        OptionRow(label: Strings.Gyroflow.maxZoomLabel, help: Strings.Gyroflow.maxZoomHelp) {
            TextField("", value: binding(\.maxZoom), format: .number)
                .textFieldStyle(.roundedBorder)
                .frame(width: Theme.Size.numberField)
        }
        OptionRow(label: Strings.Gyroflow.adaptiveZoomWindowLabel, help: Strings.Gyroflow.adaptiveZoomWindowHelp) {
            TextField("", value: binding(\.adaptiveZoomWindow), format: .number)
                .textFieldStyle(.roundedBorder)
                .frame(width: Theme.Size.numberField)
        }
        OptionRow(label: Strings.Gyroflow.adaptiveZoomMethodLabel, help: Strings.Gyroflow.adaptiveZoomMethodHelp) {
            Picker("", selection: methodBinding) {
                ForEach(AdaptiveZoomMethod.allCases) { method in
                    Text(method.label).tag(method)
                }
            }
            .labelsHidden()
            .pickerStyle(.segmented)
            .frame(width: Theme.Size.zoomMethodPicker)
        }
    }

    static func zoomMethod(of settings: StabilizationSettings?) -> AdaptiveZoomMethod {
        AdaptiveZoomMethod(rawValue: settings?.adaptiveZoomMethod ?? AdaptiveZoomMethod.dynamic.rawValue) ?? .dynamic
    }

    private func binding(_ keyPath: WritableKeyPath<StabilizationSettings, Double?>) -> Binding<Double?> {
        Binding(
            get: { settings?[keyPath: keyPath] },
            set: { newValue in
                var updated = settings ?? StabilizationSettings()
                updated[keyPath: keyPath] = newValue
                settings = updated
            }
        )
    }

    private var methodBinding: Binding<AdaptiveZoomMethod> {
        Binding(
            get: { Self.zoomMethod(of: settings) },
            set: { newValue in
                var updated = settings ?? StabilizationSettings()
                updated.adaptiveZoomMethod = newValue.rawValue
                settings = updated
            }
        )
    }
}
