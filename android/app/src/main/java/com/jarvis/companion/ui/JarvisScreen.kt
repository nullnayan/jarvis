package com.jarvis.companion.ui

import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.jarvis.companion.InteractionMode
import com.jarvis.companion.network.ChatMessage
import com.jarvis.companion.theme.*
import com.jarvis.companion.ui.components.JarvisOrb
import com.jarvis.companion.ui.components.OrbState
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun JarvisScreen(
    isConnected: Boolean,
    isPcOnline: Boolean,
    orbState: OrbState,
    messages: List<ChatMessage>,
    batteryLevel: Int,
    isSpeaking: Boolean,
    interactionMode: InteractionMode,
    isDealHunterOn: Boolean = false,
    dealPincodes: String = "",
    onDealToggle: (Boolean) -> Unit = {},
    onDealPincodesUpdate: (String) -> Unit = {},
    currentHost: String = "",
    currentPort: String = "8765",
    currentToken: String = "",
    onUpdateServerConfig: ((String, String, String) -> Unit)? = null,
    onModeSelected: (InteractionMode) -> Unit,
    onSendCommand: (String) -> Unit,
    onMicClicked: () -> Unit,
    onStopSpeaking: () -> Unit
) {
    val coroutineScope = rememberCoroutineScope()
    val listState = rememberLazyListState()
    var inputText by remember { mutableStateOf("") }
    var showSettingsDialog by remember { mutableStateOf(false) }

    // Auto-scroll on new message
    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) {
            listState.animateScrollToItem(messages.size - 1)
        }
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(
                brush = Brush.verticalGradient(
                    colors = listOf(
                        VoidBlack,
                        Color(0xFF070F20),
                        VoidBlack
                    )
                )
            )
            .statusBarsPadding()
            .navigationBarsPadding()
            .imePadding()
    ) {
        Column(
            modifier = Modifier.fillMaxSize()
        ) {
            // 1. TOP HUD STATUS HEADER
            HudStatusHeader(
                isConnected = isConnected,
                isPcOnline = isPcOnline,
                batteryLevel = batteryLevel,
                onOpenSettings = { showSettingsDialog = true }
            )

            // 1B. INTERACTION MODE TOGGLE & PC LINK BADGE
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 2.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                InteractionModeToggle(
                    currentMode = interactionMode,
                    onModeSelected = onModeSelected
                )

                Column(horizontalAlignment = Alignment.End) {
                    if (!isPcOnline) {
                        Row(
                            modifier = Modifier
                                .clip(RoundedCornerShape(8.dp))
                                .background(Color(0x22EF4444))
                                .border(1.dp, NeonRed.copy(alpha = 0.4f), RoundedCornerShape(8.dp))
                                .padding(horizontal = 8.dp, vertical = 4.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Box(
                                modifier = Modifier
                                    .size(6.dp)
                                    .clip(CircleShape)
                                    .background(NeonRed)
                            )
                            Spacer(modifier = Modifier.width(5.dp))
                            Text(
                                text = "PC OFFLINE",
                                color = NeonRed,
                                fontSize = 9.sp,
                                fontFamily = FontFamily.Monospace,
                                fontWeight = FontWeight.Bold
                            )
                        }
                    } else {
                        Row(
                            modifier = Modifier
                                .clip(RoundedCornerShape(8.dp))
                                .background(Color(0x2200F0FF))
                                .border(1.dp, CyanCore.copy(alpha = 0.3f), RoundedCornerShape(8.dp))
                                .padding(horizontal = 8.dp, vertical = 4.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Box(
                                modifier = Modifier
                                    .size(6.dp)
                                    .clip(CircleShape)
                                    .background(CyanCore)
                            )
                            Spacer(modifier = Modifier.width(5.dp))
                            Text(
                                text = "PC LINKED",
                                color = CyanCore,
                                fontSize = 9.sp,
                                fontFamily = FontFamily.Monospace,
                                fontWeight = FontWeight.Bold
                            )
                        }
                    }

                    Spacer(modifier = Modifier.height(6.dp))

                    // Deal Hunter Small Toggle
                    Row(
                        modifier = Modifier
                            .clip(RoundedCornerShape(8.dp))
                            .background(if (isDealHunterOn) Color(0x2200F0FF) else Color(0x2264748B))
                            .border(1.dp, if (isDealHunterOn) CyanCore.copy(alpha = 0.5f) else Color(0xFF64748B).copy(alpha = 0.5f), RoundedCornerShape(8.dp))
                            .clickable { onDealToggle(!isDealHunterOn) }
                            .padding(horizontal = 8.dp, vertical = 4.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Box(
                            modifier = Modifier
                                .size(6.dp)
                                .clip(CircleShape)
                                .background(if (isDealHunterOn) CyanCore else Color(0xFF64748B))
                        )
                        Spacer(modifier = Modifier.width(5.dp))
                        Text(
                            text = "DEALHUNTER",
                            color = if (isDealHunterOn) CyanCore else Color(0xFF64748B),
                            fontSize = 9.sp,
                            fontFamily = FontFamily.Monospace,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }
            }

            // 2. CENTER ARC REACTOR ORB & TELEMETRY
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 8.dp),
                contentAlignment = Alignment.Center
            ) {
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    val orbSize = if (messages.isNotEmpty()) 125.dp else 175.dp
                    JarvisOrb(
                        state = orbState,
                        size = orbSize
                    )

                    Spacer(modifier = Modifier.height(6.dp))

                    // Orb State Hologram Label
                    OrbStatusBadge(orbState = orbState)

                    Spacer(modifier = Modifier.height(8.dp))

                    // Audio Waveform Equalizer (reacts during speaking / listening)
                    if (orbState == OrbState.LISTENING || orbState == OrbState.SPEAKING) {
                        AudioVisualizerBars(isActive = true)
                    }

                    // Quick Action Chips
                    QuickActionChipsRow(
                        onChipSelected = { command ->
                            onSendCommand(command)
                        }
                    )
                }
            }

            // 3. CHAT STREAM / HOLOGRAPHIC LOG
            LazyColumn(
                state = listState,
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                if (messages.isEmpty()) {
                    item {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(top = 28.dp),
                            contentAlignment = Alignment.Center
                        ) {
                            Text(
                                text = "// JARVIS READY FOR COMMANDS\nTap mic to speak or enter task below",
                                color = TextSecondary.copy(alpha = 0.6f),
                                fontSize = 12.sp,
                                fontFamily = FontFamily.Monospace,
                                textAlign = TextAlign.Center,
                                lineHeight = 18.sp
                            )
                        }
                    }
                }

                items(messages, key = { it.id }) { msg ->
                    ChatBubble(message = msg)
                }
            }




            // 4. BOTTOM COMMAND DOCK & PULSING MIC
            BottomCommandDock(
                inputText = inputText,
                onInputTextChanged = { inputText = it },
                onSend = {
                    if (inputText.isNotBlank()) {
                        onSendCommand(inputText)
                        inputText = ""
                    }
                },
                orbState = orbState,
                isSpeaking = isSpeaking,
                interactionMode = interactionMode,
                onMicClicked = onMicClicked,
                onStopSpeaking = onStopSpeaking
            )
        }

        if (showSettingsDialog) {
            ConnectionSettingsDialog(
                initialHost = currentHost,
                initialPort = currentPort,
                initialToken = currentToken,
                onDismiss = { showSettingsDialog = false },
                onSave = { host, port, token ->
                    showSettingsDialog = false
                    onUpdateServerConfig?.invoke(host, port, token)
                }
            )
        }
    }
}

