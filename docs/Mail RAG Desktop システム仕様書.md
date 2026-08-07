# Mail RAG Desktop システム仕様書

**Version:** 1.0  
**開発形態:** オープンソース  
**公開先:** GitHub  
**アプリ形態:** ローカルデスクトップアプリケーション  
**主要AI:** Google Gemini API  
**主要言語:** TypeScript / Python

---

# 1. プロジェクト概要

Mail RAG Desktopは、メールディーラー、Thunderbird、MBOX、EML、CSV等からエクスポートした過去のメール対応履歴をRAGナレッジとして構築し、新たに届いた顧客メールに対する返信案を生成するデスクトップアプリケーションである。

日常利用時はメールシステムとのAPI連携を必要としない。

利用者は顧客メールをコピーし、本アプリへ貼り付けることで返信案を生成する。

継続的なメールのやり取りについてはConversationとして管理し、それまでの会話履歴とRAG検索結果の双方を考慮して次の返信案を生成する。

---

# 2. 基本コンセプト

通常利用者が行う操作は極力単純にする。

## 新規問い合わせ

```text
メールソフト
    ↓
顧客メールをコピー
    ↓
新規入力画面へ貼り付け
    ↓
返答を生成
    ↓
AI返答案
    ↓
コピー
    ↓
メールソフトへ貼り付け
```

## 継続問い合わせ

```text
顧客から再返信
    ↓
返答履歴
    ↓
該当Conversationを開く
    ↓
新しいメールを貼り付け
    ↓
過去Conversation + RAG検索
    ↓
返答を生成
```

RAG、Embedding、Vector DB等の技術的要素を通常利用者へ意識させない。

---

# 3. 非対象

v1.0では以下を実装対象外とする。

- メール自動受信
- メール自動送信
- Mail Dealer API連携
- Gmail API連携
- Thunderbird直接操作
- ユーザー登録
- ログイン
- SaaS機能
- 複数ユーザー同時利用
- クラウドDB
- 自動回答送信
- GraphRAG必須化

メール送受信は既存メールシステムで行う。

本アプリは、

**「返信案生成支援ツール」**

に徹する。

---

# 4. システム構成

```text
┌─────────────────────────────────────────┐
│          Mail RAG Desktop               │
│                                         │
│ Tauri 2                                 │
│ React + TypeScript                      │
│                                         │
│ ┌──────────┐ ┌──────────┐ ┌─────────┐ │
│ │ 新規入力 │ │ 返答履歴 │ │  設定   │ │
│ └────┬─────┘ └────┬─────┘ └────┬────┘ │
│      │             │             │      │
│      └─────────────┼─────────────┘      │
│                    ↓                    │
│             Python Sidecar              │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │ Mail Parser                         │ │
│ │ Conversation Manager                │ │
│ │ QA Extractor                        │ │
│ │ Hybrid RAG Engine                   │ │
│ │ Gemini Client                       │ │
│ │ Embedding Engine                    │ │
│ └─────────────────────────────────────┘ │
│           │              │              │
│           ↓              ↓              │
│        SQLite         LanceDB           │
│                                         │
└──────────────────┬──────────────────────┘
                   │
             必要時のみ通信
                   ↓
            Google Gemini API
```

---

# 5. 採用技術

## Desktop

Tauri 2

役割：

- デスクトップアプリ化
- OS連携
- Python Sidecar起動
- アプリ配布
- ファイル選択
- Credential Store連携

---

# 6. Frontend

React + TypeScript

役割：

- 新規入力画面
- 返答履歴画面
- 設定画面
- RAG構築状況表示
- AI返答案表示
- コピー操作
- Conversation管理

---

# 7. AI / RAG Engine

Python

役割：

- メール解析
- CSV解析
- MBOX解析
- EML解析
- Customer / Staff判定
- Conversation再構築
- QA抽出
- Embedding生成
- Hybrid Search
- Gemini問い合わせ
- Conversation要約
- 回答案生成

---

# 8. ローカルDB

SQLiteを使用する。

保存対象：

- Conversation
- Message
- QA
- Import履歴
- AI生成履歴
- RAG参照履歴
- 設定
- Conversation Summary

---

# 9. Vector DB

LanceDBを使用する。

保存対象：

- QA Embedding
- 過去メールEmbedding
- 検索用Metadata
- 全文検索Index

検索方式は、

