import json
from groq import Groq
from apps.core.config import settings

SYSTEM_PROMPT="""You are ArveX Hosting AI, a concise technical hosting assistant.
Use the provided hosting tools when live user context is needed. Never invent infrastructure state.
Never expose passwords, API keys, tokens, encrypted credentials, or private infrastructure secrets.
Never execute arbitrary shell commands. You may only use the explicitly provided read-only hosting tools.
If a destructive action is requested, explain that the application requires an explicit confirmation outside the AI.
"""
TOOLS=[
 {"type":"function","function":{"name":"get_invite_balance","description":"Read the user's current invite balance.","parameters":{"type":"object","properties":{}}}},
 {"type":"function","function":{"name":"list_my_servers","description":"List the user's hosting servers and their application status.","parameters":{"type":"object","properties":{}}}},
 {"type":"function","function":{"name":"get_server_status","description":"Read status for one of the user's servers by id.","parameters":{"type":"object","properties":{"server_id":{"type":"string"}},"required":["server_id"]}}},
]

class GroqService:
    def __init__(self):
        self.client=Groq(api_key=settings.groq_api_key) if settings.groq_api_key else None; self.model=settings.groq_model

    def chat(self,user_text:str,context:dict|None=None)->str:
        if not self.client:return "AI is not configured yet. Add GROQ_API_KEY to the environment."
        safe_context=context or {}; messages=[{"role":"system","content":SYSTEM_PROMPT},{"role":"system","content":"Available read-only context:\n"+json.dumps(safe_context,default=str)},{"role":"user","content":user_text}]
        def executor(name,args):
            if name=="get_invite_balance": return {"invite_balance":safe_context.get("invite_balance",0)}
            servers=safe_context.get("servers",[])
            if name=="list_my_servers": return {"servers":[{"id":s.get("id"),"name":s.get("name"),"status":s.get("status"),"kind":s.get("kind")} for s in servers]}
            if name=="get_server_status":
                found=next((s for s in servers if str(s.get("id"))==str(args.get("server_id"))),None)
                return found or {"error":"Server not found or not owned by this user"}
            return {"error":"Tool not allowed"}
        return self.chat_with_tools(messages,TOOLS,executor)

    def chat_with_tools(self,messages:list[dict],tools:list[dict],executor):
        if not self.client:return "AI is not configured yet."
        working=list(messages)
        for _ in range(4):
            result=self.client.chat.completions.create(model=self.model,messages=working,tools=tools,tool_choice="auto",temperature=0.1,max_completion_tokens=1400)
            msg=result.choices[0].message; working.append(msg.model_dump(exclude_none=True))
            if not msg.tool_calls:return msg.content or "Done."
            for call in msg.tool_calls:
                try: output=executor(call.function.name,json.loads(call.function.arguments or "{}"))
                except Exception: output={"error":"Tool execution failed"}
                working.append({"role":"tool","tool_call_id":call.id,"name":call.function.name,"content":json.dumps(output,default=str)})
        return "I reached the safe tool-call limit. Please try again."