// -------------------------------------------------------------
// COMPONENT 1: Top HUD Status Bar
// -------------------------------------------------------------
@Composable
fun HudStatusHeader(
    isConnected: Boolean,
    isPcOnline: Boolean,
    batteryLevel: Int,
    onOpenSettings: () -> Unit = {}
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 8.dp)
            .clip(RoundedCornerShape(16.dp))
            .background(GlassSurface)
            .border(1.dp, GlassBorder, RoundedCornerShape(16.dp))
            .padding(horizontal = 14.dp, vertical = 10.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        // Left: Jarvis Title & System Status
        Column {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = "JARVIS",
                    color = CyanCore,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Black,
                    fontFamily = FontFamily.Monospace,
                    letterSpacing = 2.sp
                )
                Spacer(modifier = Modifier.width(6.dp))
                Text(
                    text = "v2.0",
                    color = TextSecondary,
                    fontSize = 10.sp,
                    fontFamily = FontFamily.Monospace
                )
            }
            Text(
                text = "NEURAL GATEWAY",
                color = ArcNeon.copy(alpha = 0.7f),
                fontSize = 9.sp,
                fontFamily = FontFamily.Monospace,
                letterSpacing = 1.sp
            )
        }

        // Right: Telemetry Badges
        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Cloud Badge (tap to open Cloud Gateway setup dialog)
            StatusBadge(
                label = "CLOUD",
                isOnline = isConnected,
                onlineColor = NeonGreen,
                offlineColor = NeonRed,
                onClick = onOpenSettings
            )

            // PC Badge
            StatusBadge(
                label = "PC AGENT",
                isOnline = isPcOnline,
                onlineColor = CyanCore,
                offlineColor = Color(0xFF64748B)
            )

            // Phone Battery
            if (batteryLevel >= 0) {
                Row(
                    modifier = Modifier
                        .clip(RoundedCornerShape(8.dp))
                        .background(Color(0x221E293B))
                        .border(1.dp, Color(0x3338BDF8), RoundedCornerShape(8.dp))
                        .padding(horizontal = 6.dp, vertical = 3.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        imageVector = Icons.Rounded.BatteryChargingFull,
                        contentDescription = "Battery",
                        tint = if (batteryLevel > 20) NeonGreen else NeonRed,
                        modifier = Modifier.size(12.dp)
                    )
                    Spacer(modifier = Modifier.width(3.dp))
                    Text(
                        text = "$batteryLevel%",
                        color = TextPrimary,
                        fontSize = 9.sp,
                        fontFamily = FontFamily.Monospace,
                        fontWeight = FontWeight.Bold
                    )
                }
            }
        }
    }
}

