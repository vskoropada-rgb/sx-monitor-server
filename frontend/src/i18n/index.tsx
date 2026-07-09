// Lightweight, dependency-free i18n layer.
// Легкий шар i18n без зовнішніх залежностей.
//
// Holds the active language, persists the choice, and exposes both a
// translator (`t` / `tn`) and locale-aware date/duration formatters so every
// component renders through a single source of truth.
// Зберігає активну мову, запам'ятовує вибір і надає як перекладач (`t` / `tn`),
// так і локалізовані форматери дат/тривалості — щоб усі компоненти
// рендерилися через єдине джерело істини.

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { ukStrings, ukPlurals } from "./locales/uk";
import { enStrings, enPlurals } from "./locales/en";

export type Lang = "uk" | "en";
export type PluralForms = { one: string; few: string; many: string };
export type StringKey = keyof typeof ukStrings;
export type PluralKey = keyof typeof ukPlurals;
type Vars = Record<string, string | number>;

// Dashboard timestamps are always shown in Kyiv time (see CLAUDE.md invariant).
// Часові мітки дашборду завжди у київському часі (інваріант із CLAUDE.md).
const TZ = "Europe/Kyiv";
const STORAGE_KEY = "sx-lang";
const BCP47: Record<Lang, string> = { uk: "uk-UA", en: "en-GB" };

const DICT = {
  uk: { strings: ukStrings, plurals: ukPlurals },
  en: { strings: enStrings, plurals: enPlurals },
} as const;

/** Replace {placeholders} with provided values. / Підставляє {змінні}. */
function interpolate(template: string, vars?: Vars): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (_, key) =>
    key in vars ? String(vars[key]) : `{${key}}`
  );
}

/**
 * Pick the correct plural form. Ukrainian has three (one/few/many);
 * English collapses to one/other (we reuse `many` as "other").
 * Обирає правильну форму множини: укр. — три (один/кілька/багато),
 * англ. — одна/решта (як "решту" використовуємо `many`).
 */
function selectPlural(lang: Lang, n: number, f: PluralForms): string {
  if (lang === "uk") {
    const mod10 = n % 10;
    const mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return f.one;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return f.few;
    return f.many;
  }
  return n === 1 ? f.one : f.many;
}

/** First-visit default: saved choice → browser language → Ukrainian. */
/** Типове значення: збережений вибір → мова браузера → українська. */
function detectLang(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "uk" || saved === "en") return saved;
  } catch {
    /* localStorage unavailable (private mode) — fall through */
  }
  const nav = (navigator.language || "").toLowerCase();
  return nav.startsWith("en") ? "en" : "uk";
}

function parseIso(iso: string): Date {
  // Backend sends naive UTC; append Z so the browser converts to Kyiv time.
  // Бекенд шле naive UTC; додаємо Z, щоб браузер перевів у київський час.
  return new Date(iso.endsWith("Z") ? iso : iso + "Z");
}

interface I18nValue {
  lang: Lang;
  locale: string;
  setLang: (lang: Lang) => void;
  t: (key: StringKey, vars?: Vars) => string;
  tn: (key: PluralKey, n: number, vars?: Vars) => string;
  fmtDateTime: (iso: string | null) => string; // DD.MM HH:mm
  fmtTime: (iso: string | null) => string; // HH:mm:ss
  fmtHm: (iso: string | null) => string; // HH:mm
  fmtDowntime: (min: number) => string;
  fmtDuration: (sec: number | null) => string; // session length, seconds → "2г 15хв"
  timeAgo: (iso: string | null) => string;
}

const I18nContext = createContext<I18nValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(detectLang);

  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* ignore persistence errors / ігноруємо помилки збереження */
    }
    document.documentElement.lang = next;
  }, []);

  const value = useMemo<I18nValue>(() => {
    const locale = BCP47[lang];
    const { strings, plurals } = DICT[lang];

    const t = (key: StringKey, vars?: Vars) =>
      interpolate(strings[key], vars);

    const tn = (key: PluralKey, n: number, vars?: Vars) =>
      interpolate(selectPlural(lang, n, plurals[key]), { n, ...vars });

    const fmtDateTime = (iso: string | null) =>
      iso
        ? parseIso(iso).toLocaleString(locale, {
            day: "2-digit",
            month: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
            timeZone: TZ,
          })
        : "—";

    const fmtTime = (iso: string | null) =>
      iso
        ? parseIso(iso).toLocaleTimeString(locale, {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
            timeZone: TZ,
          })
        : "—";

    const fmtHm = (iso: string | null) =>
      iso
        ? parseIso(iso).toLocaleTimeString(locale, {
            hour: "2-digit",
            minute: "2-digit",
            timeZone: TZ,
          })
        : "—";

    const fmtDowntime = (min: number) => {
      if (min < 60) return lang === "uk" ? `${min} хв` : `${min} min`;
      const h = Math.floor(min / 60);
      const m = min % 60;
      if (lang === "uk") return m > 0 ? `${h}г ${m}хв` : `${h} год`;
      return m > 0 ? `${h}h ${m}m` : `${h} h`;
    };

    const fmtDuration = (sec: number | null) => {
      if (sec == null) return "—";
      if (sec < 60) return lang === "uk" ? `${sec} с` : `${sec} s`;
      const totalMin = Math.floor(sec / 60);
      const h = Math.floor(totalMin / 60);
      const m = totalMin % 60;
      if (h === 0) return lang === "uk" ? `${m} хв` : `${m} min`;
      if (lang === "uk") return m > 0 ? `${h}г ${m}хв` : `${h} год`;
      return m > 0 ? `${h}h ${m}m` : `${h} h`;
    };

    const timeAgo = (iso: string | null) => {
      if (!iso) return "—";
      const sec = Math.floor((Date.now() - parseIso(iso).getTime()) / 1000);
      const u =
        lang === "uk"
          ? { s: "с тому", m: "хв тому", h: "г тому", d: "д тому" }
          : { s: "s ago", m: "m ago", h: "h ago", d: "d ago" };
      if (sec < 60) return `${sec}${u.s}`;
      const min = Math.floor(sec / 60);
      if (min < 60) return `${min}${u.m}`;
      const hr = Math.floor(min / 60);
      if (hr < 24) return `${hr}${u.h}`;
      return `${Math.floor(hr / 24)}${u.d}`;
    };

    return {
      lang,
      locale,
      setLang,
      t,
      tn,
      fmtDateTime,
      fmtTime,
      fmtHm,
      fmtDowntime,
      fmtDuration,
      timeAgo,
    };
  }, [lang, setLang]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within <I18nProvider>");
  return ctx;
}
