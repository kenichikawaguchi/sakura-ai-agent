import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import gradio as gr
from agent import run_agent, compare_models, AVAILABLE_MODELS

def single_mode(theme, model):
    report, filepath, status, _ = run_agent(theme, model)
    return report, filepath, status

def compare_mode(theme, model_a, model_b):
    report, filepath, status, _ = compare_models(theme, [model_a, model_b])
    return report, filepath, status

with gr.Blocks(title="AI調査レポート生成器") as demo:
    gr.Markdown("# 🔍 AI調査レポート生成器（LangGraph + MCP + モデル比較版）")
    gr.Markdown("LangGraphのStateGraphで「検索→要約→統合→保存」を管理。複数モデルの比較も可能です。")
    
    with gr.Tab("単一モデル"):
        with gr.Row():
            theme_single = gr.Textbox(
                label="調査テーマ",
                placeholder="例: 2026年の生成AIエージェントの最新動向",
                lines=1,
            )
            model_single = gr.Dropdown(
                label="使用モデル",
                choices=AVAILABLE_MODELS,
                value="gpt-oss-120b",
            )
        btn_single = gr.Button("レポート生成", variant="primary")
    
    with gr.Tab("モデル比較（2モデル）"):
        with gr.Row():
            theme_compare = gr.Textbox(
                label="調査テーマ",
                placeholder="例: 2026年の生成AIエージェントの最新動向",
                lines=1,
            )
        with gr.Row():
            model_a = gr.Dropdown(
                label="モデルA",
                choices=AVAILABLE_MODELS,
                value="gpt-oss-120b",
            )
            model_b = gr.Dropdown(
                label="モデルB",
                choices=AVAILABLE_MODELS,
                value="llm-jp-3.1-8x13b-instruct4",
            )
        btn_compare = gr.Button("2モデルで比較生成", variant="primary")
    
    status_text = gr.Textbox(label="処理状況", interactive=False)
    
    with gr.Row():
        report_output = gr.Markdown(label="生成されたレポート")
    
    with gr.Row():
        file_output = gr.File(label="Markdownダウンロード")
    
    btn_single.click(
        fn=single_mode,
        inputs=[theme_single, model_single],
        outputs=[report_output, file_output, status_text],
    )
    
    btn_compare.click(
        fn=compare_mode,
        inputs=[theme_compare, model_a, model_b],
        outputs=[report_output, file_output, status_text],
    )

if __name__ == "__main__":
    demo.launch()
