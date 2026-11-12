package com.ashok.jarvis

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.speech.RecognizerIntent
import android.speech.tts.TextToSpeech
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.ashok.jarvis.ui.JarvisOrb
import com.ashok.jarvis.ui.OrbState
import com.ashok.jarvis.ui.theme.JarvisTheme
import com.ashok.jarvis.ui.theme.TextMuted
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.Locale

private data class ReminderItem(
    val id: Int,
    val title: String,
    val dueAt: String,
    val completed: Boolean,
    val recurrence: String,
)

private fun parseReminderItems(payload: String): List<ReminderItem> {
    val items = JSONObject(payload).optJSONArray("items") ?: return emptyList()
    return (0 until items.length()).mapNotNull { index ->
        items.optJSONObject(index)?.let { item ->
            ReminderItem(
                id = item.optInt("id", -1),
                title = item.optString("title"),
                dueAt = item.optString("due_at"),
                completed = item.optInt("completed", 0) == 1,
                recurrence = item.optString("recurrence", "none"),
            ).takeIf { it.id >= 0 }
        }
    }
}

// One visible exchange in the chat card; also sent to the backend as short history.
private data class ChatTurn(val role: String, val content: String)

private val PERSONALITY_MODES = listOf(
    "assistant" to "Assistant",
    "friend" to "Friend",
    "teacher" to "Teacher",
    "storyteller" to "Storyteller",
    "doctor" to "Doctor",
)

private val QUICK_ACTIONS = listOf(
    "What is my system status?",
    "Tell me a short story",
    "Sing me a song",
    "Teach me something about AWS",
    "What reminders do I have today?",
)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            JarvisTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background,
                ) { CommandCentreScreen() }
            }
        }
    }
}

@Composable
private fun SectionCard(title: String, content: @Composable () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(title, style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.primary)
            content()
        }
    }
}

