import AVFoundation
import PhotosUI
import SwiftUI
import UniformTypeIdentifiers
import UIKit

public struct NativeClientActionHost: View {
    public let action: ClientActionDTO
    public let onComplete: (String, [String: String]) -> Void

    public init(
        action: ClientActionDTO,
        onComplete: @escaping (String, [String: String]) -> Void
    ) {
        self.action = action
        self.onComplete = onComplete
    }

    public var body: some View {
        NativeClientActionRegistry.view(for: action, onComplete: onComplete)
            .interactiveDismissDisabled()
    }
}

private enum NativeClientActionRegistry {
    @ViewBuilder
    static func view(
        for action: ClientActionDTO,
        onComplete: @escaping (String, [String: String]) -> Void
    ) -> some View {
        switch action.actionType {
        case "file_picker":
            NativeFilePickerAction(action: action, onComplete: onComplete)
        case "photo_library":
            NativePhotoLibraryAction(action: action, onComplete: onComplete)
        case "camera_capture":
            NativeCameraAction(action: action, onComplete: onComplete)
        case "voice_recorder":
            NativeVoiceRecorderAction(action: action, onComplete: onComplete)
        case "share_sheet":
            NativeShareAction(action: action, onComplete: onComplete)
        case "file_upload":
            NativeFileUploadAction(action: action, onComplete: onComplete)
        case "file_download":
            NativeFileDownloadAction(action: action, onComplete: onComplete)
        case "voice_transcribe":
            NativeVoiceTranscriptionAction(action: action, onComplete: onComplete)
        default:
            UnsupportedNativeAction(action: action, onComplete: onComplete)
        }
    }
}

private struct ActionShell<Content: View>: View {
    let title: String
    let cancel: () -> Void
    @ViewBuilder let content: Content

    var body: some View {
        NavigationStack {
            content
                .navigationTitle(title)
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("取消", action: cancel)
                    }
                }
        }
    }
}

private struct NativeFilePickerAction: View {
    let action: ClientActionDTO
    let onComplete: (String, [String: String]) -> Void
    @State private var presented = false

    var body: some View {
        ActionShell(title: "选择文件", cancel: { onComplete("CANCELLED", [:]) }) {
            ProgressView("正在打开文件选择器…")
                .onAppear { presented = true }
                .fileImporter(
                    isPresented: $presented,
                    allowedContentTypes: [.item],
                    allowsMultipleSelection: action.payload.allowsMultiple ?? false
                ) { result in
                    switch result {
                    case .success(let urls):
                        onComplete("SUCCEEDED", [
                            "selection_count": String(urls.count),
                            "result_kind": "security_scoped_urls"
                        ])
                    case .failure(let error):
                        if (error as NSError).code == NSUserCancelledError {
                            onComplete("CANCELLED", [:])
                        } else {
                            onComplete("FAILED", ["error_code": "file_picker_failed"])
                        }
                    }
                }
        }
    }
}

private struct NativePhotoLibraryAction: View {
    let action: ClientActionDTO
    let onComplete: (String, [String: String]) -> Void
    @State private var presented = false
    @State private var items: [PhotosPickerItem] = []

    var body: some View {
        ActionShell(title: "选择照片", cancel: { onComplete("CANCELLED", [:]) }) {
            ProgressView("正在打开照片图库…")
                .onAppear { presented = true }
                .photosPicker(
                    isPresented: $presented,
                    selection: $items,
                    maxSelectionCount: action.payload.selectionLimit ?? 1,
                    matching: .images
                )
                .onChange(of: presented) { _, isPresented in
                    guard !isPresented else { return }
                    if items.isEmpty {
                        onComplete("CANCELLED", [:])
                    } else {
                        onComplete("SUCCEEDED", [
                            "selection_count": String(items.count),
                            "result_kind": "photos_picker_items"
                        ])
                    }
                }
        }
    }
}

private struct NativeCameraAction: View {
    let action: ClientActionDTO
    let onComplete: (String, [String: String]) -> Void

    var body: some View {
        CameraPicker(
            camera: action.payload.camera == "front" ? .front : .rear,
            completion: onComplete
        )
        .ignoresSafeArea()
    }
}

