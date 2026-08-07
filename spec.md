# spec.md

# Mail RAG Desktop — 製品仕様（WHAT）

**Based on:** `idea.md` / `plan.md`  
**出典:** `docs/Mail RAG Desktop システム仕様書.md` / `docs/Mail RAG Desktop.md`  
**Status:** Draft  
**対象:** 主に MVP v0.1（将来項目は明示）

---

## 1. 概要

過去メール履歴から Hybrid RAG を構築し、貼り付けた顧客メールに対する返信案を生成するローカルデスクトップアプリ。  
日常利用でメールシステムAPI連携は行わない。

---

## 2. ユーザーストーリー

- [ ] US-1: サポート担当として、顧客メールを貼り付けて過去対応に基づく返答案が欲しい
- [ ] US-2: 同一案件の再返信でも、これまでのやり取りを踏まえた案が欲しい
- [ ] US-3: 管理者として、Mail Dealer 等の Dump を取り込み RAG を構築したい
- [ ] US-4: 根拠不足なら無理に答えず、参照した過去QAを確認したい
- [ ] US-5: API Key や個人情報を不用意に外部・ログへ出したくない

---

## 3. 画面構成

メニューは3つのみ。

```text
Mail RAG Desktop
├ 新規入力
├ 返答履歴
└ 設定
```

### 3.1 新規入力

- 顧客メール貼り付けエリア
- 「返答を生成」ボタン
- 生成後は掲示板形式（お客様 / AI返答案 / コピー / 参考情報）へ切替
- 初回生成で Conversation を作成し履歴へ保存

### 3.2 返答履歴

- Conversation 一覧（タイトル、最終更新、往復数、状態: 継続中/完了）
- 検索（v0.2で本格化可。v0.1は一覧+詳細で可）
- 詳細は掲示板形式 + 下部に「新しい返信」貼付 + 返答生成

### 3.3 設定

| セクション | 内容 |
|------------|------|
| AI設定 | Gemini API Key、QA抽出/回答/Embedding モデル、接続テスト |
| 回答設定 | 会社名、基本挨拶、回答スタイル、追加指示、禁止表現 |
| RAGデータ | 登録件数、最終更新、データ追加、構築進捗、再構築（v0.2） |

API Key は SQLite 平文保存禁止。OS Keychain / Credential Store を使用。

---

## 4. 機能要件

| ID | 要件 | 優先度 |
|----|------|--------|
| FR-1 | 顧客メール貼付から返答案生成 | Must (v0.1) |
| FR-2 | Conversation 作成・継続・状態管理 | Must (v0.1) |
| FR-3 | タイトル自動生成と手動編集 | Must (v0.1) |
| FR-4 | Hybrid RAG（Vector + FTS + Rerank） | Must (v0.1) |
| FR-5 | Mail Dealer CSV / MBOX Import | Must (v0.1) |
| FR-6 | Generic MBOX Import | Must (v0.1) |
| FR-7 | Role 判定（customer/staff/system/unknown） | Must (v0.1) |
| FR-8 | QA 抽出・Embedding・差分更新 | Must (v0.1) |
| FR-9 | 重複判定による差分 Import | Must (v0.1) |
| FR-10 | RAG Source 表示 | Must (v0.1) |
| FR-11 | 返答案コピー | Must (v0.1) |
| FR-12 | Conversation Summary + Token削減 | Must (v0.1) |
| FR-13 | 根拠不足時の回答抑制 | Must (v0.1) |
| FR-14 | Sidecar / Gemini エラーの非破壊表示 | Must (v0.1) |
| FR-15 | PII マスキング（送信前） | Should (v0.1最小 / v0.2高度化) |
| FR-16 | Thunderbird / EML / CSV | Should (v0.2) |
| FR-17 | RAG 再構築 | Should (v0.2) |
| FR-18 | GraphRAG | Could (v0.3+) |

---

## 5. 非機能要件

| ID | 要件 | 基準 |
|----|------|------|
| NFR-1 | ローカルファースト | DB・Vector はローカル。通信は Gemini 必要時のみ |
| NFR-2 | オフライン | RAG検索はローカル可。回答生成時のみエラー |
| NFR-3 | 秘密情報 | API Key は Credential Store。ログ・Git 禁止 |
| NFR-4 | ログ | 顧客メール全文を通常ログに出さない |
| NFR-5 | 再構築可能性 | RAW を保持し、Parser/QA/Embedding 変更後に再構築可能 |
| NFR-6 | 抽象化 | AIProvider / EmbeddingProvider Interface（v1.0実装はGeminiのみ） |

---

## 6. スコープ

### In Scope（v0.1）

- Tauri Desktop + React UI + Python Sidecar
- SQLite / LanceDB / Gemini
- Mail Dealer CSV・MBOX、Generic MBOX
- 新規入力・返答履歴・設定の3画面
- Hybrid Search による返答案
- 匿名化サンプルデータと必須テスト

### Out of Scope（v1.0）

- メール自動送受信、各種メールAPI連携
- ユーザー登録・ログイン・SaaS・マルチユーザー
- クラウドDB、自動送信
- GraphRAG 必須化
- AI返答案の Knowledge 再学習

---

## 7. 主要処理フロー

### 7.1 新規問い合わせ

```text
貼付 → 入力チェック → 本文クリーニング → PII Mask
  → Conversation作成 → 検索Query生成 → Hybrid RAG
  → 過去QA取得 → Gemini → 返答案 → 履歴保存
```