```text
Vector Search
+
Full Text Search
+
Rerank
```

によるHybrid Searchを基本とする。

---

# 10. AI

Google Gemini APIを利用する。

使用用途：

- QA抽出
- 問い合わせ分類
- Conversation要約
- 検索Query生成
- 返信案生成

モデル名をコードへ固定しない。

設定画面から変更可能にする。

---

# 11. Embedding

Gemini Embeddingモデルを基本とする。

Embedding対象：

- Question
- Question + Answer
- 正規化メール本文

初期実装ではQA単位を主要検索単位とする。

---

# 12. 画面構成

アプリの主要画面は3画面とする。

```text
1. 新規入力
2. 返答履歴
3. 設定
```

---

# 13. 新規入力画面

新しい問い合わせを開始する画面。

## UI

```text
┌─────────────────────────────────────────┐
│ Mail RAG Desktop                        │
│                                         │
│ 新規入力 ｜ 返答履歴 ｜ 設定            │
├─────────────────────────────────────────┤
│                                         │
│ 新しい問い合わせ                       │
│                                         │
│ お客様からのメール                     │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │                                     │ │
│ │ メール内容を貼り付けてください      │ │
│ │                                     │ │
│ └─────────────────────────────────────┘ │
│                                         │
│              [ 返答を生成 ]            │
│                                         │
└─────────────────────────────────────────┘
```

---

# 14. 新規入力処理

「返答を生成」を押した場合：

```text
メール本文
   ↓
入力チェック
   ↓
本文クリーニング
   ↓
PII Mask
   ↓
Conversation作成
   ↓
検索Query生成
   ↓
Hybrid RAG
   ↓
過去QA取得
   ↓
Gemini
   ↓
返答案生成
   ↓
履歴保存
```

---

# 15. 新規Conversation

初回問い合わせを受けた時点でConversationを生成する。

保存情報：

```text
id
title
summary
status
created_at
updated_at
```

初期状態：

```text
status = active
```

---

# 16. Conversationタイトル

問い合わせ本文から簡潔なタイトルを生成する。

例：

```text
ABC-100の電源トラブル

返品について

配送日の確認

支払い方法について
```

自動生成後、利用者による編集を可能にする。

---

# 17. 返答結果

生成後は掲示板形式で表示する。

```text
■ お客様

ABC-100の電源が入りません。
どうすればよいでしょうか？


■ AI返答案

お問い合わせありがとうございます。

ABC-100については、
まずACアダプターをご確認ください。

                 [コピー]


参考情報

過去QA #1023
類似度 94%

過去QA #3821
類似度 89%
```

---

# 18. 返答履歴画面

Conversation一覧を表示する。

```text
┌─────────────────────────────────────────┐
│ 返答履歴                                │
├─────────────────────────────────────────┤
│                                         │
│ [ 検索.............................. ] │
│                                         │
│ ABC-100の電源トラブル                   │
│ 最終更新 2026/08/08                     │
│ 3往復                         継続中   │
│                                         │
│ --------------------------------------- │
│                                         │
│ 商品XYZの返品                          │
│ 最終更新 2026/08/07                     │
│ 2往復                         完了     │
│                                         │
└─────────────────────────────────────────┘
```

---

# 19. Conversation状態

```text
active
completed
```

UI表示：

```text
継続中
完了
```

将来的に、

```text
pending
needs_review
```

を追加可能とする。

---

# 20. 返答履歴詳細画面

掲示板形式とする。

```text
ABC-100の電源トラブル

━━━━━━━━━━━━━━━━━━

■ お客様

ABC-100の電源が入りません。


■ AI返答案

ACアダプターをご確認ください。

[コピー]

━━━━━━━━━━━━━━━━━━

■ お客様

確認しましたが改善しませんでした。
赤いランプが3回点滅します。


■ AI返答案

赤ランプが3回点滅する場合は……

[コピー]

━━━━━━━━━━━━━━━━━━

新しい返信

┌─────────────────────────────┐
│ 次の顧客メールを貼り付け    │
└─────────────────────────────┘

[返答を生成]
```

---

# 21. 継続問い合わせ処理

2回目以降は最新メールだけを検索に使用しない。

以下を組み合わせる。

```text
Conversation Summary
+
直近Conversation
+
今回のメール
```

これらから検索用Queryを生成する。

---

# 22. Conversation Context