@Composable
fun StatusBadge(
    label: String,
    isOnline: Boolean,
    onlineColor: Color,
    offlineColor: Color,
    onClick: (() -> Unit)? = null
) {
    val infiniteTransition = rememberInfiniteTransition(label = "pulseBadge")
    val dotAlpha by infiniteTransition.animateFloat(
        initialValue = 0.4f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(1000, easing = LinearEasing),
            repeatMode = RepeatMode.Reverse
        ),
        label = "dotAlpha"
    )

    Row(
        modifier = Modifier
            .clip(RoundedCornerShape(8.dp))
            .then(if (onClick != null) Modifier.clickable { onClick() } else Modifier)
            .background(Color(0x221E293B))
            .border(
                1.dp,
                if (isOnline) onlineColor.copy(alpha = 0.4f) else offlineColor.copy(alpha = 0.3f),
                RoundedCornerShape(8.dp)
            )
            .padding(horizontal = 7.dp, vertical = 3.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            modifier = Modifier
                .size(6.dp)
                .clip(CircleShape)
                .background(
                    if (isOnline) onlineColor.copy(alpha = dotAlpha) else offlineColor
                )
        )
        Spacer(modifier = Modifier.width(5.dp))
        Text(
            text = label,
            color = if (isOnline) TextPrimary else TextSecondary,
            fontSize = 9.sp,
            fontFamily = FontFamily.Monospace,
            fontWeight = FontWeight.SemiBold
        )
    }
}

// -------------------------------------------------------------
// COMPONENT 2: Orb State Holographic Label
// -------------------------------------------------------------
@Composable
fun OrbStatusBadge(orbState: OrbState) {
    val (text, color) = when (orbState) {
        OrbState.IDLE -> "SYSTEM STANDBY // READY" to CyanCore
        OrbState.LISTENING -> "AUDIO CAPTURE // LISTENING..." to NeonGreen
        OrbState.THINKING -> "AZURE NEURAL // REASONING..." to ElectricBlue
        OrbState.SPEAKING -> "VOICE SYNTHESIS // ACTIVE" to ArcNeon
    }

    Text(
        text = text,
        color = color,
        fontSize = 11.sp,
        fontFamily = FontFamily.Monospace,
        fontWeight = FontWeight.Bold,
        letterSpacing = 1.5.sp
    )
}

