import Foundation

/// Builds the BLE provisioning frame the device's pairing characteristic expects:
/// `0x01, ssidLength, ssid bytes, passwordLength, password bytes`, strings UTF-8 encoded,
/// each length a single byte.
public enum WiFiProvisioning {
    public static let opcode: UInt8 = 0x01
    public static let maxFieldLength = 63

    public enum Error: Swift.Error, Equatable {
        case fieldTooLong(String)
    }

    public static func frame(ssid: String, password: String) throws -> Data {
        guard ssid.utf8.count <= maxFieldLength else { throw Error.fieldTooLong("ssid") }
        guard password.utf8.count <= maxFieldLength else { throw Error.fieldTooLong("password") }
        var data = Data([opcode])
        data.append(UInt8(ssid.utf8.count))
        data.append(contentsOf: Array(ssid.utf8))
        data.append(UInt8(password.count))
        data.append(contentsOf: Array(password.utf8))
        return data
    }
}
