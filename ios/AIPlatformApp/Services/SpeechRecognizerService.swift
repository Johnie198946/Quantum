//
//  SpeechRecognizerService.swift
//  AIPlatformApp
//
//  语音状态机（idle → recording → processing → idle）+ SFSpeechRecognizer(zh-CN) 端侧识别。
//  语音能力不可用时保留输入，不生成模拟转写。
//

import Foundation
import Combine
import AVFoundation
import Speech

public enum VoiceState: Equatable {
    case idle
    case recording
    case processing
}

@MainActor
public final class SpeechRecognizerService: ObservableObject {
    @Published public var state: VoiceState = .idle
    @Published public var transcript: String = ""
    @Published public var audioLevels: [CGFloat] = []
    @Published public var elapsedSeconds: Int = 0
    @Published public var permissionDenied: Bool = false
    @Published public var isMockMode: Bool = false
    @Published public var mockHint: String? = nil

    private let audioEngine = AVAudioEngine()
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?
    private let speechRecognizer: SFSpeechRecognizer?

    private var silenceTimer: Timer?
        private var tickTimer: Timer?
    private var lastSpeechAt = Date()
    private let silenceThreshold: TimeInterval = 3.5
    private var shouldAutoStopOnSilence = true
    public private(set) var capturedAudioURL: URL?
    private var captureAudioRequested = false
    private var recordingFile: AVAudioFile?

