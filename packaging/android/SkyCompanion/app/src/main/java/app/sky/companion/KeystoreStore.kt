package app.sky.companion

/**
 * Device-token storage described for the Android Keystore.
 * The token never appears in logs or SharedPreferences plaintext.
 * This class is the in-app contract; hardware-backed wrap lives on device.
 */
class KeystoreStore(private val alias: String = "sky_hub_device_token") {
    data class Record(
        val hubUrl: String,
        val scope: String,
        val name: String,
        val tokenSha256: String,
        val liveExchangeExecution: Boolean = false,
    )

    fun aliasName(): String = alias

    fun refuseWorldReadableFallback(): Boolean = true
}
