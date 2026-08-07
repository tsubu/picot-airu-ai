# AGENTS.md

# Mail RAG Desktop — Agent Handoff Guide

**Version:** 0.1  
**正の仕様:** `idea.md` → `plan.md` → `spec.md` → `task.md`  
**詳細出典:** `docs/Mail RAG Desktop システム仕様書.md` / `docs/Mail RAG Desktop.md`

エージェントは実装前に本ファイルと対象タスクを読む。手順の長文はここに増やさず、上記ドキュメントへ逃がす。

---

## 1. Project Identity

Mail RAG Desktop は、過去メール対応履歴を RAG ナレッジとし、貼り付けた顧客メールへの返信案を生成する **ローカルデスクトップ OSS** である。

**Is:**

- Tauri 2 デスクトップアプリ
- React + TypeScript UI
- Python Sidecar（RAG / Import / Gemini）
- SQLite + LanceDB
- コピー＆ペースト運用の返信案支援ツール

**Is not:**

- メール送受信クライアント
- Mail Dealer / Gmail / Thunderbird API 連携製品（v1.0）
- SaaS / マルチユーザー / クラウドDB前提アプリ
- Laravel / PHP / WordPress アプリ
- GraphRAG 必須製品（v0.3 以降の任意拡張）

---

## 2. Mandatory Stack

| 領域 | 採用 |
|------|------|
| Desktop | Tauri 2 |
| Frontend | React + TypeScript |
| Engine | Python |
| DB | SQLite |
| Vector | LanceDB |
| AI | Google Gemini API |
| Embedding | Gemini Embedding（モデル名は設定で変更。コード固定禁止） |
| 通信 | 必要時のみ Gemini。Sidecar↔UI は JSON |

---

## 3. Forbidden

次を採用・導入しない（明示依頼があっても v1.0 範囲外なら拒否し `spec.md` を更新させる）:

- メール自動送受信、クラウド同期必須化
- API Key の SQLite 平文 / ログ / Git 保存
- 顧客メール全文の通常ログ出力
- AI返答案の RAG Knowledge 自動追加
- 実顧客メールの `sample/` や Git 投入
- Next.js / Laravel / Django をメインアプリ化する構成
- 根拠なしの Gemini 一般知識による企業固有断定回答（デフォルト）

---

## 4. Repository Structure

```text
mail-rag-desktop/
├ desktop/          # Tauri + React
│  ├ src/
│  └ src-tauri/
├ python/
│  ├ importer/
│  ├ mail/
│  ├ conversation/
│  ├ rag/
│  ├ ai/
│  ├ database/
│  └ security/
├ tests/
├ sample/anonymized/
├ docs/             # 詳細仕様（出典）
├ idea.md
├ plan.md
├ spec.md
├ task.md
├ AGENTS.md
├ README.md
├ CONTRIBUTING.md
├ SECURITY.md
└ LICENSE
```

Python 配下の役割はシステム仕様書 §67 に従う。

---

## 5. Responsibility Boundaries

| 層 | やってよいこと | やらないこと |
|----|----------------|--------------|
| React | 3画面UI、コピー、進捗表示、入力 | 重い解析、Embedding、Gemini直叩き（原則） |
| Tauri | Sidecar起動、ファイル選択、Credential Store、配布 | ビジネスロジックの本体 |
| Python | Import、Role、QA、RAG、返答案、要約 | UI描画 |
| SQLite | メタ・履歴・QA・設定（Key以外） | 巨大バイナリの乱用 |
| LanceDB | Embedding・検索 | アプリ設定の正本 |
| Gemini | QA抽出、分類、要約、Query、文章再構成 | Knowledge の唯一の根拠 |

---

## 6. Non-Negotiable Design Rules

1. **UX:** 日常操作はコピー → 貼付 → 生成 → コピーに閉じる
2. **Knowledge根拠:** 実際の Customer Mail + Staff Reply のみ
3. **AI回答の再学習禁止:** 生成案を QA/LanceDB に自動投入しない
4. **Hybrid RAG必須:** Vector のみに依存しない（型番・固有名詞は FTS）
5. **Token削減:** Summary + 直近2–4往復 + RAG Top3–5
6. **RAW保持:** 解析を変えても RAW から再構築できる
7. **Role判定:** ルール優先。Gemini補助は最後
8. **Mail Dealer最優先:** 他Importerより先に品質を確保
9. **エラー耐性:** Sidecar停止でアプリ全体を落とさない
10. **仕様先行:** 挙動変更は `spec.md` / `task.md` を先に更新

---

## 7. Screen Scope（v0.1）

実装してよい画面は次のみ:

1. 新規入力
2. 返答履歴（一覧・詳細）
3. 設定（AI / 回答 / RAGデータ）

RAG・Embedding・Graph 用語を通常利用者向けに前面に出さない。

---

## 8. Implementation Workflow

```text
idea.md → plan.md → spec.md → task.md → 実装 → テスト
```

1. 作業対象タスク ID（`T0xx`）を明示する
2. スコープ外機能を足さない（YAGNI）
3. 変更後は該当テストを走らせる
4. 仕様と実装がズレたら **コードより先に spec を直す**

Implement してよい条件:

- 変更が `task.md` のいずれかに対応している
- `spec.md` の In Scope / Out of Scope に反しない
- 秘密情報をコミットしない

---

## 9. Testing Minimum

必須:

- Mail Dealer CSV Parser
- MBOX Parser
- Role Detector
- Conversation Builder
- 重複判定
- QA Extractor
- Hybrid Search
- PII Mask
- Conversation Summary
- Reply Generator
- **AI回答が Knowledge に混入しないこと**

テストデータは `sample/anonymized/` の架空データのみ。

---

## 10. Security Checklist

- [ ] API Key は OS Credential Store のみ
- [ ] ログに API Key / 顧客メール全文を出さない
- [ ] Gemini 送信前 PII Mask（設定に従う）。RAWは不変
- [ ] 実メールをリポジトリに置かない

---

## 11. When Unsure

1. `spec.md` の該当節を確認する
2. 詳細は `docs/` の仕様書を参照する
3. それでも曖昧なら実装せず、未決事項として質問する
4. 「便利そう」なメール自動連携・SaaS化は提案しても v1.0 に入れない

---

## 12. Current Priority

`task.md` の Phase 0 → Phase 1（MVP v0.1）を最優先。  
v0.2 以降（Thunderbird / GraphRAG 等）はバックログ扱い。
