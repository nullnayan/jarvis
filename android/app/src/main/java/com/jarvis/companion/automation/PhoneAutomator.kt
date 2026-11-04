package com.jarvis.companion.automation

import android.app.SearchManager
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import android.os.BatteryManager
import android.provider.MediaStore
import android.provider.Settings
import android.util.Log
import org.json.JSONObject

class PhoneAutomator(private val context: Context) {

    private val tag = "PhoneAutomator"

    private val appPackageMap = mapOf(
        "whatsapp" to "com.whatsapp",
        "youtube" to "com.google.android.youtube",
        "instagram" to "com.instagram.android",
        "spotify" to "com.spotify.music",
        "maps" to "com.google.android.apps.maps",
        "google maps" to "com.google.android.apps.maps",
        "chrome" to "com.android.chrome",
        "camera" to "camera_intent",
        "settings" to "settings_intent",
        "phone" to "dial_intent",
        "dialer" to "dial_intent",
        "telegram" to "org.telegram.messenger",
        "twitter" to "com.twitter.android",
        "x" to "com.twitter.android",
        "reddit" to "com.reddit.frontpage",
        "gmail" to "com.google.android.gm",
        "calculator" to "com.google.android.calculator"
    )

    companion object {
        fun isSleepModeActive(context: Context): Boolean {
            val prefs = context.getSharedPreferences("jarvis_config", Context.MODE_PRIVATE)
            return prefs.getBoolean("sleep_mode_active", false)
        }
    }

    fun execute(action: String, params: JSONObject): Boolean {
        Log.i(tag, "Executing action: $action with params: $params")
        return try {
            when (action.lowercase().trim()) {
                "launch_app", "open_app", "phone_open_app" -> {
                    val appName = params.optString("app_name", params.optString("app", params.optString("name", "")))
                    launchApp(appName)
                }
                "open_url", "browse" -> {
                    val url = params.optString("url", "")
                    openUrl(url)
                }
                "dial", "call", "phone_call" -> {
                    val phone = params.optString("phone", params.optString("number", params.optString("recipient", "")))
                    dialNumber(phone)
                }
                "search_web", "google" -> {
                    val query = params.optString("query", "")
                    searchWeb(query)
                }
                "open_settings" -> {
                    openSettings()
                }
                "phone_dnd", "phone_silence" -> {
                    val enabled = params.optBoolean("enabled", true)
                    setDndMode(enabled)
                }
                "sleep_mode_toggle" -> {
                    val enabled = params.optBoolean("enabled", true)
                    setSleepMode(enabled)
                }
                "call_answer" -> {
                    answerCall()
                }
                "call_decline" -> {
                    declineCall()
                }
                "enable_call_forwarding" -> {
                    val number = params.optString("twilio_number", "")
                    if (number.isNotBlank()) enableCallForwarding(number) else false
                }
                "disable_call_forwarding" -> {
                    disableCallForwarding()
                }
                else -> {
                    Log.w(tag, "Unknown action: $action")
                    false
                }
            }
        } catch (e: Exception) {
            Log.e(tag, "Failed to execute $action: ${e.message}", e)
            false
        }
    }

    fun launchApp(appName: String): Boolean {
        val cleanName = appName.trim().lowercase()
        if (cleanName.isEmpty()) return false

        if (cleanName == "camera" || cleanName == "camera_intent") {
            val intent = Intent(MediaStore.ACTION_IMAGE_CAPTURE).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK
            }
            context.startActivity(intent)
            return true
        }

        if (cleanName == "settings" || cleanName == "settings_intent") {
            return openSettings()
        }

        if (cleanName == "phone" || cleanName == "dialer") {
            return dialNumber("")
        }

        val targetPackage = appPackageMap[cleanName] ?: cleanName
        val pm = context.packageManager

        // 1. Try launching by direct package name
        var launchIntent = pm.getLaunchIntentForPackage(targetPackage)

