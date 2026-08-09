# Mail RAG Desktop

過去のメール対応履歴をRAGナレッジとして利用し、顧客メールへの返信案を生成するローカルデスクトップOSSです。

## 特徴

- コピー＆ペーストだけで返信案を生成
- Conversation単位で継続問い合わせに対応
- Hybrid RAG（Vector + 全文検索 + Rerank）
- Mail Dealer 等の Dump Import
- 必要時のみ Google Gemini API に接続

## ドキュメント

| ファイル | 内容 |
|----------|------|
| [idea.md](./idea.md) | ビジョン |
| [plan.md](./plan.md) | 実装フェーズ |
| [spec.md](./spec.md) | 製品仕様 |
| [task.md](./task.md) | タスク一覧 |
| [AGENTS.md](./AGENTS.md) | エージェント実装指針 |
| [docs/](./docs/) | 詳細仕様書 |

## 必要環境

- Node.js 20+
- Rust（Tauri 2）
- Python 3.11+

## 開発起動

```bash
# 初回のみ
./scripts/setup.sh

# 起動（Sidecar + Tauri）
./start.sh
# または
./scripts/start.sh

# 停止
./scripts/stop.sh
```

その他の起動モード:

```bash
./scripts/start.sh web      # Sidecar + Vite（ブラウザ）
./scripts/start.sh sidecar # Sidecar のみ
```

テスト:

```bash
source python/.venv/bin/activate
python -m pytest tests/ -q
```

> 注意: サンプル CSV や登録済みワークスペース（`~/MailRAG` 等）はリポジトリに含めません。ローカル確認用データは `sample/anonymized/` に各自配置してください。

> 注意: Tauri 2 の依存関係は **rustc 1.88+** を推奨します。ディスク空き容量が少ないと `rustup update` / `cargo` が失敗することがあります。

# デスクトップ配布ビルド（.app / .dmg / .exe）

```bash
# Sidecar + Tauri 一括
./scripts/build_desktop.sh

# 成果物例
# macOS: desktop/src-tauri/target/release/bundle/macos/*.app
#        desktop/src-tauri/target/release/bundle/dmg/*.dmg
# Windows: CI の Artifacts（下記）
```

GitHub Actions: `.github/workflows/release-desktop.yml`  
`workflow_dispatch` または `v*` タグ push で macOS / Windows 成果物を作成します。

## ライセンス

MIT（予定）。詳細は [LICENSE](./LICENSE) を参照。

## セキュリティ

API Key や顧客データの扱いは [SECURITY.md](./SECURITY.md) を参照してください。
