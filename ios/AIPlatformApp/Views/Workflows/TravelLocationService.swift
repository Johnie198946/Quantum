import CoreLocation
import Foundation

@MainActor final class TravelLocationService: NSObject, CLLocationManagerDelegate {
    private let manager = CLLocationManager()
    private var continuation: CheckedContinuation<CLLocation, Error>?
    private var deadline: Task<Void, Never>?
    override init() { super.init(); manager.delegate = self; manager.desiredAccuracy = kCLLocationAccuracyBest }
    func coordinate() async throws -> CLLocation {
        guard continuation == nil else { throw APIError.network("正在读取定位") }
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { result in
                continuation = result
                deadline = Task { try? await Task.sleep(for: .seconds(20)); if !Task.isCancelled { finish(.failure(APIError.network("定位超时，请重试"))) } }
                switch manager.authorizationStatus {
                case .notDetermined: manager.requestWhenInUseAuthorization()
                case .authorizedAlways, .authorizedWhenInUse: manager.requestLocation()
                default: finish(.failure(APIError.network("请在系统设置中允许使用时定位")))
                }
            }
        } onCancel: { Task { @MainActor in self.cancel() } }
    }
    func cancel() { finish(.failure(CancellationError())) }
    private func finish(_ result: Result<CLLocation, Error>) {
        let pending = continuation; continuation = nil
        deadline?.cancel(); deadline = nil; manager.stopUpdatingLocation(); pending?.resume(with: result)
    }
    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        guard continuation != nil else { return }
        switch manager.authorizationStatus {
        case .authorizedAlways, .authorizedWhenInUse: manager.requestLocation()
        case .denied, .restricted: finish(.failure(APIError.network("定位权限未开启")))
        default: break
        }
    }
    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let value = locations.last, value.horizontalAccuracy >= 0, Date().timeIntervalSince(value.timestamp) < 30 else { return }
        finish(.success(value))
    }
    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) { finish(.failure(error)) }
}
