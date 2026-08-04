import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { adminClient, clearAdminToken, getAdminToken, setAdminToken } from "@/lib/api";

const AdminAuthContext = createContext(null);

export function AdminAuthProvider({ children }) {
  const [status, setStatus] = useState(getAdminToken() ? "authenticated" : "guest");
  const [email, setEmail] = useState(null);

  useEffect(() => {
    if (status !== "authenticated") return;
    let cancelled = false;
    adminClient
      .get("/admin/me")
      .then((r) => {
        if (!cancelled) setEmail(r.data.email);
      })
      .catch(() => {
        if (!cancelled) {
          clearAdminToken();
          setStatus("guest");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [status]);

  const login = useCallback(async (emailIn, password) => {
    const { data } = await adminClient.post("/admin/login", {
      email: emailIn,
      password,
    });
    setAdminToken(data.token);
    setEmail(data.admin.email);
    setStatus("authenticated");
    return data;
  }, []);

  const logout = useCallback(() => {
    clearAdminToken();
    setEmail(null);
    setStatus("guest");
  }, []);

  return (
    <AdminAuthContext.Provider value={{ status, email, login, logout }}>
      {children}
    </AdminAuthContext.Provider>
  );
}

export const useAdminAuth = () => useContext(AdminAuthContext);
