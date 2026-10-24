import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google import genai

from app.config import get_settings
from app.personality import SYSTEM_INSTRUCTIONS, language_instruction
from app.schemas import ChatRequest, ChatResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("jarvis")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create the SDK client only when a key is configured.
    app.state.gemini_client = genai.Client(api_key=settings.gemini_api_key) if settings.gemini_api_key else None
    yield
    app.state.gemini_client = None


app = FastAPI(
    title="JARVIS Personal AI API",
    description="A Gemini-powered personal assistant starter API.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "jarvis-personal-ai"}


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    client = getattr(app.state, "gemini_client", None)
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="Gemini API is not configured. Set GEMINI_API_KEY in your local .env file.",
        )

    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=request.message,
            config={
                "system_instruction": (
                    SYSTEM_INSTRUCTIONS + "\n\n" + language_instruction(request.language)
                ),
                "temperature": 0.8,
            },
        )
        reply = (response.text or "").strip()
        if not reply:
            raise HTTPException(status_code=502, detail="The AI returned an empty response.")
        return ChatResponse(reply=reply, model=settings.gemini_model, language=request.language)
    except HTTPException:
        raise
    except Exception:
        # Avoid returning provider errors or secret-bearing request details to clients.
        logger.exception("Gemini request failed")
        raise HTTPException(status_code=502, detail="The AI request failed. Check server logs and API configuration.")
