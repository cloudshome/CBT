package app.sky.companion

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.net.URI

/**
 * HTTPS Hub client. Pairing, loop-health and paper mutations only.
 * There is no order, withdraw, or signed-exchange method on this type.
 */
class HubClient(
    origin: String,
    private val token: String,
    private val http: OkHttpClient = OkHttpClient(),
) {
    val origin: String = validateOrigin(origin)

    fun read(path: String): Request =
        Request.Builder()
            .url(origin + path)
            .header("Authorization", "Bearer $token")
            .header("Accept", "application/json")
            .header("X-SKY-Client-Version", CLIENT_BUILD.toString())
            .get()
            .build()

    fun mutate(path: String, jsonBody: String, idempotencyKey: String): Request {
        require(idempotencyKey.length >= 8) { "idempotency key too short" }
        return Request.Builder()
            .url(origin + path)
            .header("Authorization", "Bearer $token")
            .header("X-SKY-Client-Version", CLIENT_BUILD.toString())
            .header("Idempotency-Key", idempotencyKey)
            .post(jsonBody.toRequestBody(JSON))
            .build()
    }

    companion object {
        const val CLIENT_BUILD = 1
        const val CLIENT_NAME = "sky-android"
        const val LIVE_EXCHANGE_EXECUTION = false
        private val JSON = "application/json; charset=utf-8".toMediaType()

        fun validateOrigin(url: String): String {
            require(url.isNotBlank()) { "hub URL is required" }
            var raw = url.trim().trimEnd('/')
            if (!raw.contains("://")) raw = "https://$raw"
            val uri = URI(raw)
            val host = (uri.host ?: "").lowercase()
            val loopback = host == "127.0.0.1" || host == "localhost" || host == "::1" || host.startsWith("127.")
            require(uri.scheme == "https" || (uri.scheme == "http" && loopback)) {
                "remote companions require HTTPS"
            }
            return "${uri.scheme}://${uri.authority}"
        }

        fun pairingBody(code: String, deviceName: String): String =
            """{"code":"$code","name":"$deviceName","client":"$CLIENT_NAME","client_build":$CLIENT_BUILD,"live_exchange_execution":$LIVE_EXCHANGE_EXECUTION}"""
    }
}
