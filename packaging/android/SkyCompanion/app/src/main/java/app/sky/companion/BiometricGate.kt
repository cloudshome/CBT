package app.sky.companion

/**
 * When the app must show BiometricPrompt before a Hub mutation.
 * Viewer scope never mutates; operator writes re-check every time.
 */
object BiometricGate {
    val mutations = setOf(
        "approve_paper",
        "journal_write",
        "revoke_device",
        "paper_reject",
        "risk_override",
    )

    fun requiresPrompt(action: String, scope: String): Boolean =
        scope == "operator" && action in mutations
}