### 7.2 継続問い合わせ

```text
Conversation Summary + 直近Conversation + 今回メール
  → 検索Query生成 → Hybrid RAG → Gemini → 返答案
```

Gemini Context 原則：

```text
SYSTEM PROMPT
+ Conversation Summary
+ 直近 2～4 往復
+ 最新メール
+ RAG Top 3～5
+ 回答生成ルール
```

### 7.3 Import / RAG構築

```text
Dump → Parse → Role判定 → Conversation再構築
  → クリーニング → QA抽出 → Embedding → LanceDB
```

増分更新のみ。既存QAの全再Embeddingはしない（再構築ボタンは別途）。

---

## 8. データ仕様（要約）

### 共通 MailMessage

`message_id`, `subject`, `from_address`, `to_addresses`, `cc_addresses`, `date`, `body_text`, `body_html`, `in_reply_to`, `references`, `source_type`, `source_id`, `metadata`

### 主要 SQLite テーブル

`settings`, `imports`, `raw_messages`, `messages`, `conversations`, `conversation_messages`, `conversation_summaries`, `qa_pairs`, `ai_responses`, `rag_sources`, `app_logs`

### Conversation

`id`, `title`, `status` (`active`/`completed`), `summary`, `created_at`, `updated_at`

### conversation_messages.role

`customer` / `ai` / `staff_note`

### QA

`id`, `conversation_id`, `question`, `answer`, `category`, `product`, `confidence`, `verified`, `source_message_ids`, `created_at`

### 重複判定

優先: Message-ID / Mail Dealer Mail ID  
補助: Date / From / To / Subject / Body Hash

### LanceDB

QA Embedding、過去メール Embedding、Metadata、全文検索 Index

検索初期値: Vector 20 + Keyword 20 → Rerank 後 Top 5（設定変更可）

---

## 9. Importer

共通 `BaseImporter` → 各形式 → `MailMessage`

v0.1: `MailDealerCSVImporter`, `MailDealerMboxImporter`, `MboxImporter`  
v0.2: `ThunderbirdImporter`, `EmlImporter`, `CsvImporter`

Role 判定優先順位:

```text
Mail Dealer固有情報 → 送受信情報 → スタッフ登録アドレス/ドメイン
  → From/To → Gemini補助判定（最後の手段）
```

---

## 10. 回答ルール（System Prompt に含める）

- 過去ナレッジを優先する
- 根拠にない情報を推測しない
- 確証がない内容を断定しない
- 顧客向けとして自然な文章にする
- 過去スタッフ回答をそのままコピーせず再構成する
- デフォルトで Gemini 一般知識による企業固有回答をしない
- 信頼度不足時は回答せず手動対応を促す

**最重要:** AI生成返答案を RAG Knowledge に自動追加しない。

---

## 11. ローカル保存レイアウト

```text
MailRAG/
├ config/
├ workspace/
│  ├ mailrag.sqlite3
│  ├ imports/
│  ├ raw/
│  ├ lancedb/
│  ├ exports/
│  └ backup/
└ logs/
```

---

## 12. Sidecar 通信（JSON）

例: `action: generate_reply` → `success`, `answer`, `confidence`, `sources[]`

Sidecar停止時は再起動UI。アプリ全体は強制終了しない。

---

## 13. 受け入れ基準（v0.1）

- [ ] AC-1: API Key を Credential Store に保存し接続テストできる
- [ ] AC-2: Mail Dealer CSV を Import し、重複なく差分追加できる
- [ ] AC-3: Import 後に Hybrid Search で型番・言い換えの双方がヒットする
- [ ] AC-4: 新規貼付で Conversation が作成され返答案と Source が出る
- [ ] AC-5: 継続貼付で Summary / 直近履歴が考慮される
- [ ] AC-6: 根拠不足時に回答を抑制できる
- [ ] AC-7: 返答案が Knowledge に混入しない
- [ ] AC-8: 必須テスト（Parser / Role / Conversation / 重複 / QA / Hybrid / PII / Summary / Reply）が通る
- [ ] AC-9: `sample/anonymized/` に実顧客メールを置かない

---

## 14. エッジケース

| ケース | 期待動作 |
|--------|----------|
| 空入力 | 生成しない / バリデーション |
| Message-ID なし | 補助ハッシュで重複判定 |
| HTML・引用・署名付き | クリーニング後に処理。RAWは保持 |
| Sidecar 停止 | 接続失敗メッセージ + 再起動 |
| ネット不通 | RAGは可。Gemini時のみエラー |
| 信頼度不足 | 無理に生成せず警告 |

---

## 15. 依存関係

- 外部: Google Gemini API（回答・QA・Embedding・要約・Query）
- ブロッカー: なし（匿名化サンプルで開発可能）

---

## 16. 未決事項

| # | 質問 | 備考 |
|---|------|------|
| OQ-1 | 配布対象OSの優先順位（macOS / Windows / Linux） | Tauri 2 前提で後続確定 |
| OQ-2 | v0.1 の PII Mask 初期オン項目 | 仕様候補あり、デフォルト要確認 |
| OQ-3 | Rerank 実装（ローカルモデル vs Gemini） | Hybrid の一部として plan 実装時に確定 |

---

## 次ドキュメント

- `task.md` … 実装タスク
- `AGENTS.md` … エージェント実装憲法
