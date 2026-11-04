package com.jarvis.companion.ui.components

import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.jarvis.companion.theme.*
import kotlin.math.cos
import kotlin.math.sin

enum class OrbState {
    IDLE, LISTENING, THINKING, SPEAKING
}

@Composable
fun JarvisOrb(
    modifier: Modifier = Modifier,
    state: OrbState = OrbState.IDLE,
    size: Dp = 220.dp
) {
    val infiniteTransition = rememberInfiniteTransition(label = "JarvisOrbTransition")

    // Rotation speeds adapt to state
    val rotDuration = when (state) {
        OrbState.THINKING -> 2000
        OrbState.LISTENING -> 4000
        OrbState.SPEAKING -> 3000
        OrbState.IDLE -> 8000
    }

    // Outer Ring Clockwise Rotation
    val outerRotation by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec = infiniteRepeatable(
            animation = tween(rotDuration, easing = LinearEasing),
            repeatMode = RepeatMode.Restart
        ),
        label = "outerRotation"
    )

    // Inner Ring Counter-Clockwise Rotation
    val innerRotation by infiniteTransition.animateFloat(
        initialValue = 360f,
        targetValue = 0f,
        animationSpec = infiniteRepeatable(
            animation = tween((rotDuration * 1.4).toInt(), easing = LinearEasing),
            repeatMode = RepeatMode.Restart
        ),
        label = "innerRotation"
    )

    // Pulse Scale for Core Glow
    val pulseScale by infiniteTransition.animateFloat(
        initialValue = 0.85f,
        targetValue = 1.15f,
        animationSpec = infiniteRepeatable(
            animation = tween(if (state == OrbState.LISTENING) 700 else 1800, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse
        ),
        label = "pulseScale"
    )

    // Ripple wave for listening / speaking
    val rippleAlpha by infiniteTransition.animateFloat(
        initialValue = 0.8f,
        targetValue = 0f,
        animationSpec = infiniteRepeatable(
            animation = tween(1400, easing = LinearEasing),
            repeatMode = RepeatMode.Restart
        ),
        label = "rippleAlpha"
    )

    val primaryGlow = when (state) {
        OrbState.LISTENING -> NeonGreen
        OrbState.THINKING -> ElectricBlue
        OrbState.SPEAKING -> CyanCore
        OrbState.IDLE -> CyanCore
    }

    Box(
        modifier = modifier.size(size),
        contentAlignment = Alignment.Center
    ) {
        Canvas(modifier = Modifier.size(size)) {
            val center = Offset(size.toPx() / 2f, size.toPx() / 2f)
            val maxRadius = (size.toPx() / 2f) * 0.9f

            // 1. Outer Expanding Ripple (when active)
            if (state == OrbState.LISTENING || state == OrbState.SPEAKING) {
                drawCircle(
                    color = primaryGlow.copy(alpha = rippleAlpha * 0.4f),
                    radius = maxRadius * (1f + (1f - rippleAlpha) * 0.35f),
                    center = center,
                    style = Stroke(width = 2.dp.toPx())
                )
            }

            // 2. Outermost Segmented Arc Ring (Clockwise)
            val outerRadius = maxRadius * 0.95f
            for (i in 0 until 4) {
                drawArc(
                    color = primaryGlow.copy(alpha = 0.85f),
                    startAngle = outerRotation + (i * 90f) + 10f,
                    sweepAngle = 70f,
                    useCenter = false,
                    topLeft = Offset(center.x - outerRadius, center.y - outerRadius),
                    size = androidx.compose.ui.geometry.Size(outerRadius * 2f, outerRadius * 2f),
                    style = Stroke(width = 3.dp.toPx(), cap = StrokeCap.Round)
                )
            }

            // 3. Middle Counter-Rotating Ring
            val midRadius = maxRadius * 0.75f
            for (i in 0 until 6) {
                drawArc(
                    color = ElectricBlue.copy(alpha = 0.7f),
                    startAngle = innerRotation + (i * 60f) + 8f,
                    sweepAngle = 44f,
                    useCenter = false,
                    topLeft = Offset(center.x - midRadius, center.y - midRadius),
                    size = androidx.compose.ui.geometry.Size(midRadius * 2f, midRadius * 2f),
                    style = Stroke(width = 2.dp.toPx(), cap = StrokeCap.Round)
                )
            }

            // 4. Perimeter Particle Dots
            val dotCount = 12
            for (i in 0 until dotCount) {
                val angle = Math.toRadians((outerRotation * 0.5 + i * (360.0 / dotCount)).toDouble())
                val dotX = center.x + (maxRadius * 0.85f * cos(angle)).toFloat()
                val dotY = center.y + (maxRadius * 0.85f * sin(angle)).toFloat()
                drawCircle(
                    color = ArcNeon.copy(alpha = 0.7f),
                    radius = 2.dp.toPx(),
                    center = Offset(dotX, dotY)
                )
            }

            // 5. Central Pulsing Radial Reactor Core
            val coreRadius = maxRadius * 0.45f * pulseScale
            drawCircle(
                brush = Brush.radialGradient(
                    colors = listOf(
                        Color.White,
                        primaryGlow,
                        ElectricBlue.copy(alpha = 0.3f),
                        Color.Transparent
                    ),
                    center = center,
                    radius = coreRadius
                ),
                radius = coreRadius,
                center = center
            )

            // 6. Center Energy Core Ring
            drawCircle(
                color = Color.White.copy(alpha = 0.9f),
                radius = coreRadius * 0.35f,
                center = center,
                style = Stroke(width = 1.5.dp.toPx())
            )
        }
    }
}
