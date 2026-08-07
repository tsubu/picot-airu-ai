import { DEFAULT_LOCALE, LOCALE_MESSAGES, type LocaleCode } from "./locales";

type Vars = Record<string, string | number | null | undefined>;

function lookup(obj: unknown, path: string): string | undefined {
  const parts = path.split(".");
  let cur: unknown = obj;
  for (const part of parts) {
    if (cur == null || typeof cur !== "object") return undefined;
    cur = (cur as Record<string, unknown>)[part];
  }
  return typeof cur === "string" ? cur : undefined;
}

function interpolate(template: string, vars?: Vars): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (_, key: string) => {
    const v = vars[key];
    return v == null ? "" : String(v);
  });
}

/** Flat key path e.g. "settings.saveSettings" */
export function translate(locale: LocaleCode, key: string, vars?: Vars): string {
  const primary = lookup(LOCALE_MESSAGES[locale], key);
  if (primary != null) return interpolate(primary, vars);
  if (locale !== DEFAULT_LOCALE) {
    const fallback = lookup(LOCALE_MESSAGES[DEFAULT_LOCALE], key);
    if (fallback != null) return interpolate(fallback, vars);
  }
  return key;
}

export type TranslateFn = (key: string, vars?: Vars) => string;
