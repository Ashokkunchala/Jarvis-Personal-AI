package com.ashok.jarvis

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
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

    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text("JARVIS Personal AI", style = MaterialTheme.typography.headlineMedium)
        Text("Native Android prototype • Device token is encrypted with Android Keystore.")
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

        Text("Chat", style = MaterialTheme.typography.titleLarge)
        Text(reply)
        OutlinedTextField(
            value = message,
            onValueChange = { message = it },
            label = { Text("Message JARVIS") },
            modifier = Modifier.fillMaxWidth()
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
                        val payload = JSONObject().put("message", message.trim()).put("language", "auto").toString()
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
