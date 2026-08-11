import json
import os
import sqlite3
import logging
from mcp.server import MCPServer

logger = logging.getLogger(__name__)

DB_PATH = "search_history.db"

def _init_db():
    """SQLiteデータベースを初期化"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS search_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            theme TEXT NOT NULL,
            results_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

# 起動時にDB初期化
_init_db()

mcp = MCPServer("search-history")

@mcp.tool()
def save_search_history(theme: str, results_json: str) -> str:
    """検索テーマと結果を履歴として保存する"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO search_history (theme, results_json) VALUES (?, ?)",
        (theme, results_json)
    )
    conn.commit()
    conn.close()
    logger.info(f"Saved search history for: {theme[:40]}")
    return f"検索履歴を保存しました: {theme[:40]}..."

@mcp.tool()
def get_search_history(theme: str) -> str:
    """指定したテーマの最新検索履歴を取得する（完全一致）"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT results_json FROM search_history WHERE theme = ? ORDER BY created_at DESC LIMIT 1",
        (theme,)
    )
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return row[0]  # JSON文字列をそのまま返す
    return ""

@mcp.tool()
def list_all_history() -> str:
    """保存済みの全検索履歴テーマ一覧を取得する"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT theme, created_at FROM search_history ORDER BY created_at DESC"
    )
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return "検索履歴はありません。"
    
    lines = []
    for theme, created_at in rows:
        lines.append(f"- [{created_at}] {theme}")
    return "検索履歴一覧:\n" + "\n".join(lines)

if __name__ == "__main__":
    mcp.run()
