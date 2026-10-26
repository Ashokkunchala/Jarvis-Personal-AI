/* JARVIS Live Voice client.
   * Capture path: Web Audio microphone -> mono PCM16 16 kHz chunks.
   * Playback path: decoded PCM16 24 kHz chunks through AudioContext.
   * This uses a user-initiated microphone session and reports capability errors.
   */
(() => {
  const $ = (id) => document.getElementById(id);
  if (!$("liveVoiceConnect")) return;

  let socket = null;
  let stream = null;
  let inputContext = null;
  let outputContext = null;
  let source = null;
  let processor = null;
  let mutedGain = null;
  let captureBuffer = [];
  let captureLength = 0;
  let inputSampleRate = 48000;
  let outputNextTime = 0;
  let active = false;
  let outputNodes = new Set();

  const status = (message, isError=false) => {
    const el = $("liveVoiceStatus");
    if (!el) return;
    el.textContent = message;
    el.className = isError ? "tiny error" : "tiny";
  };
  const setUi = (state, detail) => {
    if (typeof window.jarvisSetVoiceState === "function") {
      window.jarvisSetVoiceState(state, state === "listening" ? "Listening to you" :
        state === "thinking" ? "JARVIS is thinking" :
        state === "speaking" ? "JARVIS is speaking" :
        "JARVIS is ready", detail);
    }
  };
  const send = (value) => {
    if (!socket || socket.readyState !== WebSocket.OPEN) return false;
    socket.send(JSON.stringify(value));
    return true;
  };
  const b64 = (bytes) => {
    let binary = "";
    const chunkSize = 0x8000;
    for (let i = 0; i < bytes.length; i += chunkSize) {
      binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
    }
    return btoa(binary);
  };
  const decodeB64 = (value) => {
    const binary = atob(value);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return bytes;
  };
  const downsampleTo16k = (float32, sampleRate) => {
    if (sampleRate === 16000) return float32;
    const ratio = sampleRate / 16000;
    const length = Math.floor(float32.length / ratio);
    const output = new Float32Array(length);
    for (let i = 0; i < length; i++) {
      const start = Math.floor(i * ratio);
      const end = Math.min(Math.floor((i + 1) * ratio), float32.length);
      let sum = 0, count = 0;
      for (let j = start; j < end; j++) { sum += float32[j]; count++; }
      output[i] = count ? sum / count : 0;
    }
    return output;
  };
  const floatToPcm16 = (samples) => {
    const pcm = new Int16Array(samples.length);
    for (let i = 0; i < samples.length; i++) {
      const clamped = Math.max(-1, Math.min(1, samples[i]));
      pcm[i] = clamped < 0 ? Math.round(clamped * 32768) : Math.round(clamped * 32767);
    }
    return new Uint8Array(pcm.buffer);
  };
  const stopPlayback = () => {
    outputNodes.forEach(node => { try { node.stop(); } catch (_) {} });
    outputNodes.clear();
    if (outputContext) outputNextTime = outputContext.currentTime;
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  };
  const playPcm24k = async (encoded) => {
    if (!outputContext) outputContext = new AudioContext({sampleRate: 24000});
    if (outputContext.state === "suspended") await outputContext.resume();
    const bytes = decodeB64(encoded);
    if (!bytes.length || bytes.length % 2) return;
    const pcm = new Int16Array(bytes.buffer, bytes.byteOffset, bytes.byteLength / 2);
    const audio = outputContext.createBuffer(1, pcm.length, 24000);
    const channel = audio.getChannelData(0);
    for (let i = 0; i < pcm.length; i++) channel[i] = pcm[i] / 32768;
    const node = outputContext.createBufferSource();
    node.buffer = audio;
    node.connect(outputContext.destination);
    const startAt = Math.max(outputContext.currentTime + 0.015, outputNextTime);
    outputNextTime = startAt + audio.duration;
    outputNodes.add(node);
    node.onended = () => outputNodes.delete(node);
    node.start(startAt);
    setUi("speaking", "Streaming live audio. Start speaking to interrupt.");
  };
  const onMessage = async (event) => {
    let message;
    try { message = JSON.parse(event.data); } catch (_) { return; }
    switch (message.type) {
      case "ready":
        status("Live audio connected · " + message.model);
        setUi("listening", "Microphone active by your request. Say something naturally.");
        break;
      case "audio":
        try { await playPcm24k(message.data); }
        catch (err) { status("Audio playback failed: " + err.message, true); }
        break;
      case "text":
        status("JARVIS response is streaming…");
        if ($("liveVoiceTranscript")) $("liveVoiceTranscript").textContent += message.text;
        break;
      case "transcript":
        if ($("liveVoiceTranscript")) {
          const prefix = message.source === "user" ? "You: " : "JARVIS: ";
          $("liveVoiceTranscript").textContent += ( $("liveVoiceTranscript").textContent ? "\n" : "" ) + prefix + message.text;
        }
        break;
      case "turn_complete":
        status("Live response complete. Keep speaking or tap Stop voice.");
        setUi("listening", "Live session remains open and ready for your next utterance.");
        break;
      case "interrupted":
        stopPlayback();
        status("JARVIS audio interrupted.");
        setUi("listening", "Listening for your next instruction.");
        break;
      case "error":
        status(message.message || "Live voice error.", true);
        break;
      case "closed":
        status("Live voice session closed.", true);
        break;
    }
  };
  const startCapture = async () => {
    if (!navigator.mediaDevices?.getUserMedia || !window.AudioContext) {
      throw new Error("Live microphone capture requires a secure context and Web Audio support.");
    }
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true}
    });
    inputContext = new AudioContext();
    inputSampleRate = inputContext.sampleRate;
    if (inputContext.state === "suspended") await inputContext.resume();
    source = inputContext.createMediaStreamSource(stream);
    processor = inputContext.createScriptProcessor(4096, 1, 1);
    mutedGain = inputContext.createGain();
    mutedGain.gain.value = 0;
    source.connect(processor);
    processor.connect(mutedGain);
    mutedGain.connect(inputContext.destination);
    captureBuffer = [];
    captureLength = 0;
    processor.onaudioprocess = (event) => {
      if (!active || !socket || socket.readyState !== WebSocket.OPEN) return;
      const mono = event.inputBuffer.getChannelData(0);
      const samples = downsampleTo16k(mono, inputSampleRate);
      // ScriptProcessor callback is typically 85 ms at 48kHz; split PCM into <=100ms frames.
      const pcm = floatToPcm16(samples);
      const maxChunkBytes = 3200; // 100 ms of mono PCM16 at 16 kHz.
      for (let offset = 0; offset < pcm.length; offset += maxChunkBytes) {
        const chunk = pcm.subarray(offset, Math.min(offset + maxChunkBytes, pcm.length));
        if (chunk.length && chunk.length % 2 === 0) send({type:"audio",data:b64(chunk)});
      }
    };
    active = true;
    status("Microphone active. Audio is being streamed to your configured JARVIS server.");
    setUi("listening", "Live microphone connected. Speak naturally; you may interrupt JARVIS.");
    $("liveVoiceConnect").disabled = true;
    $("liveVoiceStop").hidden = false;
  };
  const stopCapture = () => {
    active = false;
    if (processor) { processor.onaudioprocess = null; try { processor.disconnect(); } catch (_) {} processor = null; }
    if (source) { try { source.disconnect(); } catch (_) {} source = null; }
    if (mutedGain) { try { mutedGain.disconnect(); } catch (_) {} mutedGain = null; }
    if (stream) { stream.getTracks().forEach(track => track.stop()); stream = null; }
    if (inputContext) { inputContext.close().catch(()=>{}); inputContext = null; }
    send({type:"audio_end"});
    stopPlayback();
    $("liveVoiceConnect").disabled = false;
    $("liveVoiceStop").hidden = true;
    setUi("", "Live microphone stopped.");
  };
  const connectLive = async () => {
    const token = $("deviceToken")?.value?.trim() || "";
    if (token.length < 32) throw new Error("Enter your JARVIS API token and save settings first.");
    if (socket && socket.readyState === WebSocket.OPEN) {
      await startCapture();
      return;
    }
    const scheme = location.protocol === "https:" ? "wss:" : "ws:";
    const url = scheme + "//" + location.host + "/api/live-voice?token=" + encodeURIComponent(token);
    socket = new WebSocket(url);
    socket.addEventListener("message", onMessage);
    socket.addEventListener("open", async () => {
      try { await startCapture(); }
      catch (err) { status(err.message, true); stopCapture(); }
    });
    socket.addEventListener("error", () => status("Live voice connection failed. Check backend, token, and Gemini Live model access.", true));
    socket.addEventListener("close", (event) => {
      stopCapture();
      socket = null;
      if (event.code === 4401) status("Live voice authorization failed. Check the device token.", true);
      else if (event.code === 4403) status("This page origin is not allowed for live voice.", true);
      else status("Live voice disconnected (" + event.code + ").", event.code !== 1000);
    });
  };

  $("liveVoiceConnect").addEventListener("click", () => {
    connectLive().catch(err => status(err.message, true));
  });
  $("liveVoiceStop").addEventListener("click", () => {
    stopCapture();
    if (socket && socket.readyState === WebSocket.OPEN) socket.close(1000, "user stopped live voice");
  });
  $("liveVoiceInterrupt").addEventListener("click", () => {
    stopPlayback();
    send({type:"stop"});
    status("Stopped current playback. Live session remains connected.");
    setUi("listening", "Speak your next instruction.");
  });
})();
