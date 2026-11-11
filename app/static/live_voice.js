/* JARVIS Live Voice client. Captures mono PCM16/16 kHz and plays PCM16/24 kHz. */
(() => {
  const $ = id => document.getElementById(id);
  if (!$("liveVoiceConnect")) return;

  let socket=null, stream=null, inputContext=null, outputContext=null, source=null, processor=null, silentGain=null;
  let active=false, outputNextTime=0, outputNodes=new Set(), reconnecting=false, reconnectAttempts=0, reconnectTimer=null, lastQueueWarning=0;

  const status=(message,isError=false)=>{const el=$("liveVoiceStatus");if(el){el.textContent=message;el.className=isError?"tiny error":"tiny";}};
  const setUi=(state,detail)=>{
    if(typeof window.jarvisSetVoiceState==="function") window.jarvisSetVoiceState(state,
      state==="listening"?"Listening to you":state==="thinking"?"JARVIS is thinking":state==="speaking"?"JARVIS is speaking":"JARVIS is ready",detail);
    const sessionVisible=active||reconnecting;
    $("liveVoiceConnect").hidden=sessionVisible;
    $("liveVoiceStop").hidden=!sessionVisible;
    $("liveVoiceInterrupt").hidden=!active;
  };
  const send=message=>{if(socket&&socket.readyState===WebSocket.OPEN){socket.send(JSON.stringify(message));return true;}return false;};
  const toBase64=bytes=>{let binary="";for(let i=0;i<bytes.length;i+=0x8000)binary+=String.fromCharCode(...bytes.subarray(i,Math.min(i+0x8000,bytes.length)));return btoa(binary);};
  const fromBase64=value=>{const binary=atob(value),bytes=new Uint8Array(binary.length);for(let i=0;i<binary.length;i++)bytes[i]=binary.charCodeAt(i);return bytes;};
  const toPcm16=samples=>{
    const pcm=new Int16Array(samples.length);
    for(let i=0;i<samples.length;i++){const x=Math.max(-1,Math.min(1,samples[i]));pcm[i]=x<0?Math.round(x*32768):Math.round(x*32767);}
    return new Uint8Array(pcm.buffer);
  };
  const stopPlayback=()=>{
    for(const node of outputNodes){try{node.stop();}catch(_){}}
    outputNodes.clear();if(outputContext)outputNextTime=outputContext.currentTime;
  };
  async function playAudio(encoded){
    if(!outputContext)outputContext=new AudioContext();
    if(outputContext.state==="suspended")await outputContext.resume();
    const bytes=fromBase64(encoded);if(!bytes.length||bytes.length%2)return;
    const pcm=new Int16Array(bytes.buffer,bytes.byteOffset,bytes.byteLength/2),buffer=outputContext.createBuffer(1,pcm.length,24000),channel=buffer.getChannelData(0);
    for(let i=0;i<pcm.length;i++)channel[i]=pcm[i]/32768;
    const node=outputContext.createBufferSource();node.buffer=buffer;node.connect(outputContext.destination);
    const start=Math.max(outputContext.currentTime+0.01,outputNextTime);outputNextTime=start+buffer.duration;outputNodes.add(node);node.onended=()=>outputNodes.delete(node);node.start(start);
    setUi("speaking","JARVIS audio is streaming. Speak to interrupt.");
  }
  function showTranscript(source,text){
    const el=$("liveVoiceTranscript");if(!el||!text)return;
    const line=(source==="user"?"You: ":"JARVIS: ")+text;
    el.textContent+=(el.textContent?"\n":"")+line;el.scrollTop=el.scrollHeight;
  }
  async function onMessage(event){
    let m;try{m=JSON.parse(event.data);}catch(_){return;}
    switch(m.type){
      case "ready":status("Live audio connected · "+m.model);setUi("listening","Microphone active by your request. Speak naturally.");break;
      case "audio":try{await playAudio(m.data);}catch(e){status("Audio playback failed: "+e.message,true);}break;
      case "text":showTranscript("assistant",m.text);break;
      case "transcript":showTranscript(m.source,m.text);break;
      case "turn_complete":status("Reply complete · live session remains open.");setUi("listening","Ready for your next utterance.");break;
      case "interrupted":stopPlayback();status("JARVIS audio interrupted.");setUi("listening","Listening for your next instruction.");break;
      case "error":status(m.message||"Live voice error.",true);break;
      case "closed":status("Live audio session closed. Checking whether it can reconnect…",true);if(socket&&socket.readyState===WebSocket.OPEN)socket.close(1011,"provider session ended");break;
    }
  }
  async function startCapture(){
    if(!navigator.mediaDevices?.getUserMedia||!window.AudioContext)throw new Error("Live audio requires a secure context and Web Audio support.");
    stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
    inputContext=new AudioContext();if(inputContext.state==="suspended")await inputContext.resume();
    if(!inputContext.audioWorklet||typeof AudioWorkletNode==="undefined")throw new Error("This browser does not support AudioWorklet live capture. Update your browser and use HTTPS or localhost.");
    await inputContext.audioWorklet.addModule("/static/audio_capture_worklet.js");
    source=inputContext.createMediaStreamSource(stream);processor=new AudioWorkletNode(inputContext,"jarvis-capture",{numberOfInputs:1,numberOfOutputs:1,outputChannelCount:[1]});silentGain=inputContext.createGain();silentGain.gain.value=0;
    source.connect(processor);processor.connect(silentGain);silentGain.connect(inputContext.destination);
    processor.port.onmessage=event=>{
      try{
        if(!active||!socket||socket.readyState!==WebSocket.OPEN)return;
        if(socket.bufferedAmount>256*1024){
          const now=Date.now();
          if(now-lastQueueWarning>5000){status("Network is congested; some live audio may be dropped.",true);lastQueueWarning=now;}
          return;
        }
        send({type:"audio",data:toBase64(toPcm16(event.data))});
      }finally{try{processor?.port.postMessage({type:"credit"});}catch(_){}}
    };
    active=true;setUi("listening","Microphone is on. Audio is streaming to your JARVIS server.");status("Live microphone active. Select Stop Live Voice to disconnect.");
  }
  function releaseCapture(sendEnd=true){
    active=false;
    if(processor){processor.port.onmessage=null;try{processor.port.close();processor.disconnect();}catch(_){}processor=null;}
    if(source){try{source.disconnect();}catch(_){}source=null;}
    if(silentGain){try{silentGain.disconnect();}catch(_){}silentGain=null;}
    if(stream){stream.getTracks().forEach(t=>t.stop());stream=null;}
    if(inputContext){inputContext.close().catch(()=>{});inputContext=null;}
    if(sendEnd)send({type:"audio_end"});
    stopPlayback();setUi("","Live microphone stopped.");
  }
  async function connect(){
    const token=$("deviceToken")?.value?.trim()||"";
    if(token.length<32)throw new Error("Enter your JARVIS API token and click Save settings first.");
    if(socket&&socket.readyState===WebSocket.OPEN){await startCapture();return;}
    // Keep the long-lived bearer token in an Authorization header. Only the
    // short-lived, single-use ticket is placed in the WebSocket URL.
    const ticketResponse=await fetch("/api/live-voice-ticket",{
      method:"POST",headers:{Authorization:"Bearer "+token,Accept:"application/json"}
    });
    if(!ticketResponse.ok)throw new Error(ticketResponse.status===401?"Device token rejected. Save settings and reconnect.":"Could not authorize a live voice session (HTTP "+ticketResponse.status+").");
    const ticketData=await ticketResponse.json();
    if(typeof ticketData.ticket!=="string"||!ticketData.ticket)throw new Error("Server did not return a live voice ticket.");
    const scheme=location.protocol==="https:"?"wss:":"ws:";
    socket=new WebSocket(scheme+"//"+location.host+"/api/live-voice?ticket="+encodeURIComponent(ticketData.ticket));
    socket.addEventListener("message",onMessage);
    socket.addEventListener("open",async()=>{try{reconnecting=false;reconnectAttempts=0;await startCapture();}catch(e){status(e.message,true);releaseCapture(false);socket?.close(1000,"microphone unavailable");}});
    socket.addEventListener("error",()=>status("Live connection failed. Check API token, backend config and model access.",true));
    socket.addEventListener("close",event=>{
      releaseCapture(false);socket=null;
      if(event.code===4401)status("Live authorization failed. Check your JARVIS token.",true);
      else if(event.code===4403)status("This page origin is not allowed for live voice.",true);
      else if(event.code===4429)status("Live Voice session limit reached. Stop another active session and try again.",true);
      else if(event.code===1013)status("Live voice is unavailable: configure a supported Gemini Live model and API key.",true);
      else status("Live voice disconnected ("+event.code+").",event.code!==1000);
      // Only retry transient transport/server disconnects. Authentication,
      // origin, normal user stop, and provider configuration errors need action.
      if([1006,1011,1012].includes(event.code)&&reconnectAttempts<2){
        reconnectAttempts++;reconnecting=true;setUi("thinking","Connection dropped. Reconnecting shortly; select Stop to cancel.");
        status("Live voice lost its connection. Retrying ("+reconnectAttempts+"/2)…",true);
        reconnectTimer=setTimeout(()=>{reconnectTimer=null;if(!reconnecting)return;connect().catch(e=>{reconnecting=false;setUi("","Reconnect failed.");status("Live voice reconnect failed: "+e.message,true);});},reconnectAttempts*1000);
      }else{reconnecting=false;reconnectAttempts=0;setUi("","Live voice stopped.");}
    });
  }
  $("liveVoiceConnect").addEventListener("click",()=>{connect().catch(e=>status(e.message,true));});
  $("liveVoiceStop").addEventListener("click",()=>{reconnecting=false;reconnectAttempts=0;if(reconnectTimer){clearTimeout(reconnectTimer);reconnectTimer=null;}releaseCapture();if(socket&&socket.readyState===WebSocket.OPEN)socket.close(1000,"user stopped live voice");});
  $("liveVoiceInterrupt").addEventListener("click",()=>{stopPlayback();send({type:"stop"});status("Playback interrupted. Speak your next instruction.");setUi("listening","JARVIS response interrupted.");});
  window.addEventListener("pagehide",()=>{reconnecting=false;if(reconnectTimer)clearTimeout(reconnectTimer);releaseCapture(false);if(socket){socket.close(1000,"page closed");socket=null;}if(outputContext)outputContext.close().catch(()=>{});});
})();
