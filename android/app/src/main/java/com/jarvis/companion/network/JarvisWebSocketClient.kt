package com.jarvis.companion.network

import android.util.Log
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import okhttp3.*
import org.json.JSONObject
import java.util.concurrent.TimeUnit

data class ChatMessage(
    val id: String = java.util.UUID.randomUUID().toString(),
    val sender: String, // "user" or "jarvis"
    val text: String,
    val timestamp: Long = System.currentTimeMillis()
)

class JarvisWebSocketClient(
    private var serverUrl: String,
    private val onTaskReceived: ((action: String, params: JSONObject) -> Unit)? = null,
    private val onSpeechResponse: ((text: String) -> Unit)? = null,
    private val onResponseReceived: (() -> Unit)? = null,
    private val onCallNotification: ((callerName: String, callerNumber: String, message: String, recordingUrl: String) -> Unit)? = null,
    private val onUrgentAlert: ((callerName: String, callerNumber: String, urgentMessage: String) -> Unit)? = null,
    private val onDealAlertReceived: ((productName: String, effectivePrice: Int, platform: String, url: String, cardOffer: String, category: String) -> Unit)? = null,
    private val onDealStatusReceived: ((message: String) -> Unit)? = null,
    private val onDealToggleState: ((isOn: Boolean) -> Unit)? = null,
    private val onCallLogReceived: ((calls: List<org.json.JSONObject>) -> Unit)? = null,
    private val onConnected: (() -> Unit)? = null,
) {
    fun updateServerUrl(newUrl: String) {
        if (serverUrl != newUrl) {
            serverUrl = newUrl
            disconnect()
            connect()
        }
    }
    private val client = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .pingInterval(15, TimeUnit.SECONDS)
        .build()

    private var webSocket: WebSocket? = null
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    private val _isConnected = MutableStateFlow(false)
    val isConnected: StateFlow<Boolean> = _isConnected.asStateFlow()

    private val _isPcOnline = MutableStateFlow(false)
    val isPcOnline: StateFlow<Boolean> = _isPcOnline.asStateFlow()

    private val _messages = MutableStateFlow<List<ChatMessage>>(emptyList())
    val messages: StateFlow<List<ChatMessage>> = _messages.asStateFlow()

    private var reconnectJob: Job? = null
    private var reconnectDelay = 2000L

    fun connect() {
        if (_isConnected.value) return
        val token = serverUrl.substringAfter("?", "").split("&")
            .firstOrNull { it.startsWith("token=") }?.substringAfter("=")
        if (token.isNullOrBlank()) {
            Log.w("JarvisWS", "Configure a server token before connecting")
            return
        }
        reconnectJob?.cancel()

        val request = Request.Builder().url(serverUrl).build()
        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(ws: WebSocket, response: Response) {
                Log.i("JarvisWS", "Connected to Cloud Jarvis Gateway")
                _isConnected.value = true
                reconnectDelay = 2000L
                onConnected?.invoke()
            }

            override fun onMessage(ws: WebSocket, text: String) {
                handleIncomingJson(text)
            }

            override fun onClosing(ws: WebSocket, code: Int, reason: String) {
                Log.w("JarvisWS", "Closing connection: $reason")
                _isConnected.value = false
            }

            override fun onClosed(ws: WebSocket, code: Int, reason: String) {
                _isConnected.value = false
                scheduleReconnect()
            }

            override fun onFailure(ws: WebSocket, t: Throwable, response: Response?) {
                Log.e("JarvisWS", "WebSocket failure: ${t.message}")
                _isConnected.value = false
                scheduleReconnect()
            }
        })
    }

    private fun handleIncomingJson(raw: String) {
        try {
            val json = JSONObject(raw)
            val type = json.optString("type")

            when (type) {
                "deal_alert" -> {
                    val alertId = json.optInt("alert_id", 0)
                    val productName = json.optString("product_name", "Deal Alert")
                    val effectivePrice = json.optInt("effective_price", 0)
                    val platform = json.optString("platform", "")
                    val url = json.optString("url", "")
                    val cardOffer = json.optString("card_offer", "")
                    val category = json.optString("category", "")
                    android.util.Log.i("JarvisWS", "Received deal_alert: $productName - Rs.$effectivePrice")
                    onDealAlertReceived?.invoke(productName, effectivePrice, platform, url, cardOffer, category)
                    if (alertId > 0) {
                        sendAckAlert(alertId)
                    }
                }
                "deal_status_alert" -> {
                    val alertId = json.optInt("alert_id", 0)
                    val message = json.optString("message", "No new deals found")
                    android.util.Log.i("JarvisWS", "Received deal_status_alert: $message")
                    onDealStatusReceived?.invoke(message)
                    if (alertId > 0) {
                        sendAckAlert(alertId)
                    }
                }
                "deal_toggle_state" -> {
                    val enabled = json.optBoolean("enabled", false)
                    onDealToggleState?.invoke(enabled)
                }

                "connected" -> {
                    _isPcOnline.value = json.optBoolean("pc_online", false)
                }
                "device_status" -> {
                    if (json.optString("device") == "pc") {
                        _isPcOnline.value = json.optString("status") == "online"
                    }
                }
                "execute_task" -> {
                    val action = json.optString("action")
                    val params = json.optJSONObject("params") ?: JSONObject()
                    onTaskReceived?.invoke(action, params)
                }
                "command_response" -> {
                    if (json.optString("cmd_type") == "phone_task") {
                        val action = json.optString("action")
                        val params = json.optJSONObject("params") ?: JSONObject()
                        if (action.isNotEmpty() && action != "none") {
                            onTaskReceived?.invoke(action, params)
                        }
                    }
                }
                "call_notification" -> {
                    val callerName = json.optString("caller_name", "Unknown")
                    val callerNumber = json.optString("caller_number", "")
                    val message = json.optString("message", "")
                    val recordingUrl = json.optString("recording_url", "")
                    onCallNotification?.invoke(callerName, callerNumber, message, recordingUrl)
                }
                "urgent_alert" -> {
                    val callerName = json.optString("caller_name", "Unknown")
                    val callerNumber = json.optString("caller_number", "")
                    val urgentMessage = json.optString("urgent_message", "")
                    onUrgentAlert?.invoke(callerName, callerNumber, urgentMessage)
                    // Also forward as task for DND/forwarding control
                    onTaskReceived?.invoke("phone_dnd", JSONObject().put("enabled", false))
                    onTaskReceived?.invoke("disable_call_forwarding", JSONObject())
                }
                "call_log_response" -> {
                    val callsArray = json.optJSONArray("calls")
                    val callsList = mutableListOf<JSONObject>()
                    if (callsArray != null) {
                        for (i in 0 until callsArray.length()) {
                            callsList.add(callsArray.optJSONObject(i) ?: JSONObject())
                        }
                    }
                    onCallLogReceived?.invoke(callsList)
                }
            }

            // Catch-all response handler: handles "command_response", "chat", "pc_task", "phone_task",
            // or ANY incoming JSON payload containing a "response" field from Cloud Jarvis.
            if (json.has("response") || type == "command_response") {
                onResponseReceived?.invoke()
                val speech = json.optString("response")
                val spokenOnPc = json.optBoolean("spoken_on_pc", false)
                if (speech.isNotEmpty()) {
                    addMessage("jarvis", speech)
                    if (!spokenOnPc) {
                        onSpeechResponse?.invoke(speech)
                    }
                }
            }
        } catch (e: Exception) {
            Log.e("JarvisWS", "JSON parse error: ${e.message}")
        }
    }

    fun sendCommand(text: String) {
        val trimmed = text.trim()
        if (trimmed.isEmpty()) return

        addMessage("user", trimmed)

        val payload = JSONObject().apply {
            put("type", "command")
            put("text", trimmed)
        }

        val sent = webSocket?.send(payload.toString()) ?: false
        if (!sent) {
            addMessage("jarvis", "Cloud is temporarily offline, boss. Reconnecting...")
        }
    }

    private fun addMessage(sender: String, text: String) {
        val msg = ChatMessage(sender = sender, text = text)
        _messages.value = _messages.value + msg
    }

    private fun scheduleReconnect() {
        reconnectJob?.cancel()
        reconnectJob = scope.launch {
            delay(reconnectDelay)
            Log.i("JarvisWS", "Attempting reconnect in ${reconnectDelay}ms...")
            reconnectDelay = (reconnectDelay * 1.5).toLong().coerceAtMost(30000L)
            connect()
        }
    }

    fun syncContactWhitelist(contacts: Map<String, String>) {
        if (contacts.isEmpty()) return
        val contactsJson = org.json.JSONObject()
        contacts.forEach { (number, name) -> contactsJson.put(number, name) }
        val payload = JSONObject().apply {
            put("type", "contacts_sync")
            put("contacts", contactsJson)
        }
        val sent = webSocket?.send(payload.toString()) ?: false
        if (sent) Log.i("JarvisWS", "Contact whitelist synced: ${contacts.size} contacts")
        else Log.w("JarvisWS", "Failed to sync contacts — WebSocket not connected")
    }

    fun requestCallLog() {
        val payload = JSONObject().apply { put("type", "call_log_request") }
        webSocket?.send(payload.toString())
    }

    fun sendUrgentDecision(decision: String) {
        val payload = JSONObject().apply {
            put("type", "urgent_decision")
            put("decision", decision)
        }
        val sent = webSocket?.send(payload.toString()) ?: false
        Log.i("JarvisWS", "Sent urgent decision: $decision (success=$sent)")
    }

    fun disconnect() {
        reconnectJob?.cancel()
        webSocket?.close(1000, "App closed")
        _isConnected.value = false
    }

    fun sendDealToggle(enabled: Boolean) {
        val payload = JSONObject().apply {
            put("type", "deal_toggle")
            put("enabled", enabled)
        }
        webSocket?.send(payload.toString())
    }

    fun sendDealSync(enabled: Boolean) {
        val payload = JSONObject().apply {
            put("type", "deal_sync")
            put("enabled", enabled)
        }
        webSocket?.send(payload.toString())
    }

    fun sendAckAlert(alertId: Int) {
        val payload = JSONObject().apply {
            put("type", "ack_alert")
            put("alert_id", alertId)
        }
        webSocket?.send(payload.toString())
    }

    fun sendDealPincodes(pincodes: List<String>) {
        val payload = JSONObject().apply {
            put("type", "deal_set_pincodes")
            put("pincodes", org.json.JSONArray(pincodes))
        }
        webSocket?.send(payload.toString())
    }
}
