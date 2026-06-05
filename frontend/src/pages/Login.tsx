import { Card, CardBody } from "@/components/ui/Card";
import { LanguageToggle } from "@/components/LanguageToggle";
import { useI18n } from "@/i18n";
import { Activity, Send } from "lucide-react";

export function Login() {
  const { t } = useI18n();
  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="absolute top-4 right-4">
        <LanguageToggle />
      </div>
      <Card className="w-full max-w-md">
        <CardBody className="flex flex-col items-center text-center gap-5 py-8">
          <div className="w-14 h-14 rounded-2xl bg-accent/15 flex items-center justify-center">
            <Activity className="w-7 h-7 text-accent" />
          </div>
          <div>
            <h1 className="text-xl font-bold">SX Monitor</h1>
            <p className="text-muted text-sm mt-1">{t("login.subtitle")}</p>
          </div>

          <div className="w-full rounded-lg bg-panel2 p-4 text-left space-y-3 text-sm">
            <div className="flex items-center gap-2 font-medium">
              <Send className="w-4 h-4 text-accent" /> {t("login.viaTelegram")}
            </div>
            <ol className="text-muted space-y-1.5 list-decimal list-inside">
              <li>{t("login.step1")}</li>
              <li>
                {t("login.step2")}{" "}
                <code className="text-text font-mono">/login</code>
              </li>
              <li>{t("login.step3")}</li>
            </ol>
          </div>

          <p className="text-xs text-muted">{t("login.note")}</p>
        </CardBody>
      </Card>
    </div>
  );
}
