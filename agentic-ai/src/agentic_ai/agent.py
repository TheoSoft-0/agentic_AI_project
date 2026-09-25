from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider

from .models import EmailImportance


def create_email_triage_agent() -> Agent:
    """Create the local email-triage agent."""
    model = OpenAIChatModel(
        model_name="qwen3:4b-instruct",
        provider=OllamaProvider(
            base_url="http://localhost:11434/v1"
        ),
    )

    return Agent(
        model,
        output_type=EmailImportance,
        model_settings={
            "temperature": 0.0,
        },
    )