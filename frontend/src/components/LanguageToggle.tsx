import { cn } from "@/lib/utils";
import { useI18n, type Lang } from "@/i18n";

const LANGS: { code: Lang; label: string }[] = [
  { code: "uk", label: "UA" },
  { code: "en", label: "EN" },
];

/** Segmented UK/EN language switch for page headers. */
/** Сегментований перемикач мов UK/EN для шапок сторінок. */
export function LanguageToggle({ className }: { className?: string }) {
  const { lang, setLang } = useI18n();
  return (
    <div
      className={cn(
        "inline-flex items-center rounded-md border border-border overflow-hidden text-xs",
        className
      )}
      role="group"
      aria-label="Language"
    >
      {LANGS.map(({ code, label }) => (
        <button
          key={code}
          type="button"
          onClick={() => setLang(code)}
          aria-pressed={lang === code}
          className={cn(
            "px-2 py-1 font-semibold transition-colors",
            lang === code ? "bg-accent text-bg" : "text-muted hover:text-text"
          )}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
