"use client";

import { applyDograhVisitorContext } from "@/lib/dograh-widget";
import { api } from "@agrayian/sdk";
import { useQuery } from "@tanstack/react-query";
import { usePathname } from "next/navigation";
import { useEffect } from "react";

type DograhEmbedConfig = {
  ready: boolean;
  voice_widget_src: string;
  chat_widget_src: string;
};

export function DograhEmbed() {
  const pathname = usePathname();
  const query = useQuery({
    queryKey: ["dograh-embed"],
    queryFn: async () => (await api<DograhEmbedConfig>("/api/v1/lifecycle/dograh/browser-test")).data,
  });
  const src = query.data?.ready ? query.data.voice_widget_src || query.data.chat_widget_src : "";

  useEffect(() => {
    if (!src) return;
    const existing = document.getElementById("dograh-widget");
    if (existing instanceof HTMLScriptElement) {
      applyDograhVisitorContext(existing);
      return;
    }
    const first = document.getElementsByTagName("script")[0];
    const script = document.createElement("script");
    script.id = "dograh-widget";
    script.async = true;
    script.src = src;
    applyDograhVisitorContext(script);
    if (first?.parentNode) first.parentNode.insertBefore(script, first);
    else document.body.appendChild(script);
    return () => {
      window.DograhWidget?.end?.();
      script.remove();
    };
  }, [src]);

  useEffect(() => {
    const existing = document.getElementById("dograh-widget");
    if (existing instanceof HTMLScriptElement) applyDograhVisitorContext(existing);
  }, [pathname]);

  return null;
}
