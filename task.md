# task.md

# Mail RAG Desktop — 実装タスク

**Based on:** `plan.md` / `spec.md`  
**対象:** Phase 0〜1（MVP v0.1）  
**凡例:** `[S]` 直列依存 / `[P]` 並列可

---

## タスク一覧

### Phase 0: 設計・骨格

- [x] T001 [S] リポジトリ骨格作成（`desktop/` `python/` `tests/` `sample/anonymized/` `docs/`）
- [x] T002 [P] README / LICENSE / CONTRIBUTING / SECURITY 下書き
- [x] T003 [S] Tauri 2 + React + TypeScript 起動確認
- [x] T004 [S] Python Sidecar 起動・JSON 疎通（health check）

### Phase 1a: データ基盤

- [x] T005 [S] SQLite スキーマ・マイグレーション（spec §8 テーブル）
- [x] T006 [P] モデル定義（conversations / messages / qa / imports 等）
- [x] T007 [S] ローカル workspace ディレクトリ初期化
- [x] T008 [S] 設定保存 + Gemini API Key を OS Credential Store へ

### Phase 1b: Import / Mail

- [x] T009 [S] `BaseImporter` + 共通 `MailMessage`
- [x] T010 [P] Mail Dealer CSV Importer
- [x] T011 [P] Mail Dealer MBOX / Generic MBOX Importer
- [x] T012 [S] 重複判定（Message-ID / Mail Dealer ID / Body Hash）
- [x] T013 [S] Role Detector（ルール優先、AIは最後）
- [x] T014 [S] 本文クリーニング（引用・署名・HTML除去。RAW保持）
- [x] T015 [S] Conversation / Thread 再構築

### Phase 1c: RAG

- [x] T016 [S] Gemini Client（Provider 抽象の骨格付き）
- [x] T017 [S] QA Extractor
- [x] T018 [S] Embedding Engine + LanceDB 書き込み
- [x] T019 [P] Vector Search
- [x] T020 [P] Full Text Search
- [x] T021 [S] Hybrid Search + Rerank + Top-K
- [x] T022 [S] 増分 Embedding（新規QAのみ）
- [x] T023 [P] Import / RAG 進捗表示 API + UI

### Phase 1d: 返信生成 UX

- [x] T024 [S] 新規入力画面（貼付 → 生成）
- [x] T025 [S] 返答案生成パイプライン（Query → RAG → Gemini → 保存）
- [x] T026 [S] Conversation タイトル自動生成
- [x] T027 [S] 掲示板表示 + コピー + RAG Source 表示
- [x] T028 [S] 返答履歴一覧（状態: 継続中/完了）
- [x] T029 [S] 返答履歴詳細 + 継続問い合わせ
- [x] T030 [S] Conversation Summary + Token削減 Context 組立
- [x] T031 [S] 根拠不足時の回答抑制
- [x] T032 [P] 設定画面（AI / 回答 / RAGデータ）

### Phase 1e: 品質・安全

- [x] T033 [P] PII Mask（送信前・RAW不変）最小実装
- [x] T034 [P] Sidecar / Gemini エラー UI（再起動・履歴失敗保存）
- [x] T035 [S] AI返答案の Knowledge 混入禁止をテストで固定
- [x] T036 [S] 匿名化サンプルデータ用意
- [x] T037 [S] 必須テスト一式
- [x] T038 [P] アプリログ方針（全文・API Key 記録禁止）

---

## 依存関係

```text
T001 → T003 → T004
T004 → T005 → T006 → T007 → T008
T008 → T009 → (T010, T011) → T012 → T013 → T014 → T015
T008 → T016 → T017 → T018 → (T019, T020) → T021 → T022
T015 + T021 → T025
T023 ∥ T018〜T022
T024 → T025 → T026 → T027
T025 → T028 → T029 → T030 → T031
T008 → T032
T025 → T033, T034, T035
T010〜T031 → T036 → T037
```

---

## タスク詳細（主要）

### T001: リポジトリ骨格

- **Files:** `desktop/`, `python/`, `tests/`, `sample/anonymized/`, `docs/`
- **Acceptance:** 仕様書 §66 のトップレベル構成が存在する
- **Test:** ディレクトリ一覧確認

### T004: Python Sidecar 疎通

- **Files:** `python/` エントリ、Tauri Sidecar 設定
- **Acceptance:** アプリ起動で Sidecar が立ち、`health` JSON が返る
- **Test:** 手動 + 自動ヘルスチェック

### T008: API Key / Credential Store

- **Files:** 設定UI、Tauri credential 連携、Python 側読取経路
- **Acceptance:** Key が SQLite / ログ / リポジトリに残らない
- **Test:** 保存先検査 + 接続テスト

### T010 / T011: Importer

- **Files:** `python/importer/`
- **Acceptance:** サンプル Dump が `MailMessage` 配列になる。差分再Importで重複ゼロ増
- **Test:** Parser / 重複判定テスト

### T021: Hybrid Search

- **Files:** `python/rag/`
- **Acceptance:** 言い換えヒット + 型番正確ヒット。Top-K 設定可
- **Test:** Hybrid Search テスト

### T025: 返答案生成

- **Files:** `python/ai/reply_generator.py`, Sidecar action, UI
- **Acceptance:** AC-4/5。sources 付き。Knowledge 非追加
- **Test:** Reply Generator + 混入禁止テスト

### T030: Summary / Token削減

- **Files:** `python/conversation/summary.py`, `context.py`
- **Acceptance:** 長文Conversationでも Summary + 直近2–4往復 + Top3–5のみ送る
- **Test:** Conversation Summary テスト

### T037: 必須テスト

対象:

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

---

## v0.4 / Phase5（実装済み）

- [x] Graph Global / DRIFT Search
- [x] FAQ 自動生成
- [x] Knowledge 分析
- [x] Workspace Export / Import
- [x] OpenAI / Ollama Provider
- [x] Gmail / Outlook / Zendesk Importer

## 任意バックログ

- 追加の高度なローカル Embedding モデル同梱
- GraphRAG 公式アルゴリズム完全互換

---

## 完了の定義（v0.1）

`spec.md` の AC-1〜AC-9 を満たし、`task.md` Phase 0〜1e がチェック完了していること。