例：

```text
商品:
ABC-100

現在の問題:
電源が入らない

確認済み:
ACアダプター
電源ケーブル
再起動

最新状態:
赤ランプ3回点滅
```

このContextを使用してRAG検索する。

---

# 23. Conversation Summary

Conversationが長くなった場合に使用する。

保存例：

```text
商品:
ABC-100

問題:
起動不能

これまでに行った対応:
・ACアダプター確認
・再起動
・別コンセント確認

現在:
赤ランプ3回点滅

状態:
未解決
```

---

# 24. Geminiへ渡すContext

基本構成：

```text
SYSTEM PROMPT

+

Conversation Summary

+

直近のConversation

+

今回のCustomer Message

+

RAG検索結果

+

回答生成ルール
```

---

# 25. Token削減

Conversation履歴全件を毎回Geminiへ渡さない。

原則：

```text
Conversation Summary
+
直近2～4往復
+
最新メール
+
RAG Top 3～5
```

とする。

---

# 26. 設定画面

設定画面には以下を配置する。

```text
AI設定

回答設定

RAGデータ
```

---

# 27. AI設定

項目：

```text
Gemini API Key

QA抽出モデル

回答生成モデル

Embeddingモデル
```

API KeyはSQLiteへ平文保存しない。

OS Keychain / Credential Storeを利用する。

---

# 28. 回答設定

項目：

```text
会社名

基本挨拶

回答スタイル

追加指示

禁止表現
```

例：

```text
会社名:
株式会社ABC

基本挨拶:
お問い合わせいただきありがとうございます。

追加指示:
専門用語をなるべく使用しない。
過去データに存在しない内容を推測しない。
```

---

# 29. RAGデータ設定

現在の状態を表示する。

```text
登録メール

128,392件


Conversation

73,921件


QA

84,291件


最終更新

2026/08/01


[ データを追加 ]
```

---

# 30. インポート形式

初期対応：

```text
Mail Dealer CSV

Mail Dealer MBOX

Thunderbird MBOX

Generic MBOX

EML

Generic CSV
```

---

# 31. Importer構成

Importerは共通Interfaceを持つ。

```text
BaseImporter

├ MailDealerCSVImporter
├ MailDealerMboxImporter
├ ThunderbirdImporter
├ MboxImporter
├ EmlImporter
└ CsvImporter
```

各Importerは最終的に共通MailMessage形式へ変換する。

---

# 32. 共通MailMessage

```text
message_id

subject

from_address

to_addresses

cc_addresses

date

body_text

body_html

in_reply_to

references

source_type

source_id

metadata
```

---

# 33. Mail Dealer

Mail Dealerについては専用処理を用意する。

取得可能な情報を利用して、

```text
Customer

Staff

送受信

担当者

Conversation
```

を可能な限りルールベースで判断する。

---

# 34. Thunderbird / MBOX

以下を利用する。

```text
Message-ID

In-Reply-To

References

From

To

Subject

Date
```

スタッフメールアドレスまたはドメインを設定画面で登録可能にする。

---

# 35. Role判定

Role：

```text
customer

staff

system

unknown
```

判定優先順位：

```text
Mail Dealer固有情報

↓

送受信情報

↓

スタッフ登録アドレス

↓

スタッフ登録ドメイン

↓

From / To

↓

Gemini補助判定
```

AI判定は最後の手段とする。

---

# 36. メール本文クリーニング

以下を除外する。

```text
過去メール引用

署名

HTMLタグ

メーラー固有文

自動返信文

Tracking URL

不要ヘッダ
```

元メールは変更しない。

---

# 37. RAWデータ

元データは必ず保持する。

処理階層：

```text
RAW

↓

Normalized Mail

↓

Conversation

↓

QA

↓

Embedding
```

解析方式を変更した場合はRAWから再構築可能とする。

---

# 38. QA抽出

ConversationからGeminiを利用してQAを抽出する。

例：

```text
Customer:

商品Aは在庫がありますか？
明日届きますか？


Staff:

在庫があります。
東京なら明日発送予定です。
```

↓

```text
QA 1

Q:
商品Aは在庫がありますか？

A:
在庫があります。


QA 2

Q:
商品Aは明日届きますか？

A:
東京の場合は明日発送予定です。
```

---

# 39. QA構造

```text
id

conversation_id

question

answer

category

product

confidence

verified

source_message_ids

created_at
```