// -------------------------------------------------------------
// COMPONENT 3: Audio Visualizer Bars
// -------------------------------------------------------------
@Composable
fun AudioVisualizerBars(isActive: Boolean) {
    val infiniteTransition = rememberInfiniteTransition(label = "audioEq")
    val heights = (0 until 9).map { i ->
        infiniteTransition.animateFloat(
            initialValue = 4f,
            targetValue = if (isActive) (14 + (i % 5) * 6).toFloat() else 4f,
            animationSpec = infiniteRepeatable(
                animation = tween(250 + i * 40, easing = FastOutSlowInEasing),
                repeatMode = RepeatMode.Reverse
            ),
            label = "barHeight$i"
        )
    }

    Row(
        modifier = Modifier.height(30.dp),
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        heights.forEach { h ->
            Box(
                modifier = Modifier
                    .width(3.dp)
                    .height(h.value.dp)
                    .clip(RoundedCornerShape(2.dp))
                    .background(CyanCore.copy(alpha = 0.85f))
            )
        }
    }
}

// -------------------------------------------------------------
// COMPONENT 4: Quick Action Chips Row
// -------------------------------------------------------------
@Composable
fun QuickActionChipsRow(onChipSelected: (String) -> Unit) {
    val quickCommands = listOf(
        "Open YouTube" to "open youtube",
        "PC Status" to "check pc status",
        "Open WhatsApp" to "open whatsapp",
        "Set Volume 50%" to "set pc volume to 50%",
        "Screen Calls" to "enable sleep call screening"
    )

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = 6.dp, bottom = 4.dp, start = 12.dp, end = 12.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        quickCommands.take(3).forEach { (label, cmd) ->
            Box(
                modifier = Modifier
                    .clip(RoundedCornerShape(20.dp))
                    .background(Color(0x33101C34))
                    .border(1.dp, Color(0x5538BDF8), RoundedCornerShape(20.dp))
                    .clickable { onChipSelected(cmd) }
                    .padding(horizontal = 12.dp, vertical = 6.dp)
            ) {
                Text(
                    text = label,
                    color = ArcNeon,
                    fontSize = 11.sp,
                    fontFamily = FontFamily.Monospace
                )
            }
        }
    }
}

// -------------------------------------------------------------
// COMPONENT 5: Chat Bubbles (User & Jarvis)
// -------------------------------------------------------------
@Composable
fun ChatBubble(message: ChatMessage) {
    val isUser = message.sender == "user"
    val timeFormatter = remember { SimpleDateFormat("HH:mm:ss", Locale.getDefault()) }
    val timeStr = remember(message.timestamp) { timeFormatter.format(Date(message.timestamp)) }

    Column(
        modifier = Modifier.fillMaxWidth(),
        horizontalAlignment = if (isUser) Alignment.End else Alignment.Start
    ) {
        // Tag Header
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.padding(bottom = 3.dp, start = 4.dp, end = 4.dp)
        ) {
            Text(
                text = if (isUser) "OPERATOR // $timeStr" else "JARVIS // $timeStr",
                color = if (isUser) CyanCore.copy(alpha = 0.8f) else NeonGreen.copy(alpha = 0.8f),
                fontSize = 9.sp,
                fontFamily = FontFamily.Monospace,
                fontWeight = FontWeight.Bold
            )
        }

        // Bubble Box
        Box(
            modifier = Modifier
                .widthIn(max = 310.dp)
                .clip(
                    RoundedCornerShape(
                        topStart = 16.dp,
                        topEnd = 16.dp,
                        bottomStart = if (isUser) 16.dp else 2.dp,
                        bottomEnd = if (isUser) 2.dp else 16.dp
                    )
                )
                .background(
                    if (isUser) Color(0x330284C7) else Color(0x330B132B)
                )
                .border(
                    width = 1.dp,
                    color = if (isUser) CyanCore.copy(alpha = 0.5f) else ElectricBlue.copy(alpha = 0.6f),
                    shape = RoundedCornerShape(
                        topStart = 16.dp,
                        topEnd = 16.dp,
                        bottomStart = if (isUser) 16.dp else 2.dp,
                        bottomEnd = if (isUser) 2.dp else 16.dp
                    )
                )
                .padding(horizontal = 14.dp, vertical = 10.dp)
        ) {
            Text(
                text = message.text,
                color = TextPrimary,
                fontSize = 13.sp,
                lineHeight = 19.sp,
                fontFamily = FontFamily.SansSerif
            )
        }
    }
}

