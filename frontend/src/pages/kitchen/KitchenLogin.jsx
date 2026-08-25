import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useKitchenAuth } from "@/context/KitchenAuthContext.jsx";
import { fmtError } from "@/lib/api";

export default function KitchenLogin() {
  const { login, status } = useKitchenAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  React.useEffect(() => {
    if (status === "authenticated") nav("/kitchen", { replace: true });
  }, [status, nav]);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await login(email.trim().toLowerCase(), password);
      nav("/kitchen", { replace: true });
    } catch (err) {
      toast.error(fmtError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0A0A0A] text-[#F5F1E8] flex items-center justify-center px-4">
      <form onSubmit={submit} className="bt-card p-8 w-full max-w-md" data-testid="kitchen-login-form">
        <div className="font-marker text-[#EF2B2D] text-lg -rotate-1">Tablette cuisine</div>
        <h1 className="font-display text-4xl uppercase mt-1 leading-none">Burger Times</h1>
        <p className="text-base text-[#A1A1A1] mt-2">
          Connecte la tablette pour recevoir les commandes en temps réel.
        </p>

        <div className="mt-6 space-y-4">
          <label className="block">
            <div className="bt-label text-base">Email</div>
            <input
              type="email"
              autoComplete="email"
              className="bt-input text-lg py-4"
              data-testid="kitchen-email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </label>
          <label className="block">
            <div className="bt-label text-base">Mot de passe</div>
            <input
              type="password"
              autoComplete="current-password"
              className="bt-input text-lg py-4"
              data-testid="kitchen-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
        </div>
        <button
          type="submit"
          disabled={loading}
          data-testid="kitchen-login-submit"
          className="bt-btn-primary w-full mt-6 py-4 text-lg disabled:opacity-40"
        >
          {loading ? "..." : "Se connecter"}
        </button>
      </form>
    </div>
  );
}
