"""AI providers: standalone (no key), OpenAI/ChatGPT, Anthropic/Claude, or any custom OpenAI-compatible endpoint."""
import os, json, urllib.request
def get_provider(name="none", api_key=None, base_url=None, model=None):
    name=(name or "none").lower()
    if name in ("none","standalone","off"): return None
    key = api_key or os.environ.get("MIRROR100_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if name in ("openai","chatgpt"): return _OpenAI(key, base_url or "https://api.openai.com/v1", model or "gpt-4o-mini")
    if name in ("anthropic","claude"): return _Anthropic(key, base_url or "https://api.anthropic.com", model or "claude-3-5-sonnet-latest")
    if name in ("custom","extra","openai-compatible"): 
        if not base_url: raise SystemExit("custom provider needs --base-url")
        return _OpenAI(key, base_url, model or "default")
    raise SystemExit(f"unknown provider {name}")
class _OpenAI:
    def __init__(self,k,u,m): self.k,self.u,self.m=k,u.rstrip("/"),m
    def analyse(self,prompt):
        if not self.k: raise SystemExit("missing API key: pass --api-key or set OPENAI_API_KEY / MIRROR100_API_KEY")
        data=json.dumps({"model":self.m,"messages":[{"role":"user","content":prompt}]}).encode()
        r=urllib.request.Request(self.u+"/chat/completions",data=data,headers={"Content-Type":"application/json","Authorization":f"Bearer {self.k}"})
        with urllib.request.urlopen(r,timeout=60) as resp: return json.load(resp)["choices"][0]["message"]["content"]
class _Anthropic:
    def __init__(self,k,u,m): self.k,self.u,self.m=k,u.rstrip("/"),m
    def analyse(self,prompt):
        if not self.k: raise SystemExit("missing API key: pass --api-key or set ANTHROPIC_API_KEY")
        data=json.dumps({"model":self.m,"max_tokens":2000,"messages":[{"role":"user","content":prompt}]}).encode()
        r=urllib.request.Request(self.u+"/v1/messages",data=data,headers={"Content-Type":"application/json","x-api-key":self.k,"anthropic-version":"2023-06-01"})
        with urllib.request.urlopen(r,timeout=60) as resp: return json.load(resp)["content"][0]["text"]
