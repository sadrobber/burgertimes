import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { kitchenClient, clearKitchenToken, getKitchenToken, setKitchenToken } from "@/lib/api";

const KitchenAuthContext = createContext(null);

export function KitchenAuthProvider({ children }) {
  const [status, setStatus] = useState(getKitchenToken() ? "authenticated" : "guest");
  const [email, setEmail] = useState(null);

  useEffect(() => {
    if (status !== "authenticated") return;
    let cancelled = false;
    kitchenClient
      .get("/kitchen/me")
      .then((r) => {
        if (!cancelled) setEmail(r.data.email);
      })
      .catch(() => {
        if (!cancelled) {
          clearKitchenToken();
          setStatus("guest");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [status]);

  const login = useCallback(async (emailIn, password) => {
    const { data } = await kitchenClient.post("/kitchen/login", {
      email: emailIn,
      password,
    });
    setKitchenToken(data.token);
    setEmail(data.user.email);
    setStatus("authenticated");
    return data;
  }, []);

  const logout = useCallback(() => {
    clearKitchenToken();
    setEmail(null);
    setStatus("guest");
  }, []);

  return (
    <KitchenAuthContext.Provider value={{ status, email, login, logout }}>
      {children}
    </KitchenAuthContext.Provider>
  );
}

export const useKitchenAuth = () => useContext(KitchenAuthContext);
