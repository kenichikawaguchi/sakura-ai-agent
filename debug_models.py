import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("SAKURA_API_KEY"),
    base_url=os.getenv("SAKURA_BASE_URL"),
)

test_prompt = "こんにちは。あなたの名前を一言で教えてください。"

for model in ["gpt-oss-120b", "preview/Kimi-K2.6", "preview/Qwen3.6-35B-A3B"]:
    print(f"\n{'='*60}")
    print(f"モデル: {model}")
    print(f"{'='*60}")
    
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": test_prompt}],
            max_tokens=100,
        )
        msg = resp.choices[0].message
        
        print(f"content: {repr(msg.content)}")
        print(f"reasoning_content: {repr(getattr(msg, 'reasoning_content', None))}")
        print(f"refusal: {repr(getattr(msg, 'refusal', None))}")
        print(f"model_extra: {getattr(msg, 'model_extra', None)}")
        print(f"finish_reason: {resp.choices[0].finish_reason}")
        
    except Exception as e:
        print(f"エラー: {e}")
