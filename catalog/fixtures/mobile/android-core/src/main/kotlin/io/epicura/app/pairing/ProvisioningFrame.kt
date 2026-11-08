package io.epicura.app.pairing

/**
 * BLE provisioning frame for the device's pairing characteristic:
 * `0x01, ssidLength, ssid bytes, passwordLength, password bytes`, strings UTF-8 encoded,
 * each length one byte.
 */
object ProvisioningFrame {
    const val OPCODE: Byte = 0x01
    const val MAX_FIELD_LENGTH = 63

    class FieldTooLong(val field: String) : IllegalArgumentException("$field exceeds $MAX_FIELD_LENGTH bytes")

    fun build(ssid: String, password: String): ByteArray {
        val ssidBytes = ssid.toByteArray(Charsets.UTF_8)
        val passwordBytes = password.toByteArray(Charsets.UTF_8)
        if (ssidBytes.size > MAX_FIELD_LENGTH) throw FieldTooLong("ssid")
        if (passwordBytes.size > MAX_FIELD_LENGTH) throw FieldTooLong("password")
        return byteArrayOf(OPCODE, ssid.length.toByte()) + ssidBytes +
            byteArrayOf(password.length.toByte()) + passwordBytes
    }
}
