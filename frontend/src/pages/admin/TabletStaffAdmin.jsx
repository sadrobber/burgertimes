import React, { useEffect, useState } from "react";
import { EyeOff, KeyRound, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { adminClient, fmtError } from "@/lib/api";

export default function TabletStaffAdmin() {
  const [staff, setStaff] = useState([]);
  const [form, setForm] = useState({ email: "", password: "" });
  const [saving, setSaving] = useState(false);

  const load = () => {
    adminClient
      .get("/admin/tablet-staff")
      .then((response) => setStaff(response.data || []))
      .catch((error) => toast.error(fmtError(error)));
  };

  useEffect(() => {
    load();
  }, []);

  const create = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      await adminClient.post("/admin/tablet-staff", form);
      toast.success("Compte tablette créé");
      setForm({ email: "", password: "" });
      load();
    } catch (error) {
      toast.error(fmtError(error));
    } finally {
      setSaving(false);
    }
  };

  const update = async (member, patch) => {
    try {
      await adminClient.put(`/admin/tablet-staff/${member.id}`, patch);
      toast.success("Compte mis à jour");
      load();
    } catch (error) {
      toast.error(fmtError(error));
    }
  };

  const remove = async (member) => {
    if (!window.confirm(`Supprimer le compte ${member.email} ?`)) return;
    try {
      await adminClient.delete(`/admin/tablet-staff/${member.id}`);
      toast.success("Compte supprimé");
      load();
    } catch (error) {
      toast.error(fmtError(error));
    }
  };

  return (
    <div className="max-w-3xl space-y-7">
      <div>
        <div className="font-marker text-[#EF2B2D] -rotate-1">Accès séparé</div>
        <h1 className="font-display text-5xl uppercase leading-none">Tablette</h1>
        <p className="mt-3 text-sm text-[#A1A1A1]">
          Ces comptes peuvent prendre une commande sur <strong>/tablet</strong> sans ouvrir l&apos;admin.
        </p>
      </div>

      <form className="bt-card space-y-4 p-5" data-testid="tablet-staff-create-form" onSubmit={create}>
        <div className="font-display text-2xl uppercase">Nouveau compte</div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="bt-label">Email</span>
            <input
              className="bt-input"
              data-testid="tablet-staff-email"
              onChange={(event) => setForm({ ...form, email: event.target.value })}
              required
              type="email"
              value={form.email}
            />
          </label>
          <label className="block">
            <span className="bt-label">Mot de passe</span>
            <input
              className="bt-input"
              data-testid="tablet-staff-password"
              minLength="8"
              onChange={(event) => setForm({ ...form, password: event.target.value })}
              required
              type="password"
              value={form.password}
            />
          </label>
        </div>
        <button className="bt-btn-primary" data-testid="tablet-staff-create" disabled={saving} type="submit">
          <Plus className="h-4 w-4" /> {saving ? "Création…" : "Créer le compte"}
        </button>
      </form>

      <div className="space-y-3" data-testid="tablet-staff-list">
        {staff.length === 0 ? (
          <div className="bt-card p-5 text-sm text-[#A1A1A1]">Aucun compte tablette créé.</div>
        ) : (
          staff.map((member) => (
            <StaffRow key={member.id} member={member} onRemove={remove} onUpdate={update} />
          ))
        )}
      </div>
    </div>
  );
}

function StaffRow({ member, onRemove, onUpdate }) {
  const [password, setPassword] = useState("");

  const resetPassword = () => {
    if (password.length < 8) {
      toast.error("Le mot de passe doit faire au moins 8 caractères");
      return;
    }
    onUpdate(member, { password });
    setPassword("");
  };

  return (
    <div className="bt-card flex flex-wrap items-center justify-between gap-4 p-4" data-testid={`tablet-staff-${member.id}`}>
      <div>
        <div className="font-bold">{member.email}</div>
        <div className={`mt-1 text-xs font-accent uppercase tracking-widest ${member.active === false ? "text-[#EF2B2D]" : "text-[#3DDC97]"}`}>
          {member.active === false ? "Désactivé" : "Actif"}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <input
          className="bt-input h-9 w-40 text-sm"
          data-testid={`tablet-staff-password-${member.id}`}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="Nouveau mot de passe"
          type="password"
          value={password}
        />
        <button
          className="bt-btn-ghost h-9 px-2 text-xs"
          data-testid={`tablet-staff-reset-${member.id}`}
          onClick={resetPassword}
          title="Changer le mot de passe"
        >
          <KeyRound className="h-3.5 w-3.5" />
        </button>
        <button
          className="bt-btn-ghost h-9 px-2 text-xs"
          data-testid={`tablet-staff-toggle-${member.id}`}
          onClick={() => onUpdate(member, { active: member.active === false })}
          title={member.active === false ? "Activer" : "Désactiver"}
        >
          <EyeOff className="h-3.5 w-3.5" />
        </button>
        <button
          className="bt-btn-ghost h-9 px-2 text-[#EF2B2D]"
          data-testid={`tablet-staff-delete-${member.id}`}
          onClick={() => onRemove(member)}
          title="Supprimer"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}