private struct CameraPicker: UIViewControllerRepresentable {
    let camera: UIImagePickerController.CameraDevice
    let completion: (String, [String: String]) -> Void

    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let completion: (String, [String: String]) -> Void
        init(completion: @escaping (String, [String: String]) -> Void) {
            self.completion = completion
        }
        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            completion("CANCELLED", [:])
        }
        func imagePickerController(
            _ picker: UIImagePickerController,
            didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]
        ) {
            guard info[.originalImage] is UIImage else {
                completion("FAILED", ["error_code": "camera_result_missing"])
                return
            }
            completion("SUCCEEDED", ["selection_count": "1", "result_kind": "captured_image"])
        }
    }

    func makeCoordinator() -> Coordinator { Coordinator(completion: completion) }
    func makeUIViewController(context: Context) -> UIImagePickerController {
        let controller = UIImagePickerController()
        controller.delegate = context.coordinator
        guard UIImagePickerController.isSourceTypeAvailable(.camera) else {
            DispatchQueue.main.async {
                completion("FAILED", ["error_code": "camera_unavailable"])
            }
            return controller
        }
        controller.sourceType = .camera
        controller.cameraDevice = camera
        return controller
    }
    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}
}

private struct NativeVoiceRecorderAction: View {
    let action: ClientActionDTO
    let onComplete: (String, [String: String]) -> Void
    @StateObject private var recorder = NativeVoiceRecorder()

    var body: some View {
        ActionShell(title: "录制语音", cancel: {
            recorder.cancel()
            onComplete("CANCELLED", [:])
        }) {
            VStack(spacing: 24) {
                Image(systemName: recorder.isRecording ? "waveform.circle.fill" : "mic.circle")
                    .font(.system(size: 72))
                Text(recorder.isRecording ? "正在录音" : "准备录音")
                Button(recorder.isRecording ? "完成录音" : "开始录音") {
                    if recorder.isRecording {
                        let duration = recorder.stop()
                        onComplete("SUCCEEDED", [
                            "duration_ms": String(Int(duration * 1000)),
                            "result_kind": "local_audio_file"
                        ])
                    } else {
                        recorder.start(maxSeconds: action.payload.maxSeconds ?? 600) { error in
                            if error != nil {
                                onComplete("FAILED", ["error_code": "microphone_unavailable"])
                            }
                        }
                    }
                }
                .buttonStyle(.borderedProminent)
            }
            .padding()
        }
    }
}

@MainActor
private final class NativeVoiceRecorder: NSObject, ObservableObject, AVAudioRecorderDelegate {
    @Published var isRecording = false
    private var recorder: AVAudioRecorder?
    private var startedAt: Date?

    func start(maxSeconds: Int, completion: @escaping (Error?) -> Void) {
        AVAudioApplication.requestRecordPermission { allowed in
            Task { @MainActor in
                guard allowed else {
                    completion(NSError(domain: "microphone", code: 1))
                    return
                }
                do {
                    let url = FileManager.default.temporaryDirectory
                        .appendingPathComponent("client-action-\(UUID().uuidString).m4a")
                    let settings: [String: Any] = [
                        AVFormatIDKey: Int(kAudioFormatMPEG4AAC),
                        AVSampleRateKey: 44_100,
                        AVNumberOfChannelsKey: 1,
                        AVEncoderAudioQualityKey: AVAudioQuality.high.rawValue
                    ]
                    let recorder = try AVAudioRecorder(url: url, settings: settings)
                    recorder.delegate = self
                    recorder.record(forDuration: TimeInterval(maxSeconds))
                    self.recorder = recorder
                    self.startedAt = Date()
                    self.isRecording = true
                    completion(nil)
                } catch {
                    completion(error)
                }
            }
        }
    }

    func stop() -> TimeInterval {
        recorder?.stop()
        isRecording = false
        return Date().timeIntervalSince(startedAt ?? Date())
    }

    func recordedData() throws -> Data {
        guard let url = recorder?.url else {
            throw NSError(domain: "voice", code: 2)
        }
        return try Data(contentsOf: url, options: [.mappedIfSafe])
    }

    func cancel() {
        recorder?.stop()
        if let url = recorder?.url { try? FileManager.default.removeItem(at: url) }
        isRecording = false
    }
}

private struct NativeShareAction: View {
    let action: ClientActionDTO
    let onComplete: (String, [String: String]) -> Void

    var body: some View {
        ShareController(
            items: [action.payload.text ?? action.payload.artifactId ?? ""],
            completion: onComplete
        )
    }
}

private struct ShareController: UIViewControllerRepresentable {
    let items: [Any]
    let completion: (String, [String: String]) -> Void

    func makeUIViewController(context: Context) -> UIActivityViewController {
        let controller = UIActivityViewController(activityItems: items, applicationActivities: nil)
        controller.completionWithItemsHandler = { activity, completed, _, error in
            if let error {
                completion("FAILED", ["error_code": "share_failed", "detail": error.localizedDescription])
            } else if completed {
                completion("SUCCEEDED", ["activity_type": activity?.rawValue ?? "unknown"])
            } else {
                completion("CANCELLED", [:])
            }
        }
        return controller
    }
    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}

private struct NativeFileUploadAction: View {
    let action: ClientActionDTO
    let onComplete: (String, [String: String]) -> Void
    @State private var presented = false
    @State private var uploading = false