        // 2. If not found, try searching installed packages
        if (launchIntent == null) {
            val installed = pm.getInstalledApplications(0)
            val matched = installed.firstOrNull {
                it.packageName.contains(cleanName, ignoreCase = true) ||
                pm.getApplicationLabel(it).toString().contains(cleanName, ignoreCase = true)
            }
            if (matched != null) {
                launchIntent = pm.getLaunchIntentForPackage(matched.packageName)
            }
        }

        return if (launchIntent != null) {
            launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(launchIntent)
            true
        } else {
            // 3. Fallback: Search the Play Store for the app
            try {
                val storeIntent = Intent(Intent.ACTION_VIEW, Uri.parse("market://search?q=$cleanName")).apply {
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                context.startActivity(storeIntent)
                true
            } catch (e: Exception) {
                Log.w(tag, "Could not find app or store: $cleanName")
                false
            }
        }
    }

    fun openUrl(rawUrl: String): Boolean {
        if (rawUrl.isBlank()) return false
        val formattedUrl = if (!rawUrl.startsWith("http://") && !rawUrl.startsWith("https://")) {
            "https://$rawUrl"
        } else rawUrl

        return try {
            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(formattedUrl)).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK
            }
            context.startActivity(intent)
            true
        } catch (e: Exception) {
            Log.e(tag, "Cannot open URL: $formattedUrl - ${e.message}")
            false
        }
    }

    fun dialNumber(number: String): Boolean {
        return try {
            val uri = if (number.isBlank()) Uri.parse("tel:") else Uri.parse("tel:$number")
            val intent = Intent(Intent.ACTION_DIAL, uri).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK
            }
            context.startActivity(intent)
            true
        } catch (e: Exception) {
            Log.e(tag, "Dialer error: ${e.message}")
            false
        }
    }

    fun searchWeb(query: String): Boolean {
        if (query.isBlank()) return false
        return try {
            val intent = Intent(Intent.ACTION_WEB_SEARCH).apply {
                putExtra(SearchManager.QUERY, query)
                flags = Intent.FLAG_ACTIVITY_NEW_TASK
            }
            context.startActivity(intent)
            true
        } catch (e: Exception) {
            openUrl("https://www.google.com/search?q=${Uri.encode(query)}")
        }
    }

    fun openSettings(): Boolean {
        return try {
            val intent = Intent(Settings.ACTION_SETTINGS).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK
            }
            context.startActivity(intent)
            true
        } catch (e: Exception) {
            Log.e(tag, "Error opening settings: ${e.message}")
            false
        }
    }

    fun getBatteryLevel(): Int {
        return try {
            val batteryStatus: Intent? = IntentFilter(Intent.ACTION_BATTERY_CHANGED).let { filter ->
                context.registerReceiver(null, filter)
            }
            val level = batteryStatus?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
            val scale = batteryStatus?.getIntExtra(BatteryManager.EXTRA_SCALE, -1) ?: -1
            if (level >= 0 && scale > 0) {
                ((level / scale.toFloat()) * 100).toInt()
            } else -1
        } catch (e: Exception) {
            -1
        }
    }

    fun isNetworkConnected(): Boolean {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager ?: return false
        val network = cm.activeNetwork ?: return false
        val caps = cm.getNetworkCapabilities(network) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }

    fun setSleepMode(enabled: Boolean): Boolean {
        val prefs = context.getSharedPreferences("jarvis_config", Context.MODE_PRIVATE)
        prefs.edit().putBoolean("sleep_mode_active", enabled).apply()
        Log.i(tag, "Jarvis sleep mode set and persisted to: $enabled")
        setDndMode(enabled)
        return true
    }

    fun setDndMode(enabled: Boolean): Boolean {
        return try {
            val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as? android.app.NotificationManager
            if (nm != null) {
                if (nm.isNotificationPolicyAccessGranted) {
                    nm.setInterruptionFilter(
                        if (enabled) android.app.NotificationManager.INTERRUPTION_FILTER_NONE
                        else android.app.NotificationManager.INTERRUPTION_FILTER_ALL
                    )
                    Log.i(tag, "Notification interruption filter set: DND=$enabled")
                    true
                } else {
                    val intent = Intent(Settings.ACTION_NOTIFICATION_POLICY_ACCESS_SETTINGS).apply {
                        flags = Intent.FLAG_ACTIVITY_NEW_TASK
                    }
                    context.startActivity(intent)
                    Log.w(tag, "Notification policy access not granted, prompted user")
                    false
                }
            } else false
        } catch (e: Exception) {
            Log.e(tag, "Error configuring DND mode: ${e.message}")
            false
        }
    }

    fun answerCall(): Boolean {
        return try {
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
                val tm = context.getSystemService(Context.TELECOM_SERVICE) as? android.telecom.TelecomManager
                tm?.acceptRingingCall()
                Log.i(tag, "Accepted ringing call via TelecomManager")
                true
            } else false
        } catch (e: Exception) {
            Log.e(tag, "Error answering incoming call: ${e.message}")
            false
        }
    }

    fun declineCall(): Boolean {
        return try {
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.P) {
                val tm = context.getSystemService(Context.TELECOM_SERVICE) as? android.telecom.TelecomManager
                tm?.endCall()
                Log.i(tag, "Ended call via TelecomManager")
                true
            } else false
        } catch (e: Exception) {
            Log.e(tag, "Error declining call: ${e.message}")
            false
        }
    }

    fun enableCallForwarding(twilioNumber: String): Boolean {
        return try {
            // Jio/Airtel/Vi/BSNL unconditional call forwarding: *21*<number>#
            val clean = twilioNumber.replace("+", "").replace(" ", "")
            val ussd = "*21*$clean%23"   // %23 = URL-encoded #
            val intent = Intent(Intent.ACTION_CALL, Uri.parse("tel:$ussd")).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK
            }
            context.startActivity(intent)
            // Persist state
            val prefs = context.getSharedPreferences("jarvis_config", Context.MODE_PRIVATE)
            prefs.edit().putBoolean("call_forwarding_active", true).putString("forwarding_number", twilioNumber).apply()
            Log.i(tag, "Call forwarding ENABLED → $twilioNumber")
            true
        } catch (e: Exception) {
            Log.e(tag, "Error enabling call forwarding: ${e.message}")
            false
        }
    }

    fun disableCallForwarding(): Boolean {
        return try {
            // Cancel all call forwarding: ##21#
            val ussd = "%23%2321%23"   // URL-encoded ##21#
            val intent = Intent(Intent.ACTION_CALL, Uri.parse("tel:$ussd")).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK
            }
            context.startActivity(intent)
            val prefs = context.getSharedPreferences("jarvis_config", Context.MODE_PRIVATE)
            prefs.edit().putBoolean("call_forwarding_active", false).remove("forwarding_number").apply()
            Log.i(tag, "Call forwarding DISABLED")
            true
        } catch (e: Exception) {
            Log.e(tag, "Error disabling call forwarding: ${e.message}")
            false
        }
    }

    fun isCallForwardingActive(): Boolean {
        val prefs = context.getSharedPreferences("jarvis_config", Context.MODE_PRIVATE)
        return prefs.getBoolean("call_forwarding_active", false)
    }

    fun getSavedContacts(): Map<String, String> {
        val contacts = mutableMapOf<String, String>()
        return try {
            val cursor = context.contentResolver.query(
                android.provider.ContactsContract.CommonDataKinds.Phone.CONTENT_URI,
                arrayOf(
                    android.provider.ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME,
                    android.provider.ContactsContract.CommonDataKinds.Phone.NUMBER,
                ),
                null, null, null
            )
            cursor?.use {
                val nameIdx = it.getColumnIndex(android.provider.ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME)
                val numIdx = it.getColumnIndex(android.provider.ContactsContract.CommonDataKinds.Phone.NUMBER)
                while (it.moveToNext()) {
                    val name = it.getString(nameIdx) ?: continue
                    val number = it.getString(numIdx)?.replace("[^+\\d]".toRegex(), "") ?: continue
                    if (number.isNotBlank()) contacts[number] = name
                }
            }
            Log.i(tag, "Loaded ${contacts.size} contacts from phone book")
            contacts
        } catch (e: Exception) {
            Log.e(tag, "Error reading contacts: ${e.message}")
            contacts
        }
    }

    private var alarmPlayer: android.media.MediaPlayer? = null

    private fun vibrateSosPattern(durationSeconds: Int) {
        try {
            val vibrator = if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
                val vm = context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as? android.os.VibratorManager
                vm?.defaultVibrator
            } else {
                @Suppress("DEPRECATION")
                context.getSystemService(Context.VIBRATOR_SERVICE) as? android.os.Vibrator
            }
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
                // SOS pattern: 200ms on, 200ms off, 500ms on, 200ms off
                val timings = longArrayOf(0, 200, 200, 200, 200, 500, 200, 500, 200)
                vibrator?.vibrate(android.os.VibrationEffect.createWaveform(timings, 0))
            } else {
                @Suppress("DEPRECATION")
                vibrator?.vibrate(longArrayOf(0, 300, 300), 0)
            }
        } catch (e: Exception) {
            Log.e(tag, "Vibration error: ${e.message}")
        }
    }

    private fun stopVibration() {
        try {
            val vibrator = if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
                val vm = context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as? android.os.VibratorManager
                vm?.defaultVibrator
            } else {
                @Suppress("DEPRECATION")
                context.getSystemService(Context.VIBRATOR_SERVICE) as? android.os.Vibrator
            }
            vibrator?.cancel()
        } catch (e: Exception) {}
    }

    fun playUrgentAlarm(durationSeconds: Int = 15) {
        try {
            stopUrgentAlarm()
            // 1. Remove DND / Silent
            setDndMode(false)
            val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as? android.media.AudioManager
            audioManager?.ringerMode = android.media.AudioManager.RINGER_MODE_NORMAL
            val maxVol = audioManager?.getStreamMaxVolume(android.media.AudioManager.STREAM_ALARM) ?: 7
            audioManager?.setStreamVolume(android.media.AudioManager.STREAM_ALARM, maxVol, 0)

            // 2. Play default alarm ringtone
            val alarmUri = android.media.RingtoneManager.getDefaultUri(android.media.RingtoneManager.TYPE_ALARM)
                ?: android.media.RingtoneManager.getDefaultUri(android.media.RingtoneManager.TYPE_RINGTONE)

            alarmPlayer = android.media.MediaPlayer().apply {
                setDataSource(context, alarmUri)
                setAudioAttributes(
                    android.media.AudioAttributes.Builder()
                        .setUsage(android.media.AudioAttributes.USAGE_ALARM)
                        .setContentType(android.media.AudioAttributes.CONTENT_TYPE_SONIFICATION)
                        .build()
                )
                isLooping = true
                prepare()
                start()
            }

            // 3. Vibrate
            vibrateSosPattern(durationSeconds)

            // 4. Auto-stop after durationSeconds
            android.os.Handler(android.os.Looper.getMainLooper()).postDelayed({
                stopUrgentAlarm()
            }, (durationSeconds * 1000).toLong())

            Log.i(tag, "Urgent alarm playing for ${durationSeconds}s")
        } catch (e: Exception) {
            Log.e(tag, "Error playing urgent alarm: ${e.message}")
        }
    }

    fun stopUrgentAlarm() {
        try {
            alarmPlayer?.let {
                if (it.isPlaying) it.stop()
                it.release()
            }
            alarmPlayer = null
            stopVibration()
            Log.i(tag, "Urgent alarm stopped")
        } catch (e: Exception) {
            Log.e(tag, "Error stopping alarm: ${e.message}")
        }
    }

    fun switchToPhoneEarpiece() {
        try {
            val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as? android.media.AudioManager
            audioManager?.let {
                it.mode = android.media.AudioManager.MODE_IN_CALL
                it.stopBluetoothSco()
                it.isBluetoothScoOn = false
                it.isSpeakerphoneOn = false
            }
            Log.i(tag, "Switched call audio to phone earpiece handset")
        } catch (e: Exception) {
            Log.e(tag, "Error switching to phone earpiece: ${e.message}")
        }
    }
}
