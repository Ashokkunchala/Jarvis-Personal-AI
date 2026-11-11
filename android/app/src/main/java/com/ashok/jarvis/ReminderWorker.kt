package com.ashok.jarvis

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.TimeUnit

/** Best-effort due-reminder polling; never stores credentials in WorkManager input data. */
class ReminderWorker(context: Context, parameters: WorkerParameters) : CoroutineWorker(context, parameters) {
    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val context = applicationContext
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            return@withContext Result.success()
        }
        val manager = context.getSystemService(NotificationManager::class.java)
        if (!manager.areNotificationsEnabled()) return@withContext Result.success()

        val backendUrl = TokenVault.readBackendUrl(context) ?: return@withContext Result.failure()
        val token = TokenVault.read(context) ?: return@withContext Result.failure()
        try {
            val connection = URL("${backendUrl.trimEnd('/')}/api/reminders/due")
                .openConnection() as HttpURLConnection
            val (statusCode, body) = try {
                connection.connectTimeout = 8_000
                connection.readTimeout = 15_000
                connection.requestMethod = "GET"
                connection.setRequestProperty("Accept", "application/json")
                connection.setRequestProperty("Authorization", "Bearer $token")
                val code = connection.responseCode
                val stream = if (code in 200..299) connection.inputStream else connection.errorStream
                code to (stream?.bufferedReader()?.use { it.readText() } ?: "{}")
            } finally {
                connection.disconnect()
            }
            if (statusCode == 401 || statusCode == 403) return@withContext Result.failure()
            if (statusCode !in 200..299) return@withContext Result.retry()

            val items = JSONObject(body).optJSONArray("items") ?: return@withContext Result.success()
            val preferences = context.getSharedPreferences(STATE_STORE, Context.MODE_PRIVATE)
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, "JARVIS reminders", NotificationManager.IMPORTANCE_DEFAULT)
            )
            if (manager.getNotificationChannel(CHANNEL_ID)?.importance == NotificationManager.IMPORTANCE_NONE) {
                return@withContext Result.success()
            }
            for (index in 0 until items.length()) {
                val reminder = items.optJSONObject(index) ?: continue
                val id = reminder.optInt("id", -1)
                val dueAt = reminder.optString("due_at")
                if (id < 0 || dueAt.isBlank() || preferences.getString("due_$id", null) == dueAt) continue

                val openApp = PendingIntent.getActivity(
                    context,
                    id,
                    Intent(context, MainActivity::class.java),
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
                )
                val notification = Notification.Builder(context, CHANNEL_ID)
                    .setSmallIcon(android.R.drawable.ic_popup_reminder)
                    .setContentTitle(reminder.optString("title", "JARVIS reminder"))
                    .setContentText("This reminder is due.")
                    .setVisibility(Notification.VISIBILITY_PRIVATE)
                    .setContentIntent(openApp)
                    .setAutoCancel(true)
                    .build()
                manager.notify(id, notification)
                preferences.edit().putString("due_$id", dueAt).apply()
            }
            Result.success()
        } catch (_: Exception) {
            Result.retry()
        }
    }

    companion object {
        private const val WORK_NAME = "jarvis_due_reminder_poll"
        private const val CHANNEL_ID = "jarvis_reminders"
        private const val STATE_STORE = "jarvis_reminder_delivery_state"
        private const val POLL_MINUTES = 15L

        fun setEnabled(context: Context, enabled: Boolean) {
            context.getSharedPreferences("jarvis_reminder_settings", Context.MODE_PRIVATE)
                .edit().putBoolean("notifications_enabled", enabled).apply()
            val workManager = WorkManager.getInstance(context)
            if (!enabled) {
                workManager.cancelUniqueWork(WORK_NAME)
                return
            }
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()
            val request = PeriodicWorkRequestBuilder<ReminderWorker>(POLL_MINUTES, TimeUnit.MINUTES)
                .setConstraints(constraints)
                .build()
            workManager.enqueueUniquePeriodicWork(WORK_NAME, ExistingPeriodicWorkPolicy.UPDATE, request)
        }
    }
}
