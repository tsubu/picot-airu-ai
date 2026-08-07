import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  DEFAULT_LOCALE,
  detectBrowserLocale,
  isLocaleCode,
  LOCALE_CATALOG,
  type LocaleCode,
} from "./locales";
import { translate, type TranslateFn } from "./translate";

type I18nContextValue = {
  locale: LocaleCode;
  setLocale: (code: LocaleCode) => void;
  t: TranslateFn;
  locales: typeof LOCALE_CATALOG;
};

const I18nContext = createContext<I18nContextValue | null>(null);

const STORAGE_KEY = "picot_airu_ui_locale";

function readStoredLocale(): LocaleCode | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return isLocaleCode(v) ? v : null;
  } catch {
    return null;
  }
}

function writeStoredLocale(code: LocaleCode) {
  try {
    localStorage.setItem(STORAGE_KEY, code);
  } catch {
    /* ignore */
  }
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<LocaleCode>(
    () => readStoredLocale() ?? detectBrowserLocale() ?? DEFAULT_LOCALE,
  );

  useEffect(() => {
    document.documentElement.lang = locale;
    document.title = translate(locale, "app.title");
    writeStoredLocale(locale);
  }, [locale]);

  const setLocale = useCallback((code: LocaleCode) => {
    if (!isLocaleCode(code)) return;
    setLocaleState(code);
  }, []);

  const t = useCallback<TranslateFn>(
    (key, vars) => translate(locale, key, vars),
    [locale],
  );

  const value = useMemo(
    () => ({ locale, setLocale, t, locales: LOCALE_CATALOG }),
    [locale, setLocale, t],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}
