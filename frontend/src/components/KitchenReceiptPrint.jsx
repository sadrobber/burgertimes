const FULFILLMENT_LABEL = { pickup: "A EMPORTER", delivery: "LIVRAISON" };
const PAYMENT_LABEL = { cash: "Especes sur place", card_in_person: "Carte sur place" };

function fmtDateTime(iso) {
  try {
    const d = new Date(iso);
    return {
      date: d.toLocaleDateString("fr-FR"),
      time: d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }),
    };
  } catch {
    return { date: "", time: "" };
  }
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

/**
 * Builds a fully standalone 80mm ticket HTML document (own inline <style>,
 * black text on a white background) — completely isolated from the app's
 * dark brutalist theme so it can never inherit it during print.
 */
function buildReceiptHtml(order) {
  const { date, time } = fmtDateTime(order.created_at);
  const customerName = `${order.customer_first_name || ""} ${order.customer_last_name || ""}`.trim();
  const cleanNote = (order.notes || "").replace("[TEST ORDER]", "").trim();
  const fulfillmentLabel = FULFILLMENT_LABEL[order.fulfillment] || "SUR PLACE";

  const itemsHtml = (order.items || [])
    .map((it) => {
      const mods = [];
      if (it.burger_config?.size?.label) mods.push(`Taille : ${esc(it.burger_config.size.label)}`);
      (it.burger_config?.meats || []).forEach((m) => mods.push(`+ ${esc(m.name)}`));
      (it.burger_config?.cheeses || []).forEach((c) => mods.push(`+ ${esc(c.name)}`));
      (it.burger_config?.supplements || []).forEach((s) => mods.push(`+ ${esc(s.name)}`));
      if (it.selected_format) mods.push(esc(it.selected_format));
      if (it.formula === "menu" && it.included_drink) mods.push(`Boisson : ${esc(it.included_drink)}`);
      (it.sauces || []).forEach((s) => mods.push(`+ ${esc(s)}`));
      return `
        <div class="kr-item">
          <div class="kr-bold">${esc(it.quantity)}x ${esc(it.name)}</div>
          <div class="kr-mods">${mods.map((m) => `<div>${m}</div>`).join("")}</div>
          ${it.notes ? `<div class="kr-callout">${esc(it.notes)}</div>` : ""}
          <div class="kr-divider-thin"></div>
        </div>`;
    })
    .join("");

  const fulfillmentBlock =
    order.fulfillment === "delivery"
      ? `<div class="kr-block">
          <div class="kr-bold">LIVRAISON</div>
          ${customerName ? `<div>Client : ${esc(customerName)}</div>` : ""}
          ${order.customer_phone ? `<div>Tel : ${esc(order.customer_phone)}</div>` : ""}
          ${
            order.address_line1 || order.address_line2
              ? `<div>${esc(order.address_line1)}${order.address_line2 ? `, ${esc(order.address_line2)}` : ""}</div>`
              : ""
          }
          ${order.postal_code || order.city ? `<div>${esc(order.postal_code)} ${esc(order.city)}</div>` : ""}
        </div>`
      : `<div class="kr-block">
          <div class="kr-bold">${esc(fulfillmentLabel)}</div>
          ${customerName ? `<div>Client : ${esc(customerName)}</div>` : ""}
          ${order.customer_phone ? `<div>Tel : ${esc(order.customer_phone)}</div>` : ""}
          ${order.pickup_code ? `<div>Code retrait : ${esc(order.pickup_code)}</div>` : ""}
        </div>`;

  return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<title>Commande ${esc(order.order_number)}</title>
<style>
  @page { size: 80mm auto; margin: 2mm; }
  * { box-sizing: border-box; }
  html, body {
    margin: 0; padding: 0; background: #fff; color: #000;
    font-family: "Courier New", Courier, monospace;
    width: 76mm;
  }
  .kr-center { text-align: center; }
  .kr-bold { font-weight: 700; }
  .kr-xl { font-size: 15pt; letter-spacing: 1px; }
  .kr-xxl { font-size: 19pt; margin: 2mm 0; }
  .kr-lg { font-size: 13pt; }
  .kr-row { display: flex; justify-content: space-between; font-size: 10pt; margin: 1mm 0; }
  .kr-divider { border-top: 1px dashed #000; margin: 2mm 0; }
  .kr-divider-thin { border-top: 1px dashed #000; margin: 1.5mm 0; }
  .kr-item { font-size: 11pt; margin-bottom: 1mm; }
  .kr-mods { padding-left: 3mm; font-size: 9.5pt; }
  .kr-callout {
    display: inline-block; font-weight: 700; border: 1px solid #000;
    padding: 0.5mm 1.5mm; margin-top: 1mm; font-size: 10pt; text-transform: uppercase;
  }
  .kr-note { border: 1.5px solid #000; padding: 1.5mm; margin: 2mm 0; font-size: 10.5pt; }
  .kr-block { font-size: 10pt; margin: 1mm 0; }
</style>
</head>
<body>
  <div class="kr-center kr-bold kr-xl">BURGER TIMES</div>
  <div class="kr-divider"></div>
  <div class="kr-center kr-bold kr-xxl">COMMANDE #${esc(order.order_number)}</div>
  <div class="kr-center kr-bold">${esc(fulfillmentLabel)}</div>
  <div class="kr-row"><span>${esc(date)}</span><span>${esc(time)}</span></div>
  <div class="kr-divider"></div>
  ${itemsHtml}
  ${
    cleanNote
      ? `<div class="kr-note"><div class="kr-bold">NOTE CLIENT :</div><div class="kr-bold">${esc(
          cleanNote.toUpperCase()
        )}</div></div>`
      : ""
  }
  <div class="kr-divider"></div>
  <div class="kr-row kr-bold kr-lg"><span>TOTAL :</span><span>${(order.total || 0)
    .toFixed(2)
    .replace(".", ",")} EUR</span></div>
  <div class="kr-divider"></div>
  ${fulfillmentBlock}
  <div class="kr-block">Paiement : ${esc(PAYMENT_LABEL[order.payment_method] || order.payment_method)}</div>
</body>
</html>`;
}

let activeIframe = null;

/**
 * Prints an order's 80mm kitchen ticket via a hidden, fully isolated
 * <iframe> — the iframe gets its OWN document with its OWN inline <style>,
 * so it can never inherit this app's dark theme, grain overlay, or any
 * ancestor CSS/layout. This is the ONLY printing mechanism (no backend
 * bridge): on the Android/SUNMI tablet, the OS-level ESC/POS print service
 * (already paired over Bluetooth) handles the job once the employee taps
 * print in the native dialog that `iframe.contentWindow.print()` opens.
 *
 * `onDone` is a best-effort callback (fires on the iframe's `afterprint`,
 * or after a generous fallback timeout on browsers that never fire it) —
 * purely for the "Imprimé" telemetry badge, never gates order status.
 */
export function printKitchenReceipt(order, onDone) {
  if (!order) return;
  if (activeIframe) {
    activeIframe.remove();
    activeIframe = null;
  }

  const iframe = document.createElement("iframe");
  iframe.style.position = "fixed";
  iframe.style.right = "0";
  iframe.style.bottom = "0";
  iframe.style.width = "0";
  iframe.style.height = "0";
  iframe.style.border = "0";
  iframe.setAttribute("aria-hidden", "true");
  document.body.appendChild(iframe);
  activeIframe = iframe;

  let done = false;
  let fallbackTimer = null;
  const cleanup = () => {
    if (done) return;
    done = true;
    if (fallbackTimer) clearTimeout(fallbackTimer);
    if (iframe.parentNode) iframe.parentNode.removeChild(iframe);
    if (activeIframe === iframe) activeIframe = null;
    onDone?.();
  };

  iframe.onload = () => {
    const win = iframe.contentWindow;
    try {
      win.addEventListener("afterprint", cleanup);
    } catch {
      // Some Android WebViews don't support afterprint on the iframe window.
    }
    win.focus();
    win.print();
    // Fallback cleanup for browsers that never fire `afterprint` — long
    // enough to not yank the iframe while the native print dialog is open.
    fallbackTimer = setTimeout(cleanup, 30000);
  };

  const doc = iframe.contentDocument || iframe.contentWindow.document;
  doc.open();
  doc.write(buildReceiptHtml(order));
  doc.close();
}