    var body: some View {
        ActionShell(title: "上传文件", cancel: { onComplete("CANCELLED", [:]) }) {
            ProgressView(uploading ? "正在上传…" : "正在打开文件选择器…")
                .onAppear { presented = true }
                .fileImporter(
                    isPresented: $presented,
                    allowedContentTypes: [.pdf, UTType(filenameExtension: "docx") ?? .data],
                    allowsMultipleSelection: false
                ) { result in
                    guard case .success(let urls) = result, let url = urls.first else {
                        if case .failure(let error) = result,
                           (error as NSError).code != NSUserCancelledError {
                            onComplete("FAILED", ["error_code": "file_picker_failed"])
                        } else {
                            onComplete("CANCELLED", [:])
                        }
                        return
                    }
                    uploading = true
                    Task {
                        let accessed = url.startAccessingSecurityScopedResource()
                        defer { if accessed { url.stopAccessingSecurityScopedResource() } }
                        do {
                            let data = try Data(contentsOf: url, options: [.mappedIfSafe])
                            let ext = url.pathExtension.lowercased()
                            let mime = ext == "pdf"
                                ? "application/pdf"
                                : "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                            let receipt = try await APIClient.shared.uploadDocument(
                                data: data, filename: url.lastPathComponent, contentType: mime
                            )
                            onComplete("SUCCEEDED", [
                                "source_id": receipt.sourceId,
                                "content_hash": receipt.contentHash,
                                "source_revision": String(receipt.sourceRevision)
                            ])
                        } catch {
                            onComplete("FAILED", ["error_code": "file_upload_failed"])
                        }
                    }
                }
        }
    }
}

private struct NativeFileDownloadAction: View {
    let action: ClientActionDTO
    let onComplete: (String, [String: String]) -> Void

    var body: some View {
        ActionShell(title: "下载文件", cancel: { onComplete("CANCELLED", [:]) }) {
            ProgressView("正在下载并校验…")
                .task {
                    guard let sourceId = action.payload.sourceId else {
                        onComplete("FAILED", ["error_code": "source_id_missing"])
                        return
                    }
                    do {
                        let receipt = try await APIClient.shared.fetchDocument(sourceId: sourceId)
                        let data = try await APIClient.shared.downloadAuthenticated(
                            path: "documents/\(sourceId)/download",
                            expectedHash: receipt.contentHash
                        )
                        let destination = FileManager.default.temporaryDirectory
                            .appendingPathComponent(receipt.filename)
                        try data.write(to: destination, options: [.atomic])
                        onComplete("SUCCEEDED", [
                            "source_id": sourceId,
                            "content_hash": receipt.contentHash,
                            "byte_size": String(data.count)
                        ])
                    } catch {
                        onComplete("FAILED", ["error_code": "file_download_failed"])
                    }
                }
        }
    }
}

private struct NativeVoiceTranscriptionAction: View {
    let action: ClientActionDTO
    let onComplete: (String, [String: String]) -> Void
    @StateObject private var recorder = NativeVoiceRecorder()
    @State private var transcribing = false

    var body: some View {
        ActionShell(title: "语音转写", cancel: {
            recorder.cancel()
            onComplete("CANCELLED", [:])
        }) {
            VStack(spacing: 24) {
                Image(systemName: recorder.isRecording ? "waveform.circle.fill" : "text.bubble")
                    .font(.system(size: 72))
                Text(transcribing ? "正在转写" : recorder.isRecording ? "正在录音" : "准备录音")
                Button(recorder.isRecording ? "完成并转写" : "开始录音") {
                    if recorder.isRecording {
                        _ = recorder.stop()
                        transcribing = true
                        Task {
                            do {
                                let response = try await APIClient.shared.transcribeVoice(
                                    data: recorder.recordedData(), contentType: "audio/m4a"
                                )
                                onComplete("SUCCEEDED", [
                                    "transcript": response.text,
                                    "language": response.language
                                ])
                            } catch {
                                onComplete("FAILED", ["error_code": "voice_transcription_failed"])
                            }
                        }
                    } else {
                        recorder.start(maxSeconds: action.payload.maxSeconds ?? 300) { error in
                            if error != nil {
                                onComplete("FAILED", ["error_code": "microphone_unavailable"])
                            }
                        }
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(transcribing)
            }
            .padding()
        }
    }
}

private struct UnsupportedNativeAction: View {
    let action: ClientActionDTO
    let onComplete: (String, [String: String]) -> Void

    var body: some View {
        ActionShell(title: "不支持的设备操作", cancel: {
            onComplete("FAILED", ["error_code": "unsupported_native_action"])
        }) {
            Text(action.actionType).padding()
        }
        .onAppear {
            onComplete("FAILED", ["error_code": "unsupported_native_action"])
        }
    }
}
