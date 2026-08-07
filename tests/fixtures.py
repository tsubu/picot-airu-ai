"""Minimal anonymized fixtures for unit tests (not shipped under sample/)."""

from __future__ import annotations

from pathlib import Path

# Fictional Mail Dealer-like CSV (6 rows / 2 threads)
MAILDEALER_SAMPLE_CSV = """mail_id,message_id,subject,from,to,date,body,role
MD-1001,<md1001@example.com>,ABC-100の電源について,customer1@example.com,support@example.com,2026-07-01 10:00:00,"ABC-100の電源が入りません。どうすればよいでしょうか？",customer
MD-1002,<md1002@example.com>,Re: ABC-100の電源について,support@example.com,customer1@example.com,2026-07-01 10:15:00,"お問い合わせありがとうございます。ABC-100については、まずACアダプターと電源ケーブルのご確認をお願いします。",staff
MD-1003,<md1003@example.com>,Re: ABC-100の電源について,customer1@example.com,support@example.com,2026-07-01 11:00:00,"確認しましたが改善しません。赤いランプが3回点滅します。",customer
MD-1004,<md1004@example.com>,Re: ABC-100の電源について,support@example.com,customer1@example.com,2026-07-01 11:20:00,"赤ランプが3回点滅する場合は、本体リセットが必要です。取扱説明書12ページの手順をご実施ください。",staff
MD-2001,<md2001@example.com>,返品について,customer2@example.com,support@example.com,2026-07-02 09:00:00,"XYZ-200を返品したいです。",customer
MD-2002,<md2002@example.com>,Re: 返品について,support@example.com,customer2@example.com,2026-07-02 09:30:00,"返品申請フォームよりお手続きください。",staff
"""


def write_maildealer_sample(tmp_path: Path) -> Path:
    path = tmp_path / "maildealer_sample.csv"
    path.write_text(MAILDEALER_SAMPLE_CSV, encoding="utf-8")
    return path
