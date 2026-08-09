"""PII masking before sending content to AI providers. RAW must stay unchanged."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:0\d{1,4}[-(]?\d{1,4}[-)]?\d{3,4}|\+?\d[\d\-()]{8,}\d)")
_POSTAL_RE = re.compile(r"〒?\s*\d{3}-?\d{4}")
_ORDER_RE = re.compile(r"\b(?:ORD|ORDER|注文番号)[-_:：\s]?\d{4,}\b", re.I)

# 都道府県〜番地号/号室までを広めに捕捉（過剰マスクより漏れを優先して避ける）
_PREFECTURES = (
    "北海道|東京都|京都府|大阪府|"
    "青森県|岩手県|宮城県|秋田県|山形県|福島県|"
    "茨城県|栃木県|群馬県|埼玉県|千葉県|神奈川県|"
    "新潟県|富山県|石川県|福井県|山梨県|長野県|"
    "岐阜県|静岡県|愛知県|三重県|"
    "滋賀県|兵庫県|奈良県|和歌山県|"
    "鳥取県|島根県|岡山県|広島県|山口県|"
    "徳島県|香川県|愛媛県|高知県|"
    "福岡県|佐賀県|長崎県|熊本県|大分県|宮崎県|鹿児島県|沖縄県"
)
_ADDRESS_RE = re.compile(
    rf"(?:{_PREFECTURES})"
    r"(?:[^\s、。\n]{1,40}?)?"
    r"(?:[市区町村郡]"
    r"[^\s、。\n]{0,40}?)?"
    r"(?:\d{1,4}(?:[-−ー－]\d{1,4}){0,3}|"
    r"[一二三四五六七八九十百千]+丁目|"
    r"\d+丁目)?"
    r"(?:[^\s、。\n]{0,20}?(?:番地?|号|号室|ビル|マンション|アパート))?"
)
# 「東京都千代田区…」以外の「〇〇市〇〇町1-2-3」
_CITY_ADDRESS_RE = re.compile(
    r"(?:[一-龥ぁ-んァ-ヶ]{2,12}[市区町村])"
    r"(?:[一-龥ぁ-んァ-ヶ0-9\-−ー－丁目番地号室]{2,40})"
)

# 敬称付き氏名 / ラベル付き氏名
_NAME_HONORIFIC_RE = re.compile(
    r"(?<![一-龥ぁ-んァ-ヶA-Za-z])"
    r"([一-龥ぁ-んァ-ヶ]{1,4}(?:[　\s]+[一-龥ぁ-んァ-ヶ]{1,4})?)"
    r"(?=様|さん|殿|氏|さま)"
)
_NAME_LABEL_RE = re.compile(
    r"(?:氏名|お名前|お客様名|ご担当者|担当者名|名前)"
    r"[：:\s]*"
    r"([一-龥ぁ-んァ-ヶA-Za-z]{2,20})"
)


@dataclass
class PiiMaskConfig:
    mask_email: bool = True
    mask_phone: bool = True
    mask_address: bool = True
    mask_name: bool = False
    mask_order_id: bool = False
    name_patterns: list[str] = field(default_factory=list)


def mask_pii(text: str, config: PiiMaskConfig | None = None) -> str:
    cfg = config or PiiMaskConfig()
    result = text
    if cfg.mask_email:
        result = _EMAIL_RE.sub("[EMAIL]", result)
    if cfg.mask_phone:
        result = _PHONE_RE.sub("[PHONE]", result)
    if cfg.mask_order_id:
        result = _ORDER_RE.sub("[ORDER]", result)
    if cfg.mask_address:
        result = _POSTAL_RE.sub("[ADDRESS]", result)
        result = _ADDRESS_RE.sub("[ADDRESS]", result)
        result = _CITY_ADDRESS_RE.sub("[ADDRESS]", result)
    if cfg.mask_name:
        for name in cfg.name_patterns:
            if name and name.strip():
                result = result.replace(name.strip(), "[NAME]")
        result = _NAME_LABEL_RE.sub(lambda m: m.group(0).replace(m.group(1), "[NAME]"), result)
        result = _NAME_HONORIFIC_RE.sub("[NAME]", result)
    return result
