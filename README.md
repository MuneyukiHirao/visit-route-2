# VRP Route Planner (Frontend + Backend)

訪問計画（VRP）を 1 週間分作成するデモアプリです。Python/Flask バックエンドと HTML/JS (Leaflet) フロントエンドで構成されています。

## 主な機能
- Google OR-Tools による VRPTW：必須優先 → 訪問件数最大化 → 移動時間最小化。時間枠（日付付き/無し）を厳守。
- Cebu 島ポリゴン内でターゲットをランダム生成（必須/時間枠の付与率や滞在時間も乱数）。
- 地図でドラッグして座標編集、ラベル常時/ホバー切替、矢印付きルート表示、日付・ドライバーごとの表示切替。
- ターゲット数変更、時間枠一括クリア、開始日の平日シフト、単日計算/複数日計算の切替。
- カレンダー表示（ドライバー×日で列固定）、リスト表示（時間枠参照列あり）、RAW 出力。

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
# API サーバ (Flask)
python scripts/api_server.py

# フロントエンドは index.html をローカルサーブ（例: VSCode Live Server など）
```
- デフォルト solver 秒数は 1 秒（UI から変更可）。開始日は今日基準で平日 5 日を生成（週末は次平日にシフト）。
- `/api/targets?count=<n>&start_date=YYYY-MM-DD` でターゲット生成。

## テスト
```bash
# ルートから一括
npm test          # backend(pytest) -> frontend(jest)

# 個別
python -m pytest  # backend
cd frontend && npm test  # frontend
```
- 回帰テストには大規模シナリオ（最大 100 件）が含まれるため、数分かかることがあります。
- solver の探索時間は max_solve_seconds（基本 5〜10 秒）に制限しています。

## ディレクトリ
- `src/vrp/` … ソルバー、距離計算、データ生成
- `scripts/api_server.py` … Flask API
- `frontend/` … UI, Jest テスト
- `tests/` … Python テスト（ロードバランス/回帰/シナリオ）

## メモ
- ネットワーク制限環境では `git push` 等が制限される場合があります。
- `.pytest_cache` などキャッシュ類はコミット対象外推奨です。
