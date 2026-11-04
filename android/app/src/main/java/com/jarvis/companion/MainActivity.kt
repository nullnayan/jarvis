package com.jarvis.companion

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.net.Uri
import androidx.core.app.NotificationCompat
import android.content.Context
import android.os.Bundle
import android.provider.Settings
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.*
import androidx.core.content.ContextCompat
import com.jarvis.companion.automation.PhoneAutomator
import com.jarvis.companion.network.JarvisWebSocketClient
import com.jarvis.companion.theme.JarvisTheme
import com.jarvis.companion.ui.JarvisScreen
import com.jarvis.companion.ui.components.OrbState
import com.jarvis.companion.voice.VoiceManager

enum class InteractionMode {
    CHAT, TALK
}

class MainActivity : ComponentActivity() {

    private lateinit var webSocketClient: JarvisWebSocketClient
    private lateinit var phoneAutomator: PhoneAutomator
    private lateinit var voiceManager: VoiceManager

    private var isAwaitingCloudResponse by mutableStateOf(false)
    private var interactionMode by mutableStateOf(InteractionMode.TALK)
    private var urgentAlertData by mutableStateOf<com.jarvis.companion.ui.UrgentAlertData?>(null)

    private val screenOffReceiver = object : android.content.BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.action == Intent.ACTION_SCREEN_OFF) {
                if (::phoneAutomator.isInitialized) {
                    phoneAutomator.stopUrgentAlarm()
                }
            }
        }
    }

    private val urgentBroadcastReceiver = object : android.content.BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            val callerName = intent?.getStringExtra("caller_name") ?: "Unknown"
            val callerNumber = intent?.getStringExtra("caller_number") ?: ""
            val urgentMessage = intent?.getStringExtra("message") ?: "Emergency call"
            urgentAlertData = com.jarvis.companion.ui.UrgentAlertData(callerName, callerNumber, urgentMessage)
            if (::phoneAutomator.isInitialized) {
                phoneAutomator.playUrgentAlarm(15)
            }
            runOnUiThread {
                window.addFlags(
                    android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON or
                    android.view.WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON
                )
            }
        }
    }


    override fun onKeyDown(keyCode: Int, event: android.view.KeyEvent?): Boolean {
        if (keyCode == android.view.KeyEvent.KEYCODE_VOLUME_DOWN || keyCode == android.view.KeyEvent.KEYCODE_VOLUME_UP) {
            if (::phoneAutomator.isInitialized) {
                phoneAutomator.stopUrgentAlarm()
            }
        }
        return super.onKeyDown(keyCode, event)
    }

    private val requestPermissionsLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val audioGranted = permissions[Manifest.permission.RECORD_AUDIO] ?: false
        if (audioGranted) {
            interactionMode = InteractionMode.TALK
            voiceManager.startListening()
        }
    }

    private fun checkAndRequestPermissions() {
        val permissionsToRequest = mutableListOf<String>()
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            permissionsToRequest.add(Manifest.permission.RECORD_AUDIO)
        }
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.READ_PHONE_STATE) != PackageManager.PERMISSION_GRANTED) {
            permissionsToRequest.add(Manifest.permission.READ_PHONE_STATE)
        }
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ANSWER_PHONE_CALLS) != PackageManager.PERMISSION_GRANTED) {
            permissionsToRequest.add(Manifest.permission.ANSWER_PHONE_CALLS)
        }
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.READ_CALL_LOG) != PackageManager.PERMISSION_GRANTED) {
            permissionsToRequest.add(Manifest.permission.READ_CALL_LOG)
        }
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.READ_CONTACTS) != PackageManager.PERMISSION_GRANTED) {
            permissionsToRequest.add(Manifest.permission.READ_CONTACTS)
        }
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                permissionsToRequest.add(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
        if (permissionsToRequest.isNotEmpty()) {
            requestPermissionsLauncher.launch(permissionsToRequest.toTypedArray())
        }

        // Check DND access
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as? android.app.NotificationManager
        if (nm != null && !nm.isNotificationPolicyAccessGranted) {
            Toast.makeText(this, "Please grant Do Not Disturb access for Sleep Mode", Toast.LENGTH_LONG).show()
            try {
                val intent = Intent(Settings.ACTION_NOTIFICATION_POLICY_ACCESS_SETTINGS).apply {
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                startActivity(intent)
            } catch (e: Exception) {}
        }

        // Create notification channels
        createNotificationChannels()
    }

    private fun createNotificationChannels() {
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
            val nm = getSystemService(Context.NOTIFICATION_SERVICE) as android.app.NotificationManager

            // Channel for regular call notifications
            val callChannel = android.app.NotificationChannel(
                "jarvis_calls",
                "Jarvis Call Secretary",
                android.app.NotificationManager.IMPORTANCE_HIGH,
            ).apply {
                description = "Notifications when Jarvis handles an incoming call"
                enableLights(true)
                lightColor = android.graphics.Color.CYAN
                enableVibration(true)
            }
            nm.createNotificationChannel(callChannel)

            // Channel for urgent alerts (overrides DND)
            val urgentChannel = android.app.NotificationChannel(
                "jarvis_urgent",
                "Jarvis Urgent Alerts",
                android.app.NotificationManager.IMPORTANCE_MAX,
            ).apply {
                description = "Urgent caller alerts that override Do Not Disturb"
                enableLights(true)
                lightColor = android.graphics.Color.RED
                enableVibration(true)
                setBypassDnd(true)
            }
            nm.createNotificationChannel(urgentChannel)
        }
    }

    private fun getServerConfig(): Triple<String, String, String> {
        val prefs = getSharedPreferences("jarvis_config", Context.MODE_PRIVATE)
        val host = prefs.getString("server_host", null)?.takeIf { it.isNotBlank() } ?: "127.0.0.1"
        val port = prefs.getString("server_port", null)?.takeIf { it.isNotBlank() } ?: "8765"
        val token = prefs.getString("server_token", null)?.takeIf { it.isNotBlank() } ?: ""
        return Triple(host, port, token)
    }

    private fun buildWsUrl(host: String, port: String, token: String): String {
        val scheme = if (host == "127.0.0.1" || host == "localhost" || host == "::1") "ws" else "wss"
        val encodedToken = java.net.URLEncoder.encode(token, "UTF-8")
        return "$scheme://$host:$port/ws/phone?token=$encodedToken"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val channel = NotificationChannel("deal_alerts", "Deal Alerts", NotificationManager.IMPORTANCE_HIGH)
        channel.description = "Product deal notifications from Jarvis"
        notificationManager.createNotificationChannel(channel)


        checkAndRequestPermissions()

        phoneAutomator = PhoneAutomator(this)

        val (initHost, initPort, initToken) = getServerConfig()

        webSocketClient = JarvisWebSocketClient(
            serverUrl = buildWsUrl(initHost, initPort, initToken),
            onTaskReceived = { action, params ->
                phoneAutomator.execute(action, params)
            },
            onSpeechResponse = { responseText ->
                if (interactionMode == InteractionMode.TALK) {
                    voiceManager.speak(responseText)
                }
            },
            onResponseReceived = {
                isAwaitingCloudResponse = false
            },
            onDealAlertReceived = { productName, effectivePrice, platform, url, cardOffer, category ->
                android.util.Log.i("JarvisApp", "Triggering deal alert notification: $productName")

                val launchIntent = Intent(this, MainActivity::class.java)

                val pendingIntent = android.app.PendingIntent.getActivity(
                    this, 0, launchIntent,
                    android.app.PendingIntent.FLAG_IMMUTABLE or android.app.PendingIntent.FLAG_UPDATE_CURRENT
                )

                val icon = if (category.lowercase().contains("laptop")) "💻" else "📱"
                val builder = androidx.core.app.NotificationCompat.Builder(this, "deal_alerts")
                    .setSmallIcon(android.R.drawable.ic_dialog_info)
                    .setContentTitle("🔥 Deal Found!")
                    .setContentText("$icon $productName - Tap to view in Jarvis")
                    .setStyle(androidx.core.app.NotificationCompat.BigTextStyle()
                        .bigText("$icon $productName\nPrice: ₹$effectivePrice on ${platform.uppercase()}\n\nTap to view details in Jarvis"))
                    .setPriority(androidx.core.app.NotificationCompat.PRIORITY_MAX)
                    .setDefaults(androidx.core.app.NotificationCompat.DEFAULT_ALL)
                    .setContentIntent(pendingIntent)
                    .setAutoCancel(true)

                val nm = getSystemService(Context.NOTIFICATION_SERVICE) as android.app.NotificationManager
                nm.notify(productName.hashCode(), builder.build())
            },
            onDealStatusReceived = { statusMessage ->
                android.util.Log.i("JarvisApp", "Triggering deal status notification: $statusMessage")

                val launchIntent = Intent(this, MainActivity::class.java)

                val pendingIntent = android.app.PendingIntent.getActivity(
                    this, 1, launchIntent,
                    android.app.PendingIntent.FLAG_IMMUTABLE or android.app.PendingIntent.FLAG_UPDATE_CURRENT
                )

                val builder = androidx.core.app.NotificationCompat.Builder(this, "deal_alerts")
                    .setSmallIcon(android.R.drawable.ic_dialog_info)
                    .setContentTitle("🔍 Deal Hunter Update")
                    .setContentText(statusMessage)
                    .setStyle(androidx.core.app.NotificationCompat.BigTextStyle()
                        .bigText("$statusMessage\n\nTap to open Telegram Deals Bot"))
                    .setPriority(androidx.core.app.NotificationCompat.PRIORITY_HIGH)
                    .setDefaults(androidx.core.app.NotificationCompat.DEFAULT_ALL)
                    .setContentIntent(pendingIntent)
                    .setAutoCancel(true)

                val nm = getSystemService(Context.NOTIFICATION_SERVICE) as android.app.NotificationManager
                nm.notify(99999, builder.build())
            },
            onDealToggleState = { isOn ->
                val prefs = getSharedPreferences("deal_prefs", Context.MODE_PRIVATE)
                prefs.edit().putBoolean("deal_toggle", isOn).apply()
            },
            onConnected = {
                val prefs = getSharedPreferences("deal_prefs", Context.MODE_PRIVATE)
                val isOn = prefs.getBoolean("deal_toggle", false)
                android.util.Log.i("JarvisApp", "WS connected: syncing deal_toggle=$isOn to server")
                webSocketClient.sendDealSync(isOn)
            },
            onUrgentAlert = { callerName, callerNumber, urgentMessage ->
                urgentAlertData = com.jarvis.companion.ui.UrgentAlertData(callerName, callerNumber, urgentMessage)
                phoneAutomator.playUrgentAlarm(15)
                runOnUiThread {
                    window.addFlags(
                        android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON or
                        android.view.WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON
                    )
                }
            }
        )

        registerReceiver(
            screenOffReceiver,
            android.content.IntentFilter(Intent.ACTION_SCREEN_OFF)
        )

        val urgentFilter = android.content.IntentFilter("com.jarvis.companion.URGENT_ALERT")
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(urgentBroadcastReceiver, urgentFilter, Context.RECEIVER_EXPORTED)
        } else {
            registerReceiver(urgentBroadcastReceiver, urgentFilter)
        }


        voiceManager = VoiceManager(this) { spokenCommand ->
            interactionMode = InteractionMode.TALK
            isAwaitingCloudResponse = true
            webSocketClient.sendCommand(spokenCommand)
        }

        setContent {
            JarvisTheme {
            val dealPrefs = getSharedPreferences("deal_prefs", android.content.Context.MODE_PRIVATE)
            var isDealHunterOn by remember { mutableStateOf(dealPrefs.getBoolean("deal_toggle", false)) }

                val isConnected by webSocketClient.isConnected.collectAsState()
                val isPcOnline by webSocketClient.isPcOnline.collectAsState()
                val messages by webSocketClient.messages.collectAsState()
                val isListening by voiceManager.isListening.collectAsState()
                val isSpeaking by voiceManager.isSpeaking.collectAsState()
                val batteryLevel = remember { phoneAutomator.getBatteryLevel() }

                val orbState = when {
                    isListening -> OrbState.LISTENING
                    isAwaitingCloudResponse -> OrbState.THINKING
                    isSpeaking -> OrbState.SPEAKING
                    else -> OrbState.IDLE
                }

                LaunchedEffect(isAwaitingCloudResponse) {
                    if (isAwaitingCloudResponse) {
                        kotlinx.coroutines.delay(12000)
                        isAwaitingCloudResponse = false
                    }
                }

                var serverConfig by remember { mutableStateOf(getServerConfig()) }

                JarvisScreen(
                    isConnected = isConnected,
                    isPcOnline = isPcOnline,
                    orbState = orbState,
                    messages = messages,
                    batteryLevel = batteryLevel,
                    isSpeaking = isSpeaking,
                    interactionMode = interactionMode,
isDealHunterOn = isDealHunterOn,
                    dealPincodes = "",
                    onDealToggle = {
                        isDealHunterOn = it
                        dealPrefs.edit().putBoolean("deal_toggle", it).apply()
                        webSocketClient.sendDealToggle(it)
                    },
                    currentHost = serverConfig.first,
                    currentPort = serverConfig.second,
                    currentToken = serverConfig.third,
                    onUpdateServerConfig = { host, port, token ->
                        val prefs = getSharedPreferences("jarvis_config", Context.MODE_PRIVATE)
                        prefs.edit()
                            .putString("server_host", host.trim())
                            .putString("server_port", port.trim())
                            .putString("server_token", token.trim())
                            .apply()
                        serverConfig = Triple(host.trim(), port.trim(), token.trim())
                        webSocketClient.updateServerUrl(buildWsUrl(host.trim(), port.trim(), token.trim()))
                    },
                    onModeSelected = { mode ->
                        interactionMode = mode
                        if (mode == InteractionMode.CHAT && isSpeaking) {
                            voiceManager.stopSpeaking()
                        }
                    },
                    onSendCommand = { command ->
                        isAwaitingCloudResponse = true
                        webSocketClient.sendCommand(command)
                    },
                    onMicClicked = {
                        toggleVoiceInput()
                    },
                    onStopSpeaking = {
                        voiceManager.stopSpeaking()
                    }
                )

                urgentAlertData?.let { alert ->
                    com.jarvis.companion.ui.UrgentCallDialog(
                        alertData = alert,
                        onConnect = {
                            phoneAutomator.stopUrgentAlarm()
                            phoneAutomator.switchToPhoneEarpiece()
                            webSocketClient.sendUrgentDecision("connect")
                            urgentAlertData = null
                        },
                        onDecline = {
                            phoneAutomator.stopUrgentAlarm()
                            webSocketClient.sendUrgentDecision("decline")
                            urgentAlertData = null
                        },
                        onMuteAlarm = {
                            phoneAutomator.stopUrgentAlarm()
                        }
                    )
                }
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        try {
            unregisterReceiver(screenOffReceiver)
        } catch (e: Exception) {}
        try {
            unregisterReceiver(urgentBroadcastReceiver)
        } catch (e: Exception) {}
        phoneAutomator.stopUrgentAlarm()
        voiceManager.shutdown()
        webSocketClient.disconnect()
    }


    private fun toggleVoiceInput() {
        if (voiceManager.isListening.value) {
            voiceManager.stopListening()
        } else {
            interactionMode = InteractionMode.TALK
            val hasAudio = ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
            if (hasAudio) {
                voiceManager.startListening()
            } else {
                requestPermissionsLauncher.launch(
                    arrayOf(
                        Manifest.permission.RECORD_AUDIO,
                        Manifest.permission.READ_PHONE_STATE,
                        Manifest.permission.ANSWER_PHONE_CALLS
                    )
                )
            }
        }
    }

    override fun onStart() {
        super.onStart()
        webSocketClient.connect()
    }
}
