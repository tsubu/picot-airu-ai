/**
 * 言語を追加する手順:
 * 1. locales/<code>.json を追加（ja.json をコピーして翻訳）
 * 2. 下で import し、LOCALE_CATALOG に1エントリ追加
 */
import ja from "./locales/ja.json";
import en from "./locales/en.json";
// import fr from "./locales/fr.json";

export type LocaleMessages = typeof ja;

export const LOCALE_CATALOG = [
  { code: "ja", nativeLabel: "日本語", messages: ja },
  { code: "en", nativeLabel: "English", messages: en },
  // { code: "fr", nativeLabel: "Français", messages: fr },
] as const satisfies ReadonlyArray<{
  code: string;
  nativeLabel: string;
  messages: LocaleMessages;
}>;

export type LocaleCode = (typeof LOCALE_CATALOG)[number]["code"];

export const DEFAULT_LOCALE: LocaleCode = "ja";

export const LOCALE_MESSAGES: Record<LocaleCode, LocaleMessages> = Object.fromEntries(
  LOCALE_CATALOG.map((l) => [l.code, l.messages]),
) as Record<LocaleCode, LocaleMessages>;

export function isLocaleCode(value: string | null | undefined): value is LocaleCode {
  return LOCALE_CATALOG.some((l) => l.code === value);
}

export function detectBrowserLocale(): LocaleCode {
  const lang = (navigator.language || "").toLowerCase();
  const match = LOCALE_CATALOG.find((l) => lang.startsWith(l.code));
  return match?.code ?? DEFAULT_LOCALE;
}
