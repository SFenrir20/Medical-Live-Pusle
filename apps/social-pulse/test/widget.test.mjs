import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { contactLinks, widgetEmbed } from "../src/features/automation/widget.ts";

const config = {
  title: "Contáctanos",
  subtitle: "Elige un canal",
  color: "#0f92ac",
  text_color: "#ffffff",
  position: "right",
  whatsapp: "+51987654321",
  whatsapp_enabled: true,
  instagram: "medical.clinica",
  instagram_enabled: true,
  messenger: "",
  messenger_enabled: false,
};

test("contact links only target validated platform accounts", () => {
  assert.deepEqual(
    contactLinks(config).map((l) => l.href),
    ["https://wa.me/51987654321", "https://www.instagram.com/medical.clinica/"],
  );
  assert.deepEqual(
    contactLinks({ ...config, whatsapp: "javascript:alert(1)", instagram: "https://evil.example" }),
    [],
  );
});

test("embed runs standalone, treats titles as text, and mounts only one widget", () => {
  const nodes = new Map();
  function element(tag) {
    return {
      tag,
      children: [],
      attributes: {},
      append(...children) {
        this.children.push(...children);
        for (const child of children) if (child.id) nodes.set(child.id, child);
      },
      attachShadow() {
        this.shadow = element("shadow");
        return this.shadow;
      },
      setAttribute(k, v) {
        this.attributes[k] = v;
      },
    };
  }
  const document = {
    getElementById: (id) => nodes.get(id),
    createElement: element,
    body: element("body"),
  };
  const dangerous = "</script><img src=x onerror=alert(1)>";
  const embed = widgetEmbed({ ...config, title: dangerous });
  assert.equal((embed.match(/<\/script>/g) || []).length, 1);
  const script = embed.slice(8, -9);
  vm.runInNewContext(script, { document });
  vm.runInNewContext(script, { document });
  assert.equal(document.body.children.length, 1);
  const box = document.body.children[0].shadow.children[1];
  assert.equal(box.children[0].textContent, dangerous);
  assert.equal(box.children[1].children[1].href, "https://wa.me/51987654321");
  box.children[0].onclick();
  assert.equal(box.children[1].hidden, true);
});
