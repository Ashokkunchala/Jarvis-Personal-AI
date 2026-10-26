import asyncio
import json
import base64
import logging
from typing import Callable, Optional
import websockets
import numpy as np

logger = logging.getLogger("jarvis.gemini_live")


class GeminiLiveClient:
    def __init__(self, api_key: str, model="gemini-2.5-flash-native-audio-preview-09-2025"):
        self.api_key = api_key
        self.model = model
        self.ws = None
        self.connected = False
        self.on_audio_received = None
        self.on_text_received = None
        self.on_turn_complete = None
        
    async def connect(self):
        # Gemini Live API WebSocket endpoint
        uri = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent?key={self.api_key}"
        try:
            self.ws = await websockets.connect(uri)
            self.connected = True
            logger.info("Connected to Gemini Live")
            
            # Send setup message
            setup = {
                "setup": {
                    "model": f"models/{self.model}",
                    "generation_config": {
                        "response_modalities": ["AUDIO"],
                        "speech_config": {
                            "voice_config": {
                                "prebuilt_voice_config": {
                                    "voice_name": "Aoede"
                                }
                            }
                        }
                    },
                    "system_instruction": {
                        "parts": [{
                            "text": """You are JARVIS, Tony Stark's AI assistant. 
Be concise, witty, helpful, and loyal. 
Respond naturally in conversation with voice.
You can control the computer, answer questions, and assist with tasks.
Keep responses conversational and efficient."""
                        }]
                    }
                }
            }
            await self.ws.send(json.dumps(setup))
            await self._receive_setup()
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Gemini Live: {e}")
            return False
    
    async def _receive_setup(self):
        response = await self.ws.recv()
        data = json.loads(response)
        logger.debug(f"Setup response: {data}")
    
    async def send_audio(self, audio_data: np.ndarray):
        if not self.connected or not self.ws:
            return
        
        # Convert to base64
        if audio_data.dtype == np.float32:
            audio_int16 = (audio_data * 32768).astype(np.int16)
        else:
            audio_int16 = audio_data
        
        audio_b64 = base64.b64encode(audio_int16.tobytes()).decode('utf-8')
        
        message = {
            "realtime_input": {
                "media_chunks": [{
                    "data": audio_b64,
                    "mime_type": "audio/pcm;rate=16000"
                }]
            }
        }
        await self.ws.send(json.dumps(message))
    
    async def send_text(self, text: str):
        if not self.connected or not self.ws:
            return
        
        message = {
            "client_content": {
                "turns": [{
                    "role": "user",
                    "parts": [{"text": text}]
                }],
                "turn_complete": True
            }
        }
        await self.ws.send(json.dumps(message))
    
    async def receive_messages(self):
        while self.connected and self.ws:
            try:
                response = await self.ws.recv()
                data = json.loads(response)
                await self._handle_response(data)
            except websockets.exceptions.ConnectionClosed:
                logger.info("Gemini Live connection closed")
                self.connected = False
                break
            except Exception as e:
                logger.error(f"Error receiving message: {e}")
    
    async def _handle_response(self, data):
        # Handle server content
        if "serverContent" in data:
            content = data["serverContent"]
            if "modelTurn" in content:
                turn = content["modelTurn"]
                for part in turn.get("parts", []):
                    if "inlineData" in part:
                        # Audio data
                        audio_b64 = part["inlineData"]["data"]
                        audio_data = base64.b64decode(audio_b64)
                        audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768
                        if self.on_audio_received:
                            await self.on_audio_received(audio_np)
                    elif "text" in part:
                        # Text response
                        if self.on_text_received:
                            await self.on_text_received(part["text"])
            if content.get("turnComplete"):
                if self.on_turn_complete:
                    await self.on_turn_complete()
        
        # Handle tool calls
        if "toolCall" in data:
            logger.info(f"Tool call received: {data['toolCall']}")
    
    async def disconnect(self):
        if self.ws:
            await self.ws.close()
        self.connected = False
        logger.info("Disconnected from Gemini Live")