// -------------------------------------------------------------
// COMPONENT 6: Bottom Command Console & Pulsing Mic
// -------------------------------------------------------------
@Composable
fun BottomCommandDock(
    inputText: String,
    onInputTextChanged: (String) -> Unit,
    onSend: () -> Unit,
    orbState: OrbState,
    isSpeaking: Boolean,
    interactionMode: InteractionMode,
    onMicClicked: () -> Unit,
    onStopSpeaking: () -> Unit
) {
    val infiniteTransition = rememberInfiniteTransition(label = "micPulse")
    val micPulseScale by infiniteTransition.animateFloat(
        initialValue = 1f,
        targetValue = 1.25f,
        animationSpec = infiniteRepeatable(
            animation = tween(700, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse
        ),
        label = "micPulseScale"
    )

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(topStart = 24.dp, topEnd = 24.dp))
            .background(Color(0xE6080E1C))
            .border(1.dp, GlassBorder, RoundedCornerShape(topStart = 24.dp, topEnd = 24.dp))
            .padding(horizontal = 14.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        // Text Input - using OutlinedTextField for reliable text rendering on all devices
        OutlinedTextField(
            value = inputText,
            onValueChange = onInputTextChanged,
            modifier = Modifier
                .weight(1f)
                .heightIn(min = 48.dp),
            placeholder = {
                Text(
                    text = if (interactionMode == InteractionMode.CHAT) "Type to chat with Jarvis..." else "Type command or speak...",
                    color = Color(0xFF94A3B8),
                    fontSize = 14.sp
                )
            },
            textStyle = TextStyle(
                color = Color.White,
                fontSize = 15.sp,
                fontFamily = FontFamily.SansSerif
            ),
            colors = OutlinedTextFieldDefaults.colors(
                focusedTextColor = Color.White,
                unfocusedTextColor = Color.White,
                cursorColor = CyanCore,
                focusedBorderColor = CyanCore,
                unfocusedBorderColor = Color(0x6638BDF8),
                focusedContainerColor = Color(0xFF0F172A),
                unfocusedContainerColor = Color(0xFF0F172A),
                focusedPlaceholderColor = Color(0xFF94A3B8),
                unfocusedPlaceholderColor = Color(0xFF94A3B8)
            ),
            shape = RoundedCornerShape(24.dp),
            singleLine = true,
            visualTransformation = androidx.compose.ui.text.input.VisualTransformation.None,
            keyboardOptions = KeyboardOptions(
                keyboardType = androidx.compose.ui.text.input.KeyboardType.Text,
                imeAction = ImeAction.Send,
                capitalization = KeyboardCapitalization.Sentences,
                autoCorrect = true
            ),
            keyboardActions = KeyboardActions(
                onSend = {
                    if (inputText.isNotBlank()) {
                        onSend()
                    }
                }
            )
        )

        // If Jarvis is currently speaking aloud, show stop voice button
        if (isSpeaking) {
            IconButton(
                onClick = onStopSpeaking,
                modifier = Modifier
                    .size(46.dp)
                    .clip(CircleShape)
                    .background(NeonRed.copy(alpha = 0.2f))
                    .border(1.dp, NeonRed, CircleShape)
            ) {
                Icon(
                    imageVector = Icons.Rounded.VolumeOff,
                    contentDescription = "Mute",
                    tint = NeonRed,
                    modifier = Modifier.size(20.dp)
                )
            }
        }

        // Send Button (if text entered) OR Mic Button (if empty)
        if (inputText.isNotBlank()) {
            IconButton(
                onClick = onSend,
                modifier = Modifier
                    .size(46.dp)
                    .clip(CircleShape)
                    .background(CyanCore)
            ) {
                Icon(
                    imageVector = Icons.Rounded.Send,
                    contentDescription = "Send",
                    tint = VoidBlack,
                    modifier = Modifier.size(20.dp)
                )
            }
        } else {
            // Futuristic Mic Button with dynamic glow rings
            Box(
                contentAlignment = Alignment.Center,
                modifier = Modifier.size(54.dp)
            ) {
                if (orbState == OrbState.LISTENING) {
                    Box(
                        modifier = Modifier
                            .size(54.dp)
                            .scale(micPulseScale)
                            .clip(CircleShape)
                            .border(2.dp, NeonGreen.copy(alpha = 0.6f), CircleShape)
                    )
                }

                IconButton(
                    onClick = onMicClicked,
                    modifier = Modifier
                        .size(46.dp)
                        .clip(CircleShape)
                        .background(
                            if (orbState == OrbState.LISTENING) NeonGreen else Color(0x3300F0FF)
                        )
                        .border(
                            1.5.dp,
                            if (orbState == OrbState.LISTENING) NeonGreen else CyanCore,
                            CircleShape
                        )
                ) {
                    Icon(
                        imageVector = Icons.Rounded.Mic,
                        contentDescription = "Voice Input",
                        tint = if (orbState == OrbState.LISTENING) VoidBlack else CyanCore,
                        modifier = Modifier.size(24.dp)
                    )
                }
            }
        }
    }
}

