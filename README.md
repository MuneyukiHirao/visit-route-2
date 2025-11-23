# VRP Route Planner (Frontend + Backend)

訪問計画（VRP）を1週間分作成するデモアプリです。Python/Flask をバックエンド、HTML/CSS/JS + Leaflet をフロントエンドに使用しています。

## 主な機能
- Google OR-Tools を用いた訪問計画最適化（訪問数最大化 > 移動時間最小化の優先度）。
- 必須フラグ、時間枠（日時指定含む）、滞在時間、ドライバー別の稼働時間/休暇設定。
- 地図上のターゲットドラッグ移動、ラベル表示切替、訪問ルートの可視化。
- ターゲット数の調整、時間枠一括クリア、開始日の平日シフト、日付フィルタ（全選択/全解除）。
- デフォルト生成ターゲットは Cebu 島のポリゴン内に限定。

## セットアップ
```bash
# バックエンド
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# フロントエンド
cd frontend
npm install
```

## 起動
```bash
# バックエンド API (Flask)
python scripts/api_server.py

# フロントエンドは index.html をローカルサーブ (例: VSCode Live Server など)
```
- デフォルトで Solver 秒数は 1 秒。開始日は今日基準で平日 5 日を生成。
- `/api/targets` は `start_date` クエリで生成開始日を指定可能。

## テスト
```bash
# バックエンド
python -m pytest

# フロントエンド
cd frontend
npm test
```

## ファイル構成
- `src/vrp/` … データ生成、距離計算、ソルバー本体。
- `scripts/api_server.py` … Flask API サーバ。
- `frontend/` … UI (Leaflet + vanilla JS)、Jest テスト。
- `tests/` … Python側ユニットテスト。

## 注意
- ネットワーク制限環境では `git push` などが失敗する場合があります。権限のある環境で実行してください。
- `.pytest_cache` などのキャッシュはコミット対象外推奨。必要に応じて `.gitignore` を更新してください。
