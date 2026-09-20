import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { clearTabletToken, getTabletToken, setTabletToken, tabletClient } from "@/lib/api";

const TabletAuthContext = createContext(null);

export function TabletAuthProvider({ children }) {
  const [status, setStatus] = useState(getTabletToken() ? "authenticated" : "guest");
  const [email, setEmail] = useState(null);

  useEffect(() => {
    if (status !== "authenticated") return undefined;
    let cancelled = false;
    tabletClient
      .get("/tablet/me")
      .then((response) => !cancelled && setEmail(response.data.email))
      .catch(() => {
        if (!cancelled) {
          clearTabletToken();
          setStatus("guest");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [status]);

  const login = useCallback(async (emailIn, password) => {
    const { data } = await tabletClient.post("/tablet/login", { email: emailIn, password });
    setTabletToken(data.token);
    setEmail(data.user.email);
    setStatus("authenticated");
    return data;
  }, []);

  const logout = useCallback(() => {
    clearTabletToken();
    setEmail(null);
    setStatus("guest");
  }, []);

  return (
    <TabletAuthContext.Provider value={{ status, email, login, logout }}>
      {children}
    </TabletAuthContext.Provider>
  );
}

export const useTabletAuth = () => useContext(TabletAuthContext);