// -------------------------------------------------------------
// COMPONENT 7: Interaction Mode Toggle (CHAT vs TALK)
// -------------------------------------------------------------
@Composable
fun InteractionModeToggle(
    currentMode: InteractionMode,
    onModeSelected: (InteractionMode) -> Unit
) {
    Row(
        modifier = Modifier
            .clip(RoundedCornerShape(20.dp))
            .background(Color(0x330B132B))
            .border(1.dp, Color(0x3338BDF8), RoundedCornerShape(20.dp))
            .padding(3.dp),
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        val isChat = currentMode == InteractionMode.CHAT
        Box(
            modifier = Modifier
                .clip(RoundedCornerShape(16.dp))
                .background(if (isChat) CyanCore.copy(alpha = 0.25f) else Color.Transparent)
                .border(
                    width = if (isChat) 1.dp else 0.dp,
                    color = if (isChat) CyanCore else Color.Transparent,
                    shape = RoundedCornerShape(16.dp)
                )
                .clickable { onModeSelected(InteractionMode.CHAT) }
                .padding(horizontal = 12.dp, vertical = 5.dp),
            contentAlignment = Alignment.Center
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    imageVector = Icons.Rounded.Chat,
                    contentDescription = "Chat Mode",
                    tint = if (isChat) CyanCore else TextSecondary,
                    modifier = Modifier.size(12.dp)
                )
                Spacer(modifier = Modifier.width(4.dp))
                Text(
                    text = "CHAT",
                    color = if (isChat) Color.White else TextSecondary,
                    fontSize = 10.sp,
                    fontFamily = FontFamily.Monospace,
                    fontWeight = if (isChat) FontWeight.Bold else FontWeight.Normal
                )
            }
        }

        val isTalk = currentMode == InteractionMode.TALK
        Box(
            modifier = Modifier
                .clip(RoundedCornerShape(16.dp))
                .background(if (isTalk) ArcNeon.copy(alpha = 0.25f) else Color.Transparent)
                .border(
                    width = if (isTalk) 1.dp else 0.dp,
                    color = if (isTalk) ArcNeon else Color.Transparent,
                    shape = RoundedCornerShape(16.dp)
                )
                .clickable { onModeSelected(InteractionMode.TALK) }
                .padding(horizontal = 12.dp, vertical = 5.dp),
            contentAlignment = Alignment.Center
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    imageVector = Icons.Rounded.RecordVoiceOver,
                    contentDescription = "Talk Mode",
                    tint = if (isTalk) ArcNeon else TextSecondary,
                    modifier = Modifier.size(12.dp)
                )
                Spacer(modifier = Modifier.width(4.dp))
                Text(
                    text = "TALK",
                    color = if (isTalk) Color.White else TextSecondary,
                    fontSize = 10.sp,
                    fontFamily = FontFamily.Monospace,
                    fontWeight = if (isTalk) FontWeight.Bold else FontWeight.Normal
                )
            }
        }
    }
}

