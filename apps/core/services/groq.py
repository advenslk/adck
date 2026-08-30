import json
from groq import Groq
from apps.core.config import settings

SYSTEM_PROMPT = """You are ArveX Hosting AI, a concise technical hosting assistant.
You can explain server status, invite balances, deployments, and safe troubleshooting.
Never invent live infrastructure state. Use tools when live state is needed.
Never request or expose passwords, API keys, tokens, or private credentials.
Never execute arbitrary shell commands. Destructive operations must be confirmed by the application.
"""


class GroqService:
    def __init__(self):
        self.client = Groq(api_key=settings.groq_api_key) if settings.groq_api_key else None
        self.model = settings.groq_model

    def chat(self, user_text: str, context: dict | None = None) -> str:
        if not self.client:
            return "AI is not configured yet. Add GROQ_API_KEY to the environment."
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if context:
            messages.append({"role": "system", "content": "Live context:\n" + json.dumps(context, default=str)})
        messages.append({"role": "user", "content": user_text})
        result = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.2,
            max_completion_tokens=1200,
        )
        return result.choices[0].message.content or "I couldn't produce a response."

    def chat_with_tools(self, messages: list[dict], tools: list[dict], executor):
        if not self.client:
            return "AI is not configured yet."
        working = list(messages)
        for _ in range(4):
            result = self.client.chat.completions.create(
                model=self.model,
                messages=working,
                tools=tools,
                tool_choice="auto",
                temperature=0.1,
                max_completion_tokens=1400,
            )
            msg = result.choices[0].message
            working.append(msg.model_dump(exclude_none=True))
            if not msg.tool_calls:
                return msg.content or "Done."
            for call in msg.tool_calls:
                try:
                    args = json.loads(call.function.arguments or "{}")
                    output = executor(call.function.name, args)
                except Exception as exc:
                    output = {"error": str(exc)}
                working.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": call.function.name,
                    "content": json.dumps(output, default=str),
                })
        return "I reached the safe tool-call limit. Please try again."