---

# 40. QA承認

MVPではQAレビューUIは必須としない。

ただしDB上は、

```text
verified
```

を持たせる。

将来的な人間による承認機能へ対応する。

---

# 41. Hybrid RAG

検索はVector Searchだけに依存しない。

```text
User Query
    ↓
Vector Search
    +
Full Text Search
    ↓
Merge
    ↓
Rerank
    ↓
Top-K
```

---

# 42. Hybrid Search採用理由

意味的検索：

```text
電源が入らない
```

と、

```text
起動しない
```

を関連付ける。

全文検索：

```text
ABC-100
```

等の、

- 型番
- 商品番号
- 固有名詞
- エラーコード

を正確に検索する。

---

# 43. 検索件数

初期値：

```text
Vector候補:
20件

Keyword候補:
20件

Rerank後:
5件
```

設定変更可能にする。

---

# 44. 回答生成

最終Gemini入力：

```text
今回の問い合わせ

+

Conversation Context

+

過去QA Top 5

+

回答スタイル設定
```

---

# 45. 回答ルール

以下をSystem Promptへ含める。

```text
過去ナレッジを優先する。

提供された根拠にない情報を推測しない。

確証がない内容を断定しない。

顧客向けメールとして自然な文章にする。

過去スタッフ回答をそのままコピーしない。

今回の問い合わせ内容に合わせて再構成する。
```

---

# 46. RAG信頼度不足

一定以上の検索結果が存在しない場合は無理に回答しない。

例：

```text
十分な過去対応データが見つかりませんでした。

内容を確認した上で、
手動で対応してください。
```

閾値は設定可能にする。

---

# 47. AI一般知識

デフォルトでは企業固有回答にGemini一般知識を使用しない。

回答優先順位：

```text
Conversation

↓

RAG Knowledge

↓

AI
```

AIは文章生成・整理に利用する。

---

# 48. 参考情報

回答結果にはRAG Sourceを表示する。

```text
参考にした過去回答

QA #821
類似度 94%

QA #1522
類似度 91%

QA #8301
類似度 87%
```

クリックすると元QAを確認可能とする。

---

# 49. SQLiteテーブル

主要テーブル：

```text
settings

imports

raw_messages

messages

conversations

conversation_messages

conversation_summaries

qa_pairs

ai_responses

rag_sources

app_logs
```

---

# 50. conversations

```text
id

title

status

summary

created_at

updated_at
```

---

# 51. conversation_messages

```text
id

conversation_id

role

content

created_at
```

role：

```text
customer

ai

staff_note
```

---

# 52. ai_responses

```text
id

conversation_id

message_id

model

prompt_version

confidence

created_at
```

---

# 53. rag_sources

```text
id

ai_response_id

qa_id

score

rank
```

---

# 54. imports

```text
id

source_type

filename

started_at

completed_at

total_messages

new_messages

duplicate_messages

qa_count

status
```

---

# 55. 重複判定

優先：

```text
Message-ID

Mail Dealer Mail ID
```

補助：

```text
Date

From

To

Subject

Body Hash
```

---

# 56. 差分インポート

同じ期間を含むDumpを再度Importしても重複登録しない。

```text
1月～6月
    ↓
Import

1月～7月
    ↓
Import

結果:
7月分のみ追加
```

---

# 57. RAG更新

新規QAだけEmbeddingする。

既存QAを毎回再Embeddingしない。

```text
New Mail

↓

New QA

↓

Embedding

↓

LanceDB Add
```

---

# 58. RAG再構築

設定画面から、

```text
[ RAGを再構築 ]
```

を実行可能にする。

用途：

- Embeddingモデル変更
- Parser変更
- QA抽出方式変更
- DB破損
- 検索方式変更

---

# 59. RAG構築状況

```text
メール解析

████████████████████ 100%


Conversation生成

████████████████████ 100%


QA抽出

██████████████████░░ 90%


Embedding

██████████████░░░░░░ 71%
```

---

# 60. GraphRAG

v1.0では必須としない。

将来機能として追加する。

用途：

```text
商品

↓

問題

↓

原因

↓

対応方法
```

または、

```text
問い合わせ全体の傾向分析
```

に使用する。

---

# 61. GraphRAG追加予定

将来的に、

```text
GraphRAG Local

GraphRAG Global

GraphRAG DRIFT
```

