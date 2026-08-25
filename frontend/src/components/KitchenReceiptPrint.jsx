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
 * Builds the INNER markup of the 80mm ticket (no <html>/<head> wrapper —
 * this gets injected directly into the live page, see printKitchenReceipt
 * below). Styling comes from the always-on (non-`@media print`) rules
 * scoped under `#kitchen-print-standalone` in index.css.
 */
function buildReceiptInnerHtml(order) {
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

  return `
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
    <div class="kr-block">Paiement : ${esc(PAYMENT_LABEL[order.payment_method] || order.payment_method)}</div>`;
}

let activeContainer = null;

function teardown(onDone) {
  document.documentElement.classList.remove("kt-printing");
  if (activeContainer && activeContainer.parentNode) {
    activeContainer.parentNode.removeChild(activeContainer);
  }
  activeContainer = null;
  onDone?.();
}

/**
 * Prints an order's 80mm kitchen ticket.
 *
 * Some Android tablet browsers (confirmed on the real SUNMI device) do NOT
 * isolate an <iframe>'s content when printing and simply rasterize whatever
 * is currently visible on the page — so relying on `@media print` CSS or a
 * hidden iframe is unsafe. Instead, this literally swaps what is on screen:
 * it appends a receipt container as the last child of <body> and toggles a
 * plain (non-media-scoped) `kt-printing` class on <html> that hides the
 * React root (#root) and the dark-theme grain overlay via ordinary CSS
 * rules (see index.css) — so the receipt is the ONLY thing visible/on the
 * page when `window.print()` fires, regardless of whether the browser
 * honours print-specific stylesheets at all. Everything is restored right
 * after (on `afterprint`, or a generous fallback timeout).
 *
 * No backend bridge: the OS-level ESC/POS print service (paired over
 * Bluetooth to the SUNMI printer) picks up the job from the native print
 * dialog `window.print()` opens.
 *
 * `onDone` is best-effort telemetry only (drives the "Imprimé" badge),
 * never gates order status.
 */
export function printKitchenReceipt(order, onDone) {
  if (!order) return;
  teardown(); // defensively clear any stuck previous run

  const container = document.createElement("div");
  container.id = "kitchen-print-standalone";
  container.innerHTML = buildReceiptInnerHtml(order);
  document.body.appendChild(container);
  activeContainer = container;
  document.documentElement.classList.add("kt-printing");

  let done = false;
  const cleanup = () => {
    if (done) return;
    done = true;
    window.removeEventListener("afterprint", cleanup);
    teardown(onDone);
  };
  window.addEventListener("afterprint", cleanup);

  // Give the browser two frames to actually paint the swapped DOM before
  // triggering print — some Android WebViews rasterize immediately and
  // would otherwise still catch the dashboard mid-transition.
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      window.print();
      setTimeout(cleanup, 30000);
    });
  });
}
