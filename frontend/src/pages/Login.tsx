import { Card, CardBody } from "@/components/ui/Card";
import { Activity, Send } from "lucide-react";

export function Login() {
  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <Card className="w-full max-w-md">
        <CardBody className="flex flex-col items-center text-center gap-5 py-8">
          <div className="w-14 h-14 rounded-2xl bg-accent/15 flex items-center justify-center">
            <Activity className="w-7 h-7 text-accent" />
          </div>
          <div>
            <h1 className="text-xl font-bold">SX Monitor</h1>
            <p className="text-muted text-sm mt-1">Панель моніторингу серверів</p>
          </div>

          <div className="w-full rounded-lg bg-panel2 p-4 text-left space-y-3 text-sm">
            <div className="flex items-center gap-2 font-medium">
              <Send className="w-4 h-4 text-accent" /> Вхід через Telegram
            </div>
            <ol className="text-muted space-y-1.5 list-decimal list-inside">
              <li>Відкрийте бота в Telegram</li>
              <li>
                Надішліть команду <code className="text-text font-mono">/login</code>
              </li>
              <li>Перейдіть за отриманим посиланням</li>
            </ol>
          </div>

          <p className="text-xs text-muted">
            Посилання діє 5 хвилин і працює лише один раз. Доступ мають тільки
            адміністратори.
          </p>
        </CardBody>
      </Card>
    </div>
  );
}
