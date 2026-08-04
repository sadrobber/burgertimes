import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

const STORAGE_KEY = "bt_cart_v1";
const CartContext = createContext(null);

function loadCart() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch (e) {
    return [];
  }
}

function persist(items) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  } catch (e) {
    /* ignore */
  }
}

function genLineId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function CartProvider({ children }) {
  const [items, setItems] = useState(() => loadCart());

  useEffect(() => {
    persist(items);
  }, [items]);

  const addPlainItem = useCallback((line) => {
    setItems((prev) => {
      // merge by (item_id, formula, selected_format, selected_variant)
      const key = (l) =>
        `${l.item_id}|${l.formula}|${l.selected_format || ""}|${l.selected_variant || ""}`;
      const idx = prev.findIndex((l) => !l.is_burger && key(l) === key(line));
      if (idx >= 0) {
        const next = [...prev];
        next[idx] = { ...next[idx], quantity: next[idx].quantity + (line.quantity || 1) };
        return next;
      }
      return [...prev, { ...line, line_id: genLineId() }];
    });
  }, []);

  const addBurgerItem = useCallback((line) => {
    setItems((prev) => [...prev, { ...line, line_id: genLineId() }]);
  }, []);

  const removeLine = useCallback((line_id) => {
    setItems((prev) => prev.filter((l) => l.line_id !== line_id));
  }, []);

  const updateQuantity = useCallback((line_id, quantity) => {
    setItems((prev) =>
      prev
        .map((l) => (l.line_id === line_id ? { ...l, quantity: Math.max(1, quantity) } : l))
        .filter((l) => l.quantity > 0)
    );
  }, []);

  const clear = useCallback(() => setItems([]), []);

  const totalItems = useMemo(
    () => items.reduce((sum, l) => sum + (l.quantity || 0), 0),
    [items]
  );

  const totalPrice = useMemo(
    () => items.reduce((sum, l) => sum + (l.unit_price || 0) * (l.quantity || 0), 0),
    [items]
  );

  const value = {
    items,
    addPlainItem,
    addBurgerItem,
    removeLine,
    updateQuantity,
    clear,
    totalItems,
    totalPrice,
  };
  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export const useCart = () => useContext(CartContext);
