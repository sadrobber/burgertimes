import React from "react";
import { Navigate, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  ClipboardList,
  UtensilsCrossed,
  Tags,
  Beef,
  Droplet,
  Star,
  Settings as SettingsIcon,
  LogOut,
  Home as HomeIcon,
  Truck,
  Ticket,
  TabletSmartphone,
  MonitorSmartphone,
} from "lucide-react";
import { useAdminAuth } from "@/context/AdminAuthContext.jsx";

const links = [
  { to: "/admin", end: true, label: "Dashboard", icon: LayoutDashboard, id: "dashboard", manager: true },
  { to: "/admin/orders", label: "Commandes", icon: ClipboardList, id: "orders" },
  { to: "/admin/stats/delivery", label: "Livraisons", icon: Truck, id: "delivery-stats" },
  { to: "/admin/menu", label: "Menu", icon: UtensilsCrossed, id: "menu", manager: true },
  { to: "/admin/categories", label: "Catégories", icon: Tags, id: "categories" },
  { to: "/admin/burger", label: "Burger Builder", icon: Beef, id: "burger" },
  { to: "/admin/sauces", label: "Sauces", icon: Droplet, id: "sauces" },
  { to: "/admin/coupons", label: "Codes promo", icon: Ticket, id: "coupons" },
  { to: "/admin/tablet-staff", label: "Tablette", icon: TabletSmartphone, id: "tablet-staff" },
  { to: "/admin/tablet-orders", label: "Ventes tablette", icon: MonitorSmartphone, id: "tablet-orders", manager: true },
  { to: "/admin/reviews", label: "Avis", icon: Star, id: "reviews" },
  { to: "/admin/settings", label: "Réglages", icon: SettingsIcon, id: "settings" },
];

export default function AdminLayout() {
  const { email, role, logout } = useAdminAuth();
  const nav = useNavigate();
  const { pathname } = useLocation();
  // A manager only gets the pages marked `manager`; links appear once the
  // role is known, and any other admin page sends them back to the dashboard.
  const visible = role === "manager" ? links.filter((l) => l.manager) : role ? links : [];
  const onAllowedPage = visible.some((l) => pathname.replace(/\/$/, "") === l.to);

  const doLogout = () => {
    logout();
    nav("/admin/login", { replace: true });
  };

  if (role === "manager" && !onAllowedPage) return <Navigate to="/admin" replace />;

  return (
    <div className="min-h-screen bg-[#0A0A0A] text-[#F5F1E8] flex">
      <aside className="w-64 shrink-0 bg-[#141414] border-r-2 border-[#262626] hidden md:flex flex-col">
        <div className="px-6 py-6 border-b-2 border-[#262626]">
          <div className="font-display text-2xl uppercase leading-none">
            <span className="text-[#F5F1E8]">Burger</span>
            <span className="text-[#EF2B2D]">Times</span>
          </div>
          <div className="text-xs text-[#A1A1A1] font-accent uppercase tracking-widest mt-1">
            Back office
          </div>
        </div>
        <nav className="flex-1 py-4">
          {visible.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.end}
              data-testid={`admin-nav-${l.id}`}
              className={({ isActive }) =>
                `flex items-center gap-3 px-6 py-3 font-accent uppercase tracking-widest text-sm transition-colors ${
                  isActive
                    ? "bg-[#EF2B2D] text-[#F5F1E8]"
                    : "text-[#B3B3B3] hover:text-[#F5F1E8] hover:bg-[#0A0A0A]"
                }`
              }
            >
              <l.icon className="w-4 h-4" />
              {l.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t-2 border-[#262626] p-4 space-y-2">
          <NavLink to="/" data-testid="admin-view-site" className="bt-btn-ghost w-full text-sm px-2">
            <HomeIcon className="w-4 h-4" /> Voir le site
          </NavLink>
          <button
            onClick={doLogout}
            data-testid="admin-logout"
            className="bt-btn-ghost w-full text-sm px-2 text-[#EF2B2D]"
          >
            <LogOut className="w-4 h-4" /> Déconnexion
          </button>
          <div className="text-xs text-[#666] truncate">{email}</div>
        </div>
      </aside>

      {/* Mobile top bar */}
      <div className="md:hidden fixed top-0 inset-x-0 z-30 bg-[#141414] border-b-2 border-[#262626] px-4 py-3 flex items-center justify-between">
        <div className="font-display text-xl uppercase">Admin</div>
        <button onClick={doLogout} className="bt-btn-ghost text-xs px-2" data-testid="admin-logout-mobile">
          <LogOut className="w-4 h-4" /> Sortir
        </button>
      </div>

      <main className="flex-1 min-w-0 md:ml-0 pt-16 md:pt-0">
        <div className="md:hidden border-b-2 border-[#262626] bg-[#141414]">
          <div className="grid grid-cols-[repeat(3,minmax(0,1fr))] gap-1 px-2 py-2">
            {visible.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                end={l.end}
                data-testid={`admin-nav-mobile-${l.id}`}
                className={({ isActive }) =>
                  `flex min-w-0 overflow-hidden items-center justify-center gap-1 px-2 py-2 text-center text-[10px] font-accent uppercase leading-tight tracking-widest ${
                    isActive ? "border-[#EF2B2D] text-[#EF2B2D]" : "border-[#262626] text-[#B3B3B3]"
                  }`
                }
              >
                <l.icon className="w-3.5 h-3.5" /> {l.label}
              </NavLink>
            ))}
          </div>
        </div>
        <div className="p-4 md:p-8 max-w-7xl">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