を追加可能な構造とする。

RAG EngineとGraphRAGを疎結合にする。

---

# 62. PIIマスキング

Gemini送信前に個人情報をマスキング可能にする。

対象候補：

```text
メールアドレス

電話番号

住所

氏名

顧客番号

注文番号
```

RAWデータは変更しない。

---

# 63. PII設定

設定画面：

```text
AI送信前マスキング

☑ メールアドレス

☑ 電話番号

☑ 住所

☐ 氏名

☐ 注文番号
```

---

# 64. API Key

Gemini API KeyはOS側Credential Storeに保存する。

以下へ保存しない。

```text
SQLite

workspace.json

Git Repository

Log
```

---

# 65. ローカル保存

基本保存先：

```text
MailRAG/
│
├ config/
│
├ workspace/
│   │
│   ├ mailrag.sqlite3
│   │
│   ├ imports/
│   │
│   ├ raw/
│   │
│   ├ lancedb/
│   │
│   ├ exports/
│   │
│   └ backup/
│
└ logs/
```

---

# 66. GitHub Repository

```text
mail-rag-desktop/
│
├ desktop/
│   ├ src/
│   ├ src-tauri/
│   └ package.json
│
├ python/
│   │
│   ├ importer/
│   ├ mail/
│   ├ conversation/
│   ├ rag/
│   ├ ai/
│   ├ database/
│   └ security/
│
├ tests/
│
├ sample/
│   └ anonymized/
│
├ docs/
│
├ README.md
├ CONTRIBUTING.md
├ SECURITY.md
├ LICENSE
└ AGENTS.md
```

---

# 67. Python構成

```text
python/
│
├ importer/
│   ├ base.py
│   ├ maildealer_csv.py
│   ├ maildealer_mbox.py
│   ├ thunderbird.py
│   ├ mbox.py
│   └ eml.py
│
├ mail/
│   ├ parser.py
│   ├ cleaner.py
│   ├ role_detector.py
│   └ thread_builder.py
│
├ conversation/
│   ├ manager.py
│   ├ summary.py
│   └ context.py
│
├ rag/
│   ├ embedding.py
│   ├ vector_search.py
│   ├ keyword_search.py
│   ├ hybrid_search.py
│   └ reranker.py
│
├ ai/
│   ├ gemini.py
│   ├ qa_extractor.py
│   ├ query_builder.py
│   └ reply_generator.py
│
├ database/
│   ├ sqlite.py
│   └ models.py
│
└ security/
    └ pii_masker.py
```

---

# 68. Desktop / Python通信

Python Sidecarをアプリ起動時に起動する。

通信データはJSONを基本とする。

例：

```json
{
  "action": "generate_reply",
  "conversation_id": 123,
  "content": "赤いランプが3回点滅しています"
}
```

返却：

```json
{
  "success": true,
  "answer": "お問い合わせありがとうございます……",
  "confidence": 0.93,
  "sources": [
    {
      "qa_id": 1023,
      "score": 0.94
    }
  ]
}
```

---

# 69. Sidecarエラー

Python Sidecarが停止した場合：

```text
AIエンジンとの接続に失敗しました。

[再起動]
```

を表示する。

アプリ全体を強制終了しない。

---

# 70. Gemini APIエラー

例：

```text
Gemini APIへの接続に失敗しました。

APIキーまたはネットワーク接続を確認してください。
```

履歴へ失敗状態を保存する。

---

# 71. インターネット未接続

RAG検索自体はローカルで実行可能とする。

Gemini回答生成時のみエラー表示する。

将来的にはローカルLLM対応可能な構造とする。

---

# 72. Provider抽象化

AI Provider Interfaceを用意する。

```text
AIProvider

├ GeminiProvider

将来

├ OpenAIProvider
├ OllamaProvider
└ OtherProvider
```

v1.0実装はGeminiのみ。

---

# 73. Embedding抽象化

同様にEmbedding Providerも分離する。

```text
EmbeddingProvider

├ GeminiEmbedding

将来

├ LocalEmbedding
└ OtherEmbedding
```

---

# 74. ログ

ログには以下を記録する。

```text
Import開始/終了

RAG構築

AI Request成功/失敗

Sidecar Error

DB Error
```

顧客メール全文を通常ログへ記録しない。

API Keyも絶対に記録しない。

---

# 75. テスト

必須テスト：

