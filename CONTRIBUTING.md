# Contributing

Mail RAG Desktop への貢献ありがとうございます。

## 開発の進め方

1. `idea.md` / `plan.md` / `spec.md` / `task.md` / `AGENTS.md` を読む
2. `task.md` のタスク ID に対応する変更のみ行う
3. 仕様変更が必要なら先に `spec.md` を更新する
4. テストを追加・実行する（実顧客メールは使わない）

## コーディング指針

- 必須スタックは `AGENTS.md` に従う（Tauri 2 / React+TS / Python / SQLite / LanceDB / Gemini）
- AI返答案を RAG Knowledge に自動追加しない
- API Key を SQLite・ログ・リポジトリに保存しない
- `sample/anonymized/` には架空データのみ置く

## Pull Request

- 対象タスク ID を記載する
- 関連するテスト結果を記載する
- 秘密情報を含めない

## 質問・議論

Issue で仕様・設計の質問をしてください。v1.0 の非対象（メール自動送受信、SaaS化など）の追加は原則受け付けません。
