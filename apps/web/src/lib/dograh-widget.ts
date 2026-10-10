export type DograhChatTurn = {
  user_message?: { text?: string } | null;
  assistant_message?: { text?: string } | null;
};

export type DograhWidgetApi = {
  start: () => void;
  end: () => void;
  startChat?: () => void;
  sendMessage?: (text: string) => Promise<DograhChatTurn[] | null>;
  setContext?: (vars: Record<string, string>) => void;
  onStatusChange?: (cb: (status: string, text?: string) => void) => void;
  onMessage?: (cb: (text: string) => void) => void;
  onChatStateChange?: (cb: (state: string) => void) => void;
  onError?: (cb: (err: Error) => void) => void;
};

declare global {
  interface Window {
    DograhWidget?: DograhWidgetApi;
  }
}

export function dograhVisitorContext(): Record<string, string> {
  return {
    page_url: window.location.href,
    today: new Date().toISOString().slice(0, 10),
  };
}

export function applyDograhVisitorContext(script: HTMLScriptElement) {
  const context = dograhVisitorContext();
  script.setAttribute("data-dograh-context", JSON.stringify(context));
  window.DograhWidget?.setContext?.(context);
}
