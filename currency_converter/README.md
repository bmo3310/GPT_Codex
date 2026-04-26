 (cd "$(git rev-parse --show-toplevel)" && git apply --3way <<'EOF' 
diff --git a/README.md b/README.md
index 207ac8edcab234bbffa1bcf40006e7902545711b..c4d04a99ec93610564a793ffe28f1b3c887e3912 100644
--- a/README.md
+++ b/README.md
@@ -1 +1,26 @@
-# GPT_Codex
\ No newline at end of file
+# GPT_Codex
+
+## 在不影響既有主程式下新增「即時匯率小程式」
+
+為了避免干擾既有專案（例如你提到的醫師排班系統），匯率工具已拆成**獨立子資料夾**：
+
+- `mini_fx_tool/app.py`
+- `mini_fx_tool/requirements.txt`
+
+這樣做的重點是：
+
+1. 不修改主系統入口檔案。
+2. 不覆蓋主系統相依套件設定。
+3. 匯率工具可用自己的虛擬環境獨立執行。
+
+### 執行方式（獨立）
+
+```bash
+cd mini_fx_tool
+python -m venv .venv
+source .venv/bin/activate
+pip install -r requirements.txt
+streamlit run app.py
+```
+
+打開終端機顯示的本機網址（通常是 `http://localhost:8501`）即可使用。
 
EOF
)