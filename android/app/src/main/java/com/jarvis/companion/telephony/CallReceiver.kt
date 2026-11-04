package com.jarvis.companion.telephony

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.telephony.TelephonyManager
import android.util.Log

/**
 * CallReceiver — simplified for Twilio-based call handling.
 *
 * Since calls are forwarded to Twilio when call-handling mode is active,
 * this receiver only logs state changes for debugging.
 * All actual call handling (TTS, STT, recording, urgency) happens on the
 * Azure VM cloud server via the Twilio webhook.
 */
class CallReceiver : BroadcastReceiver() {

    private val tag = "CallReceiver"

    override fun onReceive(context: Context, intent: Intent) {
        val state = intent.getStringExtra(TelephonyManager.EXTRA_STATE) ?: return
        val incomingNumber = intent.getStringExtra(TelephonyManager.EXTRA_INCOMING_NUMBER) ?: ""

        Log.d(tag, "Call state changed: $state, number: $incomingNumber")

        when (state) {
            TelephonyManager.EXTRA_STATE_RINGING -> {
                if (com.jarvis.companion.automation.PhoneAutomator.isSleepModeActive(context)) {
                    Log.i(tag, "Jarvis Sleep Mode active. Answering incoming call from: $incomingNumber")
                    try {
                        val automator = com.jarvis.companion.automation.PhoneAutomator(context)
                        automator.answerCall()
                    } catch (e: Exception) {
                        Log.e(tag, "Failed to auto-answer call: ${e.message}")
                    }
                } else {
                    Log.d(tag, "Incoming call from: $incomingNumber (Sleep mode inactive)")
                }
            }
            TelephonyManager.EXTRA_STATE_OFFHOOK -> {
                Log.d(tag, "Call connected")
            }
            TelephonyManager.EXTRA_STATE_IDLE -> {
                Log.d(tag, "Call ended")
            }
        }
    }
}
