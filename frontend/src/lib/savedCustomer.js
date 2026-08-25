// "Remember me" for checkout — no accounts, no backend, just the browser.
// localStorage holds the long-lived saved profile (survives forever until
// the customer's browser data is cleared). sessionStorage is a short-lived
// bridge that carries the just-submitted form over from Checkout -> the
// order-success page, which is where we actually ask "save this for next
// time?" (so the question doesn't block the order itself).
const SAVED_KEY = "bt_saved_customer";
const PENDING_KEY = "bt_pending_save_prompt";

export function getSavedCustomer() {
  try {
    const raw = localStorage.getItem(SAVED_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function saveCustomer(profile) {
  try {
    localStorage.setItem(SAVED_KEY, JSON.stringify(profile));
  } catch {
    // Storage disabled/full — silently skip, it's a convenience feature only.
  }
}

export function setPendingSavePrompt(profile) {
  try {
    sessionStorage.setItem(PENDING_KEY, JSON.stringify(profile));
  } catch {
    // ignore
  }
}

export function popPendingSavePrompt() {
  try {
    const raw = sessionStorage.getItem(PENDING_KEY);
    sessionStorage.removeItem(PENDING_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
