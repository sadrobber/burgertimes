import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { adminClient, fmtError } from "@/lib/api";
import { Check, Star, Trash2, X } from "lucide-react";

export default function ReviewsAdmin() {
  const [items, setItems] = useState([]);
  const load = () => adminClient.get("/admin/reviews").then((r) => setItems(r.data || []));
  useEffect(() => { load(); }, []);

  const approve = async (r, approved) => {
    try {
      await adminClient.put(`/admin/reviews/${r.id}`, { approved });
      load();
    } catch (e) {
      toast.error(fmtError(e));
    }
  };
  const del = async (id) => {
    if (!window.confirm("Supprimer ?")) return;
    await adminClient.delete(`/admin/reviews/${id}`);
    load();
  };

  return (
    <div className="space-y-6">
      <div>
        <div className="font-marker text-[#EF2B2D] -rotate-1">Public</div>
        <h1 className="font-display text-5xl uppercase leading-none">Avis</h1>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {items.map((r) => (
          <div key={r.id} className="bt-card p-5" data-testid={`admin-review-${r.id}`}>
            <div className="flex items-center gap-1 text-[#EF2B2D]">
              {[1, 2, 3, 4, 5].map((n) => (
                <Star key={n} className={`w-4 h-4 ${n <= r.rating ? "fill-current" : "opacity-30"}`} />
              ))}
            </div>
            <p className="mt-2 text-[#D1D1D1]">&laquo; {r.comment} &raquo;</p>
            <div className="mt-2 text-xs uppercase tracking-widest text-[#A1A1A1]">— {r.author_name}</div>
            <div className="mt-3 flex gap-2">
              {r.approved ? (
                <button onClick={() => approve(r, false)} className="bt-btn-ghost text-xs px-2" data-testid={`review-unapprove-${r.id}`}>
                  <X className="w-3 h-3" /> Retirer
                </button>
              ) : (
                <button onClick={() => approve(r, true)} className="bt-btn-ghost text-xs px-2 text-[#00FF66]" data-testid={`review-approve-${r.id}`}>
                  <Check className="w-3 h-3" /> Publier
                </button>
              )}
              <button onClick={() => del(r.id)} className="bt-btn-ghost text-xs px-2 text-[#EF2B2D]">
                <Trash2 className="w-3 h-3" /> Suppr
              </button>
            </div>
          </div>
        ))}
        {items.length === 0 && (
          <div className="col-span-full text-sm text-[#A1A1A1] bt-card p-8 text-center">Aucun avis reçu.</div>
        )}
      </div>
    </div>
  );
}
