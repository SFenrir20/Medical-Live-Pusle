import type { WidgetConfig } from "./studio.types";

export function contactLinks(c: WidgetConfig) {
  const links: { label: string; href: string }[] = [];
  if (c.whatsapp_enabled && /^\+[1-9][0-9]{7,14}$/.test(c.whatsapp))
    links.push({ label: "WhatsApp", href: `https://wa.me/${c.whatsapp.slice(1)}` });
  if (c.instagram_enabled && /^[A-Za-z0-9._]{1,60}$/.test(c.instagram))
    links.push({
      label: "Instagram",
      href: `https://www.instagram.com/${encodeURIComponent(c.instagram)}/`,
    });
  if (c.messenger_enabled && /^[A-Za-z0-9._-]{1,60}$/.test(c.messenger))
    links.push({ label: "Messenger", href: `https://m.me/${encodeURIComponent(c.messenger)}` });
  return links;
}

/** Standalone snapshot: no credentials, external script dependency or CRM access. */
export function widgetEmbed(c: WidgetConfig): string {
  const color = (value: string, fallback: string) =>
    /^#[0-9a-fA-F]{6}$/.test(value) ? value : fallback;
  const config = JSON.stringify({
    title: c.title,
    subtitle: c.subtitle,
    color: color(c.color, "#0f92ac"),
    text: color(c.text_color, "#ffffff"),
    position: c.position === "left" ? "left" : "right",
    links: contactLinks(c),
  })
    .replace(/</g, "\\u003c")
    .replace(/>/g, "\\u003e")
    .replace(/&/g, "\\u0026")
    .replace(/\u2028/g, "\\u2028")
    .replace(/\u2029/g, "\\u2029");
  return `<script>(function(){"use strict";const c=${config};if(document.getElementById("medical-clic-widget"))return;const host=document.createElement("div");host.id="medical-clic-widget";const root=host.attachShadow({mode:"open"});const style=document.createElement("style");style.textContent=":host{position:fixed;bottom:24px;"+c.position+":24px;z-index:2147483000;font:14px/1.5 system-ui,sans-serif;color:"+c.text+";max-width:calc(100vw - 48px)}section{background:"+c.color+";border-radius:18px;padding:18px;box-shadow:0 8px 28px #0003;width:280px;max-width:100%;box-sizing:border-box}button{font:inherit;font-weight:700;background:none;border:0;color:inherit;cursor:pointer;padding:0;text-align:left;width:100%}p{margin:8px 0 12px}a{display:inline-block;color:inherit;border:1px solid currentColor;border-radius:20px;padding:6px 10px;margin:3px;text-decoration:none}[hidden]{display:none}";root.append(style);const box=document.createElement("section"),button=document.createElement("button"),panel=document.createElement("div"),subtitle=document.createElement("p");button.textContent=c.title;button.setAttribute("aria-expanded","true");button.onclick=function(){panel.hidden=!panel.hidden;button.setAttribute("aria-expanded",String(!panel.hidden))};subtitle.textContent=c.subtitle;panel.append(subtitle);for(const link of c.links){const a=document.createElement("a");a.textContent=link.label;a.href=link.href;a.target="_blank";a.rel="noopener noreferrer";panel.append(a)}box.append(button,panel);root.append(box);(document.body||document.documentElement).append(host)})();</script>`;
}
