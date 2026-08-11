import os
import json
import asyncio
import re
from typing import TypedDict
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
from tavily import TavilyClient
from langgraph.graph import StateGraph, END
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

sakura = OpenAI(
    api_key=os.getenv("SAKURA_API_KEY"),
    base_url=os.getenv("SAKURA_BASE_URL"),
)
tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

REQUEST_LOG_FILE = "request_log.json"

MODEL_LIMITS = {
    "gpt-oss-120b": {"summarize": 400, "integrate": 3000},
    "llm-jp-3.1-8x13b-instruct4": {"summarize": 400, "integrate": 1500},
    "preview/Kimi-K2.6": {"summarize": 800, "integrate": 3000},
    "preview/Qwen3.6-35B-A3B": {"summarize": 800, "integrate": 3000},
    "preview/gemma-4-31B-it": {"summarize": 400, "integrate": 2000},
    "preview/Kimi-K2.7-Code": {"summarize": 400, "integrate": 2000},
    "preview/Qwen3-VL-30B-A3B-Instruct": {"summarize": 400, "integrate": 2000},
    "preview/Qwen3-0.6B-cpu": {"summarize": 400, "integrate": 1000},
    "preview/Phi-4-mini-instruct-cpu": {"summarize": 400, "integrate": 1000},
    "preview/Qwen3-Embedding-4B-FP16": {"summarize": 400, "integrate": 1000},
    "multilingual-e5-large": {"summarize": 400, "integrate": 1000},
    "whisper-large-v3-turbo": {"summarize": 400, "integrate": 1000},
}

def get_model_limit(model: str, phase: str) -> int:
    if model in MODEL_LIMITS:
        return MODEL_LIMITS[model][phase]
    return 1000 if phase == "integrate" else 400

def load_request_log():
    if os.path.exists(REQUEST_LOG_FILE):
        with open(REQUEST_LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"total": 0, "sessions": []}

