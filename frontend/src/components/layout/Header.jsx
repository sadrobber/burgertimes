import React from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { ShoppingBag, Menu as MenuIcon, X, Globe } from "lucide-react";
import { useI18n } from "@/context/I18nContext.jsx";
import { useCart } from "@/context/CartContext.jsx";
import StatusBanner from "@/components/StatusBanner.jsx";

export default function Header() {
  const { t, lang, setLang } = useI18n();
  const { totalItems } = useCart();
  const [open, setOpen] = React.useState(false);
  const location = useLocation();

  React.useEffect(() => {
    setOpen(false);
  }, [location.pathname]);

  const navLink = (to, key, testId) => (
    <NavLink
      to={to}
      data-testid={testId}
      className={({ isActive }) =>
        `font-accent uppercase tracking-widest text-lg transition-colors ${
          isActive ? "text-[#EF2B2D]" : "text-[#F5F1E8] hover:text-[#EF2B2D]"
        }`
      }
    >
      {t(key)}
    </NavLink>
  );

  return (
    <header className="sticky top-0 z-40 bg-[#0A0A0A]/95 backdrop-blur-sm border-b-2 border-[#262626]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="h-16 md:h-20 flex items-center justify-between gap-4">
          <Link to="/" data-testid="logo-link" className="flex items-center gap-3">
            <span className="font-display text-2xl md:text-3xl uppercase leading-none">
              <span className="text-[#F5F1E8]">Burger</span>
              <span className="text-[#EF2B2D]">Times</span>
            </span>
            <span className="hidden sm:inline-block h-4 w-px bg-[#262626]" />
            <StatusBanner variant="pill" />
          </Link>

          <nav className="hidden md:flex items-center gap-8">
            {navLink("/", "nav.home", "nav-home")}
            {navLink("/menu", "nav.menu", "nav-menu")}
            {navLink("/cart", "nav.cart", "nav-cart")}
          </nav>

          <div className="flex items-center gap-3">
            <button
              data-testid="lang-toggle"
              onClick={() => setLang(lang === "fr" ? "en" : "fr")}
              className="hidden sm:inline-flex items-center gap-1 px-3 py-2 border-2 border-[#262626] hover:border-[#EF2B2D] font-accent uppercase tracking-widest text-xs"
              aria-label="Toggle language"
            >
              <Globe className="w-4 h-4" />
              {lang.toUpperCase()}
            </button>
            <Link
              to="/cart"
              data-testid="cart-icon-link"
              className="relative inline-flex items-center justify-center w-11 h-11 border-2 border-[#262626] hover:border-[#EF2B2D] transition-colors"
              aria-label="Cart"
            >
              <ShoppingBag className="w-5 h-5" />
              {totalItems > 0 && (
                <span
                  data-testid="cart-badge"
                  className="absolute -top-2 -right-2 bg-[#EF2B2D] text-[#F5F1E8] text-xs font-bold w-5 h-5 flex items-center justify-center"
                >
                  {totalItems}
                </span>
              )}
            </Link>
            <button
              data-testid="mobile-menu-toggle"
              onClick={() => setOpen((v) => !v)}
              className="md:hidden inline-flex items-center justify-center w-11 h-11 border-2 border-[#262626]"
              aria-label="Menu"
            >
              {open ? <X className="w-5 h-5" /> : <MenuIcon className="w-5 h-5" />}
            </button>
          </div>
        </div>
      </div>
      {open && (
        <div className="md:hidden border-t-2 border-[#262626] bg-[#0A0A0A]">
          <div className="px-4 py-4 flex flex-col gap-4">
            {navLink("/", "nav.home", "nav-home-mobile")}
            {navLink("/menu", "nav.menu", "nav-menu-mobile")}
            {navLink("/cart", "nav.cart", "nav-cart-mobile")}
            <button
              data-testid="lang-toggle-mobile"
              onClick={() => setLang(lang === "fr" ? "en" : "fr")}
              className="inline-flex items-center gap-2 px-3 py-2 border-2 border-[#262626] font-accent uppercase tracking-widest text-xs w-fit"
            >
              <Globe className="w-4 h-4" />
              {lang.toUpperCase()}
            </button>
          </div>
        </div>
      )}
    </header>
  );
}
