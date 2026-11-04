package com.jarvis.companion.ui

import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.CallEnd
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import kotlinx.coroutines.delay

data class UrgentAlertData(
    val callerName: String,
    val callerNumber: String,
    val message: String
)

@Composable
fun UrgentCallDialog(
    alertData: UrgentAlertData,
    onConnect: () -> Unit,
    onDecline: () -> Unit,
    onMuteAlarm: () -> Unit
) {
    var timeLeft by remember { mutableStateOf(20) }

    // 20-second countdown timer
    LaunchedEffect(Unit) {
        while (timeLeft > 0) {
            delay(1000)
            timeLeft--
        }
        // Auto-decline when timer expires
        onDecline()
    }

    // Pulsing animation for warning icon
    val infiniteTransition = rememberInfiniteTransition(label = "pulse")
    val pulseScale by infiniteTransition.animateFloat(
        initialValue = 1.0f,
        targetValue = 1.25f,
        animationSpec = infiniteRepeatable(
            animation = tween(600, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse
        ),
        label = "pulseScale"
    )

    Dialog(
        onDismissRequest = { /* Prevent dismiss by touching outside */ },
        properties = DialogProperties(
            dismissOnBackPress = false,
            dismissOnClickOutside = false,
            usePlatformDefaultWidth = false
        )
    ) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(Color(0xE6050510))
                .padding(24.dp),
            contentAlignment = Alignment.Center
        ) {
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .wrapContentHeight(),
                shape = RoundedCornerShape(24.dp),
                colors = CardDefaults.cardColors(containerColor = Color(0xFF14142B)),
                elevation = CardDefaults.cardElevation(defaultElevation = 16.dp)
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    // Urgent Warning Header
                    Box(
                        modifier = Modifier
                            .size(72.dp)
                            .clip(CircleShape)
                            .background(Color(0x33FF3344)),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(
                            imageVector = Icons.Default.Warning,
                            contentDescription = "Urgent",
                            tint = Color(0xFFFF3344),
                            modifier = Modifier.size(42.dp)
                        )
                    }

                    Spacer(modifier = Modifier.height(16.dp))

                    Text(
                        text = "🚨 URGENT CALL",
                        color = Color(0xFFFF3344),
                        fontSize = 20.sp,
                        fontWeight = FontWeight.Black,
                        letterSpacing = 2.sp
                    )

                    Spacer(modifier = Modifier.height(8.dp))

                    Text(
                        text = alertData.callerName,
                        color = Color.White,
                        fontSize = 24.sp,
                        fontWeight = FontWeight.Bold
                    )

                    if (alertData.callerNumber.isNotBlank()) {
                        Text(
                            text = alertData.callerNumber,
                            color = Color(0xFF8888AA),
                            fontSize = 14.sp
                        )
                    }

                    Spacer(modifier = Modifier.height(16.dp))

                    // Message Box
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(12.dp))
                            .background(Color(0xFF1E1E38))
                            .padding(16.dp)
                    ) {
                        Column {
                            Text(
                                text = "MESSAGE FROM CALLER:",
                                color = Color(0xFF9999BB),
                                fontSize = 11.sp,
                                fontWeight = FontWeight.Bold
                            )
                            Spacer(modifier = Modifier.height(6.dp))
                            Text(
                                text = "\"${alertData.message}\"",
                                color = Color(0xFFEAEAFF),
                                fontSize = 16.sp,
                                fontWeight = FontWeight.Medium
                            )
                        }
                    }

                    Spacer(modifier = Modifier.height(16.dp))

                    // Timer Countdown Text
                    Text(
                        text = "Auto-declining in ${timeLeft}s",
                        color = if (timeLeft <= 5) Color(0xFFFF3344) else Color(0xFF8888AA),
                        fontSize = 13.sp,
                        fontWeight = FontWeight.SemiBold
                    )

                    Spacer(modifier = Modifier.height(6.dp))

                    // Timer Progress Bar
                    LinearProgressIndicator(
                        progress = { timeLeft / 20.0f },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(6.dp)
                            .clip(RoundedCornerShape(3.dp)),
                        color = if (timeLeft <= 5) Color(0xFFFF3344) else Color(0xFF6C63FF),
                        trackColor = Color(0xFF242445)
                    )

                    Spacer(modifier = Modifier.height(24.dp))

                    // Buttons Row: Connect vs Decline
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(16.dp)
                    ) {
                        // Decline Button (Red)
                        Button(
                            onClick = {
                                onMuteAlarm()
                                onDecline()
                            },
                            modifier = Modifier
                                .weight(1f)
                                .height(56.dp),
                            shape = RoundedCornerShape(16.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF38141E))
                        ) {
                            Icon(Icons.Default.CallEnd, contentDescription = "Decline", tint = Color(0xFFFF4455))
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("DECLINE", color = Color(0xFFFF4455), fontWeight = FontWeight.Bold)
                        }

                        // Connect Button (Green)
                        Button(
                            onClick = {
                                onMuteAlarm()
                                onConnect()
                            },
                            modifier = Modifier
                                .weight(1f)
                                .height(56.dp),
                            shape = RoundedCornerShape(16.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF00C853))
                        ) {
                            Icon(Icons.Default.Call, contentDescription = "Connect", tint = Color.White)
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("CONNECT", color = Color.White, fontWeight = FontWeight.Bold)
                        }
                    }

                    Spacer(modifier = Modifier.height(12.dp))

                    Text(
                        text = "Tip: Press Volume or Power key to silence alarm",
                        color = Color(0xFF666688),
                        fontSize = 11.sp,
                        textAlign = TextAlign.Center
                    )
                }
            }
        }
    }
}
