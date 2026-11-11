/* JARVIS Live Voice client. Captures mono PCM16/16 kHz and plays PCM16/24 kHz. */
(() => {
  const $ = id => document.getElementById(id);
  if (!$("liveVoiceConnect")) return;

  let socket=null, stream=null, inputContext=null, outputContext=null, source=null, processor=null, silentGain=null;
  let active=false, outputNextTime=0, outputNodes=new Set(), reconnecting=false,userStopped=false,attempt=0,retryTimer=null,wasReconnect=false;

  const status=(message,isError=false)=>{const el=$("liveVoiceStatus");if(el){el.textContent=message;el.className=isError?"tiny error":"tiny";}};
  const setUi=(state,detail,title)=>{
    document.body.dataset.liveState=active?"active":reconnecting?"reconnecting":"off";
    if(typeof window.jarvisSetVoiceState==="function") window.jarvisSetVoiceState(state,
      title||(state==="listening"?"Listening to you":state==="thinking"?"JARVIS is thinking":state==="speaking"?"JARVIS is speaking":"JARVIS is ready"),detail);
    const dictationStop=$("voiceStop");if(dictationStop)dictationStop.hidden=true; // dictation is not running during live voice
    $("liveVoiceConnect").hidden=active;
    $("liveVoiceStop").hidden=!(active||reconnecting);
    $("liveVoiceInterrupt").hidden=!active;
  };
  const send=message=>{if(socket&&socket.readyState===WebSocket.OPEN){socket.send(JSON.stringify(message));return true;}return false;};
  const toBase64=bytes=>{let binary="";for(let i=0;i<bytes.length;i+=0x8000)binary+=String.fromCharCode(...bytes.subarray(i,Math.min(i+0x8000,bytes.length)));return btoa(binary);};
  const fromBase64=value=>{const binary=atob(value),bytes=new Uint8Array(binary.length);for(let i=0;i<binary.length;i++)bytes[i]=binary.charCodeAt(i);return bytes;};
  const downsample=(input,rate)=>{
    if(rate===16000)return input;
    const ratio=rate/16000,output=new Float32Array(Math.floor(input.length/ratio));
    for(let i=0;i<output.length;i++){let sum=0,count=0;for(let j=Math.floor(i*ratio),end=Math.min(Math.floor((i+1)*ratio),input.length);j<end;j++){sum+=input[j];count++;}output[i]=count?sum/count:0;}
    return output;
  };
  const toPcm16=samples=>{
    const pcm=new Int16Array(samples.length);
    for(let i=0;i<samples.length;i++){const x=Math.max(-1,Math.min(1,samples[i]));pcm[i]=x<0?Math.round(x*32768):Math.round(x*32767);}
    return new Uint8Array(pcm.buffer);
  };
  // After a manual interrupt the server may still have audio of the old reply in
  // flight. Drop it until that turn ends (turn_complete or interrupted), or 5 s pass.
  let dropAudioUntilTurnEnd=false,dropTimer=null;
  const dropStaleAudio=()=>{dropAudioUntilTurnEnd=true;clearTimeout(dropTimer);dropTimer=setTimeout(()=>{dropAudioUntilTurnEnd=false;},5000);};
  const endStaleAudioWindow=()=>{dropAudioUntilTurnEnd=false;clearTimeout(dropTimer);};
  const stopPlayback=()=>{
    for(const node of outputNodes){try{node.stop();}catch(_){}}
    outputNodes.clear();if(outputContext)outputNextTime=outputContext.currentTime;
  };
  async function playAudio(encoded){
    if(dropAudioUntilTurnEnd)return;
    if(!outputContext)outputContext=new AudioContext();
    if(outputContext.state==="suspended")await outputContext.resume();
    const bytes=fromBase64(encoded);if(!bytes.length||bytes.length%2)return;
    const pcm=new Int16Array(bytes.buffer,bytes.byteOffset,bytes.byteLength/2),buffer=outputContext.createBuffer(1,pcm.length,24000),channel=buffer.getChannelData(0);
    for(let i=0;i<pcm.length;i++)channel[i]=pcm[i]/32768;
    const node=outputContext.createBufferSource();node.buffer=buffer;node.connect(outputContext.destination);
    // Bound queued playback to 20 s so a slow device cannot build unbounded lag.
    if(outputNextTime-outputContext.currentTime>20)return;
    const start=Math.max(outputContext.currentTime+0.01,outputNextTime);outputNextTime=start+buffer.duration;outputNodes.add(node);node.onended=()=>outputNodes.delete(node);node.start(start);
    setUi("speaking","JARVIS audio is streaming. Speak to interrupt.");
  }
  function showTranscript(source,text){
    const el=$("liveVoiceTranscript");if(!el||!text)return;
    const line=(source==="user"?"You: ":"JARVIS: ")+text;
    el.textContent+=(el.textContent?"\n":"")+line;el.scrollTop=el.scrollHeight;
  }
  // Approval prompt for state-changing voice tools. Text is set with textContent
  // only; the server treats anything but an explicit Approve as a denial.
  let approvalBox=null,approvalTimer=null,approvalTick=null;
  function clearApproval(){
    if(approvalTimer){clearTimeout(approvalTimer);approvalTimer=null;}
    if(approvalTick){clearInterval(approvalTick);approvalTick=null;}
    if(approvalBox){approvalBox.remove();approvalBox=null;}
    document.body.classList.remove("has-approval");
  }
  function showApproval(m){
    clearApproval();
    const slot=$("approvalSlot"),anchor=slot||$("liveVoiceStatus");if(!anchor||typeof m.id!=="string")return;
    const box=document.createElement("div");box.setAttribute("role","alertdialog");box.setAttribute("aria-label","Approve JARVIS action");box.setAttribute("aria-live","assertive");
    if(!slot)box.style.cssText="margin:.4rem 0;padding:.5rem;border:1px solid var(--muted,#888);border-radius:8px;font-size:.85rem";
    const label=document.createElement("div");label.textContent="JARVIS asks to: "+String(m.summary||m.name||"make a change").slice(0,300);
    const cd=document.createElement("span");cd.className="cd";
    const yes=document.createElement("button");yes.type="button";yes.className="primary";yes.textContent="Approve";
    const no=document.createElement("button");no.type="button";no.textContent="Deny";
    const stop=document.createElement("button");stop.type="button";stop.textContent="Stop voice";
    const answer=approve=>{send({type:"approval",id:m.id,approve:approve===true});clearApproval();status(approve?"Approved. Waiting for JARVIS to finish.":"Denied. Nothing was changed.");};
    yes.addEventListener("click",()=>answer(true));no.addEventListener("click",()=>answer(false));
    stop.addEventListener("click",()=>{clearApproval();$("liveVoiceStop").click();}); // closing the session is a denial on the server
    box.append(label,cd,yes,no,stop);(slot?slot.append(box):anchor.after(box));approvalBox=box;
    document.body.classList.add("has-approval");
    try{yes.focus({preventScroll:true});}catch(_){}
    const ttl=Math.max(1,Number(m.expires_in)||60),end=Date.now()+ttl*1000;
    const paint=()=>{cd.textContent="Auto-denies in "+Math.max(0,Math.ceil((end-Date.now())/1000))+" s if you do nothing.";};paint();
    approvalTick=setInterval(paint,1000);
    approvalTimer=setTimeout(()=>{clearApproval();status("Approval timed out. Nothing was changed.");},ttl*1000);
  }
  async function onMessage(event){
    let m;try{m=JSON.parse(event.data);}catch(_){return;}
    switch(m.type){
      case "ready":attempt=0;reconnecting=false;if(wasReconnect){wasReconnect=false;const t=$("liveVoiceTranscript");if(t)t.textContent+=(t.textContent?"\n":"")+"-- reconnected. JARVIS does not remember what was said before the drop. --";}status("Live audio connected · "+m.model);setUi("listening","Microphone active by your request. Speak naturally.");break;
      case "audio":try{await playAudio(m.data);}catch(e){status("Audio playback failed: "+e.message,true);}break;
      case "text":showTranscript("assistant",m.text);break;
      case "transcript":showTranscript(m.source,m.text);break;
      case "turn_complete":endStaleAudioWindow();status("Reply complete · live session remains open.");setUi("listening","Ready for your next utterance.");break;
      case "interrupted":endStaleAudioWindow();stopPlayback();status("JARVIS audio interrupted.");setUi("listening","Listening for your next instruction.");break;
      case "tool":status("Tool "+String(m.name)+(m.ok?" finished.":" did not run."),!m.ok);break;
      case "approval_request":showApproval(m);break;
      case "error":status(m.message||"Live voice error.",true);break;
      case "closed":status("Live audio session closed.",true);break;
    }
  }
  async function startCapture(){
    if(!navigator.mediaDevices?.getUserMedia||!window.AudioContext)throw new Error("Live audio requires a secure context and Web Audio support.");
    // The socket can close while the browser is still asking for the microphone
    // (server drop, user pressed Stop). Never leave the microphone on without a session.
    const abandoned=()=>userStopped||!socket||socket.readyState!==WebSocket.OPEN;
    const local=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
    if(abandoned()){local.getTracks().forEach(t=>t.stop());return;}
    stream=local;
    inputContext=new AudioContext();if(inputContext.state==="suspended")await inputContext.resume();
    if(abandoned()){stream.getTracks().forEach(t=>t.stop());stream=null;inputContext.close().catch(()=>{});inputContext=null;return;}
    source=inputContext.createMediaStreamSource(stream);processor=inputContext.createScriptProcessor(4096,1,1);silentGain=inputContext.createGain();silentGain.gain.value=0;
    source.connect(processor);processor.connect(silentGain);silentGain.connect(inputContext.destination);
    processor.onaudioprocess=event=>{
      if(!active||!socket||socket.readyState!==WebSocket.OPEN)return;
      const frame=toPcm16(downsample(event.inputBuffer.getChannelData(0),inputContext.sampleRate));
      const maxBytes=3200;
      for(let offset=0;offset<frame.length;offset+=maxBytes){let chunk=frame.subarray(offset,Math.min(offset+maxBytes,frame.length));if(chunk.length%2)chunk=chunk.subarray(0,chunk.length-1);if(chunk.length)send({type:"audio",data:toBase64(chunk)});}
    };
    active=true;setUi("listening","Microphone is on. Audio is streaming to your JARVIS server.");status("Live microphone active. Select Stop Live Voice to disconnect.");
  }
  function releaseCapture(sendEnd=true){
    active=false;clearApproval();endStaleAudioWindow();
    if(processor){processor.onaudioprocess=null;try{processor.disconnect();}catch(_){}processor=null;}
    if(source){try{source.disconnect();}catch(_){}source=null;}
    if(silentGain){try{silentGain.disconnect();}catch(_){}silentGain=null;}
    if(stream){stream.getTracks().forEach(t=>t.stop());stream=null;}
    if(inputContext){inputContext.close().catch(()=>{});inputContext=null;}
    if(sendEnd)send({type:"audio_end"});
    stopPlayback();setUi("","Live microphone stopped.");
  }
  // Unexpected drops (server restart, network loss) retry up to 4 times with
  // backoff. Stop Live Voice cancels. Auth/config/limit closes never retry.
  function scheduleReconnect(){
    clearTimeout(retryTimer);
    if(userStopped)return;
    attempt++;
    if(attempt>4){reconnecting=false;wasReconnect=false;setUi("","Live voice could not reconnect.");status("Live voice could not reconnect. Select Start Live Voice to try again.",true);return;}
    reconnecting=true;wasReconnect=true;
    const delay=1000*2**(attempt-1);
    setUi("","Connection lost. The microphone is off until the session is back.","Reconnecting");
    status("Connection lost. Reconnecting ("+attempt+"/4) in "+delay/1000+" s. Select Stop Live Voice to cancel.",true);
    retryTimer=setTimeout(async()=>{if(userStopped)return;try{await connect();}catch(e){scheduleReconnect();}},delay);
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
    socket.addEventListener("open",async()=>{try{await startCapture();}catch(e){status(e.message,true);releaseCapture(false);socket?.close(1000,"microphone unavailable");}});
    socket.addEventListener("error",()=>status("Live connection failed. Check API token, backend config and model access.",true));
    socket.addEventListener("close",event=>{
      releaseCapture(false);socket=null;
      if(!userStopped&&!event.wasClean&&![4401,4403,1013].includes(event.code)){scheduleReconnect();return;}
      if(event.code===4401)status("Live authorization failed. Check your JARVIS token.",true);
      else if(event.code===4403)status("This page origin is not allowed for live voice.",true);
      else if(event.code===1013)status("Live voice is unavailable: configure a supported Gemini Live model and API key.",true);
      else status("Live voice disconnected ("+event.code+").",event.code!==1000);
    });
  }
  $("liveVoiceConnect").addEventListener("click",()=>{userStopped=false;attempt=0;reconnecting=false;connect().catch(e=>status(e.message,true));});
  $("liveVoiceStop").addEventListener("click",()=>{userStopped=true;reconnecting=false;wasReconnect=false;clearTimeout(retryTimer);releaseCapture();status("Live voice stopped.");if(socket&&socket.readyState===WebSocket.OPEN)socket.close(1000,"user stopped live voice");});
  $("liveVoiceInterrupt").addEventListener("click",()=>{dropStaleAudio();stopPlayback();send({type:"stop"});status("Playback interrupted. Speak your next instruction.");setUi("listening","JARVIS response interrupted.");});
  window.addEventListener("pagehide",()=>{userStopped=true;clearTimeout(retryTimer);releaseCapture(false);if(socket){socket.close(1000,"page closed");socket=null;}if(outputContext)outputContext.close().catch(()=>{});});
})();