@Composable
fun ConnectionSettingsDialog(
    initialHost: String,
    initialPort: String,
    initialToken: String,
    onDismiss: () -> Unit,
    onSave: (String, String, String) -> Unit
) {
    var host by remember { mutableStateOf(initialHost) }
    var port by remember { mutableStateOf(initialPort) }
    var token by remember { mutableStateOf(initialToken) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Text(
                text = "CLOUD GATEWAY SETUP",
                color = CyanCore,
                fontFamily = FontFamily.Monospace,
                fontWeight = FontWeight.Bold,
                fontSize = 16.sp
            )
        },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(
                    text = "Configure your Azure Cloud Server connection details. These are stored locally on your device.",
                    color = TextSecondary,
                    fontSize = 12.sp
                )
                OutlinedTextField(
                    value = host,
                    onValueChange = { host = it },
                    label = { Text("Server Host / IP", color = TextSecondary) },
                    singleLine = true,
                    textStyle = TextStyle(color = Color.White),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedTextColor = Color.White,
                        unfocusedTextColor = Color.White,
                        focusedBorderColor = CyanCore,
                        unfocusedBorderColor = Color(0x6638BDF8)
                    )
                )
                OutlinedTextField(
                    value = port,
                    onValueChange = { port = it },
                    label = { Text("Port (Default: 8765)", color = TextSecondary) },
                    singleLine = true,
                    textStyle = TextStyle(color = Color.White),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedTextColor = Color.White,
                        unfocusedTextColor = Color.White,
                        focusedBorderColor = CyanCore,
                        unfocusedBorderColor = Color(0x6638BDF8)
                    )
                )
                OutlinedTextField(
                    value = token,
                    onValueChange = { token = it },
                    label = { Text("Auth Token", color = TextSecondary) },
                    singleLine = true,
                    textStyle = TextStyle(color = Color.White),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedTextColor = Color.White,
                        unfocusedTextColor = Color.White,
                        focusedBorderColor = CyanCore,
                        unfocusedBorderColor = Color(0x6638BDF8)
                    )
                )
            }
        },
        confirmButton = {
            Button(
                onClick = { onSave(host, port, token) },
                colors = ButtonDefaults.buttonColors(containerColor = CyanCore)
            ) {
                Text("Save & Connect", color = Color.Black, fontWeight = FontWeight.Bold)
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel", color = TextSecondary)
            }
        },
        containerColor = Color(0xFF0F172A)
    )
}



@Composable
fun DealHunterPanel(
    isOn: Boolean,
    onToggle: (Boolean) -> Unit,
    pincode: String,
    onPincodeChange: (String) -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 8.dp),
        colors = CardDefaults.cardColors(containerColor = Color(0xFF1E293B))
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text("🛒 Deal Hunter", color = Color.White, fontWeight = androidx.compose.ui.text.font.FontWeight.Bold)
                Switch(checked = isOn, onCheckedChange = onToggle)
            }
            Spacer(modifier = Modifier.height(8.dp))
            OutlinedTextField(
                value = pincode,
                onValueChange = onPincodeChange,
                label = { Text("Pincodes (comma separated)", color = Color.Gray) },
                singleLine = true,
                textStyle = TextStyle(color = Color.White),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedTextColor = Color.White,
                    unfocusedTextColor = Color.White
                )
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text("Watching:\n📱 Phones (Edge 70 specs) - Active\n💻 Laptops (35-40K best) - Active", color = Color.Gray, fontSize = 12.sp)
        }
    }
}
