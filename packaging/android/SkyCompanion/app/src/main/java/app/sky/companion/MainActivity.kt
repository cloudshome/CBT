package app.sky.companion

import android.app.Activity
import android.os.Bundle
import android.widget.TextView

/**
 * Native shell. Pairing + allowlisted Hub WebView. Offline is read-only.
 * Deep links: sky://record/{signal|risk|paper|journal|dashboard}[/{id}]
 */
class MainActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val view = TextView(this)
        view.text = "SKY Android companion — Hub client only. live_exchange_execution=false"
        setContentView(view)
    }
}
