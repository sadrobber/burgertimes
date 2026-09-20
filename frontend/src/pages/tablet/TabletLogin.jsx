import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useTabletAuth } from "@/context/TabletAuthContext.jsx";
import { fmtError } from "@/lib/api";

export default function TabletLogin() {
  const { login, status } = useTabletAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (status === "authenticated") nav("/tablet", { replace: true });
  }, [nav, status]);

  const submit = async (event) => {
    event.preventDefault();
    setLoading(true);
    try {
      await login(email.trim().toLowerCase(), password);
      nav("/tablet", { replace: true });
    } catch (error) {
      toast.error(fmtError(error));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0A0A0A] text-[#F5F1E8] flex items-center justify-center px-4">
      <form className="bt-card p-8 w-full max-w-md" data-testid="tablet-login-form" onSubmit={submit}>
        <div className="font-marker text-[#EF2B2D] text-lg -rotate-1">Prise de commande</div>
        <h1 className="font-display text-4xl uppercase mt-1 leading-none">Burger Times</h1>
        <p className="text-base text-[#A1A1A1] mt-2">Connexion réservée à la tablette du restaurant.</p>
        <label className="block mt-6">
          <div className="bt-label text-base">Email</div>
          <input
            autoComplete="email"
            className="bt-input text-lg py-4"
            data-testid="tablet-login-email"
            onChange={(event) => setEmail(event.target.value)}
            required
            type="email"
            value={email}
          />
        </label>
        <label className="block mt-4">
          <div className="bt-label text-base">Mot de passe</div>
          <input
            autoComplete="current-password"
            className="bt-input text-lg py-4"
            data-testid="tablet-login-password"
            onChange={(event) => setPassword(event.target.value)}
            required
            type="password"
            value={password}
          />
        </label>
        <button
          className="bt-btn-primary w-full mt-6 py-4 text-lg disabled:opacity-40"
          data-testid="tablet-login-submit"
          disabled={loading}
          type="submit"
        >
          {loading ? "..." : "Se connecter"}
        </button>
      </form>
    </div>
  );
}