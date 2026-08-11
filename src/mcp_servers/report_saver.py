import os
import logging
from mcp.server import MCPServer

# STDIOサーバーではstdoutを使えないのでlogging（stderr）を使用
logger = logging.getLogger(__name__)

mcp = MCPServer("report-saver")

@mcp.tool()
def save_report(filename: str, content: str) -> str:
    """レポートをMarkdownファイルとして保存する"""
    os.makedirs("reports", exist_ok=True)
    filepath = f"reports/{filename}"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info(f"Saved report: {filepath}")
    return f"レポートを保存しました: {filepath}"

@mcp.tool()
def list_reports() -> str:
    """保存済みレポートの一覧を取得する"""
    os.makedirs("reports", exist_ok=True)
    files = os.listdir("reports")
    if not files:
        return "保存済みレポートはありません。"
    return "保存済みレポート:\n" + "\n".join(f"- {f}" for f in sorted(files))

if __name__ == "__main__":
    mcp.run()
