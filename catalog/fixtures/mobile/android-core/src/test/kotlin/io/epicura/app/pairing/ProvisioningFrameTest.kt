package io.epicura.app.pairing

import org.junit.jupiter.api.Assertions.assertArrayEquals
import org.junit.jupiter.api.Assertions.assertThrows
import org.junit.jupiter.api.Test

class ProvisioningFrameTest {
    @Test
    fun asciiFrameLayout() {
        val frame = ProvisioningFrame.build("Home", "secret")
        val expected = byteArrayOf(0x01, 4) + "Home".toByteArray() + byteArrayOf(6) + "secret".toByteArray()
        assertArrayEquals(expected, frame)
    }

    @Test
    fun tooLongSsidIsRejected() {
        assertThrows(ProvisioningFrame.FieldTooLong::class.java) {
            ProvisioningFrame.build("a".repeat(64), "x")
        }
    }
}