    public init() {
        #if targetEnvironment(simulator)
        // 模拟器没有端侧识别能力，保持空转写并提示使用文字输入。
        self.speechRecognizer = nil
        self.isMockMode = true
        self.mockHint = "当前模拟器不支持语音识别，请使用文字输入。"
        #else
        let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "zh-CN"))
        self.speechRecognizer = recognizer
        self.isMockMode = (recognizer == nil) || !(recognizer?.isAvailable ?? false)
        if self.isMockMode {
            self.mockHint = "语音识别暂不可用，请使用文字输入。"
        }
        #endif
    }

    deinit {
        // 定时器均使用 [weak self]，deinit 时安全；录制结束/取消时由 stopTimers() 统一失效。
    }

    // MARK: - 对外入口

    public func toggle() {
        switch state {
        case .idle:
            Task { await start() }
        case .recording, .processing:
            stop()
        }
    }

    public func start(autoStopOnSilence: Bool = true, captureAudio: Bool = false) async {
        guard state == .idle else { return }
        shouldAutoStopOnSilence = autoStopOnSilence
        captureAudioRequested = captureAudio
        capturedAudioURL = nil
        if isMockMode {
            recordingUnavailable()
            return
        }
        // 真实设备：先申请权限
        let granted = await requestPermissions()
        if !granted {
            permissionDenied = true
            return
        }
        permissionDenied = false
        startRealRecording()
    }

    public func stop() {
        switch state {
        case .recording:
            finishRecording(cancelled: false)
        case .processing:
            break
        case .idle:
            break
        }
    }

    public func cancel() {
        if state == .recording {
            finishRecording(cancelled: true)
        } else {
            resetToIdle()
        }
    }

    // MARK: - 权限

    private func requestPermissions() async -> Bool {
        // 语音识别权限
        let speechGranted: Bool = await withCheckedContinuation { cont in
            SFSpeechRecognizer.requestAuthorization { status in
                cont.resume(returning: status == .authorized)
            }
        }
        guard speechGranted else { return false }

        // 麦克风权限
        let micGranted: Bool = await withCheckedContinuation { cont in
            #if os(iOS)
            AVAudioApplication.requestRecordPermission { granted in
                cont.resume(returning: granted)
            }
            #else
            cont.resume(returning: true)
            #endif
        }
        return micGranted
    }

    // MARK: - 真实识别

    private func startRealRecording() {
        guard let recognizer = speechRecognizer, recognizer.isAvailable else {
            isMockMode = true
            mockHint = "语音识别暂不可用，请使用文字输入。"
            recordingUnavailable()
            return
        }

        // Speech output owns a `.playback` session while reading. Stop it before changing
        // the shared session to an input-capable category for recognition.
        SpeechPlaybackController.shared.stop()
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.record, mode: .measurement, options: [])
            try session.setActive(true)
        } catch {
            isMockMode = true
            mockHint = "无法启动录音，请检查麦克风权限后重试。"
            recordingUnavailable()
            return
        }

        state = .recording
        transcript = ""
        elapsedSeconds = 0
        audioLevels = []
        lastSpeechAt = Date()

        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        recognitionRequest = request

        do {
            let inputNode = audioEngine.inputNode
            let format = inputNode.outputFormat(forBus: 0)
            if captureAudioRequested {
                let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".m4a")
                recordingFile = try AVAudioFile(forWriting: url, settings: [
                    AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: format.sampleRate,
                    AVNumberOfChannelsKey: format.channelCount, AVEncoderBitRateKey: 32000
                ], commonFormat: .pcmFormatFloat32, interleaved: false)
                capturedAudioURL = url
            }
            let capturedFile = recordingFile
            inputNode.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buffer, _ in
                guard let self else { return }
                request.append(buffer)
                try? capturedFile?.write(from: buffer)
                let level = Self.computeLevel(buffer: buffer)
                let speechDetected = level > 0.02
                DispatchQueue.main.async {
                    self.appendLevel(level)
                    if speechDetected {
                        self.lastSpeechAt = Date()
                    }
                }
            }

            audioEngine.prepare()
            try audioEngine.start()

            recognitionTask = recognizer.recognitionTask(with: request) { [weak self] result, error in
                guard let self else { return }
                DispatchQueue.main.async {
                    if let result {
                        self.transcript = result.bestTranscription.formattedString
                        self.lastSpeechAt = Date()
                    }
                    if error != nil || (result?.isFinal ?? false) {
                        self.finishRecording(cancelled: false)
                    }
                }
            }

            startTimers()
        } catch {
            isMockMode = true
            mockHint = "无法启动录音，请稍后重试或使用文字输入。"
            cleanupRecognition()
            recordingUnavailable()
        }
    }

    private static func computeLevel(buffer: AVAudioPCMBuffer) -> CGFloat {
        guard let channel = buffer.floatChannelData?[0] else { return 0 }
        let frames = Int(buffer.frameLength)
        guard frames > 0 else { return 0 }
        var rms: Float = 0
        for i in 0..<frames {
            let v = channel[i]
            rms += v * v
        }
        rms = sqrt(rms / Float(frames))
        return CGFloat(min(1, max(0, rms * 6)))
    }

    private func finishRecording(cancelled: Bool) {
        stopTimers()
        if !isMockMode {
            audioEngine.stop()
            audioEngine.inputNode.removeTap(onBus: 0)
            recognitionRequest?.endAudio()
            recognitionRequest = nil
        }

        if cancelled {
            recordingFile = nil
            if let capturedAudioURL { try? FileManager.default.removeItem(at: capturedAudioURL) }
            capturedAudioURL = nil
            recognitionTask?.cancel()
            recognitionTask = nil
            resetToIdle()
            return
        }

        state = .processing
        recognitionTask?.finish()
        recognitionTask = nil

        DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) { [weak self] in
            guard let self else { return }
            if !self.isMockMode {
                self.cleanupRecognition()
            }
            self.transcript = self.transcript.trimmingCharacters(in: .whitespacesAndNewlines)
            self.state = .idle
        }
    }

    private func cleanupRecognition() {
        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
        recognitionRequest = nil
        recognitionTask?.cancel()
        recognitionTask = nil
        recordingFile = nil
        try? AVAudioSession.sharedInstance().setActive(
            false,
            options: .notifyOthersOnDeactivation
        )
    }

    // MARK: - 不可用状态

    private func recordingUnavailable() {
        stopTimers()
        transcript = ""
        audioLevels = []
        elapsedSeconds = 0
        state = .idle
    }

    // MARK: - 计时 / 静音检测

    private func startTimers() {
        tickTimer?.invalidate()
        tickTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            guard let self else { return }
            DispatchQueue.main.async {
                self.elapsedSeconds += 1
                // 真实模式静音 3.5s 自动结束
                if self.shouldAutoStopOnSilence,
                   !self.isMockMode,
                   self.state == .recording,
                   Date().timeIntervalSince(self.lastSpeechAt) >= self.silenceThreshold {
                    self.finishRecording(cancelled: false)
                }
            }
        }
    }

    private func stopTimers() {
        silenceTimer?.invalidate()
        silenceTimer = nil
        tickTimer?.invalidate()
        tickTimer = nil
    }

    private func appendLevel(_ level: CGFloat) {
        audioLevels.append(level)
        if audioLevels.count > 60 {
            audioLevels.removeFirst(audioLevels.count - 60)
        }
    }

    private func resetToIdle() {
        stopTimers()
        cleanupRecognition()
        state = .idle
        transcript = ""
        audioLevels = []
        elapsedSeconds = 0
    }
}
