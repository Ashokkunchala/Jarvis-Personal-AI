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
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp

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
    var endpoint by remember { mutableStateOf("https://your-secure-jarvis-host.example") }
    var token by remember { mutableStateOf("") }
    var status by remember { mutableStateOf("Not connected. Secure backend pairing is not implemented yet.") }
    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Text("JARVIS Personal AI", style = MaterialTheme.typography.headlineMedium)
        Text("Native Android starter • Voice and device actions will request permissions only when implemented.")
        OutlinedTextField(
            value = endpoint,
            onValueChange = { endpoint = it },
            label = { Text("HTTPS backend URL") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true
        )
        OutlinedTextField(
            value = token,
            onValueChange = { token = it },
            label = { Text("Device token (not stored yet)") },
            visualTransformation = PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth(),
            singleLine = true
        )
        Button(onClick = {
            status = if (!endpoint.startsWith("https://")) {
                "Use HTTPS. Plain HTTP is disabled for security."
            } else if (token.length < 32) {
                "A secure device token must be at least 32 characters."
            } else {
                "Inputs validated locally. Network pairing is not implemented; no data was sent or stored."
            }
        }) { Text("Validate setup") }
        Text(status)
    }
}
