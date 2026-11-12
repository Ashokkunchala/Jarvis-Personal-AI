package com.ashok.jarvis.ui

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp

/** What the AI core is doing right now. */
enum class OrbState { IDLE, LISTENING, SPEAKING, BUSY, OFFLINE }

/**
 * The glowing JARVIS AI core: a pulsing light with two slowly rotating arcs.
 * Pure Compose canvas; no assets, no network, no sensors.
 */
@Composable
fun JarvisOrb(state: OrbState, modifier: Modifier = Modifier.size(96.dp)) {
    val transition = rememberInfiniteTransition(label = "jarvis-orb")
    val pulseDuration = when (state) {
        OrbState.BUSY -> 500
        OrbState.LISTENING -> 750
        OrbState.SPEAKING -> 900
        else -> 1900
    }
    val rotationDuration = if (state == OrbState.BUSY) 1300 else 6500
    val pulse by transition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = pulseDuration, easing = LinearEasing),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "orb-pulse",
    )
    val rotation by transition.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = rotationDuration, easing = LinearEasing),
            repeatMode = RepeatMode.Restart,
        ),
        label = "orb-rotation",
    )

    val coreColor = when (state) {
        OrbState.OFFLINE -> Color(0xFF5B6B8C)
        OrbState.SPEAKING -> Color(0xFFFFB347)
        OrbState.BUSY -> Color(0xFF7FEDFF)
        OrbState.IDLE -> Color(0xFF35E0FF)
        OrbState.LISTENING -> Color(0xFF35E0FF)
    }
    val ringColor = if (state == OrbState.OFFLINE) Color(0xFF3A4A6E) else coreColor

    Canvas(modifier = modifier) {
        val diameter = size.minDimension
        val center = Offset(size.width / 2f, size.height / 2f)
        val outerRadius = diameter / 2f

        // Soft glow halo.
        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(
                    coreColor.copy(alpha = 0.50f + 0.25f * pulse),
                    coreColor.copy(alpha = 0.12f),
                    Color.Transparent,
                ),
                center = center,
                radius = outerRadius,
            ),
            radius = outerRadius,
            center = center,
        )
        // Solid core.
        drawCircle(
            color = coreColor,
            radius = outerRadius * (0.15f + 0.05f * pulse),
            center = center,
        )
        // Inner halo ring.
        drawCircle(
            color = ringColor.copy(alpha = 0.75f),
            radius = outerRadius * 0.34f,
            center = center,
            style = Stroke(width = 3f),
        )
        // Two rotating arcs, centered even if the canvas is not square.
        val inset = outerRadius * 0.20f
        val side = diameter - inset * 2
        val topLeft = Offset((size.width - side) / 2f, (size.height - side) / 2f)
        val arcSize = Size(side, side)
        drawArc(
            color = ringColor,
            startAngle = rotation,
            sweepAngle = 100f,
            useCenter = false,
            topLeft = topLeft,
            size = arcSize,
            style = Stroke(width = 4f, cap = StrokeCap.Round),
        )
        drawArc(
            color = ringColor.copy(alpha = 0.45f),
            startAngle = rotation + 180f,
            sweepAngle = 55f,
            useCenter = false,
            topLeft = topLeft,
            size = arcSize,
            style = Stroke(width = 3f, cap = StrokeCap.Round),
        )
    }
}
