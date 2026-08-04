import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useAdminAuth } from "@/context/AdminAuthContext.jsx";
import { fmtError } from "@/lib/api";

export default function AdminLogin() {
  const { login, status } = useAdminAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  React.useEffect(() => {
    if (status === "authenticated") nav("/admin", { replace: true });
  }, [status, nav]);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await login(email.trim().toLowerCase(), password);
      toast.success("Connecté");
      nav("/admin", { replace: true });
    } catch (err) {
      toast.error(fmtError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0A0A0A] text-[#F5F1E8] flex items-center justify-center px-4">
      <form onSubmit={submit} className="bt-card p-8 w-full max-w-sm" data-testid="admin-login-form">
        <div className="font-marker text-[#EF2B2D] text-lg -rotate-1">Back office</div>
        <h1 className="font-display text-4xl uppercase mt-1 leading-none">Burger Times</h1>
        <p className="text-sm text-[#A1A1A1] mt-2">Connecte-toi pour gérer le resto.</p>

        <div className="mt-6 space-y-4">
          <label className="block">
            <div className="bt-label">Email</div>
            <input
              type="email"
              autoComplete="email"
              className="bt-input"
              data-testid="admin-email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </label>
          <label className="block">
            <div className="bt-label">Mot de passe</div>
            <input
              type="password"
              autoComplete="current-password"
              className="bt-input"
              data-testid="admin-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
        </div>
        <button
          type="submit"
          disabled={loading}
          data-testid="admin-login-submit"
          className="bt-btn-primary w-full mt-6 disabled:opacity-40"
        >
          {loading ? "..." : "Se connecter"}
        </button>
      </form>
    </div>
  );
}