def save_request_log(log):
    with open(REQUEST_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

def add_request_count(count, description):
    log = load_request_log()
    log["total"] += count
    log["sessions"].append({
        "datetime": datetime.now().isoformat(),
        "count": count,
        "description": description,
    })
    save_request_log(log)
    return log["total"]

async def call_mcp_server(server_script, tool_name, arguments):
    server_params = StdioServerParameters(
        command="python",
        args=[f"src/mcp_servers/{server_script}"],
        env=None,
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            return result.content[0].text

def extract_from_reasoning(reasoning_text: str) -> str:
    """reasoningフィールドから結論部分を抽出"""
    if not reasoning_text:
        return ""
    
    # 最後の「応該/回答/結論」部分を探す
    lines = reasoning_text.strip().split('\n')
    
    # 最後の数行に「実際の回答」が含まれていることが多い
    # 逆順に探して、空行でない最後の意味のある行を返す
    for line in reversed(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith('Thinking') and not stripped.startswith('分析') and not stripped.startswith('1.') and len(stripped) > 5:
            return stripped
    
    # 見つからなければ最後の30文字を返す
    return reasoning_text.strip()[-200:] if len(reasoning_text) > 200 else reasoning_text.strip()

def get_content_from_response(resp):
    message = resp.choices[0].message
    
    # 1. 通常の content を確認
    if message.content:
        return message.content.strip()
    
    # 2. reasoning_content を確認
    if hasattr(message, "reasoning_content") and message.reasoning_content:
        return message.reasoning_content.strip()
    
    # 3. model_extra.reasoning を確認（Kimi, Qwen等）
    if hasattr(message, "model_extra") and message.model_extra:
        reasoning = message.model_extra.get("reasoning")
        if reasoning:
            extracted = extract_from_reasoning(reasoning)
            if extracted:
                return extracted
        
        for key in ["reasoning_content", "thinking", "text"]:
            if key in message.model_extra and message.model_extra[key]:
                return str(message.model_extra[key]).strip()
    
    # 4. finish_reason が length なら警告
    finish_reason = resp.choices[0].finish_reason
    if finish_reason == "length":
        return "（応答がトークン制限で途中で切れました。max_tokensを増やす必要があります。）"
    
    return "（AIからの応答が空でした）"

def call_sakura(messages, model, max_tokens=500):
    resp = sakura.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
    )
    return resp, get_content_from_response(resp)

class ReportState(TypedDict):
    theme: str
    model: str
    search_results: list
    summaries: list
    report: str
    filename: str
    ai_calls: int
    status: str

def search_node(state: ReportState):
    theme = state["theme"]
    print(f"[Node: search] '{theme[:40]}...' の検索を開始")
    
    try:
        history_json = asyncio.run(call_mcp_server(
            "search_history.py", "get_search_history", {"theme": theme}
        ))
    except Exception as e:
        print(f"[MCPエラー] search-history: {e}")
        history_json = ""
    
    if history_json:
        print("[Node: search] 履歴再利用")
        search_results = json.loads(history_json)
    else:
        print("[Node: search] Tavily新規検索")
        search_results = tavily.search(query=theme, max_results=3)
        try:
            asyncio.run(call_mcp_server(
                "search_history.py", "save_search_history",
                {
                    "theme": theme,
                    "results_json": json.dumps(search_results, ensure_ascii=False)
                }
            ))
        except Exception as e:
            print(f"[MCPエラー] save_search_history: {e}")
    
    return {
        "search_results": search_results["results"],
        "ai_calls": 0,
        "status": "検索完了"
    }

def summarize_node(state: ReportState):
    theme = state["theme"]
    model = state["model"]
    results = state["search_results"]
    limit = get_model_limit(model, "summarize")
    print(f"[Node: summarize] モデル={model} (max_tokens={limit}) で{len(results)}件の要約を開始")
    
    summaries = []
    ai_calls = 0
    for i, result in enumerate(results, 1):
        print(f"  [{i}/{len(results)}] {result['title'][:40]}...")
        prompt = f"""以下のWebページの内容を、調査テーマ「{theme}」に関連する部分だけを抽出し、300字以内で要約してください。

---
{result['content'][:4000]}
---"""
        _, content = call_sakura([{"role": "user", "content": prompt}], model, max_tokens=limit)
        summaries.append({
            "title": result["title"],
            "url": result["url"],
            "summary": content,
        })
        ai_calls += 1
    
    return {
        "summaries": summaries,
        "ai_calls": state["ai_calls"] + ai_calls,
        "status": f"要約完了（{ai_calls}回のAI呼び出し）"
    }

def integrate_node(state: ReportState):
    theme = state["theme"]
    model = state["model"]
    summaries = state["summaries"]
    limit = get_model_limit(model, "integrate")
    print(f"[Node: integrate] モデル={model} (max_tokens={limit}) で統合レポートを生成")
    
    combined = "\n\n".join([
        f"【{s['title']}】\n{s['summary']}\n出典: {s['url']}"
        for s in summaries
    ])
    
    prompt = f"""以下は調査テーマ「{theme}」に関する複数情報源の要約です。これらを統合して、読みやすいMarkdown形式の調査レポートを作成してください。

# 調査レポート: {theme}

## 概要
（全体の要約を2〜3文で）

## 詳細
（各情報源の内容を整理して記載）

## まとめ
（結論・今後の展望）

---
{combined}
---"""
    
    _, report = call_sakura([{"role": "user", "content": prompt}], model, max_tokens=limit)
    
    return {
        "report": report,
        "ai_calls": state["ai_calls"] + 1,
        "status": "統合レポート生成完了"
    }

def save_node(state: ReportState):
    theme = state["theme"]
    model = state["model"]
    report = state["report"]
    ai_calls = state["ai_calls"]
    print("[Node: save] MCP経由で保存")
    
    safe_model = model.replace('/', '_').replace(':', '_')
    safe_name = theme.replace(' ', '_').replace('/', '_').replace('　', '_')[:40]
    filename = f"report_{safe_model}_{safe_name}.md"
    
    if len(filename) > 200:
        safe_model_short = safe_model[:15]
        safe_name_short = safe_name[:30]
        filename = f"report_{safe_model_short}_{safe_name_short}.md"
    
    try:
        save_result = asyncio.run(call_mcp_server(
            "report_saver.py", "save_report",
            {"filename": filename, "content": report}
        ))
        print(f"[MCP] {save_result}")
    except Exception as e:
        print(f"[MCPエラー] report_saver: {e}")
        os.makedirs("reports", exist_ok=True)
        with open(f"reports/{filename}", "w", encoding="utf-8") as f:
            f.write(report)
    
    total = add_request_count(ai_calls, f"LangGraph[{model}]: {theme[:30]}")
    print(f"[消費記録] 今回: {ai_calls}回 / 累計: {total}回")
    
    return {
        "filename": f"reports/{filename}",
        "status": f"完了！モデル={model} | 今回{ai_calls}回 / 累計{total}回"
    }

workflow = StateGraph(ReportState)

workflow.add_node("search", search_node)
workflow.add_node("summarize", summarize_node)
workflow.add_node("integrate", integrate_node)
workflow.add_node("save", save_node)

workflow.set_entry_point("search")
workflow.add_edge("search", "summarize")
workflow.add_edge("summarize", "integrate")
workflow.add_edge("integrate", "save")
workflow.add_edge("save", END)

graph = workflow.compile()

AVAILABLE_MODELS = [
    "gpt-oss-120b",
    "llm-jp-3.1-8x13b-instruct4",
    "preview/Kimi-K2.6",
    "preview/Qwen3.6-35B-A3B",
    "preview/gemma-4-31B-it",
    "preview/Kimi-K2.7-Code",
    "preview/Qwen3-VL-30B-A3B-Instruct",
]

def run_agent(theme: str, model: str = "gpt-oss-120b"):
    if not theme.strip():
        return "テーマを入力してください。", None, "0", AVAILABLE_MODELS
    
    initial_state = {
        "theme": theme,
        "model": model,
        "search_results": [],
        "summaries": [],
        "report": "",
        "filename": "",
        "ai_calls": 0,
        "status": "開始",
    }
    
    result = graph.invoke(initial_state)
    return result["report"], result["filename"], result["status"], AVAILABLE_MODELS

def compare_models(theme: str, models: list):
    if not theme.strip():
        return "テーマを入力してください。", None, "0", AVAILABLE_MODELS
    
    reports = []
    total_ai_calls = 0
    
    for model in models:
        print(f"\n{'='*60}")
        print(f"[モデル比較] {model} でレポート生成開始")
        print(f"{'='*60}")
        
        initial_state = {
            "theme": theme,
            "model": model,
            "search_results": [],
            "summaries": [],
            "report": "",
            "filename": "",
            "ai_calls": 0,
            "status": "開始",
        }
        
        result = graph.invoke(initial_state)
        reports.append({
            "model": model,
            "report": result["report"],
            "filename": result["filename"],
            "ai_calls": result["ai_calls"],
        })
        total_ai_calls += result["ai_calls"]
    
    comparison = f"# モデル比較レポート: {theme}\n\n"
    comparison += f"**比較モデル数**: {len(models)}個  \n"
    comparison += f"**合計AI呼び出し**: {total_ai_calls}回  \n\n"
    comparison += "---\n\n"
    
    for r in reports:
        comparison += f"## モデル: `{r['model']}`\n\n"
        comparison += f"**AI呼び出し**: {r['ai_calls']}回  \n\n"
        comparison += r["report"][:3000]
        comparison += "\n\n---\n\n"
    
    total = add_request_count(total_ai_calls, f"モデル比較[{len(models)}モデル]: {theme[:30]}")
    status = f"比較完了！{len(models)}モデル | 合計{total_ai_calls}回 / 累計{total}回"
    
    return comparison, None, status, AVAILABLE_MODELS
