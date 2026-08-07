# plan.md

# Mail RAG Desktop — 実装計画

**Based on:** `idea.md`  
**出典:** システム仕様書 §77–81  
**Status:** Draft

---

## Phase 0: 設計固定

### 目的

実装前にスタック・画面・データモデル・非対象を固定する。

### 成果物

- `idea.md` / `plan.md` / `spec.md` / `task.md` / `AGENTS.md`
- リポジトリ骨格（`desktop/` / `python/` / `tests/` / `sample/` / `docs/`）

### 完了条件

- 必須スタックと禁止事項が `AGENTS.md` に明記されている
- MVP（v0.1）の In / Out of Scope が確定している

---

## Phase 1: MVP v0.1（最優先）

### 目的

Mail Dealer CSV / MBOX を取り込み、新規・継続の返信案生成が動く最小製品にする。

### 機能

- Tauri 2 デスクトップシェル
- React + TypeScript UI（新規入力 / 返答履歴 / 設定）
- Python Sidecar
- SQLite + LanceDB
- Gemini API Key（OS Credential Store）
- Mail Dealer CSV / MBOX Import
- Generic MBOX Import
- Customer / Staff 判定
- Conversation 生成・継続
- QA 抽出 + Gemini Embedding
- Hybrid Search（Vector + Full Text + Rerank）
- 返答案生成・コピー・RAG Source 表示

### 完了条件

- [ ] API Key 設定と接続テストができる
- [ ] Dump Import → RAG 構築が進み状況表示される
- [ ] 新規入力で Conversation が作られ返答案が出る
- [ ] 返答履歴から継続問い合わせができる
- [ ] 参考QAが表示されコピーできる
- [ ] AI返答案が Knowledge に追加されない

---

## Phase 2: v0.2

### 目的

Importer 拡充と運用品質を上げる。

### 機能

- Thunderbird 専用 Importer
- EML / Generic CSV
- PII Mask 高度化
- 回答スタイル設定（会社名 / 挨拶 / 禁止表現等）
- Conversation 検索
- RAG 再構築
- Import 詳細ログ
- QA 確認（将来承認の土台。MVPでは必須UIではないが DB に `verified`）

### 完了条件

- [x] Thunderbird / EML で差分 Import できる
- [x] スタッフアドレス・ドメイン設定で Role 判定できる
- [x] Embedding モデル変更後に RAG 再構築できる

---

## Phase 3: v0.3

### 目的

GraphRAG の基盤を疎結合で追加する（必須化しない）。

### 機能

- 商品 / 問題 / 原因 / 対応 Entity
- Graph Local Search
- 問い合わせ傾向分析（最小）

### 完了条件

- [x] Vector RAG と GraphRAG が疎結合である
- [x] Graph 未構築でも Hybrid RAG が動作する

---

## Phase 4: v0.4

### 目的

分析と知識運用を広げる。

### 機能

- Graph Global / DRIFT Search
- FAQ 自動生成
- Knowledge 分析
- Workspace Export / Import

### 完了条件

- [x] Global / DRIFT 検索が利用できる
- [x] FAQ / Knowledge 分析 / Workspace 入出力ができる

---

## Phase 5以降（将来拡張）

- [x] OpenAI / Ollama Provider 切替（ローカルLLM含む）
- [x] Embedding Provider 抽象（OpenAI / Gemini）
- [x] Gmail Dump / Outlook Dump / Zendesk Importer
- [ ] 追加の高度なローカル Embedding モデル同梱（任意）

---

## 技術方針（全フェーズ共通）

```text
Tauri 2 + React/TS
        ↕ JSON
   Python Sidecar
        ↕
  SQLite + LanceDB
        ↕（必要時のみ）
   Google Gemini API
```

| 層 | 技術 | 責務 |
|----|------|------|
| Desktop | Tauri 2 | 配布、OS連携、Sidecar起動、Credential Store、ファイル選択 |
| Frontend | React + TypeScript | 3画面UI、コピー、進捗表示 |
| Engine | Python | Import、解析、RAG、Gemini、要約、返答案 |
| DB | SQLite | Conversation / QA / 履歴 / 設定 |
| Vector | LanceDB | Embedding・Hybrid Search |

---

## 実装順序（v0.1）

1. リポジトリ骨格 + Tauri / React / Python Sidecar 疎通
2. SQLite スキーマ + 設定（API Key / Credential Store）
3. Importer（Mail Dealer CSV → MailMessage）
4. Role 判定 + Conversation 再構築 + 本文クリーニング
5. QA 抽出 + Embedding + LanceDB
6. Hybrid Search
7. 新規入力 → 返答案生成
8. 返答履歴 + 継続問い合わせ + Summary
9. コピー / Source 表示 / エラーハンドリング
10. 匿名化サンプル + 必須テスト

---

## リスクと対策

| リスク | 影響 | 対策 |
|--------|------|------|
| Mail Dealer CSV 形式差 | Import 失敗 | 専用 Importer + サンプル + 重複判定 |
| Role 誤判定 | QA品質低下 | ルール優先、AI判定は最後 |
| Token 肥大 | コスト・遅延 | Summary + 直近2–4往復 + Top 3–5 |
| 根拠不足の幻覚 | 誤回答 | 閾値未満は回答拒否 |
| API Key 漏洩 | 重大 | Keychain のみ、ログ禁止 |
| Sidecar 停止 | 利用不可 | 再起動UI、アプリ全体は落とさない |

---

## 次ドキュメント

- `spec.md` … 画面・データ・処理の WHAT
- `task.md` … v0.1 タスク分解
