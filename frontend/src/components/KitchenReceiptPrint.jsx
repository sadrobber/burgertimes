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

/**
 * Styles for the dedicated print document. Deliberately self-contained and
 * inline: the print tab must not depend on the app CSS bundle loading, and
 * must not inherit the dashboard dark theme.
 */
const RECEIPT_CSS = `
  @page { size: 80mm auto; margin: 2mm; }
  * { box-sizing: border-box; }
  html, body {
    margin: 0; padding: 0;
    background: #fff; color: #000;
    -webkit-print-color-adjust: exact; print-color-adjust: exact;
  }
  body {
    width: 76mm; margin: 0 auto; padding: 2mm 0;
    font-family: "Courier New", Courier, monospace;
    font-size: 11pt; line-height: 1.25;
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
`;

function buildStandaloneDoc(order) {
  return `<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ticket ${esc(order.order_number)}</title>
<style>${RECEIPT_CSS}</style></head>
<body>${buildReceiptInnerHtml(order)}</body></html>`;
}

/** Reused handle to the ticket tab, so repeated prints do not pile up tabs. */
let ticketTab = null;

/**
 * Opens (or reuses) the ticket tab. MUST be called synchronously from the
 * click handler - Android Chrome blocks window.open() once the call stack has
 * gone through an await. Returns null when the browser blocked it, in which
 * case the caller falls back to the in-page path.
 */
export function openTicketTab() {
  try {
    if (ticketTab && !ticketTab.closed) return ticketTab;
  } catch {
    ticketTab = null;
  }
  let w = null;
  try {
    w = window.open("", "burgertimes_ticket");
  } catch {
    w = null;
  }
  if (w) {
    try {
      w.document.open();
      w.document.write(
        '<!doctype html><meta charset="utf-8"><title>Ticket</title>' +
          '<body style="margin:0;padding:16px;font-family:sans-serif;background:#fff;color:#000">' +
          "Preparation du ticket..."
      );
      w.document.close();
    } catch {
      /* about:blank not writable yet - printInTicketTab retries */
    }
  }
  ticketTab = w;
  return w;
}

function printInTicketTab(w, order, onDone) {
  try {
    w.document.open();
    w.document.write(buildStandaloneDoc(order));
    w.document.close();
  } catch {
    return printInPageFallback(order, onDone);
  }

  // Chrome ignores `@page { size: 80mm auto }` and silently falls back to the
  // default paper (Letter/A4) - verified. An explicit height IS honoured, so
  // measure the rendered ticket and pin the page to exactly that, which keeps
  // a receipt of any length on a single continuous 80mm page.
  const applyExactPageHeight = () => {
    try {
      const d = w.document;
      const px = Math.ceil(d.body.getBoundingClientRect().height);
      const mm = Math.max(40, Math.ceil((px / 96) * 25.4) + 8); // +8mm feed tail
      const st = d.createElement("style");
      st.textContent = "@page { size: 80mm " + mm + "mm; margin: 2mm; }";
      d.head.appendChild(st);
    } catch {
      /* fall back to the stylesheet default */
    }
  };

  const fire = () => {
    applyExactPageHeight();
    try {
      w.focus();
      w.print();
    } catch {
      /* the operator can still print the open tab manually */
    }
    onDone?.();
  };

  // document.write()+close() leaves the document already parsed; two frames is
  // enough for layout. We never close or mutate this tab afterwards: on
  // Android the rasterisation happens AFTER print() returns, and this tab
  // holds nothing but the receipt, so whenever the print service reads it the
  // output is correct.
  try {
    w.requestAnimationFrame(() => w.requestAnimationFrame(fire));
  } catch {
    setTimeout(fire, 80);
  }
  return true;
}

let activeContainer = null;

function teardown() {
  document.documentElement.classList.remove("kt-printing");
  if (activeContainer && activeContainer.parentNode) {
    activeContainer.parentNode.removeChild(activeContainer);
  }
  activeContainer = null;
}

/**
 * Swaps the page for the receipt, prints it, and LEAVES IT SWAPPED until the
 * operator taps the screen.
 *
 * That is the whole fix on this path. The previous implementation restored the
 * dashboard on `afterprint` (or a 30s timer). On desktop that is safe, because
 * window.print() blocks until the preview is dismissed - which is why printing
 * from the PC always worked. On Android it is not: window.print() hands off to
 * the system print service and returns immediately, `afterprint` fires on
 * hand-off, and the page is only rasterised later, after the operator picks a
 * printer. Restoring on hand-off meant the print service read the restored
 * dashboard - which is exactly the reported "it prints the whole page with the
 * buttons", and the blank ticket when it read the intermediate teardown state.
 */
function printInPageFallback(order, onDone) {
  teardown();

  const container = document.createElement("div");
  container.id = "kitchen-print-standalone";
  container.innerHTML = buildReceiptInnerHtml(order);
  document.body.appendChild(container);
  activeContainer = container;
  document.documentElement.classList.add("kt-printing");

  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      try {
        window.print();
      } catch {
        /* ignore */
      }
      onDone?.();

      const restore = () => {
        document.removeEventListener("pointerdown", restore, true);
        clearTimeout(safety);
        teardown();
      };
      // 5 minute backstop so the dashboard can never stay stuck.
      const safety = setTimeout(restore, 300000);
      // Delay arming so the originating click cannot restore it immediately.
      setTimeout(() => document.addEventListener("pointerdown", restore, true), 1500);
    });
  });
  return true;
}

/**
 * Prints an order 80mm kitchen ticket.
 *
 * `tab` is the window returned by openTicketTab(), which the caller must have
 * opened synchronously inside the click handler. Omit it for flows that call
 * this directly from a click (e.g. Reimprimer).
 *
 * `onDone` is best-effort telemetry only (drives the "Imprime" badge) and
 * never gates order status.
 */
export function printKitchenReceipt(order, onDone, tab) {
  if (!order) return false;

  let w = tab;
  try {
    if (!w || w.closed) w = openTicketTab();
  } catch {
    w = null;
  }

  if (w) return printInTicketTab(w, order, onDone);
  return printInPageFallback(order, onDone);
}

/** Closes the ticket tab, e.g. when an accept turned out to be a no-op. */
export function closeTicketTab(tab) {
  const w = tab || ticketTab;
  try {
    if (w && !w.closed) w.close();
  } catch {
    /* ignore */
  }
  if (w === ticketTab) ticketTab = null;
}
