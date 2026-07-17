// Dica de instalação do PWA — com instruções específicas para iPhone (iOS),
// onde não existe o prompt automático de instalação (beforeinstallprompt).

import { useEffect, useState } from "react";

function isIOS(): boolean {
  const ua = navigator.userAgent;
  return /iPad|iPhone|iPod/.test(ua) && !("MSStream" in window);
}

function isStandalone(): boolean {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    // iOS Safari
    (navigator as unknown as { standalone?: boolean }).standalone === true
  );
}

export default function InstallHint() {
  const [deferred, setDeferred] = useState<Event | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    const handler = (e: Event) => {
      e.preventDefault();
      setDeferred(e);
    };
    window.addEventListener("beforeinstallprompt", handler);
    return () => window.removeEventListener("beforeinstallprompt", handler);
  }, []);

  if (dismissed || isStandalone()) return null;

  // Android/desktop: botão nativo de instalação.
  if (deferred) {
    return (
      <div className="install-hint">
        <span>Instale o StormWatch na tela inicial para receber os alertas.</span>
        <button
          type="button"
          onClick={async () => {
            // @ts-expect-error prompt existe no BeforeInstallPromptEvent
            deferred.prompt();
            setDeferred(null);
          }}
        >
          Instalar
        </button>
      </div>
    );
  }

  // iPhone: instrução manual (Compartilhar → Adicionar à Tela de Início).
  if (isIOS()) {
    return (
      <div className="install-hint">
        <span>
          No iPhone: toque em <strong>Compartilhar</strong> (⬆️) e depois em{" "}
          <strong>“Adicionar à Tela de Início”</strong> para instalar e receber alertas.
        </span>
        <button type="button" onClick={() => setDismissed(true)}>
          Entendi
        </button>
      </div>
    );
  }

  return null;
}