@Composable
private fun CommandCentreScreen() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val lifecycleOwner = LocalLifecycleOwner.current
    var endpoint by remember { mutableStateOf(runCatching { TokenVault.readBackendUrl(context).orEmpty() }.getOrDefault("")) }
    var token by remember { mutableStateOf(runCatching { TokenVault.read(context).orEmpty() }.getOrDefault("")) }
    var masterToken by remember { mutableStateOf("") }
    var deviceName by remember { mutableStateOf("Android device") }
    var pairedDeviceId by remember { mutableStateOf(runCatching { TokenVault.readDeviceId(context).orEmpty() }.getOrDefault("")) }
    var showRevokeConfirmation by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }
    var reply by remember { mutableStateOf("Connect to your private HTTPS backend to start chatting.") }
    var status by remember {
        mutableStateOf(
            if (endpoint.isNotBlank() && token.isNotBlank()) {
                "Stored encrypted credentials loaded. Tap Connect securely."
            } else {
                "Enter the HTTPS backend URL and device token."
            }
        )
    }
    var busy by remember { mutableStateOf(false) }
    var voiceBusy by remember { mutableStateOf(false) }
    var language by remember { mutableStateOf("auto") }
    var reminderTitle by remember { mutableStateOf("") }
    var reminderDueAt by remember { mutableStateOf("") }
    var reminders by remember { mutableStateOf(listOf<ReminderItem>()) }
    var reminderRecurrence by remember { mutableStateOf("none") }
    var memoryText by remember { mutableStateOf("") }
    var memories by remember { mutableStateOf(listOf<Pair<Int, String>>()) }
    var reminderNotificationsEnabled by remember {
        mutableStateOf(
            context.getSharedPreferences("jarvis_reminder_settings", android.content.Context.MODE_PRIVATE)
                .getBoolean("notifications_enabled", false)
        )
    }
    var personalityMode by remember {
        mutableStateOf(
            context.getSharedPreferences("jarvis_reminder_settings", android.content.Context.MODE_PRIVATE)
                .getString("personality_mode", "assistant") ?: "assistant"
        )
    }
    var conversation by remember { mutableStateOf(listOf<ChatTurn>()) }
    var runtimeEvents by remember { mutableStateOf(listOf<String>()) }
    var runtimeCursor by remember { mutableStateOf(0) }
    var liveVoiceActive by remember { mutableStateOf(false) }
    var liveVoiceStatus by remember { mutableStateOf("Live Voice is off. Start it explicitly when ready.") }
    val liveVoiceController = remember(context) {
        val mainThread = Handler(Looper.getMainLooper())
        LiveVoiceController { message, active ->
            mainThread.post {
                liveVoiceStatus = message
                liveVoiceActive = active
            }
        }
    }
    DisposableEffect(liveVoiceController, lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) liveVoiceController.stop()
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
            liveVoiceController.stop()
        }
    }
    fun startLiveVoice() {
        scope.launch {
            try {
                val base = TokenVault.readBackendUrl(context) ?: endpoint.trim().trimEnd('/')
                val activeToken = TokenVault.read(context) ?: token
                liveVoiceActive = true
                liveVoiceController.start(base, activeToken)
            } catch (error: Exception) {
                liveVoiceActive = false
                liveVoiceStatus = error.message ?: "Could not start Live Voice."
            }
        }
    }
    val phoneSettingsAction = when (message.trim().lowercase()) {
        "open settings", "open device settings", "device settings" -> Settings.ACTION_SETTINGS
        "open wifi settings", "open wi-fi settings", "wifi settings", "wi-fi settings" -> Settings.ACTION_WIFI_SETTINGS
        "open bluetooth settings", "bluetooth settings" -> Settings.ACTION_BLUETOOTH_SETTINGS
        "open app permissions", "open jarvis app permissions", "jarvis app permissions" -> Settings.ACTION_APPLICATION_DETAILS_SETTINGS
        else -> null
    }

    val speechLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        voiceBusy = false
        if (result.resultCode == Activity.RESULT_OK) {
            val spoken = result.data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull()
            if (!spoken.isNullOrBlank()) {
                message = spoken
                status = "Voice captured. Review the transcript, then tap Send."
            } else {
                status = "No speech was recognized. Try again."
            }
        } else {
            status = "Voice input cancelled or unavailable."
        }
    }
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) launchSpeech(speechLauncher, language) { voiceBusy = it }
        else status = "Microphone permission was denied. You can still type."
    }
    val notificationPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            ReminderWorker.setEnabled(context, true)
            reminderNotificationsEnabled = true
            status = "Android reminder notifications enabled. Delivery is best-effort and may be delayed."
        } else {
            status = "Notification permission was denied. Reminders remain available in the app."
        }
    }
    val liveVoicePermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) startLiveVoice()
        else liveVoiceStatus = "Microphone permission was denied. Typed chat remains available."
    }
    val tts = remember {
        TextToSpeech(context) { result ->
            if (result == TextToSpeech.SUCCESS) {
                // Use the installed system voice. No audio is sent by text-to-speech.
            }
        }
    }
    DisposableEffect(Unit) {
        onDispose {
            tts.stop()
            tts.shutdown()
        }
    }
    LaunchedEffect(reply) {
        if (!reply.startsWith("Connect to your private")) {
            tts.language = Locale.getDefault().let { locale ->
                if (language == "te") Locale("te", "IN") else Locale("en", "IN")
            }
            tts.speak(reply, TextToSpeech.QUEUE_FLUSH, null, "jarvis-reply")
        }
    }

    // One poll of the bounded backend activity feed; never throws.
    suspend fun refreshActivity() {
        try {
            val base = TokenVault.readBackendUrl(context) ?: endpoint.trim().trimEnd('/')
            val activeToken = TokenVault.read(context) ?: token
            if (base.isBlank() || activeToken.length < 32) return
            val result = withContext(Dispatchers.IO) {
                request("$base/api/runtime/events?after_id=$runtimeCursor&limit=20", null, activeToken)
            }
            if (result.first != 200) return
            val parsed = JSONObject(result.second)
            val events = parsed.optJSONArray("events") ?: return
            val lines = mutableListOf<Pair<Int, String>>()
            for (i in 0 until events.length()) {
                val event = events.optJSONObject(i) ?: continue
                val id = event.optInt("id", 0)
                val category = event.optString("category", "event")
                val detail = event.optString("tool",
                    event.optString("provider", event.optString("action", event.optString("task_id", ""))))
                val risk = event.optString("risk", "")
                val outcome = if (event.has("success")) {
                    if (event.optBoolean("success")) "ok" else "failed"
                } else ""
                val timestamp = event.optString("timestamp", "").take(19).replace("T", " ")
                val label = buildString {
                    append(category)
                    if (detail.isNotBlank()) append(" · ").append(detail)
                    if (risk.isNotBlank()) append(" · risk: ").append(risk)
                    if (outcome.isNotBlank()) append(" · ").append(outcome)
                }
                if (id > 0) lines.add(id to "$timestamp  $label")
            }
            if (lines.isNotEmpty()) {
                runtimeCursor = lines.maxOf { it.first }
                runtimeEvents = (lines.map { it.second } + runtimeEvents).take(8)
            }
        } catch (_: Exception) {
            // The feed is best-effort; chat continues when the backend is unreachable.
        }
    }

    // Poll the backend activity feed while this screen is alive.
    LaunchedEffect(Unit) {
        while (true) {
            refreshActivity()
            delay(20_000)
        }
    }

    val connected = endpoint.isNotBlank() && token.length >= 32
    val orbState = when {
        !connected -> OrbState.OFFLINE
        voiceBusy || liveVoiceActive -> OrbState.LISTENING
        busy -> OrbState.BUSY
        else -> OrbState.IDLE
    }

    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        // Command-centre header: AI core orb + status bar.
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            JarvisOrb(state = orbState, modifier = Modifier.size(96.dp))
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(
                    "JARVIS",
                    style = MaterialTheme.typography.headlineLarge,
                    color = MaterialTheme.colorScheme.primary,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    when (orbState) {
                        OrbState.OFFLINE -> "CORE OFFLINE - connect to your backend"
                        OrbState.LISTENING -> "LISTENING"
                        OrbState.BUSY -> "WORKING"
                        OrbState.SPEAKING -> "SPEAKING"
                        OrbState.IDLE -> "CORE ONLINE - systems ready"
                    },
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Text(
                    "Voice is user-initiated; no always-on microphone.",
                    style = MaterialTheme.typography.bodySmall,
                    color = TextMuted,
                )
            }
        }

        SectionCard(title = "CONNECTION") {
            OutlinedTextField(
                value = endpoint,
                onValueChange = { endpoint = it.trimEnd('/') },
                label = { Text("HTTPS backend URL") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true
            )
            OutlinedTextField(
                value = token,
                onValueChange = { token = it },
                label = { Text("Device token") },
                visualTransformation = PasswordVisualTransformation(),
                modifier = Modifier.fillMaxWidth(),
                singleLine = true
            )
            Button(
                enabled = !busy,
                onClick = {
                    scope.launch {
                        busy = true
                        status = "Checking HTTPS backend…"
                        try {
                            val base = endpoint.trim().trimEnd('/')
                            require(base.startsWith("https://") && URL(base).host.isNotBlank()) { "Enter a valid HTTPS backend URL." }
                            require(token.length >= 32 && !token.startsWith("replace_")) { "Enter the real device token (at least 32 characters)." }
                            val code = withContext(Dispatchers.IO) { request(base + "/health", null, null) }
                            require(code.first == 200) { "Backend health check returned HTTP ${code.first}." }
                            val previousToken = TokenVault.read(context)
                            TokenVault.store(context, token)
                            TokenVault.storeBackendUrl(context, base)
                            if (previousToken != token) {
                                TokenVault.clearDeviceId(context)
                                pairedDeviceId = ""
                            }
                            status = "Connected to backend. Token encrypted on this device."
                        } catch (error: Exception) {
                            status = error.message ?: "Connection failed."
                        } finally { busy = false }
                    }
                }
            ) { Text(if (busy) "Connecting…" else "Connect securely") }

            Text("Pair this Android device", style = MaterialTheme.typography.titleSmall)
            Text(
                "Use the backend master token once to issue a device token. The master token is never stored by this app.",
                style = MaterialTheme.typography.bodySmall,
                color = TextMuted,
            )
            OutlinedTextField(
                value = deviceName,
                onValueChange = { deviceName = it },
                label = { Text("Device name") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true
            )
            OutlinedTextField(
                value = masterToken,
                onValueChange = { masterToken = it },
                label = { Text("Backend master token (pairing only)") },
                visualTransformation = PasswordVisualTransformation(),
                modifier = Modifier.fillMaxWidth(),
                singleLine = true
            )
            Button(enabled = !busy && pairedDeviceId.isBlank(), onClick = {
                scope.launch {
                    busy = true
                    status = "Pairing this device securely…"
                    try {
                        val base = endpoint.trim().trimEnd('/')
                        val bootstrapToken = masterToken.trim()
                        require(base.startsWith("https://") && URL(base).host.isNotBlank()) { "Enter a valid HTTPS backend URL." }
                        require(bootstrapToken.length >= 32 && !bootstrapToken.startsWith("replace_")) { "Enter the configured master API token." }
                        require(deviceName.isNotBlank()) { "Enter a name for this device." }
                        val payload = JSONObject().put("name", deviceName.trim()).toString()
                        val result = withContext(Dispatchers.IO) {
                            request(base + "/api/devices/issue", payload, bootstrapToken)
                        }
                        val parsed = JSONObject(result.second)
                        require(result.first in 200..299) {
                            parsed.optString("detail", "Device pairing failed with HTTP ${result.first}.")
                        }
                        val issuedToken = parsed.optString("token")
                        val issuedDeviceId = parsed.optString("device_id")
                        require(issuedToken.length >= 32 && issuedDeviceId.isNotBlank()) { "Backend returned incomplete pairing details." }
                        TokenVault.store(context, issuedToken)
                        TokenVault.storeBackendUrl(context, base)
                        TokenVault.storeDeviceId(context, issuedDeviceId)
                        token = issuedToken
                        endpoint = base
                        pairedDeviceId = issuedDeviceId
                        status = "Paired as ${parsed.optString("name", deviceName)}. Device token encrypted on this phone."
                    } catch (error: Exception) {
                        status = error.message ?: "Device pairing failed."
                    } finally {
                        masterToken = ""
                        busy = false
                    }
                }
            }) { Text(if (pairedDeviceId.isNotBlank()) "Revoke existing pairing first" else if (busy) "Pairing…" else "Pair device") }

            if (pairedDeviceId.isNotBlank()) {
                Button(enabled = !busy, onClick = { showRevokeConfirmation = true }) { Text("Revoke paired device") }
            }
            if (showRevokeConfirmation) {
                AlertDialog(
                    onDismissRequest = { showRevokeConfirmation = false },
                    title = { Text("Revoke this device token?") },
                    text = { Text("Enter the master token in the pairing field above before confirming. This immediately disables this phone's paired token and clears it from this phone.") },
                    confirmButton = {
                        TextButton(onClick = {
                            showRevokeConfirmation = false
                            scope.launch {
                                busy = true
                                try {
                                    val base = TokenVault.readBackendUrl(context) ?: endpoint.trim().trimEnd('/')
                                    val bootstrapToken = masterToken.trim()
                                    require(base.startsWith("https://") && URL(base).host.isNotBlank()) { "Reconnect to the HTTPS backend first." }
                                    require(bootstrapToken.length >= 32 && !bootstrapToken.startsWith("replace_")) { "Enter the configured master API token before revoking." }
                                    val deviceId = TokenVault.readDeviceId(context) ?: pairedDeviceId
                                    require(deviceId.isNotBlank()) { "No paired device ID is stored on this phone." }
                                    val result = withContext(Dispatchers.IO) {
                                        request("$base/api/devices/$deviceId", null, bootstrapToken, "DELETE")
                                    }
                                    val parsed = JSONObject(result.second)
                                    require(result.first in 200..299) {
                                        parsed.optString("detail", "Device revocation failed with HTTP ${result.first}.")
                                    }
                                    TokenVault.clear(context)
                                    ReminderWorker.setEnabled(context, false)
                                    reminderNotificationsEnabled = false
                                    liveVoiceController.stop()
                                    liveVoiceActive = false
                                    token = ""
                                    endpoint = ""
                                    pairedDeviceId = ""
                                    status = "Device token revoked on the backend and cleared from this phone."
                                } catch (error: Exception) {
                                    status = error.message ?: "Device revocation failed."
                                } finally {
                                    masterToken = ""
                                    busy = false
                                }
                            }
                        }) { Text("Revoke device") }
                    },
                    dismissButton = {
                        TextButton(onClick = { showRevokeConfirmation = false }) { Text("Cancel") }
                    }
                )
            }
            Button(onClick = { language = when (language) { "auto" -> "en"; "en" -> "te"; else -> "auto" } }) { Text("Reply language: $language (tap to change)") }
        }

        SectionCard(title = "TALK TO JARVIS") {
            Text(
                when (personalityMode) {
                    "doctor" -> "Doctor mode gives general health information only - it is not a doctor and not medical advice."
                    "storyteller" -> "Storyteller mode tells original stories on request."
                    else -> "Choose how JARVIS talks to you."
                },
                style = MaterialTheme.typography.bodySmall,
                color = TextMuted,
            )
            Row(
                modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                PERSONALITY_MODES.forEach { (modeKey, label) ->
                    FilterChip(
                        selected = personalityMode == modeKey,
                        onClick = {
                            personalityMode = modeKey
                            context.getSharedPreferences("jarvis_reminder_settings", android.content.Context.MODE_PRIVATE)
                                .edit().putString("personality_mode", modeKey).apply()
                        },
                        label = { Text(label) },
                    )
                }
            }
            if (conversation.isNotEmpty()) {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    conversation.takeLast(6).forEach { turn ->
                        Text(
                            (if (turn.role == "user") "YOU  " else "JARVIS  ") + turn.content,
                            style = MaterialTheme.typography.bodyMedium,
                            color = if (turn.role == "user") MaterialTheme.colorScheme.secondary else MaterialTheme.colorScheme.onSurface,
                        )
                    }
                }
            } else {
                Text(reply, style = MaterialTheme.typography.bodyMedium)
            }
            OutlinedTextField(
                value = message,
                onValueChange = { message = it },
                label = { Text("Message JARVIS") },
                modifier = Modifier.fillMaxWidth()
            )
            Row(
                modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                QUICK_ACTIONS.forEach { prompt ->
                    AssistChip(
                        onClick = {
                            message = prompt
                            status = "Quick action ready. Tap Send."
                        },
                        label = { Text(prompt) },
                    )
                }
            }
            Button(
                enabled = !busy && !voiceBusy,
                onClick = {
                    if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) ==
                        android.content.pm.PackageManager.PERMISSION_GRANTED
                    ) {
                        launchSpeech(speechLauncher, language) { voiceBusy = it }
                    } else {
                        permissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                    }
                }
            ) { Text(if (voiceBusy) "Listening…" else "Speak to JARVIS") }
            Button(
                enabled = !busy && phoneSettingsAction != null,
                onClick = {
                    val action = phoneSettingsAction
                    if (action != null) {
                        val uri = if (action == Settings.ACTION_APPLICATION_DETAILS_SETTINGS) Uri.parse("package:" + context.packageName) else null
                        openSystemSettings(context, action, status = { status = it }, uri = uri)
                    }
                }
            ) { Text("Run recognized phone command") }
            Text(
                "Supported voice commands: open device settings, open Wi-Fi settings, open Bluetooth settings, open JARVIS app permissions.",
                style = MaterialTheme.typography.bodySmall,
                color = TextMuted,
            )
            Button(
                enabled = !busy && message.isNotBlank(),
                onClick = {
                    scope.launch {
                        busy = true
                        try {
                            val base = endpoint.trim().trimEnd('/')
                            require(base.startsWith("https://")) { "Connect to an HTTPS backend first." }
                            val activeToken = TokenVault.read(context) ?: token
                            require(activeToken.length >= 32) { "Connect with a device token first." }
                            val sent = message.trim()
                            val history = JSONArray()
                            conversation.takeLast(10).forEach { turn ->
                                history.put(JSONObject().put("role", turn.role).put("content", turn.content))
                            }
                            val payload = JSONObject().put("message", sent)
                                .put("language", language)
                                .put("mode", personalityMode)
                                .put("history", history)
                                .toString()
                            val result = withContext(Dispatchers.IO) {
                                request(base + "/api/chat", payload, activeToken)
                            }
                            val parsed = JSONObject(result.second)
                            if (result.first !in 200..299) {
                                throw IllegalStateException(parsed.optString("detail", "Chat failed with HTTP ${result.first}."))
                            }
                            reply = parsed.optString("reply", "JARVIS returned no text.")
                            conversation = (conversation + ChatTurn("user", sent) + ChatTurn("model", reply)).takeLast(20)
                            message = ""
                            status = "Message sent securely over HTTPS."
                        } catch (error: Exception) {
                            status = error.message ?: "Chat request failed."
                        } finally { busy = false }
                    }
                }
            ) { Text(if (busy) "Working…" else "Send") }
        }

        SectionCard(title = "ACTIVITY & APPROVALS") {
            Text(
                "Live feed from your JARVIS backend. JARVIS still asks before anything sensitive or irreversible - confirmations stay on your laptop; this feed shows you what it is doing.",
                style = MaterialTheme.typography.bodySmall,
                color = TextMuted,
            )
            if (runtimeEvents.isEmpty()) {
                Text(
                    "No backend activity yet. Events appear here while the app is open.",
                    style = MaterialTheme.typography.bodyMedium,
                )
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    runtimeEvents.forEach { eventLine ->
                        Text(eventLine, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurface)
                    }
                }
            }
            TextButton(enabled = !busy, onClick = { scope.launch { refreshActivity() } }) { Text("Refresh activity now") }
        }

        SectionCard(title = "LIVE VOICE") {
            Text(
                "Starts only after you tap and grant microphone permission. Audio is sent to your configured Gemini Live backend.",
                style = MaterialTheme.typography.bodySmall,
                color = TextMuted,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(enabled = !busy && !liveVoiceActive, onClick = {
                    if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) ==
                        android.content.pm.PackageManager.PERMISSION_GRANTED
                    ) {
                        startLiveVoice()
                    } else {
                        liveVoicePermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                    }
                }) { Text("Start Live Voice") }
                Button(enabled = liveVoiceActive, onClick = { liveVoiceController.interrupt() }) { Text("Interrupt") }
                Button(enabled = liveVoiceActive, onClick = { liveVoiceController.stop() }) { Text("Stop") }
            }
            Text(liveVoiceStatus, style = MaterialTheme.typography.bodyMedium)
        }

        SectionCard(title = "PHONE CONTROLS") {
            Text(
                "These open Android's own settings screens. JARVIS does not silently toggle protected settings.",
                style = MaterialTheme.typography.bodySmall,
                color = TextMuted,
            )
            Row(
                modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Button(onClick = { openSystemSettings(context, Settings.ACTION_SETTINGS, status = { status = it }) }) { Text("Device settings") }
                Button(onClick = { openSystemSettings(context, Settings.ACTION_WIFI_SETTINGS, status = { status = it }) }) { Text("Wi-Fi") }
                Button(onClick = { openSystemSettings(context, Settings.ACTION_BLUETOOTH_SETTINGS, status = { status = it }) }) { Text("Bluetooth") }
                Button(onClick = {
                    openSystemSettings(context, Settings.ACTION_APPLICATION_DETAILS_SETTINGS, status = { status = it },
                        uri = Uri.parse("package:" + context.packageName))
                }) { Text("App permissions") }
            }
        }

        SectionCard(title = "REMINDERS & ROUTINES") {
            Text(
                "Use an ISO-8601 date/time with timezone, for example 2026-10-27T08:00:00+05:30.",
                style = MaterialTheme.typography.bodySmall,
                color = TextMuted,
            )
            OutlinedTextField(
                value = reminderTitle,
                onValueChange = { reminderTitle = it },
                label = { Text("Reminder title") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true
            )
            OutlinedTextField(
                value = reminderDueAt,
                onValueChange = { reminderDueAt = it },
                label = { Text("Due date/time with timezone") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = {
                    reminderRecurrence = when (reminderRecurrence) {
                        "none" -> "daily"
                        "daily" -> "weekly"
                        "weekly" -> "monthly"
                        else -> "none"
                    }
                }) { Text("Repeat: $reminderRecurrence") }
                Button(enabled = !busy && reminderTitle.isNotBlank() && reminderDueAt.isNotBlank(), onClick = {
                    scope.launch {
                        busy = true
                        try {
                            val base = endpoint.trim().trimEnd('/')
                            val activeToken = TokenVault.read(context) ?: token
                            require(base.startsWith("https://") && activeToken.length >= 32) { "Connect securely before creating reminders." }
                            val payload = JSONObject().put("title", reminderTitle.trim())
                                .put("due_at", reminderDueAt.trim()).put("recurrence", reminderRecurrence).toString()
                            val result = withContext(Dispatchers.IO) { request(base + "/api/reminders", payload, activeToken) }
                            val parsed = JSONObject(result.second)
                            if (result.first !in 200..299) throw IllegalStateException(parsed.optString("detail", "Reminder creation failed (${result.first})."))
                            reminderTitle = ""
                            status = "Reminder saved to your authenticated JARVIS backend."
                        } catch (error: Exception) {
                            status = error.message ?: "Could not create reminder."
                        } finally { busy = false }
                    }
                }) { Text("Create") }
                Button(enabled = !busy, onClick = {
                    scope.launch {
                        busy = true
                        try {
                            val base = endpoint.trim().trimEnd('/')
                            val activeToken = TokenVault.read(context) ?: token
                            require(base.startsWith("https://") && activeToken.length >= 32) { "Connect securely before loading reminders." }
                            val result = withContext(Dispatchers.IO) { request(base + "/api/reminders", null, activeToken) }
                            val parsed = JSONObject(result.second)
                            if (result.first !in 200..299) throw IllegalStateException(parsed.optString("detail", "Could not load reminders (${result.first})."))
                            reminders = parseReminderItems(result.second)
                            status = "Loaded ${reminders.size} reminder(s)."
                        } catch (error: Exception) {
                            status = error.message ?: "Could not load reminders."
                        } finally { busy = false }
                    }
                }) { Text("Refresh") }
            }
            reminders.forEach { reminder ->
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    val repeatLabel = if (reminder.recurrence == "none") "" else " · ${reminder.recurrence}"
                    Text(
                        "${reminder.title} — ${reminder.dueAt}$repeatLabel",
                        modifier = Modifier.weight(1f),
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    Button(enabled = !busy && !reminder.completed, onClick = {
                        scope.launch {
                            busy = true
                            try {
                                val base = endpoint.trim().trimEnd('/')
                                val activeToken = TokenVault.read(context) ?: token
                                require(base.startsWith("https://") && activeToken.length >= 32) { "Connect securely before completing reminders." }
                                val completion = withContext(Dispatchers.IO) {
                                    request(base + "/api/reminders/${reminder.id}/complete", "{}", activeToken, "POST")
                                }
                                val completed = JSONObject(completion.second)
                                if (completion.first !in 200..299) {
                                    throw IllegalStateException(completed.optString("detail", "Reminder completion failed (${completion.first})."))
                                }
                                val refreshed = withContext(Dispatchers.IO) {
                                    request(base + "/api/reminders", null, activeToken)
                                }
                                if (refreshed.first !in 200..299) throw IllegalStateException("Reminder was completed but the list refresh failed.")
                                reminders = parseReminderItems(refreshed.second)
                                status = if (completed.optBoolean("completed", true)) {
                                    "Reminder completed."
                                } else {
                                    "Reminder completed; next occurrence scheduled."
                                }
                            } catch (error: Exception) {
                                status = error.message ?: "Could not complete reminder."
                            } finally { busy = false }
                        }
                    }) { Text(if (reminder.completed) "Done" else "Complete") }
                }
            }
            Text("Android notifications", style = MaterialTheme.typography.titleSmall)
            Text(
                "When enabled, JARVIS checks the backend about every 15 minutes while network access is available. Delivery may be delayed; this is not an alarm service.",
                style = MaterialTheme.typography.bodySmall,
                color = TextMuted,
            )
            Button(onClick = {
                if (reminderNotificationsEnabled) {
                    ReminderWorker.setEnabled(context, false)
                    reminderNotificationsEnabled = false
                    status = "Android reminder notifications disabled."
                } else {
                    val savedEndpoint = TokenVault.readBackendUrl(context)
                    val savedToken = TokenVault.read(context)
                    if (savedEndpoint.isNullOrBlank() || savedToken.isNullOrBlank()) {
                        status = "Connect securely before enabling reminder notifications."
                    } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
                        context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) !=
                        android.content.pm.PackageManager.PERMISSION_GRANTED
                    ) {
                        notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                    } else {
                        ReminderWorker.setEnabled(context, true)
                        reminderNotificationsEnabled = true
                        status = "Android reminder notifications enabled. Delivery is best-effort and may be delayed."
                    }
                }
            }) { Text(if (reminderNotificationsEnabled) "Disable Android notifications" else "Enable Android notifications") }
        }

        SectionCard(title = "EXPLICIT MEMORIES") {
            Text(
                "Save only facts or preferences you choose to keep. Review or delete them here.",
                style = MaterialTheme.typography.bodySmall,
                color = TextMuted,
            )
            OutlinedTextField(
                value = memoryText,
                onValueChange = { memoryText = it },
                label = { Text("Memory to save") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(enabled = !busy && memoryText.isNotBlank(), onClick = {
                    scope.launch {
                        busy = true
                        try {
                            val base = endpoint.trim().trimEnd('/')
                            val activeToken = TokenVault.read(context) ?: token
                            require(base.startsWith("https://") && activeToken.length >= 32) { "Connect securely before saving memories." }
                            val payload = JSONObject().put("text", memoryText.trim()).put("category", "general").toString()
                            val result = withContext(Dispatchers.IO) {
                                request(base + "/api/memories", payload, activeToken)
                            }
                            val parsed = JSONObject(result.second)
                            if (result.first !in 200..299) throw IllegalStateException(parsed.optString("detail", "Memory save failed (${result.first})."))
                            memoryText = ""
                            status = "Memory saved. Refresh to review it."
                        } catch (error: Exception) {
                            status = error.message ?: "Could not save memory."
                        } finally { busy = false }
                    }
                }) { Text("Save memory") }
                Button(enabled = !busy, onClick = {
                    scope.launch {
                        busy = true
                        try {
                            val base = endpoint.trim().trimEnd('/')
                            val activeToken = TokenVault.read(context) ?: token
                            require(base.startsWith("https://") && activeToken.length >= 32) { "Connect securely before loading memories." }
                            val result = withContext(Dispatchers.IO) {
                                request(base + "/api/memories", null, activeToken)
                            }
                            val parsed = JSONObject(result.second)
                            if (result.first !in 200..299) throw IllegalStateException(parsed.optString("detail", "Memory list failed (${result.first})."))
                            val items = parsed.optJSONArray("items")
                            memories = (0 until (items?.length() ?: 0)).mapNotNull { i ->
                                items?.optJSONObject(i)?.let { item ->
                                    item.optInt("id") to (item.optString("category") + ": " + item.optString("text"))
                                }
                            }
                            status = "Loaded ${memories.size} saved memory(s)."
                        } catch (error: Exception) {
                            status = error.message ?: "Could not load memories."
                        } finally { busy = false }
                    }
                }) { Text("Review memories") }
            }
            memories.forEach { (id, text) ->
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(text, style = MaterialTheme.typography.bodyMedium)
                    TextButton(enabled = !busy, onClick = {
                        scope.launch {
                            busy = true
                            try {
                                val base = endpoint.trim().trimEnd('/')
                                val activeToken = TokenVault.read(context) ?: token
                                require(base.startsWith("https://") && activeToken.length >= 32) { "Connect securely before deleting memories." }
                                val result = withContext(Dispatchers.IO) {
                                    request(base + "/api/memories/$id", null, activeToken, "DELETE")
                                }
                                if (result.first !in 200..299) throw IllegalStateException("Memory deletion failed (${result.first}).")
                                memories = memories.filterNot { it.first == id }
                                status = "Memory deleted."
                            } catch (error: Exception) {
                                status = error.message ?: "Could not delete memory."
                            } finally { busy = false }
                        }
                    }) { Text("Delete") }
                }
            }
        }

        SectionCard(title = "THIS DEVICE") {
            Button(onClick = {
                TokenVault.clear(context)
                ReminderWorker.setEnabled(context, false)
                reminderNotificationsEnabled = false
                liveVoiceController.stop()
                liveVoiceActive = false
                token = ""
                endpoint = ""
                pairedDeviceId = ""
                status = "Local credentials cleared. The backend token remains active until an administrator revokes it."
            }) { Text("Forget device token") }
            Text(status, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

private fun launchSpeech(
    launcher: androidx.activity.result.ActivityResultLauncher<Intent>,
    language: String,
    setBusy: (Boolean) -> Unit
) {
    try {
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, if (language == "te") "te-IN" else "en-IN")
            putExtra(RecognizerIntent.EXTRA_PROMPT, "Speak to JARVIS")
        }
        setBusy(true)
        launcher.launch(intent)
    } catch (error: Exception) {
        setBusy(false)
    }
}

private fun request(url: String, body: String?, token: String?, method: String? = null): Pair<Int, String> {
    val connection = URL(url).openConnection() as HttpURLConnection
    try {
        connection.connectTimeout = 8000
        connection.readTimeout = 15000
        connection.requestMethod = method ?: if (body == null) "GET" else "POST"
        connection.setRequestProperty("Accept", "application/json")
        if (token != null) connection.setRequestProperty("Authorization", "Bearer $token")
        if (body != null) {
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
        }
        val code = connection.responseCode
        val stream = if (code in 200..299) connection.inputStream else connection.errorStream
        val text = stream?.bufferedReader()?.use { it.readText() } ?: "{}"
        return code to text
    } finally {
        connection.disconnect()
    }
}


private fun openSystemSettings(
    context: android.content.Context,
    action: String,
    status: (String) -> Unit,
    uri: Uri? = null
) {
    try {
        val intent = Intent(action).apply {
            if (uri != null) data = uri
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        context.startActivity(intent)
        status("Opened Android settings. Review and confirm changes in the system screen.")
    } catch (error: Exception) {
        status("This Android settings screen is not available on this device.")
    }
}