```text
Mail Dealer CSV Parser

MBOX Parser

Role Detector

Conversation Builder

重複判定

QA Extractor

Hybrid Search

PII Mask

Conversation Summary

Reply Generator
```

---

# 76. テストデータ

GitHubへ実際の顧客メールを置かない。

```text
sample/anonymized/
```

には架空データのみ置く。

最低限、

```text
正常メール

複数往復

複数質問

引用付き返信

署名付き返信

HTMLメール

重複メール

Message-IDなし
```

を用意する。

---

# 77. MVP v0.1

実装対象：

```text
Tauri Desktop

React UI

Python Sidecar

SQLite

Gemini API設定

Mail Dealer CSV Import

MBOX Import

Customer / Staff判定

Conversation生成

QA抽出

Gemini Embedding

LanceDB

Hybrid Search

新規入力

返答生成

返答履歴

Conversation継続

コピー機能

RAG Source表示
```

---

# 78. v0.2

```text
Thunderbird専用Importer

EML

PII Mask高度化

QA確認

回答スタイル設定

Conversation検索

RAG再構築

Import詳細ログ
```

---

# 79. v0.3

```text
GraphRAG

商品Entity

問題Entity

原因Entity

対応Entity

Graph Local Search

問い合わせ分析
```

---

# 80. v0.4

```text
Graph Global Search

DRIFT Search

FAQ自動生成

Knowledge分析

Workspace Export / Import
```

---

# 81. 将来拡張

以下を追加できる設計とする。

```text
OpenAI API

Ollama

ローカルEmbedding

Gmail Dump

Outlook Dump

Zendesk

その他サポートシステム
```

ただしMail Dealer対応を最優先とする。

---

# 82. UX原則

利用者に求める基本操作は以下のみとする。

## 初期設定

```text
Gemini API Key設定

↓

過去メールDump Import

↓

RAG構築
```

## 新規問い合わせ

```text
コピー

↓

貼り付け

↓

返答生成

↓

コピー
```

## 継続問い合わせ

```text
返答履歴

↓

Conversation選択

↓

メール貼り付け

↓

返答生成

↓

コピー
```

---

# 83. 最重要設計原則

AIが生成した返信案を自動的にRAGのKnowledgeへ追加しない。

Knowledgeの根拠は、

```text
過去の実際のCustomer Mail

+

過去の実際のStaff Reply
```

とする。

AI回答をKnowledgeとして再学習すると、

```text
AI誤回答

↓

Knowledge化

↓

次回RAG検索

↓

誤情報増幅
```

が発生する可能性があるため禁止する。

---

# 84. システムの役割

本システムにおける役割分担：

```text
過去メール
=
企業固有Knowledge


RAG
=
何を回答するべきか検索


Conversation
=
今回のやり取りの文脈


Gemini
=
今回の顧客向け文章へ再構成
```

---

# 85. 最終アーキテクチャ

```text
                 Mail Dealer
                 Thunderbird
                    MBOX
                     EML
                      │
                      ↓
               Importer Layer
                      │
                      ↓
               Mail Normalizer
                      │
                      ↓
           Conversation Builder
                      │
                      ↓
                QA Extractor
                      │
              Gemini API
                      │
                      ↓
                 QA Database
                      │
                      ↓
                  Embedding
                      │
                      ↓
                  LanceDB
                      │
                      ↓
               Hybrid Search
                      │
                      │
┌─────────────────────┼─────────────────────┐
│                     │                     │
│               Mail RAG Desktop            │
│                                           │
│   新規入力       返答履歴        設定     │
│                                           │
└─────────────────────┬─────────────────────┘
                      │
            Conversation Context
                      +
               Hybrid RAG
                      │
                      ↓
                  Gemini
                      │
                      ↓
                  返答案
                      │
                      ↓
                   コピー
                      │
                      ↓
                メールソフト
```

---

# 86. プロジェクト定義

Mail RAG Desktopは、

**「過去のメール対応履歴をRAGナレッジとして利用し、現在の問い合わせとこれまでのConversationを考慮して、企業の過去の実際の対応を根拠とした返信案を生成するローカルデスクトップOSS」**

と定義する。

v1.0ではGraphRAG等の高度な分析よりも、

**Conversation対応Hybrid RAGの精度と、コピー・貼り付けだけで利用できるシンプルなUX**

を最優先する。