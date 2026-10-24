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
import java.net.HttpURLConnection
import java.net.URL

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    SetupScreen()
                }
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
    var status by remember { mutableStateOf("Enter your HTTPS backend URL and device token. No data is sent until you press Connect.") }
    var busy by remember { mutableStateOf(false) }

    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Text("JARVIS Personal AI", style = MaterialTheme.typography.headlineMedium)
        Text("Native Android starter • Token is encrypted with an Android Keystore key on this device.")
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
                    status = "Checking secure backend connection…"
                    try {
                        val normalized = endpoint.trim().trimEnd('/')
                        require(normalized.startsWith("https://")) { "Use HTTPS. Plain HTTP is disabled." }
                        require(URL(normalized).host.isNotBlank()) { "Enter a valid HTTPS URL." }
                        require(token.length >= 32 && !token.startsWith("replace_")) { "Enter the real device token (at least 32 characters)." }
                        val code = withContext(Dispatchers.IO) {
                            val connection = (URL("$normalized/health").openConnection() as HttpURLConnection)
                            try {
                                connection.connectTimeout = 5000
                                connection.readTimeout = 5000
                                connection.requestMethod = "GET"
                                connection.responseCode
                            } finally {
                                connection.disconnect()
                            }
                        }
                        require(code == 200) { "Backend health check returned HTTP $code." }
                        TokenVault.store(context, token)
                        status = "Backend reachable. Token encrypted on this device. Authenticated API pairing/chat is the next integration step."
                    } catch (error: Exception) {
                        status = error.message ?: "Connection failed. Check URL and network."
                    } finally {
                        busy = false
                    }
                }
            }
        ) { Text(if (busy) "Connecting…" else "Connect securely") }
        Button(onClick = {
            TokenVault.clear(context)
            token = ""
            status = "Stored device token cleared from this device."
        }) { Text("Forget device token") }
        Text(status)
    }
}
