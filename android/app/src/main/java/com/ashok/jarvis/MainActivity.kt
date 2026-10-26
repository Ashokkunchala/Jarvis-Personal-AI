package com.ashok.jarvis

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.net.Uri
import android.provider.Settings
import android.speech.RecognizerIntent
import android.speech.tts.TextToSpeech
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.Locale

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) { SetupScreen() }
            }
        }
    }
}

@Composable
private fun SetupScreen() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var endpoint by remember { mutableStateOf("") }
    var token by remember { mutableStateOf(runCatching { TokenVault.read(context).orEmpty() }.getOrDefault("")) }
    var message by remember { mutableStateOf("") }
    var reply by remember { mutableStateOf("Connect to your private HTTPS backend to start chatting.") }
    var status by remember { mutableStateOf("Enter the HTTPS backend URL and device token.") }
    var busy by remember { mutableStateOf(false) }
    var voiceBusy by remember { mutableStateOf(false) }
    var language by remember { mutableStateOf("auto") }
    var reminderTitle by remember { mutableStateOf("") }
    var reminderDueAt by remember { mutableStateOf("") }
    var reminders by remember { mutableStateOf(listOf<String>()) }

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

    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text("JARVIS Personal AI", style = MaterialTheme.typography.headlineMedium)
        Text("Native Android prototype • Voice is user-initiated; no always-on microphone.")
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
                        TokenVault.store(context, token)
                        status = "Connected to backend. Token encrypted on this device."
                    } catch (error: Exception) {
                        status = error.message ?: "Connection failed."
                    } finally { busy = false }
                }
            }
        ) { Text(if (busy) "Connecting…" else "Connect securely") }

        Button(onClick = { language = when (language) { "auto" -> "en"; "en" -> "te"; else -> "auto" } }) { Text("Reply language: $language (tap to change)") }
        Text("Phone quick controls", style = MaterialTheme.typography.titleLarge)
        Text("These open Android's own settings screens. JARVIS does not silently toggle protected settings.")
        Button(onClick = { openSystemSettings(context, Settings.ACTION_SETTINGS, status = { status = it }) }) { Text("Open device settings") }
        Button(onClick = { openSystemSettings(context, Settings.ACTION_WIFI_SETTINGS, status = { status = it }) }) { Text("Open Wi-Fi settings") }
        Button(onClick = { openSystemSettings(context, Settings.ACTION_BLUETOOTH_SETTINGS, status = { status = it }) }) { Text("Open Bluetooth settings") }
        Button(onClick = {
            openSystemSettings(context, Settings.ACTION_APPLICATION_DETAILS_SETTINGS, status = { status = it },
                uri = Uri.parse("package:" + context.packageName))
        }) { Text("Open JARVIS app permissions") }

        Text("Reminders & routines", style = MaterialTheme.typography.titleLarge)
        Text("Use an ISO-8601 date/time with timezone, for example 2026-10-27T08:00:00+05:30.")
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
        Button(enabled = !busy && reminderTitle.isNotBlank() && reminderDueAt.isNotBlank(), onClick = {
            scope.launch {
                busy = true
                try {
                    val base = endpoint.trim().trimEnd('/')
                    val activeToken = TokenVault.read(context) ?: token
                    require(base.startsWith("https://") && activeToken.length >= 32) { "Connect securely before creating reminders." }
                    val payload = JSONObject().put("title", reminderTitle.trim()).put("due_at", reminderDueAt.trim()).toString()
                    val result = withContext(Dispatchers.IO) { request(base + "/api/reminders", payload, activeToken) }
                    val parsed = JSONObject(result.second)
                    if (result.first !in 200..299) throw IllegalStateException(parsed.optString("detail", "Reminder creation failed (${result.first})."))
                    reminderTitle = ""
                    status = "Reminder saved to your authenticated JARVIS backend."
                } catch (error: Exception) {
                    status = error.message ?: "Could not create reminder."
                } finally { busy = false }
            }
        }) { Text("Create reminder") }
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
                    val items = parsed.optJSONArray("items")
                    reminders = (0 until (items?.length() ?: 0)).mapNotNull { i ->
                        items?.optJSONObject(i)?.let { item ->
                            val done = item.optInt("completed", 0) == 1
                            "${if (done) "✓" else "○"} ${item.optString("title")} — ${item.optString("due_at")}"
                        }
                    }
                    status = "Loaded ${reminders.size} reminder(s)."
                } catch (error: Exception) {
                    status = error.message ?: "Could not load reminders."
                } finally { busy = false }
            }
        }) { Text("Refresh reminders") }
        reminders.forEach { Text(it, style = MaterialTheme.typography.bodyMedium) }

        Text("Chat", style = MaterialTheme.typography.titleLarge)
        Text(reply)
        OutlinedTextField(
            value = message,
            onValueChange = { message = it },
            label = { Text("Message JARVIS") },
            modifier = Modifier.fillMaxWidth()
        )
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
            enabled = !busy && message.isNotBlank(),
            onClick = {
                scope.launch {
                    busy = true
                    try {
                        val base = endpoint.trim().trimEnd('/')
                        require(base.startsWith("https://")) { "Connect to an HTTPS backend first." }
                        val activeToken = TokenVault.read(context) ?: token
                        require(activeToken.length >= 32) { "Connect with a device token first." }
                        val payload = JSONObject().put("message", message.trim()).put("language", language).toString()
                        val result = withContext(Dispatchers.IO) {
                            request(base + "/api/chat", payload, activeToken)
                        }
                        val parsed = JSONObject(result.second)
                        if (result.first !in 200..299) {
                            throw IllegalStateException(parsed.optString("detail", "Chat failed with HTTP ${result.first}."))
                        }
                        reply = parsed.optString("reply", "JARVIS returned no text.")
                        message = ""
                        status = "Message sent securely over HTTPS."
                    } catch (error: Exception) {
                        status = error.message ?: "Chat request failed."
                    } finally { busy = false }
                }
            }
        ) { Text(if (busy) "Working…" else "Send") }

        Button(onClick = {
            TokenVault.clear(context)
            token = ""
            status = "Stored device token cleared from this device."
        }) { Text("Forget device token") }
        Text(status)
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

private fun request(url: String, body: String?, token: String?): Pair<Int, String> {
    val connection = URL(url).openConnection() as HttpURLConnection
    try {
        connection.connectTimeout = 8000
        connection.readTimeout = 15000
        connection.requestMethod = if (body == null) "GET" else "POST"
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
