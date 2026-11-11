package com.ashok.jarvis

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.util.Base64
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.TimeUnit

/** Visible, user-started, full-duplex PCM session for the Android foreground UI. */
class LiveVoiceController(
    private val onStatus: (String, Boolean) -> Unit,
) {
    private val client = OkHttpClient.Builder().readTimeout(0, TimeUnit.MILLISECONDS).build()
    @Volatile private var active = false
    @Volatile private var webSocket: WebSocket? = null
    @Volatile private var recorder: AudioRecord? = null
    @Volatile private var player: AudioTrack? = null
    @Volatile private var captureThread: Thread? = null
    @Volatile private var playbackThread: Thread? = null
    @Volatile private var sessionGeneration = 0
    @Volatile private var lastCongestionNotice = 0L
    @Volatile private var lastPlaybackWarning = 0L
    private val playbackQueue = ArrayBlockingQueue<ByteArray>(MAX_QUEUED_AUDIO_FRAMES)

    suspend fun start(backendUrl: String, token: String) {
        require(backendUrl.startsWith("https://")) { "Live Voice requires an HTTPS backend." }
        require(token.length >= 32 && !token.startsWith("replace_")) { "Connect with a valid device token first." }
        check(!active) { "A Live Voice session is already active." }
        active = true
        val generation = synchronized(this) { ++sessionGeneration }
        onStatus("Requesting a short-lived Live Voice session…", true)
        try {
            val ticket = withContext(Dispatchers.IO) { requestTicket(backendUrl.trimEnd('/'), token) }
            if (!active || generation != sessionGeneration) return
            val socketUrl = backendUrl.trimEnd('/').replaceFirst("https://", "wss://") +
                "/api/live-voice?ticket=" + java.net.URLEncoder.encode(ticket, Charsets.UTF_8.name())
            val request = Request.Builder().url(socketUrl).build()
            webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(socket: WebSocket, response: Response) {
                if (!active) {
                    socket.close(1000, "session stopped before audio started")
                    return
                }
                try {
                    startAudio(socket)
                    onStatus("Live Voice connected. Microphone and speaker are active.", true)
                } catch (error: Exception) {
                    onStatus(error.message ?: "Could not start the audio devices.", false)
                    stop()
                }
            }

            override fun onMessage(socket: WebSocket, text: String) {
                handleServerMessage(text)
            }

            override fun onClosed(socket: WebSocket, code: Int, reason: String) {
                releaseAudio()
                active = false
                onStatus(if (reason.isBlank()) "Live Voice disconnected ($code)." else "Live Voice disconnected: $reason", false)
            }

            override fun onFailure(socket: WebSocket, error: Throwable, response: Response?) {
                releaseAudio()
                active = false
                onStatus("Live Voice failed: ${error.message ?: "connection error"}", false)
            }
            })
        } catch (error: Exception) {
            active = false
            releaseAudio()
            onStatus(error.message ?: "Could not start Live Voice.", false)
            throw error
        }
    }

    fun interrupt() {
        webSocket?.send(JSONObject().put("type", "stop").toString())
        flushPlayback()
        onStatus("Playback interrupted. Speak to continue.", true)
    }

    private fun flushPlayback() {
        playbackQueue.clear()
        synchronized(this) {
            player?.let { track ->
                runCatching { track.pause() }
                runCatching { track.flush() }
                runCatching { track.play() }
            }
        }
    }

    fun stop() {
        if (!active) return
        active = false
        synchronized(this) { sessionGeneration += 1 }
        webSocket?.send(JSONObject().put("type", "audio_end").toString())
        releaseAudio()
        webSocket?.close(1000, "user stopped Live Voice")
        webSocket = null
        onStatus("Live Voice stopped. The microphone is off.", false)
    }

    private fun requestTicket(backendUrl: String, token: String): String {
        val connection = URL("$backendUrl/api/live-voice-ticket").openConnection() as HttpURLConnection
        try {
            connection.connectTimeout = 8_000
            connection.readTimeout = 15_000
            connection.requestMethod = "POST"
            connection.setRequestProperty("Accept", "application/json")
            connection.setRequestProperty("Authorization", "Bearer $token")
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val body = stream?.bufferedReader()?.use { it.readText() } ?: "{}"
            if (code !in 200..299) {
                throw IllegalStateException(JSONObject(body).optString("detail", "Live Voice authorization failed ($code)."))
            }
            return JSONObject(body).getString("ticket")
        } finally {
            connection.disconnect()
        }
    }

    private fun startAudio(socket: WebSocket) {
        val inputMin = AudioRecord.getMinBufferSize(
            INPUT_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
        )
        check(inputMin > 0) { "This device cannot open a 16 kHz microphone stream." }
        val input = AudioRecord.Builder()
            .setAudioSource(MediaRecorder.AudioSource.VOICE_RECOGNITION)
            .setAudioFormat(
                AudioFormat.Builder()
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setSampleRate(INPUT_RATE)
                    .setChannelMask(AudioFormat.CHANNEL_IN_MONO)
                    .build()
            )
            .setBufferSizeInBytes(maxOf(inputMin * 2, INPUT_FRAME_BYTES * 2))
            .build()
        check(input.state == AudioRecord.STATE_INITIALIZED) { "The microphone could not be initialized." }

        val outputMin = AudioTrack.getMinBufferSize(
            OUTPUT_RATE,
            AudioFormat.CHANNEL_OUT_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
        )
        check(outputMin > 0) { "This device cannot open a 24 kHz speaker stream." }
        val output = AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ASSISTANT)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setSampleRate(OUTPUT_RATE)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .build()
            )
            .setTransferMode(AudioTrack.MODE_STREAM)
            .setBufferSizeInBytes(maxOf(outputMin * 2, OUTPUT_RATE / 2))
            .build()
        check(output.state == AudioTrack.STATE_INITIALIZED) { "The speaker could not be initialized." }

        recorder = input
        player = output
        output.play()
        playbackThread = Thread({ playbackLoop(output) }, "jarvis-live-speaker").apply {
            isDaemon = true
            start()
        }
        input.startRecording()
        captureThread = Thread({ captureLoop(input, socket) }, "jarvis-live-microphone").apply {
            isDaemon = true
            start()
        }
    }

    private fun captureLoop(input: AudioRecord, socket: WebSocket) {
        val frame = ByteArray(INPUT_FRAME_BYTES)
        var filled = 0
        while (active) {
            val count = input.read(frame, filled, frame.size - filled, AudioRecord.READ_BLOCKING)
            if (count < 0) {
                if (active) {
                    onStatus("Microphone input failed ($count).", false)
                    stop()
                }
                return
            }
            filled += count
            if (filled == frame.size) {
                val json = JSONObject()
                    .put("type", "audio")
                    .put("data", Base64.encodeToString(frame, Base64.NO_WRAP))
                    .toString()
                if (socket.queueSize() > MAX_SOCKET_QUEUE_BYTES) {
                    val now = System.currentTimeMillis()
                    if (now - lastCongestionNotice > 5_000) {
                        onStatus("Network is congested; some microphone audio may be dropped.", true)
                        lastCongestionNotice = now
                    }
                } else if (!socket.send(json)) {
                    onStatus("Live Voice connection closed while sending audio.", false)
                    stop()
                    return
                }
                filled = 0
            }
        }
    }

    private fun handleServerMessage(raw: String) {
        try {
            val event = JSONObject(raw)
            when (event.optString("type")) {
                "ready" -> onStatus("Live Voice ready (${event.optString("model")}).", true)
                "audio" -> {
                    val bytes = Base64.decode(event.getString("data"), Base64.DEFAULT)
                    if (!playbackQueue.offer(bytes)) {
                        val now = System.currentTimeMillis()
                        if (now - lastPlaybackWarning > 5_000) {
                            onStatus("Speaker output is congested; some response audio may be dropped.", true)
                            lastPlaybackWarning = now
                        }
                    }
                }
                "transcript" -> onStatus(
                    "${if (event.optString("source") == "user") "You" else "JARVIS"}: ${event.optString("text")}",
                    true,
                )
                "interrupted" -> {
                    flushPlayback()
                    onStatus("JARVIS audio interrupted. Speak to continue.", true)
                }
                "error" -> onStatus(event.optString("message", "Live Voice error."), false)
                "closed" -> onStatus("Live Voice provider session closed.", false)
            }
        } catch (error: Exception) {
            onStatus("Could not process Live Voice audio: ${error.message ?: "invalid frame"}", false)
        }
    }

    private fun releaseAudio() {
        active = false
        playbackQueue.clear()
        val inputThread = captureThread
        captureThread = null
        val outputThread = playbackThread
        playbackThread = null
        val input = recorder
        recorder = null
        runCatching { input?.stop() }
        inputThread?.interrupt()
        outputThread?.interrupt()
        if (inputThread != Thread.currentThread()) runCatching { inputThread?.join(250) }
        if (outputThread != Thread.currentThread()) runCatching { outputThread?.join(250) }
        synchronized(this) {
            input?.release()
            player?.let { track ->
                runCatching { track.pause() }
                runCatching { track.flush() }
                track.release()
            }
            player = null
        }
    }

    private fun playbackLoop(track: AudioTrack) {
        while (active && !Thread.currentThread().isInterrupted) {
            val frame = try {
                playbackQueue.poll(100, TimeUnit.MILLISECONDS)
            } catch (_: InterruptedException) {
                return
            } ?: continue
            val written = synchronized(this) {
                if (player !== track) return
                track.write(frame, 0, frame.size, AudioTrack.WRITE_BLOCKING)
            }
            if (written < 0) {
                onStatus("Speaker output failed ($written).", false)
                stop()
                return
            }
        }
    }

    companion object {
        private const val INPUT_RATE = 16_000
        private const val OUTPUT_RATE = 24_000
        private const val INPUT_FRAME_BYTES = 1_280
        private const val MAX_SOCKET_QUEUE_BYTES = 256 * 1024L
        private const val MAX_QUEUED_AUDIO_FRAMES = 8
    }
}
